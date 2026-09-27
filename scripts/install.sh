#!/usr/bin/env bash
#
# One-command install on a fresh Raspberry Pi (DietPi, Python 3.11+).
# Creates a venv, installs dependencies, copies .env.example → .env, and
# installs a systemd unit. Run as root (or with sudo).
#
#   sudo bash scripts/install.sh
#
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$APP_DIR/.venv"
SERVICE_NAME="home-voice-assistant"
PORT="${PORT:-8000}"

echo "==> Installing Home Voice Assistant into $APP_DIR"

# 1. Python venv
if [ ! -x "$VENV/bin/python" ]; then
  echo "==> Creating virtualenv"
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$APP_DIR/requirements.txt"

# 2. .env
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  echo "==> Created $APP_DIR/.env — EDIT IT with your keys, then re-run this script."
else
  echo "==> $APP_DIR/.env already exists — leaving it untouched"
fi

# 3. systemd unit
UNIT="/etc/systemd/system/$SERVICE_NAME.service"
cat > "$UNIT" <<EOF
[Unit]
Description=Home Voice Assistant (FastAPI + uvicorn)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$VENV/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl restart "$SERVICE_NAME"

echo
echo "==> Done. The assistant is served on http://<pi-ip>:$PORT"
echo "==> Check it with:  curl http://localhost:$PORT/api/health"
echo "==> Logs:           journalctl -u $SERVICE_NAME -f"
