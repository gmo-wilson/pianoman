#!/usr/bin/env bash
# One-time install on the Raspberry Pi (Raspberry Pi OS Bookworm 64-bit, desktop image).
#   sudo bash v2/deploy/install.sh
# Idempotent: safe to run again after a git pull.
set -euo pipefail

APP_USER="${SUDO_USER:-pi}"
APP_HOME="$(getent passwd "$APP_USER" | cut -d: -f6)"
CODE_DIR="$(cd "$(dirname "$0")/.." && pwd)"          # .../v2
DATA_DIR=/var/lib/piano-timer
GODOT_DIR=/opt/piano-timer/godot

echo "==> user:  $APP_USER"
echo "==> code:  $CODE_DIR"
echo "==> data:  $DATA_DIR  (records live here; updates never touch it)"

# ---- packages
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip libasound2-dev libjack-dev sqlite3 git curl \
    libgl1-mesa-dri libgles2 libxi6 libxcursor1 libxinerama1 libxrandr2 libxkbcommon0 libpulse0 libwayland-client0 libdecor-0-0

install -d -o "$APP_USER" -g "$APP_USER" "$DATA_DIR" "$DATA_DIR"/{sprites,songs,releases,backups} "$GODOT_DIR"

# ---- backend venv
if [ ! -d "$CODE_DIR/backend/.venv" ]; then
  sudo -u "$APP_USER" python3 -m venv "$CODE_DIR/backend/.venv"
fi
sudo -u "$APP_USER" "$CODE_DIR/backend/.venv/bin/pip" install -q --upgrade pip
sudo -u "$APP_USER" "$CODE_DIR/backend/.venv/bin/pip" install -q -r "$CODE_DIR/backend/requirements.txt"

# ---- import v1 data once (only if the database doesn't exist yet)
if [ ! -f "$DATA_DIR/piano.db" ] && [ -d "$CODE_DIR/../pi" ]; then
  echo "==> importing v1 records from $CODE_DIR/../pi"
  (cd "$CODE_DIR/backend" && sudo -u "$APP_USER" PIANO_DATA_DIR="$DATA_DIR" .venv/bin/python migrate_v1.py "$CODE_DIR/../pi")
fi

# ---- backend: system service
sed -e "s#__CODE_DIR__#$CODE_DIR#g" -e "s#__DATA_DIR__#$DATA_DIR#g" -e "s#__USER__#$APP_USER#g" \
    "$CODE_DIR/deploy/piano-backend.service" > /etc/systemd/system/piano-backend.service
systemctl daemon-reload
systemctl enable --now piano-backend.service

# ---- let the backend restart itself from the admin "Update" button
echo "$APP_USER ALL=(root) NOPASSWD: /bin/systemctl restart piano-backend.service" > /etc/sudoers.d/piano-timer
chmod 440 /etc/sudoers.d/piano-timer

# ---- kiosk: started by the desktop session via XDG autostart (wayfire / labwc / LXDE all honour it).
#      kiosk.sh waits for the display + backend and relaunches the UI if it exits.
AUTOSTART_DIR="$APP_HOME/.config/autostart"
install -d -o "$APP_USER" -g "$APP_USER" "$AUTOSTART_DIR"
sed -e "s#__CODE_DIR__#$CODE_DIR#g" "$CODE_DIR/deploy/piano-kiosk.desktop" > "$AUTOSTART_DIR/piano-kiosk.desktop"
chown "$APP_USER:$APP_USER" "$AUTOSTART_DIR/piano-kiosk.desktop"
chmod +x "$CODE_DIR/deploy/kiosk.sh"
touch "$DATA_DIR/backups/kiosk.log"; chown "$APP_USER:$APP_USER" "$DATA_DIR/backups/kiosk.log"
# remove the older user-service variant if a previous install created it
USER_UNIT="$APP_HOME/.config/systemd/user/piano-kiosk.service"
if [ -f "$USER_UNIT" ]; then
  sudo -u "$APP_USER" XDG_RUNTIME_DIR="/run/user/$(id -u "$APP_USER")" systemctl --user disable --now piano-kiosk.service >/dev/null 2>&1 || true
  rm -f "$USER_UNIT"
fi
if [ -f "$GODOT_DIR/piano-timer.arm64" ]; then
  chmod +x "$GODOT_DIR/piano-timer.arm64"
  echo "==> kiosk autostart installed ($AUTOSTART_DIR/piano-kiosk.desktop). Start it now without rebooting:"
  echo "      bash \"$CODE_DIR/deploy/kiosk.sh\" &"
else
  echo "==> kiosk binary not found yet in $GODOT_DIR — copy the Godot export there; autostart is already in place"
fi

# ---- kiosk-friendly desktop: no screen blanking, no mouse cursor
if command -v raspi-config >/dev/null; then
  raspi-config nonint do_blanking 1 >/dev/null 2>&1 || true   # 1 = disable blanking
fi

# ---- nightly backup
cat > /etc/cron.d/piano-timer-backup <<EOF
15 3 * * * $APP_USER bash "$CODE_DIR/deploy/backup.sh" >/dev/null 2>&1
EOF

IP=$(hostname -I | awk '{print $1}')
echo
echo "Backend:  http://$IP:8080/admin"
echo "Logs:     journalctl -u piano-backend -f      tail -f $DATA_DIR/backups/kiosk.log"
