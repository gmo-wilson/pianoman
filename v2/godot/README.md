# Piano Timer v2 — Godot kiosk

Godot **4.3 or newer**, Compatibility renderer. Open `project.godot` in the editor.

## Running on your Mac against the backend
1. Start the backend (see `../backend`): `PIANO_DATA_DIR=./data uvicorn app.main:app --port 8080`
2. In Godot press F5. The kiosk talks to `http://127.0.0.1:8080` by default.
   To point at the Pi instead: run with `PIANO_API_BASE=http://raspberrypi.local:8080`, or create
   `user://kiosk.cfg` with `[api]\nbase_url="http://raspberrypi.local:8080"`.
3. Plug in a USB MIDI keyboard — Godot opens all MIDI inputs automatically.

## Structure
| Path | Role |
|---|---|
| `autoload/Updater.gd` | mounts `user://main.pck` at boot; downloads new releases (**first autoload — keep stable**) |
| `autoload/App.gd` | settings, students, buddy statuses, the practice session state machine, palette |
| `autoload/Api.gd` | async HTTP → backend |
| `autoload/Midi.gd` | `InputEventMIDI` → signals, chord detection, hot-plug |
| `autoload/BuddyLib.gd` | sprite manifest sync → `SpriteFrames` cache (placeholder when no art) |
| `autoload/Router.gd` | screen transitions (`slide_left/right`, `zoom`, `fade`) + back stack |
| `ui/theme/ThemeBuilder.gd` | the Theme, built in code: `PrimaryButton`, `GhostButton`, `DangerButton`, `Card`, `Surface`, `Pill`, label variations `Title/Heading/Body/Caption/Timer/Huge` |
| `components/` | `Buddy` (AnimatedSprite2D state machine), `TimerRing`, `MiniPiano` |
| `screens/` | `Select`, `Session`, `Recap`, `Lessons`, `BuddyDetail` — layouts are built in `_ready()` |

Screens receive parameters through `setup(params)` (called before `_ready`), e.g. `Router.go("BuddyDetail", {"student": s})`.

## Fonts
Drop any `.ttf`/`.otf` into `ui/fonts/` — it is picked up automatically (upright file preferred; a variable font gets weight 600 for text and 800 for titles). Without one, Godot's default font is used. Variable fonts render fine on the Pi; if text looks heavy, lower `UI_WEIGHT` in `ThemeBuilder.gd`.

## Exporting
- **Full build** preset → `deploy/build/piano-timer.arm64` + `piano-timer.arm64.pck` (install once on the Pi).
- **Content only** preset → `deploy/build/main.pck`. Upload it in the admin → *Releases*. Kiosks pick it up on the next idle check (every 15 min) or on reboot.

Because `Updater.gd` mounts the pck with `replace_files = true` *before* the other autoloads load, everything except `Updater.gd` and `project.godot` is hot-updatable.
