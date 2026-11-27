#!/usr/bin/env bash
# Build and release to a host whose Caddy serves the site straight from /srv/sites/neon-zenith: the build is sent
# into a new timestamped release, `current` is swapped to it atomically and older releases are removed. Caddy
# resolves `current` on every request, so nothing restarts.
# GATEWAY_FRAGMENT names the site block (deploy/gateway.caddy.example shows its shape). When FRAGMENT_INSTALLER is set
# and the block differs from the installed one, the host runs `$FRAGMENT_INSTALLER install zenith <block>`; the live
# host uses the shared gateway's install_gateway_site_fragment.sh, which validates the whole configuration, reloads
# it, and restores the previous block on failure. Without it, install the block in your Caddy by hand.
# The target comes from the environment or from deploy/local.conf (not committed):
#   HOST=user@host   KEY=/path/to/ssh-key   SITE=https://your.host/ (checked after the release)
#   GATEWAY_FRAGMENT=deploy/local/gateway.caddy
#   FRAGMENT_INSTALLER=/path/on/host/install_gateway_site_fragment.sh (optional)
# The host user needs passwordless sudo.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${HOST:?set HOST (user@host) in the environment or in deploy/local.conf}"
: "${KEY:?set KEY (ssh key file) in the environment or in deploy/local.conf}"
STAMP=$(date +%Y%m%d-%H%M%S)
NAME=zenith
: "${GATEWAY_FRAGMENT:?set GATEWAY_FRAGMENT to the site block (see deploy/gateway.caddy.example)}"
R=/srv/sites/neon-zenith

npm run build
# Vite stamps its copy of public/ with new mtimes; put the originals back so unchanged files keep their ETag and
# link to the previous release
rsync -a public/ dist/
# the hashed bundles are named by their content, so a fixed mtime lets an unchanged one link too
find dist/assets -type f -exec touch -t 200001010000 {} +
PREV=$(ssh -i "$KEY" "$HOST" "sudo install -d -o root -g root -m 0755 $R/releases && (readlink -e $R/current || true)")
# Sent straight into the new release with the previous one as the basis: unchanged files (same content and mtime)
# become hard links into it and changed ones travel as deltas, so nothing is staged on the host.
rsync -rlptz --rsync-path="sudo rsync" ${PREV:+--link-dest="$PREV/"} -e "ssh -i $KEY" dist/ "$HOST:$R/releases/$STAMP/"
rsync -z -e "ssh -i $KEY" "$GATEWAY_FRAGMENT" "$HOST:$NAME-site.caddy"
ssh -i "$KEY" "$HOST" "STAMP=$STAMP NAME=$NAME R=$R FRAGMENT_INSTALLER=${FRAGMENT_INSTALLER:-} bash -s" <<'REMOTE'
set -euo pipefail
sudo chmod -R a+rX "$R/releases/$STAMP"
# a rename is atomic, so no request finds `current` missing
sudo ln -sfn "releases/$STAMP" "$R/current.next"
sudo mv -T "$R/current.next" "$R/current"
for old in "$R"/releases/*; do
  [ "$(basename "$old")" = "$STAMP" ] || sudo rm -rf -- "$old"
done
if [ -n "$FRAGMENT_INSTALLER" ]; then
  installed=$("$FRAGMENT_INSTALLER" status "$NAME" 2>/dev/null | awk 'length($1) == 64 { print $1 }' || true)
  wanted=$(sha256sum < ~/"$NAME"-site.caddy | cut -d' ' -f1)
  [ "$wanted" = "$installed" ] || "$FRAGMENT_INSTALLER" install "$NAME" ~/"$NAME"-site.caddy
fi
rm -f ~/"$NAME"-site.caddy
echo "released $STAMP"
REMOTE
if [ -n "${SITE:-}" ]; then curl -fsS -o /dev/null -w "live %{http_code}\n" "$SITE"; fi
