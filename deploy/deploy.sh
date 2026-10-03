#!/usr/bin/env bash
# Build and release to the Lightsail host: a new timestamped release, `current` repointed, container recreated.
# Earlier releases stay in /opt/neon-zenith/releases for rollback (repoint `current`, then recreate).
# compose.yaml is installed at /opt/neon-zenith/, where its ./current and ./deploy paths resolve.
# The container serves on :8080 inside a Docker network shared with your reverse proxy (GATEWAY_NETWORK).
# A proxy site block (GATEWAY_FRAGMENT, see gateway.caddy.example) is copied but not reloaded: validate and
# reload the proxy by hand after changing it.
# Settings come from the environment or deploy/local.conf (not tracked):
#   KEY=<ssh key file>  HOST=user@host  SITE=https://zenith.example.com/
#   GATEWAY_NETWORK=proxy  GATEWAY_FRAGMENT=deploy/local/gateway.caddy
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f deploy/local.conf ] && . deploy/local.conf
: "${KEY:?set KEY (ssh key) in the environment or deploy/local.conf}"
: "${HOST:?set HOST (user@host)}"
GATEWAY_NETWORK=${GATEWAY_NETWORK:-proxy}
STAMP=$(date +%Y%m%d-%H%M%S)

npm run build
# Vite stamps its copy of public/ with new mtimes; put the originals back so unchanged files keep their ETag
rsync -a public/ dist/
# the hashed bundles are named by their content, so a fixed mtime lets an unchanged one link to the previous release
find dist/assets -type f -exec touch -t 200001010000 {} +
ssh -i "$KEY" "$HOST" 'mkdir -p ~/zenith-upload'
rsync -az --delete -e "ssh -i $KEY" dist/ "$HOST:zenith-upload/dist/"
rsync -az --delete -e "ssh -i $KEY" deploy/Caddyfile deploy/compose.yaml "$HOST:zenith-upload/deploy/"
if [ -n "${GATEWAY_FRAGMENT:-}" ]; then rsync -az -e "ssh -i $KEY" "$GATEWAY_FRAGMENT" "$HOST:zenith-upload/deploy/gateway.caddy"; fi
ssh -i "$KEY" "$HOST" "STAMP=$STAMP GATEWAY_NETWORK=$GATEWAY_NETWORK bash -s" <<'REMOTE'
set -euo pipefail
R=/opt/neon-zenith
sudo mkdir -p $R/releases $R/deploy
# unchanged files are hard links into the previous release, so a release costs only what changed; created as
# root to match the earlier releases
PREV=$(readlink -e $R/current || true)
sudo rsync -a --no-owner --no-group ${PREV:+--link-dest=$PREV/} ~/zenith-upload/dist/ $R/releases/$STAMP/
sudo cp ~/zenith-upload/deploy/Caddyfile $R/deploy/
[ -f ~/zenith-upload/deploy/gateway.caddy ] && sudo cp ~/zenith-upload/deploy/gateway.caddy $R/deploy/
sudo cp ~/zenith-upload/deploy/compose.yaml $R/compose.yaml
sudo ln -sfn releases/$STAMP $R/current
sudo chown -R root:root $R
sudo chmod -R a+rX $R
# the bind mount resolves `current` when the container starts
cd $R && sudo env GATEWAY_NETWORK=$GATEWAY_NETWORK docker compose up -d --force-recreate
for i in $(seq 1 30); do sudo docker exec neon-zenith wget -q -O - http://127.0.0.1:8080/healthz 2>/dev/null && break; sleep 1; done
echo
echo "released $STAMP"
REMOTE
if [ -n "${SITE:-}" ]; then curl -fsS -o /dev/null -w "live %{http_code}\n" "$SITE"; fi
