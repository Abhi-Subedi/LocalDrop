"""Per-user service management for the native installs.

LocalDrop is a LAN file server, so on every platform it wants to be running
before anyone thinks to launch it:

* macOS  - a per-user LaunchAgent (this module)
* Linux  - a system systemd unit, installed by install.sh
* Windows - a Start Menu entry, or `install.ps1 -StartServer`

Only macOS is handled here, because it is the only platform where the natural
install path (Homebrew) is strictly per-user and cannot write to /etc or
/Library. A LaunchAgent keeps LocalDrop running across logout and sleep without
asking for root, which is what a Homebrew user expects.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

LAUNCHD_LABEL = "io.github.abhisubedi.localdrop"


def agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def plist_path() -> Path:
    return agents_dir() / f"{LAUNCHD_LABEL}.plist"


def _launchctl(*args: str) -> tuple[int, str, str]:
    if sys.platform != "darwin":
        raise RuntimeError("launchd service management is macOS-only")
    # `args` is built from literals and paths this module generated; there is
    # no shell and no user-controlled argument.
    proc = subprocess.run(  # noqa: S603
        ["/bin/launchctl", *args], capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def build_plist(executable: Path, data_dir: Path, env_file: Path | None) -> bytes:
    """Serialise the LaunchAgent definition."""
    env: dict[str, str] = {
        "LOCALDROP_DATA_DIR": str(data_dir),
    }
    if env_file and env_file.is_file():
        # launchd has no EnvironmentFile, so the values are baked in here.
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key.startswith("LOCALDROP_") and value.strip():
                env[key] = value.strip()
    return plistlib.dumps(
        {
            "Label": LAUNCHD_LABEL,
            "ProgramArguments": [str(executable), "--no-browser"],
            "WorkingDirectory": str(data_dir),
            "EnvironmentVariables": env,
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "ProcessType": "Background",
            "StandardOutPath": str(data_dir / "localdrop.log"),
            "StandardErrorPath": str(data_dir / "localdrop.err.log"),
            "ExitTimeOut": 30,
        },
        sort_keys=True,
    )


def install(executable: Path, data_dir: Path, env_file: Path | None) -> str:
    """Write the LaunchAgent and load it. Returns a human-readable status."""
    if sys.platform != "darwin":
        return "not macOS: nothing to do (use systemd on Linux)"
    data_dir.mkdir(parents=True, exist_ok=True)
    agents_dir().mkdir(parents=True, exist_ok=True)

    path = plist_path()
    path.write_bytes(build_plist(executable, data_dir, env_file))
    # The plist carries LOCALDROP_SECRET_KEY, so it must not be world-readable.
    os.chmod(path, 0o600)

    unload()
    code, _, err = _launchctl("bootstrap", "gui/$(id -u)", str(path))
    if code != 0:
        # Older macOS releases only know `load -w`.
        code, _, err = _launchctl("load", "-w", str(path))
        if code != 0:
            raise RuntimeError(f"launchctl could not load the agent: {err or code}")
    _launchctl("enable", f"gui/{os.getuid()}/{LAUNCHD_LABEL}")
    return f"LaunchAgent installed at {path}; LocalDrop now starts at login"


def uninstall() -> str:
    if sys.platform != "darwin":
        return "not macOS: nothing to do"
    existed = plist_path().exists()
    unload()
    if existed:
        plist_path().unlink()
        return f"removed {plist_path()}; LocalDrop will no longer start at login"
    return "no LaunchAgent was installed"


def uninstalled() -> bool:
    return not plist_path().exists()


def loaded() -> bool:
    if sys.platform != "darwin":
        return False
    code, out, _ = _launchctl("print", f"gui/{os.getuid()}/{LAUNCHD_LABEL}")
    return code == 0 and LAUNCHD_LABEL in out


def unload() -> None:
    if sys.platform == "darwin":
        _launchctl("bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}")


def executable_path() -> Path:
    """Absolute path of the running binary, for the plist's ProgramArguments."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    # `pip install localdrop` puts the console script next to the interpreter.
    candidate = Path(sys.executable).parent / "localdrop"
    if candidate.exists():
        return candidate.resolve()
    which = shutil.which("localdrop")
    return Path(which).resolve() if which else Path(sys.executable).resolve()
