"""Self-provisioned embedded PostgreSQL for single-binary installs.

When LOCALDROP_DATABASE_URL is not configured, the launcher downloads the
Zonky embedded-PostgreSQL binaries for this platform into LOCALDROP_DATA_DIR,
initialises a cluster bound to 127.0.0.1, starts it, and points LocalDrop at
it. The cluster lives entirely inside the data dir, so backing up LocalDrop
means backing up one folder.

Production deployments that already run PostgreSQL should set
LOCALDROP_DATABASE_URL — the embedded cluster is then never touched.
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

PG_VERSION = "16.4.0"
_MAVEN = (
    "https://repo1.maven.org/maven2/io/zonky/test/postgres/"
    "embedded-postgres-binaries-{plat}/{v}/embedded-postgres-binaries-{plat}-{v}.jar"
)


def _plat_slug() -> str:
    if sys.platform == "win32":
        return "windows-amd64"
    if sys.platform == "darwin":
        return "osx-arm64" if platform.machine() == "arm64" else "osx-amd64"
    machine = platform.machine().lower()
    return "linux-arm64v8" if machine in ("arm64", "aarch64") else "linux-amd64"


class EmbeddedPostgres:
    """Download-once, run-local PostgreSQL cluster inside a data dir."""

    def __init__(self, root: Path, port: int = 5439) -> None:
        self.root = root
        self.port = port
        self.bin_dir = self.root / "bin"
        self.data_dir = self.root / "data"
        self.log_file = self.root / "pg.log"

    # -- helpers ---------------------------------------------------------

    def _exe(self, name: str) -> Path:
        return self.bin_dir / (name + (".exe" if os.name == "nt" else ""))

    def _run(self, cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
        # pg_ctl start MUST NOT use pipes: postgres inherits them and the
        # pipe never hits EOF, so communicate() blocks forever.
        kwargs = {"capture_output": True, "text": True} if capture else {
            "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
        }
        return subprocess.run([str(c) for c in cmd], **kwargs)

    def _download(self) -> Path:
        plat = _plat_slug()
        jar = self.root / f"embedded-postgres-{plat}-{PG_VERSION}.jar"
        if jar.exists():
            return jar
        url = _MAVEN.format(plat=plat, v=PG_VERSION)
        print(f"  Downloading embedded PostgreSQL {PG_VERSION} ({plat})…")
        part = jar.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {done // (1 << 20)} / {total // (1 << 20)} MB", end="", flush=True)
        print()
        part.replace(jar)
        return jar

    def ensure_binaries(self) -> None:
        if self._exe("pg_ctl").exists():
            return
        self.root.mkdir(parents=True, exist_ok=True)
        jar = self._download()
        with zipfile.ZipFile(jar) as z:
            txz = next(n for n in z.namelist() if n.endswith(".txz"))
            with z.open(txz) as stream, tarfile.open(fileobj=stream, mode="r|xz") as t:
                t.extractall(self.root, filter="tar")
        if not self._exe("pg_ctl").exists():
            raise RuntimeError("embedded PostgreSQL archive did not contain bin/pg_ctl")

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        first_run = not self.data_dir.exists()
        if first_run:
            print("  Initialising embedded database (first run)…")
            r = self._run([
                self._exe("initdb"), "-D", self.data_dir, "-U", "postgres",
                "-A", "trust", "-E", "UTF8", "--no-instructions",
            ])
            if r.returncode != 0:
                detail = (r.stderr or r.stdout or "").strip().splitlines()
                hint = ""
                if "administrator" in (r.stderr or "").lower() or "root" in (r.stderr or "").lower():
                    hint = " (do not run LocalDrop as Administrator/root — run it as a normal user)"
                raise RuntimeError("initdb failed" + hint + ": " + "; ".join(detail[-2:]))
        r = self._run([
            self._exe("pg_ctl"), "-D", self.data_dir,
            "-o", f'-p {self.port} -k "{self.root}"', "-l", self.log_file, "start",
        ], capture=False)
        if r.returncode != 0:
            # uncaptured run gives no output; check readiness instead
            r = subprocess.CompletedProcess(r.args, 1, "", "")
        if r.returncode != 0:
            raise RuntimeError("pg_ctl start failed: " + (r.stderr or r.stdout or "").strip()[-300:])
        for _ in range(60):
            with socket.socket() as sock:
                sock.settimeout(1.0)
                if sock.connect_ex(("127.0.0.1", self.port)) == 0:
                    break
            time.sleep(0.5)
        else:
            raise RuntimeError("embedded PostgreSQL did not become ready; see " + str(self.log_file))
        if first_run:
            import psycopg

            with psycopg.connect(
                f"host=127.0.0.1 port={self.port} user=postgres dbname=postgres",
                connect_timeout=5, autocommit=True,
            ) as c:
                c.execute("CREATE DATABASE localdrop")

    def stop(self) -> None:
        if self.data_dir.exists():
            self._run([self._exe("pg_ctl"), "-D", self.data_dir, "-m", "fast", "stop"])

    def url(self) -> str:
        return f"postgresql+psycopg://postgres@127.0.0.1:{self.port}/localdrop"
