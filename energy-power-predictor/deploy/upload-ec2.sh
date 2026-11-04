#!/usr/bin/env bash
# Usage: EC2_HOST=... EC2_KEY=... bash deploy/upload-ec2.sh
# Or resolve an existing EC2 through AWS CLI: EC2_INSTANCE_ID=i-... EC2_KEY=...
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${EC2_KEY:?Set path to existing private key}"
user=${EC2_USER:-ubuntu}
host=${EC2_HOST:-}
if [ -z "$host" ]; then
  : "${EC2_INSTANCE_ID:?Set EC2_HOST or existing EC2_INSTANCE_ID}"
  host=$(aws ec2 describe-instances --region "${AWS_REGION:-ap-northeast-2}" --instance-ids "$EC2_INSTANCE_ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
fi
[[ "$host" =~ ^[a-zA-Z0-9.-]+$ && "$host" != None ]] || exit 1
[[ "$user" =~ ^[a-zA-Z0-9_-]+$ ]] || exit 1
revision=$(git rev-parse HEAD)
archive=$(mktemp)
trap 'rm -f "$archive"' EXIT
git archive --format=tar.gz HEAD > "$archive"
# Strict host verification: register/verify server fingerprint before first use.
scp -o StrictHostKeyChecking=yes -i "$EC2_KEY" "$archive" "$user@$host:/tmp/energy-release-$revision.tar.gz"
ssh -o StrictHostKeyChecking=yes -i "$EC2_KEY" "$user@$host" bash -s -- "$revision" <<'REMOTE'
set -euo pipefail
revision="$1"
release="$HOME/energy-releases/$revision"
mkdir -p "$release"
tar -xzf "/tmp/energy-release-$revision.tar.gz" -C "$release"
cd "$release"
DEPLOY_REVISION="$revision" bash energy-power-predictor/deploy/deploy-ec2.sh
REMOTE
curl -fsS --max-time 15 "http://$host/_stcore/health"
