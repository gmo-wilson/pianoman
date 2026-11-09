#!/usr/bin/env bash
# Consistent SQLite backup + sprites/songs tarball. Keeps the last 30.
set -euo pipefail
DATA_DIR="${PIANO_DATA_DIR:-/var/lib/piano-timer}"
OUT="$DATA_DIR/backups"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$OUT"
sqlite3 "$DATA_DIR/piano.db" ".backup '$OUT/piano-$STAMP.db'"
tar -czf "$OUT/files-$STAMP.tgz" -C "$DATA_DIR" sprites songs 2>/dev/null || true
ls -1t "$OUT"/piano-*.db | tail -n +31 | xargs -r rm -f
ls -1t "$OUT"/files-*.tgz | tail -n +31 | xargs -r rm -f
echo "backup ok: $OUT/piano-$STAMP.db"
# Optional off-site copy (install rclone and configure a remote named "backup"):
# rclone copy "$OUT" backup:piano-timer-backups --max-age 2d
