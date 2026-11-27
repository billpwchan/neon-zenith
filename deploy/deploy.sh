#!/usr/bin/env bash
# Build and release to a host whose Caddy serves the site straight from /srv/sites/neon-zenith: the build becomes a
# new timestamped release, `current` is swapped to it atomically and older releases are removed. Caddy resolves
# `current` on every request, so nothing restarts.
# GATEWAY_FRAGMENT names the site block (deploy/gateway.caddy.example shows its shape). When FRAGMENT_INSTALLER is set
# and the block differs from the installed one, the host runs `$FRAGMENT_INSTALLER install zenith <block>`; the live
# host uses the shared gateway's install_gateway_site_fragment.sh, which validates the whole configuration, reloads
# it, and restores the previous block on failure. Without it, install the block in your Caddy by hand.
# The target comes from the environment or from deploy/local.conf (not committed):
#   HOST=user@host   KEY=/path/to/ssh-key   SITE=https://your.host/ (checked after the release)
#   GATEWAY_FRAGMENT=deploy/local/gateway.caddy
#   FRAGMENT_INSTALLER=/path/on/host/install_gateway_site_fragment.sh (optional)
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${HOST:?set HOST (user@host) in the environment or in deploy/local.conf}"
: "${KEY:?set KEY (ssh key file) in the environment or in deploy/local.conf}"
STAMP=$(date +%Y%m%d-%H%M%S)
UPLOAD=zenith-upload
: "${GATEWAY_FRAGMENT:?set GATEWAY_FRAGMENT to the site block (see deploy/gateway.caddy.example)}"

npm run build
# Vite stamps its copy of public/ with new mtimes; put the originals back so unchanged files keep their ETag and
# link to the previous release
rsync -a public/ dist/
# the hashed bundles are named by their content, so a fixed mtime lets an unchanged one link too
find dist/assets -type f -exec touch -t 200001010000 {} +
ssh -i "$KEY" "$HOST" "mkdir -p ~/$UPLOAD"
rsync -az --delete -e "ssh -i $KEY" dist/ "$HOST:$UPLOAD/dist/"
rsync -az -e "ssh -i $KEY" "$GATEWAY_FRAGMENT" "$HOST:$UPLOAD/site.caddy"
ssh -i "$KEY" "$HOST" "STAMP=$STAMP UPLOAD=$UPLOAD FRAGMENT_INSTALLER=${FRAGMENT_INSTALLER:-} bash -s" <<'REMOTE'
set -euo pipefail
R=/srv/sites/neon-zenith
sudo install -d -o root -g root -m 0755 "$R/releases"
PREV=$(readlink -e "$R/current" || true)
# files unchanged since the previous release (same content and mtime) become hard links into it
sudo rsync -a --no-owner --no-group ${PREV:+--link-dest="$PREV/"} ~/"$UPLOAD"/dist/ "$R/releases/$STAMP/"
sudo chown -R root:root "$R/releases/$STAMP"
sudo chmod -R a+rX "$R/releases/$STAMP"
# a rename is atomic, so no request finds `current` missing
sudo ln -sfn "releases/$STAMP" "$R/current.next"
sudo mv -T "$R/current.next" "$R/current"
for old in "$R"/releases/*; do
  [ "$(basename "$old")" = "$STAMP" ] || sudo rm -rf -- "$old"
done
if [ -n "$FRAGMENT_INSTALLER" ]; then
  installed=$("$FRAGMENT_INSTALLER" status zenith 2>/dev/null | awk 'length($1) == 64 { print $1 }' || true)
  wanted=$(sha256sum < ~/"$UPLOAD"/site.caddy | cut -d' ' -f1)
  [ "$wanted" = "$installed" ] || "$FRAGMENT_INSTALLER" install zenith ~/"$UPLOAD"/site.caddy
fi
echo "released $STAMP"
REMOTE
if [ -n "${SITE:-}" ]; then curl -fsS -o /dev/null -w "live %{http_code}\n" "$SITE"; fi
