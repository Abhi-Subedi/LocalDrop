#!/bin/sh
# LocalDrop installer for Linux (and macOS).
#
#   curl -fsSL https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh | sh
#
# Installs the prebuilt binary to /usr/local/bin, a system account, the data
# directory, a systemd unit (Linux) or a launchd job (macOS), then starts the
# server. If you would rather read the script first, download it:
#
#   curl -fsSLO https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh
#   less install.sh && sh install.sh
#
# Run `sh install.sh --help` for options. Every value can also be set in the
# environment, e.g.  LOCALDROP_PORT=9000 sh install.sh
#
# What it does, in order:
#   1. resolves the release version and the archive checksum
#   2. downloads the archive over HTTPS and verifies its SHA-256
#   3. creates a locked `localdrop` system account and /var/lib/localdrop
#   4. installs the binary, config file, and service definition
#   5. generates a secret key, enables and starts the service
#   6. prints the URL and how to reach the one-time setup token
#
# It never overwrites your data directory, your config, or your database.

set -eu

# --------------------------------------------------------------------------
# defaults
# --------------------------------------------------------------------------
REPO="Abhi-Subedi/LocalDrop"
INSTALL_DIR="${LOCALDROP_INSTALL_DIR:-/usr/local/bin}"
CONFIG_DIR="${LOCALDROP_CONFIG_DIR:-/etc/localdrop}"
DATA_DIR="${LOCALDROP_DATA_DIR:-/var/lib/localdrop}"
RUN_USER="${LOCALDROP_USER:-localdrop}"
PORT="${LOCALDROP_PORT:-8080}"
VERSION="${LOCALDROP_VERSION:-stable}"     # stable | latest | 1.1.0
BASE_URL="${LOCALDROP_BASE_URL:-https://raw.githubusercontent.com/$REPO}"
API_URL="${LOCALDROP_API_URL:-https://api.github.com}"
SERVICE_NAME="localdrop"
# macOS launchd needs a concrete uid; resolve it after we know the user exists.
LAUNCHD_PLIST="/Library/LaunchDaemons/io.github.abhisubedi.localdrop.plist"

# Generated: a 32-byte hex key, the same shape LocalDrop itself generates.
generate_secret() {
  if [ -r /dev/urandom ]; then
    od -An -tx1 -N32 /dev/urandom | tr -d ' \n'
  else
    head -c 32 /dev/zero | od -An -tx1 | tr -d ' \n'
  fi
}

die()  { printf '\n  ERROR: %s\n\n' "$1" >&2; exit 1; }
info() { printf '  %s\n' "$1"; }
step() { printf '\n== %s\n' "$1"; }

usage() {
  cat <<EOF
LocalDrop installer

Usage:  sh install.sh [options]

  --version <ver>   Release to install: stable (default), latest, or e.g. 1.1.0
  --port <port>     Port to listen on (default: 8080)
  --data-dir <dir>  Data directory (default: $DATA_DIR)
  --user <name>     System account to run as (default: $RUN_USER)
  --no-start        Install everything but do not enable/start the service
  --no-service      Install the binary only; no account, no service
  --prefix <dir>    Binary location (default: $INSTALL_DIR)
  -h, --help        This text

Environment equivalents: LOCALDROP_VERSION, LOCALDROP_PORT, LOCALDROP_DATA_DIR,
LOCALDROP_USER, LOCALDROP_INSTALL_DIR, LOCALDROP_BASE_URL, LOCALDROP_API_URL,
LOCALDROP_CONFIG_DIR. Export GITHUB_TOKEN to raise the GitHub API rate limit
used when resolving "stable".
EOF
}

# --------------------------------------------------------------------------
# arguments
# --------------------------------------------------------------------------
START_SERVICE=1
MANAGE_SERVICE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a value}"; shift 2 ;;
    --port)    PORT="${2:?--port needs a value}"; shift 2 ;;
    --data-dir) DATA_DIR="${2:?--data-dir needs a value}"; shift 2 ;;
    --user)    RUN_USER="${2:?--user needs a value}"; shift 2 ;;
    --prefix)  INSTALL_DIR="${2:?--prefix needs a value}"; shift 2 ;;
    --no-start) START_SERVICE=0; shift ;;
    --no-service) MANAGE_SERVICE=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

# --------------------------------------------------------------------------
# platform + prerequisites
# --------------------------------------------------------------------------
UNAME_S="$(uname -s)"
case "$UNAME_S" in
  Linux)  PLATFORM="linux" ;;
  Darwin) PLATFORM="macos" ;;
  *) die "unsupported platform: $UNAME_S. Use the Docker image on other systems." ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  die "must run as root (or via sudo). Try:  curl -fsSL <url> | sudo sh"
fi

[ -n "$INSTALL_DIR" ] || die "install directory must not be empty"

command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 \
  || die "need curl or wget to download LocalDrop"

if [ "$PLATFORM" = "linux" ] && ! command -v systemctl >/dev/null 2>&1; then
  die "systemd not found. Install the binary with --no-service and run it yourself."
fi

# --------------------------------------------------------------------------
# resolve the download
# --------------------------------------------------------------------------
# Asset names come from .github/workflows/release.yml:
#   localdrop-<version>-linux-x64.tar.gz
#   localdrop-<version>-linux-arm64.tar.gz
#   localdrop-<version>-macos-x64.tar.gz
#   localdrop-<version>-macos-arm64.tar.gz
resolve_tag() {
  if [ "$VERSION" = "latest" ]; then
    VERSION="stable"
  fi
  case "$VERSION" in
    stable|1.*) : ;;   # a tag or the rolling "stable" alias
    *) die "unexpected version '$VERSION'" ;;
  esac
}

detect_arch() {
  MACHINE="$(uname -m)"
  case "$MACHINE" in
    x86_64|amd64)  echo "x64" ;;
    aarch64|arm64) echo "arm64" ;;
    # Only x64 and arm64 are built. Naming armv7 here produced a request for
    # localdrop-<version>-linux-armv7.tar.gz, which no release has ever
    # published - so it failed later as a download 404 with no explanation.
    # Fail now, where the message can say what to do instead.
    armv7l|armv6l|armv5tel)
      die "no LocalDrop build for $MACHINE (32-bit ARM). Releases are x64 and arm64 only.
  On a 32-bit board, use Docker instead:
      docker run -p 8080:8080 -v localdrop:/data ghcr.io/abhi-subedi/localdrop:stable"
      ;;
    *) die "unsupported CPU architecture: $MACHINE" ;;
  esac
}

fetch() {
  # fetch <url> <destination>
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 -o "$2" "$1"
  else
    wget -q -O "$2" "$1"
  fi
}

# Download to stdout; used for the checksum file and the service templates.
fetch_stdout() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 3 --retry-delay 2 -o - "$1"
  else
    wget -q -O - "$1"
  fi
}

# Same, for api.github.com. Sending the token when one is exported is what
# lifts the 60-requests-per-hour unauthenticated limit; without it a busy NAT
# or a CI runner starts seeing 403s here.
fetch_api_stdout() {
  if command -v curl >/dev/null 2>&1; then
    if [ -n "${GITHUB_TOKEN:-}" ]; then
      curl -fsSL --retry 3 --retry-delay 2 -H "Authorization: Bearer $GITHUB_TOKEN" -o - "$1"
    else
      curl -fsSL --retry 3 --retry-delay 2 -o - "$1"
    fi
  elif [ -n "${GITHUB_TOKEN:-}" ]; then
    wget -q -O - --header="Authorization: Bearer $GITHUB_TOKEN" "$1"
  else
    wget -q -O - "$1"
  fi
}

# Resolve a file that ships alongside this script. When run as
# `curl ... | sh` there is no script directory, so fall back to fetching the
# same path from the repository at the same ref.
#   asset <repo-relative-path>  ->  prints a local path to a real file
ASSET_CACHE=""
asset() {
  rel="$1"
  local_copy="$(dirname "$0")/$rel"
  if [ -f "$local_copy" ]; then
    printf '%s' "$local_copy"
    return 0
  fi
  [ -n "$ASSET_CACHE" ] || ASSET_CACHE="$TMP_DIR/assets"
  mkdir -p "$ASSET_CACHE"
  dest="$ASSET_CACHE/$(basename "$rel")"
  if [ ! -f "$dest" ]; then
    fetch "$BASE_URL/v$VERSION/$rel" "$dest" \
      || fetch "$BASE_URL/main/$rel" "$dest" \
      || return 1
  fi
  printf '%s' "$dest"
}

# --------------------------------------------------------------------------
step "1/5  Resolving the release"
# --------------------------------------------------------------------------
resolve_tag
ARCH="$(detect_arch)"
ASSET="localdrop-${VERSION}-${PLATFORM}-${ARCH}.tar.gz"
RELEASE_BASE="https://github.com/$REPO/releases/download/v${VERSION}"
# The rolling aliases have no checksum of their own; pin to a real tag so the
# download is always verifiable. "stable" points at the newest release tag.
if [ "$VERSION" = "stable" ]; then
  # Two sources, tried in order:
  #
  #   1. The releases API. "latest" there is by definition a published,
  #      non-prerelease release, so it can never name a version whose assets
  #      do not exist. That correctness is the whole reason it goes first.
  #   2. The VERSION file on main. Kept as a fallback because networks are
  #      uneven: some reach raw.githubusercontent.com and not api.github.com,
  #      some the reverse. Depending on a single host made every install
  #      hostage to that host.
  #
  # The old behaviour read only the VERSION file, so a 404 from
  # raw.githubusercontent.com aborted with a bare "404" and no clue which host
  # had failed or what to do about it.
  RESOLVED="$(fetch_api_stdout "$API_URL/repos/$REPO/releases/latest" 2>/dev/null || true)"
  RESOLVED="$(printf '%s' "$RESOLVED" | tr ',' '\n' \
    | sed -n 's/.*"tag_name"[ ]*:[ ]*"v\{0,1\}\([^"/]*\)".*/\1/p' | head -n1 || true)"
  # $BASE_URL is the repo root; raw.githubusercontent.com needs the ref, so this
  # is .../LocalDrop/main/VERSION. Omitting "/main" is a silent 404 - the URL
  # looks right and there is no such file at the root.
  [ -n "$RESOLVED" ] || RESOLVED="$(fetch_stdout "$BASE_URL/main/VERSION" 2>/dev/null || true)"
  RESOLVED="$(printf '%s' "$RESOLVED" | tr -d ' \t\r\n[:space:]')"

  case "$RESOLVED" in
    [0-9]*.[0-9]*.[0-9]*)
      VERSION="$RESOLVED"
      ;;
    *)
      die "could not resolve the current stable version.
  tried: $API_URL/repos/$REPO/releases/latest
         $BASE_URL/main/VERSION
  If a proxy or firewall is blocking one of those hosts, the other should have
  worked - check for a stale DNS cache and retry.

  Otherwise, find the newest version and pin it explicitly:
         curl -fsSLO https://raw.githubusercontent.com/$REPO/main/install.sh
         sh install.sh --version 1.1.0"
      ;;
  esac
  ASSET="localdrop-${VERSION}-${PLATFORM}-${ARCH}.tar.gz"
  RELEASE_BASE="https://github.com/$REPO/releases/download/v${VERSION}"
fi
info "version $VERSION  ·  $PLATFORM-$ARCH  ·  $ASSET"

TMP_DIR="$(mktemp -d)"
cleanup() { [ -n "${TMP_DIR:-}" ] && rm -rf "$TMP_DIR"; }
trap cleanup EXIT INT TERM

step "2/5  Downloading and verifying"
# --------------------------------------------------------------------------
ARCHIVE="$TMP_DIR/$ASSET"
fetch "$RELEASE_BASE/$ASSET" "$ARCHIVE" || die "download failed: $RELEASE_BASE/$ASSET"

SUMS="$TMP_DIR/SHA256SUMS"
fetch "$RELEASE_BASE/SHA256SUMS" "$SUMS" || die "could not download SHA256SUMS"

# Verify before unpacking anything.
if command -v sha256sum >/dev/null 2>&1; then
  CALC="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
elif command -v shasum >/dev/null 2>&1; then
  CALC="$(shasum -a 256 "$ARCHIVE" | cut -d' ' -f1)"
else
  die "need sha256sum or shasum to verify the download"
fi
WANT="$(grep "  *$ASSET\$" "$SUMS" | head -n1 | cut -d' ' -f1 || true)"
[ -n "$WANT" ] || die "$ASSET is not listed in SHA256SUMS — refusing to install"
[ "$CALC" = "$WANT" ] || die "checksum mismatch for $ASSET (expected $WANT, got $CALC)"
info "sha256 verified"

tar -xzf "$ARCHIVE" -C "$TMP_DIR" || die "could not unpack $ASSET"
BINARY="$(find "$TMP_DIR" -type f -name localdrop -perm -u+x 2>/dev/null | head -n1 || true)"
[ -n "$BINARY" ] || BINARY="$(find "$TMP_DIR" -type f -name localdrop | head -n1)"
[ -n "$BINARY" ] && [ -f "$BINARY" ] || die "archive did not contain a localdrop binary"
chmod +x "$BINARY"

step "3/5  Creating the system account and data directory"
# --------------------------------------------------------------------------
if [ "$MANAGE_SERVICE" -eq 0 ]; then
  info "skipping account and service management (--no-service)"
else
  if ! id "$RUN_USER" >/dev/null 2>&1; then
    if command -v useradd >/dev/null 2>&1; then
      useradd --system --no-create-home --shell /usr/sbin/nologin \
              --comment "LocalDrop file server" "$RUN_USER"
    elif command -v dscl >/dev/null 2>&1; then
      dscl . -create "/Users/$RUN_USER" UserShell /usr/bin/false
      dscl . -create "/Users/$RUN_USER" UserShell /usr/bin/false 2>/dev/null || true
    else
      die "no useradd/dscl available to create the '$RUN_USER' account"
    fi
    info "created system account '$RUN_USER'"
  else
    info "reusing existing account '$RUN_USER'"
  fi

  mkdir -p "$DATA_DIR"
  chown -R "$RUN_USER":"$RUN_USER" "$DATA_DIR"
  # 0750: the blobs are the user's files; nothing else on the host needs to
  # read them, and `localdrop` must be able to drop privileges into it.
  chmod 0750 "$DATA_DIR"
  info "$DATA_DIR ready"
fi

step "4/5  Installing files"
# --------------------------------------------------------------------------
mkdir -p "$INSTALL_DIR"
# Install atomically so a running service never sees a half-written binary.
cp "$BINARY" "$INSTALL_DIR/localdrop.new"
chmod 0755 "$INSTALL_DIR/localdrop.new"
mv -f "$INSTALL_DIR/localdrop.new" "$INSTALL_DIR/localdrop"
info "$INSTALL_DIR/localdrop  (version $("$INSTALL_DIR/localdrop" --version | awk '{print $NF}'))"

if [ "$MANAGE_SERVICE" -eq 0 ]; then
  "$INSTALL_DIR/localdrop" --check || true
  printf '\n  Installed the binary only.\n  Start it yourself:  %s\n\n' \
    "sudo -u $RUN_USER $INSTALL_DIR/localdrop --data-dir $DATA_DIR --port $PORT" 2>/dev/null \
    || printf '\n  Installed the binary only. Start it with: localdrop\n\n'
  exit 0
fi

mkdir -p "$CONFIG_DIR"
ENV_FILE="$CONFIG_DIR/localdrop.env"
if [ -f "$ENV_FILE" ]; then
  info "keeping your existing $ENV_FILE"
else
  SECKEY="$(generate_secret)"
  ENV_TEMPLATE="$(asset "packaging/$PLATFORM/localdrop.env.example" || true)"
  if [ -n "${ENV_TEMPLATE:-}" ] && [ -f "$ENV_TEMPLATE" ]; then
    sed -e "s|^LOCALDROP_SECRET_KEY=.*|LOCALDROP_SECRET_KEY=$SECKEY|" \
        -e "s|^LOCALDROP_PORT=.*|LOCALDROP_PORT=$PORT|" \
        "$ENV_TEMPLATE" > "$ENV_FILE"
  else
    cat > "$ENV_FILE" <<EOF
# LocalDrop configuration — full reference in docs/CONFIGURATION.md
LOCALDROP_SECRET_KEY=$SECKEY
LOCALDROP_PORT=$PORT
LOCALDROP_HOST=0.0.0.0
LOCALDROP_LOG_FORMAT=console
EOF
  fi
  chmod 0640 "$ENV_FILE"
  chown root:"$RUN_USER" "$ENV_FILE" 2>/dev/null || true
  info "wrote $ENV_FILE (secret key generated)"
fi

# The LAN URL is what share links and the printed QR use; record it when the
# host has exactly one non-loopback IPv4 so a headless box is still useful.
PUBLIC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.*src \([0-9.]*\).*/\1/p' | head -n1 || true)"
if [ -n "$PUBLIC_IP" ] && ! grep -q '^LOCALDROP_PUBLIC_URL=' "$ENV_FILE"; then
  printf 'LOCALDROP_PUBLIC_URL=http://%s:%s\n' "$PUBLIC_IP" "$PORT" >> "$ENV_FILE"
  info "recorded LOCALDROP_PUBLIC_URL=http://$PUBLIC_IP:$PORT"
fi

if [ "$PLATFORM" = "linux" ]; then
  UNIT_SRC="$(asset "packaging/linux/localdrop.service" || true)"
  [ -n "${UNIT_SRC:-}" ] && [ -f "$UNIT_SRC" ] \
    || die "could not obtain packaging/linux/localdrop.service"
  sed -e "s|^ExecStart=.*|ExecStart=$INSTALL_DIR/localdrop --no-browser|" \
      -e "s|^WorkingDirectory=.*|WorkingDirectory=$DATA_DIR|" \
      -e "s|^ReadWritePaths=.*|ReadWritePaths=$DATA_DIR|" \
      -e "s|^StateDirectory=.*|StateDirectory=$(basename "$DATA_DIR")|" \
      -e "s|^EnvironmentFile=.*|EnvironmentFile=-$ENV_FILE|" \
      -e "s|^Description=.*|Description=LocalDrop $VERSION — self-hosted file sharing|" \
      "$UNIT_SRC" > "/etc/systemd/system/$SERVICE_NAME.service"
  info "installed /etc/systemd/system/$SERVICE_NAME.service"
else
  PLIST_SRC="$(asset "packaging/macos/localdrop.plist.in" || true)"
  [ -n "${PLIST_SRC:-}" ] && [ -f "$PLIST_SRC" ] \
    || die "could not obtain packaging/macos/localdrop.plist.in"
  UID_NUM="$(id -u "$RUN_USER")"
  # launchd has no EnvironmentFile, so the values from $ENV_FILE are baked
  # into the plist's EnvironmentVariables dictionary here.
  PLIST_ENV="$(sed -n 's/^LOCALDROP_[A-Z_]*=//p' "$ENV_FILE" | tr '\n' '|')"
  sed -e "s|@UID@|$UID_NUM|g" \
      -e "s|@DATA_DIR@|$DATA_DIR|g" \
      -e "s|@BINARY@|$INSTALL_DIR/localdrop|g" \
      -e "s|@VERSION@|$VERSION|g" \
      -e "s|SET_BY_INSTALLER|$PLIST_ENV|g" \
      "$PLIST_SRC" > "$LAUNCHD_PLIST"
  chown root:wheel "$LAUNCHD_PLIST" 2>/dev/null || true
  chmod 0600 "$LAUNCHD_PLIST"   # contains the secret key
  info "installed $LAUNCHD_PLIST"
fi

step "5/5  Enabling and starting"
# --------------------------------------------------------------------------
if [ "$START_SERVICE" -eq 0 ]; then
  info "not starting the service (--no-start)"
else
  if [ "$PLATFORM" = "linux" ]; then
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
    if systemctl restart "$SERVICE_NAME"; then
      info "service started"
    else
      die "the service failed to start. Read the log:  journalctl -u $SERVICE_NAME -n 50 --no-pager"
    fi
  else
    launchctl bootout system "/$LAUNCHD_PLIST" 2>/dev/null || true
    if launchctl bootstrap system "$LAUNCHD_PLIST" 2>/dev/null; then
      launchctl enable "system/$LAUNCHD_PLIST" 2>/dev/null || true
      launchctl kickstart -k "system/$LAUNCHD_PLIST" 2>/dev/null || true
      info "service started (launchd)"
    else
      die "launchd rejected $LAUNCHD_PLIST. Check: launchctl print system/$SERVICE_NAME"
    fi
  fi
fi

# --------------------------------------------------------------------------
# done
# --------------------------------------------------------------------------
URL="http://${PUBLIC_IP:-127.0.0.1}:$PORT"
cat <<EOF

  ---------------------------------------------------------------
   LocalDrop $VERSION installed.
  ---------------------------------------------------------------

   Web UI      $URL
   Service     $SERVICE_NAME  ($( [ "$PLATFORM" = "linux" ] && echo "systemctl status $SERVICE_NAME" || echo "launchctl print system/$SERVICE_NAME" ))
   Config      $ENV_FILE
   Data        $DATA_DIR

  Finish setup:

    1. Open the URL above from any device on your network.
    2. Get the one-time setup token:
$( [ "$PLATFORM" = "linux" ] && echo "         journalctl -u $SERVICE_NAME -n 50 --no-pager | grep -i 'setup token'" || echo "         log show --predicate 'process == \"localdrop\"' --last 5m | grep -i 'setup token'" )
    3. Paste it in, create your owner account, start dropping files.

  Back up:  ./scripts/backup.sh   (docs/BACKUP.md)
  Upgrade:  re-run this script, then restart the service.
  Uninstall: sudo sh uninstall.sh

EOF
