#!/usr/bin/env bash
set -euo pipefail
# Run on EC2 from a checkout of the commit being deployed.
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo 'Install Docker Engine and Compose first'; exit 1; }
if ! docker info >/dev/null 2>&1; then
  docker() { sudo --preserve-env=ENERGY_IMAGE docker "$@"; }
fi
docker compose version >/dev/null
exec 9>/tmp/energy-predictor-deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
revision=${DEPLOY_REVISION:-$(git rev-parse HEAD)}
export ENERGY_IMAGE="energy-predictor:$revision"
envfile="$HOME/.config/energy-predictor/container.env"
mkdir -p "$(dirname "$envfile")"
if [ ! -f "$envfile" ]; then
  (umask 077; printf 'PREDICTION_API_TOKEN=%s\n' "$(openssl rand -hex 32)" > "$envfile")
fi
compose=(docker compose --env-file "$envfile" -f deploy/compose.ec2.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" build app
# Fail before changing the existing application unless Nginx is configured.
sudo nginx -t
# Stop legacy services only after the new image was built successfully.
sudo systemctl stop energy-predictor energy-api || true
if ! "${compose[@]}" up -d --wait --wait-timeout 120; then
  "${compose[@]}" logs --tail 80 app
  "${compose[@]}" stop app
  sudo systemctl start energy-api energy-predictor || true
  exit 1
fi
curl --fail --max-time 15 http://127.0.0.1:8501/_stcore/health
curl --fail --max-time 15 http://127.0.0.1/_stcore/health
sudo systemctl disable energy-predictor energy-api || true
"${compose[@]}" ps
printf '\nDeployed commit: %s\n' "$revision"
