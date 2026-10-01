#!/bin/sh
# Remove a LocalDrop native install (Linux systemd / macOS launchd).
#
#   sudo sh uninstall.sh                 # asks before deleting data
#   sudo sh uninstall.sh --purge         # delete config and data as well
#   sudo sh uninstall.sh --keep-data     # the default: your files are kept
#
# Your files are never deleted unless you pass --purge. Take a backup first if
# you are not sure (see docs/BACKUP.md).

set -eu

INSTALL_BIN="${LOCALDROP_INSTALL_DIR:-/usr/local/bin}/localdrop"
CONFIG_DIR="${LOCALDROP_CONFIG_DIR:-/etc/localdrop}"
DATA_DIR="${LOCALDROP_DATA_DIR:-/var/lib/localdrop}"
RUN_USER="${LOCALDROP_USER:-localdrop}"
SERVICE_NAME="localdrop"
LAUNCHD_PLIST="/Library/LaunchDaemons/io.github.abhisubedi.localdrop.plist"
PLIST_LABEL="io.github.abhisubedi.localdrop"

PURGE=0
KEEP_DATA=1
for arg in "$@"; do
  case "$arg" in
    --purge)     PURGE=1; KEEP_DATA=0 ;;
    --keep-data) PURGE=0; KEEP_DATA=1 ;;
    -h|--help)
      cat <<EOF
Usage: sudo sh uninstall.sh [--purge | --keep-data]

  --purge      also delete $CONFIG_DIR and $DATA_DIR (irreversible)
  --keep-data  keep $DATA_DIR (default)
EOF
      exit 0 ;;
    *) printf 'unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

[ "$(id -u)" -eq 0 ] || { printf 'must run as root (or via sudo)\n' >&2; exit 1; }

info() { printf '  %s\n' "$1"; }

UNAME_S="$(uname -s)"

if [ "$UNAME_S" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
  info "stopping and disabling $SERVICE_NAME"
  systemctl disable --now "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/$SERVICE_NAME.service"
  systemctl daemon-reload 2>/dev/null || true
elif [ "$UNAME_S" = "Darwin" ] && command -v launchctl >/dev/null 2>&1; then
  info "stopping and unloading $PLIST_LABEL"
  launchctl bootout "system/$PLIST_LABEL" 2>/dev/null || true
  rm -f "$LAUNCHD_PLIST"
fi

if [ -f "$INSTALL_BIN" ]; then
  info "removing $INSTALL_BIN"
  rm -f "$INSTALL_BIN"
fi

if [ "$PURGE" -eq 1 ]; then
  printf '\n  This will permanently delete:\n    %s\n    %s\n' "$CONFIG_DIR" "$DATA_DIR"
  printf '  Type yes to continue: '
  read -r reply
  if [ "$reply" = "yes" ]; then
    rm -rf "$CONFIG_DIR" "$DATA_DIR"
    info "removed $CONFIG_DIR and $DATA_DIR"
  else
    info "aborted; nothing further removed"
    exit 0
  fi
elif [ "$KEEP_DATA" -eq 1 ] && [ -d "$DATA_DIR" ]; then
  info "kept your data in $DATA_DIR"
  info "delete it later with: rm -rf $DATA_DIR   (or re-run with --purge)"
fi

if [ "$PURGE" -eq 1 ] && id "$RUN_USER" >/dev/null 2>&1; then
  # Only remove the account if this install created it (no login shell).
  if userdel "$RUN_USER" 2>/dev/null; then
    info "removed system account '$RUN_USER'"
  else
    info "left account '$RUN_USER' in place (in use or owned by something else)"
  fi
fi

cat <<EOF

  LocalDrop removed.

  Reinstall:  curl -fsSL https://raw.githubusercontent.com/Abhi-Subedi/LocalDrop/main/install.sh | sh
  Or Docker:  https://github.com/Abhi-Subedi/LocalDrop

EOF
