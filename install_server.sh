#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/task-reminder-bot"
SERVICE="task-reminder-bot"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash install_server.sh" >&2
  exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Debian/Ubuntu (apt-get)." >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip ca-certificates
id -u taskbot >/dev/null 2>&1 || useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin taskbot
mkdir -p "$APP_DIR"
cp -a bot.py config.py requirements.txt "$APP_DIR/"
if [[ -f tasks.json && ! -f "$APP_DIR/tasks.json" ]]; then cp tasks.json "$APP_DIR/tasks.json"; fi
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
chown -R taskbot:taskbot "$APP_DIR"
chmod 700 "$APP_DIR"
chmod 600 "$APP_DIR/config.py"

cat >/etc/systemd/system/${SERVICE}.service <<EOF
[Unit]
Description=Telegram task reminder bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=taskbot
Group=taskbot
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/bot.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=${APP_DIR}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
cat <<'MSG'
Installed files and dependencies. Next:
  nano /opt/task-reminder-bot/config.py
Paste the NEW token, save, then run:
  systemctl enable --now task-reminder-bot
  systemctl status task-reminder-bot --no-pager
Logs:
  journalctl -u task-reminder-bot -f
MSG
