#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sudo install -d -m 755 /usr/local/lib/energy-operations
sudo install -m 644 log_bridge.py poll_deploy.py /usr/local/lib/energy-operations/
sudo install -m 644 energy-log-bridge.service energy-log-bridge.timer energy-auto-deploy.service energy-auto-deploy.timer /etc/systemd/system/
sudo install -m 644 energy-predictor-logrotate /etc/logrotate.d/energy-predictor
sudo systemctl daemon-reload
sudo systemctl start energy-log-bridge.service
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c "file:$PWD/cloudwatch-agent.json" -s
sudo systemctl enable amazon-cloudwatch-agent
sudo systemctl enable --now energy-log-bridge.timer energy-auto-deploy.timer
