#!/usr/bin/env bash
# Install the agent as a systemd service. Run as root from the project folder:
#   sudo ./deploy/install.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run as root (sudo)."; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/aiops-agent

id aiops &>/dev/null || useradd --system --home-dir "$APP" --shell /usr/sbin/nologin aiops
mkdir -p "$APP"
cp -r "$SRC/aiops_agent" "$SRC/requirements.txt" "$APP/"
[ -f "$APP/config.yaml" ] || cp "$SRC/config.yaml" "$APP/config.yaml"   # keep your edits on upgrade
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R root:aiops "$APP"; chmod -R g+rX,o-rwx "$APP"

if [ ! -f /etc/aiops-agent.env ]; then
  install -m 600 -o root -g root "$SRC/deploy/aiops-agent.env.example" /etc/aiops-agent.env
  echo ">> Edit /etc/aiops-agent.env (LLM key + notification channels), then re-run this script."
  exit 0
fi

install -m 644 "$SRC/deploy/aiops-agent.service" /etc/systemd/system/aiops-agent.service
systemctl daemon-reload
systemctl enable --now aiops-agent
systemctl --no-pager status aiops-agent | head -n 8
echo ">> Logs: journalctl -u aiops-agent -f"
