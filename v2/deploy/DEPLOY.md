# Deploying Piano Timer v2 to the Raspberry Pi

Target: Raspberry Pi 4/5, **Raspberry Pi OS Bookworm 64-bit with desktop**, 7" touchscreen, USB MIDI piano.
Everything below is done once; afterwards updates ship from the admin (see §5).

---

## 1. Prepare the Pi (5 min)

```bash
sudo raspi-config
```
- *System Options → Boot / Auto Login* → **Desktop Autologin** (the kiosk runs inside the desktop session).
- *Display Options → Screen Blanking* → **Disable** (install.sh also does this). The app turns the screen off itself: after 60 s idle or when the piano is off, waking on touch / key / power-on (admin → Settings → Screen sleep).
- Optional but recommended: *Interface Options → SSH* → Enable, so you can manage it from the Mac.

Give the Pi a fixed hostname (e.g. `piano`) so the admin is always at `http://piano.local:8080/admin`:
*System Options → Hostname*.

## 2. Get the code onto the Pi

```bash
cd ~
git clone <your repo URL> "Piano timer"      # or scp the folder; keep v1 (pi/) inside — install.sh imports its records
cd "Piano timer"
sudo bash v2/deploy/install.sh
```
`install.sh` installs system packages, creates the backend venv, **imports your v1 students/lessons/songs into
`/var/lib/piano-timer/piano.db` (only on the very first run)**, installs and starts `piano-backend.service`,
installs the kiosk autostart entry, the sudoers rule for the admin "Update" button, and a nightly backup.

Check: `http://<pi-ip>:8080/admin` loads and the sidebar says `piano ✓ <your keyboard>` once the piano is plugged in.

## 3. Export the kiosk from your Mac

In Godot (4.3+), once per machine: *Editor → Manage Export Templates → Download and Install*.

Then *Project → Export…*:
1. Preset **"Linux arm64 (Pi) — full build"** → *Export Project* → produces `v2/deploy/build/piano-timer.arm64`
   and `piano-timer.arm64.pck`.
2. (Later, for hot updates) Preset **"Content only (.pck) — hot update"** → *Export PCK/Zip* → `main.pck`.

Or from a terminal (no editor UI):
```bash
cd v2/godot
godot --headless --export-release "Linux arm64 (Pi) — full build" ../deploy/build/piano-timer.arm64
godot --headless --export-pack    "Content only (.pck) — hot update" ../deploy/build/main.pck
```

Copy the full build to the Pi and enable the kiosk:
```bash
scp v2/deploy/build/piano-timer.arm64 v2/deploy/build/piano-timer.arm64.pck pi@piano.local:/opt/piano-timer/godot/
ssh pi@piano.local 'sudo bash ~/Piano\ timer/v2/deploy/install.sh'      # re-run: now finds the binary and enables the service
```
The kiosk starts on every boot right after the desktop logs in (XDG autostart → `deploy/kiosk.sh`, which waits for the backend and relaunches the UI if it ever exits). To start it right away without rebooting: `bash ~/"Piano timer"/v2/deploy/kiosk.sh &`.

## 4. Switch off v1

If v1 autostarts, remove its line from `~/.config/lxsession/LXDE-pi/autostart` (or `~/.config/wayfire.ini` /
`~/.config/labwc/autostart` on Bookworm) and reboot. Keep the `pi/` folder for now — its JSON is your fallback
until you've seen v2 run for a few days.

## 5. Day-to-day

| Task | How |
|---|---|
| Update kiosk screens/logic | export **Content only (.pck)** → admin → *Releases* → upload, keep "make current". Kiosks apply it at the next idle check (≤15 min) or reboot. Roll back by making an older release current. |
| Update backend/admin | `git push` from the Mac, then admin → *Settings → Update backend* (runs `deploy/update.sh`: pull, pip, migrations, restart). Or over SSH: `bash v2/deploy/update.sh`. |
| New sprites, levels, students, settings | admin only — the kiosk syncs on boot and every home screen. |
| New Godot engine version | export a new **full build**, `scp` both files to `/opt/piano-timer/godot/`, then `pkill -f piano-timer.arm64` (kiosk.sh relaunches it). |
| Backups | nightly to `/var/lib/piano-timer/backups/` (30 kept). Off-site: install `rclone`, configure a remote named `backup`, uncomment the last line of `deploy/backup.sh`. |
| Remote access away from home | install Tailscale on the Pi and your Mac; the admin is then at `http://piano:8080/admin` from anywhere. Set `PIANO_ADMIN_TOKEN` in `/etc/systemd/system/piano-backend.service` and paste it in *Settings → Admin token*. |

## 6. Useful commands on the Pi

```bash
journalctl -u piano-backend -f                 # backend log
tail -f /var/lib/piano-timer/backups/kiosk.log # kiosk log (Godot output)
pkill -f piano-timer.arm64                     # restart the UI (kiosk.sh relaunches it)
systemctl restart piano-backend                # restart the API
curl -s localhost:8080/api/v1/midi/ports       # what the backend sees on the MIDI bus
```

## 7. Troubleshooting

- **Kiosk never appears** → `tail -50 /var/lib/piano-timer/backups/kiosk.log`. No log at all means the desktop didn't
  run the autostart entry: check `ls ~/.config/autostart/` and that autologin to desktop is on (§1). On Bookworm's Wayland
  the binary runs through XWayland by default; to run natively add `--display-driver wayland` to the launch line in `deploy/kiosk.sh`.
- **"Backend offline" chip** → `systemctl status piano-backend`; most often a `pip install` failure for `python-rtmidi`
  (needs `libasound2-dev`, which install.sh installs).
- **Piano not detected** → `aconnect -l` shows ALSA MIDI devices. If it's listed there but not in `/api/v1/midi/ports`,
  set `PIANO_MIDI_IN=<part of its name>` in the backend service file.
- **Touch works but is offset** → the 7" display is rotated; set `display_rotate` / `lcd_rotate` in `/boot/firmware/config.txt`.
- **Performance** → the Compatibility renderer should hold 60 fps. If not, lower `window/stretch` to `viewport` in
  `project.godot` or reduce sprite sheet sizes (≤1024 px atlases).
