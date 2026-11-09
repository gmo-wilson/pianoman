# Piano Timer v2

Godot kiosk + FastAPI/SQLite backend + admin web app. See **ARCHITECTURE.md** for the why and the roadmap.
v1 (`../pi`) keeps working untouched; run both side by side until v2 reaches parity.

```
v2/
  backend/   FastAPI app, SQLite schema + migrations, v1 importer, MIDI-out service, tests
  admin/     dependency-free admin SPA (served by the backend at /admin)
  godot/     Godot 4.3+ project (Compatibility renderer)
  deploy/    install.sh, systemd units, update.sh, backup.sh
```

## 1. Try it on your Mac (10 minutes)

```bash
cd v2/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest -v                                  # 19 tests, stdlib only
PIANO_DATA_DIR=./data python3 migrate_v1.py ../../pi     # imports Eva/Mara/Willy, lessons, songs
PIANO_DATA_DIR=./data uvicorn app.main:app --reload --port 8080
```
Open http://localhost:8080/admin → *Sprites → Generate placeholders* to get art for all 32 levels.

Then open `v2/godot/project.godot` in Godot 4.3+ and press F5. Plug in a USB MIDI keyboard; the Select screen shows the buddies, *Practice* starts a session, the ring fills while you play.

## 2. Install on the Pi

Follow **`deploy/DEPLOY.md`** — prepare the Pi (desktop autologin), clone, `sudo bash v2/deploy/install.sh`, export the Godot build from your Mac, copy it to `/opt/piano-timer/godot/`, re-run install.sh. The kiosk then starts on every boot.

## 3. Updating later, without losing records

| What changed | How it ships |
|---|---|
| Godot screens, art, logic | export *Content only (.pck)* → admin *Releases* → kiosks pick it up when idle |
| Backend / admin / MIDI service | admin *Settings → Update backend* (or `bash deploy/update.sh` over SSH) |
| Buddy sprites | admin *Sprites* — no release needed, kiosks sync the manifest on boot and on each Select screen |
| Godot engine binary | copy a new `piano-timer.arm64` to `/opt/piano-timer/godot/`, restart the kiosk service |

Records (`/var/lib/piano-timer/piano.db`) are backed up nightly to `/var/lib/piano-timer/backups/`.
Schema changes are numbered SQL files in `backend/migrations/` and apply automatically on start.
