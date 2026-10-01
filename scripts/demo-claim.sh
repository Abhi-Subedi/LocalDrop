#!/usr/bin/env bash
# Claim the owner account on a running public demo, closing it to new visitors.
#
#   bash scripts/demo-claim.sh https://something.trycloudflare.com [username]
#
# Demo mode opens a claim window so the maintainer can take the owner account
# before strangers arrive. Creating an owner closes that window: afterwards
# /api/v1/demo/session returns 503 and no new visitors can be served.
#
# The owner is what an operator needs in order to look at the demo, restart it,
# or inspect what is stored. Everyone else is a throwaway account.
#
# Needs curl. Run it on any machine that can reach the demo URL.

set -euo pipefail

URL="${1:-}"
USERNAME="${2:-owner}"
PASSWORD="${DEMO_CLAIM_PASSWORD:-}"

die() { printf '\n  ERROR: %s\n\n' "$1" >&2; exit 1; }
info() { printf '  %s\n' "$1"; }

[ -n "$URL" ] || die "usage: bash scripts/demo-claim.sh <demo-url> [username]"
URL="${URL%/}"

command -v curl >/dev/null 2>&1 || die "curl is required"

# Refuse to claim a production instance by accident. The two failure modes are
# worth telling apart: a 404 means "this is a real server, keep your hands off",
# a connection failure means "the tunnel is down, try again".
info "checking that $URL is a demo instance"
# curl prints 000 itself when it never connected, so do not append a fallback
# code on top of that.
STATUS=$(curl -s -o /tmp/ld-demo-status.json -w '%{http_code}' --max-time 15 \
  "$URL/api/v1/demo/status" 2>/dev/null) || true
STATUS="${STATUS:-000}"

case "$STATUS" in
  200) : ;;
  404|405)
    die "$URL answered, but /api/v1/demo/status is $STATUS.
     That instance is NOT in demo mode. Refusing to touch it - claim the owner
     on your own server instead (see docs/INSTALLATION.md)."
    ;;
  000)
    die "$URL could not be reached at all. Is the tunnel still up?"
    ;;
  *)
    die "$URL returned HTTP $STATUS for /api/v1/demo/status."
    ;;
esac

if grep -q '"demo_mode": *true' /tmp/ld-demo-status.json 2>/dev/null; then
  info "confirmed: demo mode is on"
else
  die "that instance did not report demo mode. Refusing to touch it."
fi

ACCEPTING=$(grep -o '"accepting_visitors": *[a-z]*' /tmp/ld-demo-status.json | grep -o '[a-z]*$' || echo false)
if [ "$ACCEPTING" != "true" ]; then
  die "the claim window is already closed - an owner exists, so the demo is no longer accepting visitors."
fi

if [ -z "$PASSWORD" ]; then
  printf '\n  Password for the owner account "%s" (min 8 chars): ' "$USERNAME"
  read -rs PASSWORD
  printf '\n'
  [ "${#PASSWORD}" -ge 8 ] || die "password must be at least 8 characters"
fi

info "requesting a setup token"
# The server prints one at boot; the endpoint mints a fresh one while the
# claim window is open. Last-writer-wins, so this invalidates the old one.
TOKEN=$(curl -fsS --max-time 15 "$URL/api/v1/setup/token" \
  | sed -n 's/.*"token" *: *"\([^"]*\)".*/\1/p')
[ -n "$TOKEN" ] || die "could not get a setup token (is onboarding already complete?)"

info "creating the owner account"
RESP=$(curl -fsS --max-time 20 -X POST "$URL/api/v1/setup/owner" \
  -H 'Content-Type: application/json' \
  -H 'X-Requested-With: localdrop' \
  --data "$(printf '{"username":%s,"password":%s,"setup_token":%s}' \
    "\"$USERNAME\"" "\"$PASSWORD\"" "\"$TOKEN\"")" 2>&1) \
  || die "the owner request failed: $RESP"

info "owner '$USERNAME' created"
cat <<EOF

  ---------------------------------------------------------------
   The demo is now yours, and closed to new visitors.
  ---------------------------------------------------------------

   URL        $URL
   Username   $USERNAME
   Password   (the one you just entered)

   The demo endpoints now return 503, so nobody new can be served.
   Existing throwaway accounts are still deleted on their TTL.

   Re-open the demo by deleting the owner and restarting the stack:

     docker compose -f docker-compose.demo.yml down -v
     docker compose -f docker-compose.demo.yml up -d

  The password is not stored anywhere by this script. If you lose it, the
  only way back in is to reset the volume, which deletes every demo file.

EOF
