#!/usr/bin/env bash
# Update backend + admin from git, apply DB migrations, restart the service.
# Triggered from the admin (Settings → Update backend) or by hand over SSH/Tailscale.
# Data in $PIANO_DATA_DIR is never touched.
set -euo pipefail
CODE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG=/var/lib/piano-timer/backups/update.log
exec >>"$LOG" 2>&1
echo "=== update $(date -Is)"

cd "$CODE_DIR"
bash "$CODE_DIR/deploy/backup.sh" || true            # snapshot before touching anything
git fetch --all --prune
git pull --ff-only
"$CODE_DIR/backend/.venv/bin/pip" install -q -r "$CODE_DIR/backend/requirements.txt"
# migrations run automatically at backend start (app/db.py); a dry run here surfaces errors early
(cd backend && PIANO_DATA_DIR="${PIANO_DATA_DIR:-/var/lib/piano-timer}" .venv/bin/python -c "from app import db; print('schema ok, applied:', db.migrate(db.connect()))")
sudo -n /bin/systemctl restart piano-backend.service || true
echo "=== done"
