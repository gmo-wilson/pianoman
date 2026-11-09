#!/usr/bin/env bash
# Kiosk launcher, started by the desktop session (XDG autostart) — works on wayfire, labwc and X11/LXDE alike.
# Waits for a display and the backend, then keeps the Godot kiosk running (restart on crash/exit).
# Logs: /var/lib/piano-timer/backups/kiosk.log
GODOT_DIR="${GODOT_DIR:-/opt/piano-timer/godot}"
BIN="$GODOT_DIR/piano-timer.arm64"
LOG=/var/lib/piano-timer/backups/kiosk.log
export PIANO_API_BASE="${PIANO_API_BASE:-http://127.0.0.1:8080}"

mkdir -p "$(dirname "$LOG")" 2>/dev/null
exec >>"$LOG" 2>&1
echo "=== kiosk.sh start $(date -Is) WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} DISPLAY=${DISPLAY:-}"

# single instance
exec 9>/tmp/piano-kiosk.lock
flock -n 9 || { echo "already running"; exit 0; }

# wait for a display (up to 60 s)
for i in $(seq 1 60); do
  [ -n "${WAYLAND_DISPLAY:-}" ] || [ -n "${DISPLAY:-}" ] && break
  sleep 1
done

# wait for the backend (up to 60 s) so the first screen isn't "offline"
for i in $(seq 1 60); do
  curl -fs "$PIANO_API_BASE/api/v1/health" >/dev/null && break
  sleep 1
done

while true; do
  if [ ! -x "$BIN" ]; then
    echo "kiosk binary missing: $BIN — retrying in 30 s"
    sleep 30
    continue
  fi
  echo "launch $(date -Is)"
  "$BIN" --rendering-driver opengl3_es --fullscreen
  code=$?
  echo "kiosk exited with $code at $(date -Is)"
  # exit code 0 = deliberate quit/updater restart → relaunch fast; crash → brief pause
  [ "$code" -eq 0 ] && sleep 1 || sleep 3
done
