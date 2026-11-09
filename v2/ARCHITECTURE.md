# Piano Timer v2 — Architecture & Refactoring Plan

Target: Raspberry Pi 4 + 7" touchscreen (800×480), USB MIDI piano.
Stack: **Godot 4.x (Compatibility / GLES3)** kiosk front-end · **FastAPI + SQLite** backend on the Pi · **dependency-free admin web app** · **Python MIDI service** (mido) for MIDI output.

---

## 1. Why this shape

| Pain in v1 | v2 answer |
|---|---|
| tkinter redraws, no transitions, hand-rolled touch scroll | Godot `Control` UI with Tween/AnimationPlayer transitions, native touch, 60 fps on Pi 4 with the Compatibility renderer |
| 1,500-line software-3D tamagotchi | 2D `AnimatedSprite2D` fed by sprite sheets the admin uploads |
| Data lives as JSON *inside the code folder* → any update risks records | Data lives in `/var/lib/piano-timer/` (SQLite + sprite files), owned by the backend; the app code folder is disposable |
| Updating = ssh + edit files | Backend serves a **release manifest**; Godot downloads a new `.pck` and reloads. Backend updates via `git pull` + `systemctl restart` through `update.sh` |
| Admin dashboard is one 4,200-line HTML file | Modular SPA (vanilla JS modules, no build step) served by the backend |

---

## 2. Components

```
┌──────────────── Raspberry Pi ───────────────────────────────────┐
│                                                                 │
│  Godot kiosk (piano-kiosk.service)        Admin browser (LAN /  │
│   ├─ MIDI IN  (InputEventMIDI, ALSA)       Tailscale)           │
│   ├─ HTTP  ───────────────┐                   │                 │
│   └─ loads main.pck from  │                   │                 │
│      user:// (updatable)  ▼                   ▼                 │
│                 FastAPI backend :8080  (piano-backend.service)  │
│                   ├─ REST /api/v1/...                           │
│                   ├─ static /admin  (SPA)                       │
│                   ├─ /files/sprites/...  /files/releases/...    │
│                   └─ MIDI OUT service (mido): metronome,        │
│                      song playback, sequencing — in-process     │
│                            │                                    │
│                            ▼                                    │
│            /var/lib/piano-timer/  (DATA — never touched by      │
│              ├─ piano.db          updates)                      │
│              ├─ sprites/<set>/<level>/{atlas.png, frames.json}  │
│              ├─ songs/*.mid                                     │
│              └─ releases/<version>/main.pck + manifest.json     │
└─────────────────────────────────────────────────────────────────┘
```

**MIDI direction split.** Godot reads the piano directly (`OS.open_midi_inputs()`) for zero-latency note display and practice-time detection. Everything that *sends* MIDI (metronome click, lesson/song playback) lives in the backend's MIDI service, because Godot has no MIDI output. Godot sends high-level commands (`play song X at 0.8×`, `metronome on 80 bpm`) and polls `/api/v1/player/status`; the service does its own tight-loop sequencing exactly as v1's `Player`/`MetronomeRunner` did.

---

## 3. Data model (SQLite)

```
students        id, name, color, avatar_set, sort_order, active
settings        key, value(json)                     -- goal_minutes, metronome bpms, inactivity…
practice_days   student_id, date, seconds, completed  -- replaces progress.json {date,time,history}
sessions        id, student_id, started_at, ended_at, duration_s, practice_s,
                total_notes, goal_reached, lesson_id, events(json blob, gz)
lessons         id, name, chords(json), midi_events(json), source_song_id, created_at
songs           id, title, composer, filename, duration_s, notes_count, chords(json), midi_events(json)
sprite_sets     id, name, is_default
sprite_levels   id, set_id, level(position, 1..N), display_name, color, atlas_path, frames_path, etag, updated_at
releases        version, pck_path, sha256, notes, created_at, is_current
```

`practice_days` is the one that matters for buddy rules. v1's `progress.json` (`{date,time,history[]}`) maps 1:1: `history[]` → rows with `completed=1`; today's `{date,time}` → a row with `seconds`.

**The road** (`backend/app/buddy.py`, stateless, from `practice_days`): each completed day = +1 step, each missed day since the first practice = −1 step (floor 0); every `road.steps_per_level` steps (default 3) is a milestone = the next evolution, capped at the set's level count. Reaching a milestone today → `evolved_today` (the Recap plays the transformation); dropping below one → `devolved`. Moods are gone.

---

## 4. Sprite pipeline

Levels are an editable ladder per **sprite set** (add, rename, recolour, reorder, delete; `level = min(N, streak+1)`).

A level's art is **one sheet per animation**, uploaded separately — which matches AI sprite generators and simple
exporters that produce one animation at a time:

| animation | required | used for | falls back to |
|---|---|---|---|
| `idle` | ✔ | front view, at rest everywhere | — |
| `dance` | | celebrations: step gained, milestone transformation | idle |
| `run` | | Runner run cycle | dance → idle |
| `jump` | | Runner jump (plays once) | run → idle |

Accepted JSON: generator grids (`frames: {"0": {x,y,w,h,duration,trim}}, meta.fps`) — duration counted in frames at
`meta.fps`, frames cropped to the union of their `trim` boxes (+2 px) so a small character on a big canvas renders
tight and stable; Aseprite/TexturePacker array or hash (`duration` in ms); a **tagged** Aseprite sheet is split into
its known tags. Each upload is normalised to `sprites/<set>/<level_id>/<anim>/{atlas.png, frames.json}`
(`{loop, fps, frames:[{x,y,w,h,ms}]}`), stored in `sprite_animations`, and exposed by
`GET /api/v1/sprites/manifest` → `levels[].animations{name → atlas_url, frames_url, etag, frame_h}`.

Godot (`BuddyLib`) downloads what changed into `user://sprites/`, builds one `SpriteFrames` per level (one texture per
animation, missing names aliased along the fallback chain) and `Buddy` normalises the idle frame to 96 px tall; the milestone transformation is a Godot effect between two levels' idle sprites (no sheet needed), so art
of any resolution looks the same size on screen.

---

## 4b. Runner mini-game

Chrome-dino style runner played with the student's own buddy sprite (`screens/Runner.gd`): tap, Space or **any piano key** jumps; obstacles are metronomes/notes; speed ramps with distance; score = distance/10.

Rules are **server-side** (`backend/app/game.py`), so the kiosk only plays and posts scores:
- Unlocks when today's goal is finished (switch to "only on evolution" by changing `unlocked` in `game.credits`).
- `runs_per_day` base runs (default 3). After the last one, the backend records the seconds practised so far as an **anchor**; practising `bonus_minutes` (default 10) more unlocks **one bonus run**. The kiosk drives this as a "bonus session" (Session screen shows the target, jumps back into the Runner when reached).
- `game_runs` keeps every run; leaderboard = best score per student for all time / this week / today. Admin can delete runs, restore credits, change the rules.

---

## 5. Update strategy

**Rule: code is replaceable, `/var/lib/piano-timer` is sacred.** Nothing in the app folders ever stores records.

1. **Godot content (hot):** export the project as a `.pck` only. Upload it in the admin → *Releases*. On boot (and every N minutes while idle on the select screen) the kiosk checks `/api/v1/releases/current`; if the sha differs from `user://current.pck`, it downloads, verifies sha256, swaps, and `get_tree().reload_current_scene()` → `ProjectSettings.load_resource_pack()` applies. Rollback = mark the previous release current in the admin.
2. **Backend/admin/MIDI service:** `deploy/update.sh` does `git pull --ff-only` in the code folder, `pip install -r requirements.txt`, runs DB migrations (`alembic`-free: numbered SQL files in `backend/migrations/`), and restarts `piano-backend.service`. It can be triggered from the admin (*Settings → Update*) or over SSH/Tailscale.
3. **Godot engine binary:** rare; swap the arm64 binary in `/opt/piano-timer/godot/` via the same script.
4. **Backups:** nightly `sqlite3 .backup` + tar of `sprites/` to `/var/lib/piano-timer/backups/` (cron line in `deploy/`). Optional rclone to cloud.

---

## 6. Godot project layout

```
godot/
  project.godot            Compatibility renderer, 800×480, stretch canvas_items/expand, touch emulation
  autoload/
    App.gd                 global state (current student, session, settings), signals
    Api.gd                 HTTPRequest wrapper → backend, JSON in/out, retry
    Midi.gd                OS.open_midi_inputs(), InputEventMIDI → note_on/note_off signals, idle detection
    Router.gd              push/replace screens with transitions (slide, fade, scale), back stack
    BuddyLib.gd            sprite manifest sync + SpriteFrames cache
    Updater.gd             pck release check / download / swap
  ui/theme/                Theme resource, fonts, StyleBoxFlat pills, colors matching v1 palette
  screens/
    Select.tscn/.gd        student cards with live buddies
    Session.tscn/.gd       timer ring, mini piano, chord grid, metronome, lesson playback controls
    Recap.tscn/.gd         apple → feed → dance → evolve
    Lessons.tscn/.gd       list + record
    BuddyDetail.tscn/.gd   stats
    Runner.tscn/.gd        mini-game
    Leaderboard.tscn/.gd   best run per student
  components/
    Buddy.tscn/.gd         AnimatedSprite2D state machine
    PillButton.tscn        themed Button with press scale tween
    TimerRing.gd           _draw() arc
    MiniPiano.gd           _draw() keys, highlights
  main.tscn                boots Updater → Router.go("Select")
```

---

## 7. Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Decisions (this doc) | ✔ |
| 1 | Backend + migration + admin shell | `migrate_v1.py` imports your JSON; admin lists students/sessions; buddy status matches v1 |
| 2 | Godot shell: Select ↔ Session ↔ Recap with transitions, MIDI in, timer, progress saved via API | A practice session end-to-end on the Pi |
| 3 | Sprite pipeline: upload in admin → buddy animates in Godot | Level 1 placeholder set live |
| 4 | Lessons, songs, metronome via MIDI service | Parity with v1 |
| 5 | Releases: pck hot-update + `update.sh`; systemd kiosk | Update from admin without touching records |
| 6 | Runner mini-game + leaderboard (credits, bonus run) | A finished practice offers 3 runs; 4th after 10 extra minutes |
| 7 | Polish: celebration, recap, idle/sleep, stats | Replace v1 |

Run v1 and v2 side by side during phases 1–4 (different ports/services); switch the autostart in phase 5.
