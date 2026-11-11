#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec 9>/tmp/energy-predictor-deploy.lock
flock -n 9 || { echo 'Another deployment is running'; exit 1; }
revision=${DEPLOY_REVISION:-$(git rev-parse HEAD)}
[[ "$revision" =~ ^[a-zA-Z0-9_.-]+$ ]] || exit 1
export ENERGY_IMAGE="energy-predictor:$revision"
if ! docker info >/dev/null 2>&1; then
  docker() { sudo --preserve-env=ENERGY_IMAGE,ENERGY_UI_PORT docker "$@"; }
fi
envfile="$HOME/.config/energy-predictor/container.env"
test -f "$envfile" || { echo 'Provision private container.env before deployment'; exit 1; }
config=/etc/nginx/sites-available/default
active=$(sudo sed -n 's/.*proxy_pass http:\/\/127.0.0.1:\(850[12]\);.*/\1/p' "$config")
case "$active" in
  8501) export ENERGY_UI_PORT=8502; slot=green ;;
  8502) export ENERGY_UI_PORT=8501; slot=blue ;;
  *) echo 'Unknown nginx upstream; refusing to change service'; exit 1 ;;
esac
compose=(docker compose -p "energy-$slot" --env-file "$envfile" -f deploy/compose.ec2.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" build app
docker run --rm "$ENERGY_IMAGE" python -m unittest test_retraining test_feedback_preparation test_host_operations test_feedback_log test_appliance_plan test_laundry test_device_forecast test_verification test_api test_verification_ui test_improvements
# Shared SQLite requires compatible schema; migrations must be planned separately.
docker volume inspect energy-predictor_history >/dev/null
sudo nginx -t
backup=$(mktemp)
sudo cat "$config" > "$backup"
switched=false
complete=false
cleanup() {
  status=$?
  if [ "$complete" != true ]; then
    if [ "$switched" = true ]; then
      sudo cp "$backup" "$config"
      sudo nginx -t && sudo systemctl reload nginx
    fi
    "${compose[@]}" stop app || true
  fi
  rm -f "$backup"
  exit "$status"
}
trap cleanup EXIT
# Retire the initial legacy container only when its port is inactive.
if [ "$active" = 8502 ] && docker container inspect energy-predictor-app-1 >/dev/null 2>&1; then
  docker stop energy-predictor-app-1 >/dev/null
fi
# Only the inactive slot is replaced. The active service keeps serving requests.
"${compose[@]}" up -d --wait --wait-timeout 120
curl -fsS --max-time 15 "http://127.0.0.1:$ENERGY_UI_PORT/_stcore/health"
docker exec "energy-$slot-app-1" python deploy/healthcheck.py
switched=true
sudo python3 - "$config" "$active" "$ENERGY_UI_PORT" <<'NGINX'
import sys
from pathlib import Path
p=Path(sys.argv[1]);s=p.read_text()
old='proxy_pass http://127.0.0.1:'+sys.argv[2]+';'
assert s.count(old)==1, 'Unexpected upstream config'
p.write_text(s.replace(old,'proxy_pass http://127.0.0.1:'+sys.argv[3]+';'))
NGINX
sudo nginx -t
sudo systemctl reload nginx
curl -fsS --max-time 15 http://127.0.0.1/_stcore/health
complete=true
"${compose[@]}" ps
printf '\nActive slot=%s port=%s revision=%s. Previous slot retained for open sessions.\n' "$slot" "$ENERGY_UI_PORT" "$revision"
