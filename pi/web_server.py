import os
import sys
import json
import time
import uuid
import threading
import mimetypes
import base64
import struct
import re
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import tamagotchi

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PROGRESS_FILE = os.path.join(BASE_DIR, "progress.json")
CLASSES_FILE = os.path.join(BASE_DIR, "classes.json")
SESSIONS_FILE = os.path.join(BASE_DIR, "sessions.json")
LIVE_STATE_FILE = os.path.join(BASE_DIR, "live_state.json")
SONGS_FILE = os.path.join(BASE_DIR, "songs.json")
SONGS_DIR = os.path.join(BASE_DIR, "songs")
COMMAND_FILE = os.path.join(BASE_DIR, "piano_command.json")
WEB_DIR = os.path.join(BASE_DIR, "web")

os.makedirs(SONGS_DIR, exist_ok=True)

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return default

def save_json(path, data):
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        print(f"Error saving {path}: {e}")
        return False

# -----------------------------------------------------------------------------
# APP IPC & DIRECT CONTROL
# -----------------------------------------------------------------------------
PIANO_APP = None

def set_piano_app(app):
    global PIANO_APP
    PIANO_APP = app

def get_piano_app():
    global PIANO_APP
    return PIANO_APP

def dispatch_piano_command(action, **kwargs):
    if PIANO_APP is not None:
        try:
            if action == "play_song":
                PIANO_APP.root.after(0, lambda: PIANO_APP.play_song(kwargs.get("song"), kwargs.get("speed", 1.0)))
            elif action == "pause":
                PIANO_APP.root.after(0, PIANO_APP.pause_song)
            elif action == "resume":
                PIANO_APP.root.after(0, PIANO_APP.resume_song)
            elif action == "stop":
                PIANO_APP.root.after(0, PIANO_APP.stop_song)
            elif action == "seek":
                PIANO_APP.root.after(0, lambda: PIANO_APP.seek_song(kwargs.get("percent", 0)))
            elif action == "speed":
                PIANO_APP.root.after(0, lambda: PIANO_APP.set_song_speed(kwargs.get("speed", 1.0)))
            return True
        except Exception as e:
            print(f"Direct app dispatch error: {e}")
    cmd = {"action": action, "processed": False, "timestamp": time.time(), **kwargs}
    save_json(COMMAND_FILE, cmd)
    return True

# -----------------------------------------------------------------------------
# MIDI PARSING & CHORD EXTRACTION HELPERS
# -----------------------------------------------------------------------------
def parse_variable_length(data, pos):
    val = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return val, pos

def parse_smf_bytes(data):
    if len(data) < 14 or data[:4] != b'MThd':
        raise ValueError("Invalid MIDI header (missing MThd)")
    header_len = struct.unpack('>I', data[4:8])[0]
    fmt, num_tracks, division = struct.unpack('>HHH', data[8:14])
    pos = 8 + header_len
    tracks_events = []
    
    for t_idx in range(num_tracks):
        if pos >= len(data) or data[pos:pos+4] != b'MTrk':
            break
        track_len = struct.unpack('>I', data[pos+4:pos+8])[0]
        track_end = pos + 8 + track_len
        t_pos = pos + 8
        pos = track_end
        abs_ticks = 0
        running_status = None
        while t_pos < track_end and t_pos < len(data):
            delta, t_pos = parse_variable_length(data, t_pos)
            abs_ticks += delta
            if t_pos >= track_end: break
            b = data[t_pos]
            if b >= 0x80:
                status = b
                t_pos += 1
                if status < 0xF0:
                    running_status = status
            else:
                status = running_status
                if status is None:
                    t_pos += 1
                    continue
            
            if status == 0xFF:
                if t_pos >= track_end: break
                meta_type = data[t_pos]
                t_pos += 1
                meta_len, t_pos = parse_variable_length(data, t_pos)
                meta_data = data[t_pos:t_pos+meta_len]
                t_pos += meta_len
                if meta_type == 0x51 and len(meta_data) == 3:
                    us_per_beat = (meta_data[0] << 16) | (meta_data[1] << 8) | meta_data[2]
                    tracks_events.append((abs_ticks, 'tempo', us_per_beat))
            elif status in (0xF0, 0xF7):
                sys_len, t_pos = parse_variable_length(data, t_pos)
                t_pos += sys_len
            else:
                event_type = status & 0xF0
                channel = status & 0x0F
                if event_type in (0x80, 0x90):
                    note = data[t_pos]
                    vel = data[t_pos+1]
                    t_pos += 2
                    is_on = (event_type == 0x90 and vel > 0)
                    tracks_events.append((abs_ticks, 'note_on' if is_on else 'note_off', note, vel, channel))
                elif event_type in (0xA0, 0xB0, 0xE0):
                    t_pos += 2
                elif event_type in (0xC0, 0xD0):
                    t_pos += 1

    tracks_events.sort(key=lambda x: x[0])
    ticks_per_beat = division if (division & 0x8000) == 0 else 480
    current_time = 0.0
    current_tick = 0
    us_per_beat = 500000
    events = []
    for ev in tracks_events:
        delta_ticks = ev[0] - current_tick
        if delta_ticks > 0:
            current_time += (delta_ticks / ticks_per_beat) * (us_per_beat / 1000000.0)
            current_tick = ev[0]
        if ev[1] == 'tempo':
            us_per_beat = ev[2]
        elif ev[1] in ('note_on', 'note_off'):
            ch = ev[4] if len(ev) > 4 else 0
            is_drum = (ch == 9)
            events.append({
                'time': round(current_time, 3),
                'type': 'on' if ev[1] == 'note_on' else 'off',
                'note': ev[2],
                'vel': ev[3] if ev[1] == 'note_on' else 0,
                'channel': ch,
                'is_drum': is_drum
            })
    return events, num_tracks

def parse_midi_file(filepath):
    try:
        import mido
        mid = mido.MidiFile(filepath)
        events = []
        cur_t = 0.0
        for msg in mid:
            cur_t += msg.time
            ch = getattr(msg, 'channel', 0)
            is_drum = (ch == 9)
            if msg.type == 'note_on':
                events.append({
                    "time": round(cur_t, 3),
                    "type": "on" if msg.velocity > 0 else "off",
                    "note": msg.note,
                    "vel": msg.velocity,
                    "channel": ch,
                    "is_drum": is_drum
                })
            elif msg.type == 'note_off':
                events.append({
                    "time": round(cur_t, 3),
                    "type": "off",
                    "note": msg.note,
                    "vel": 0,
                    "channel": ch,
                    "is_drum": is_drum
                })
        if events:
            return events, len(mid.tracks)
    except Exception:
        pass
    with open(filepath, 'rb') as f:
        data = f.read()
    return parse_smf_bytes(data)

def extract_chords_from_events(events):
    NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    CHORDS_MAP = {
        frozenset([0, 4, 7]): "",
        frozenset([0, 3, 7]): "m",
        frozenset([0, 3, 6]): "dim",
        frozenset([0, 4, 8]): "aug",
        frozenset([0, 4, 7, 10]): "7",
        frozenset([0, 4, 7, 11]): "maj7",
        frozenset([0, 3, 7, 10]): "m7",
        frozenset([0, 5, 7]): "sus4",
        frozenset([0, 2, 7]): "sus2"
    }
    active = set()
    chord_counts = {}
    last_chord = None
    for ev in events:
        if ev.get("is_drum") or ev.get("channel") == 9:
            continue
        if ev.get("type") == "on":
            active.add(ev["note"])
            if len(active) >= 3:
                pcs = set(n % 12 for n in active)
                matched = None
                for root in pcs:
                    rel = frozenset((p - root) % 12 for p in pcs)
                    if rel in CHORDS_MAP:
                        matched = NOTES[root] + CHORDS_MAP[rel]
                        break
                if matched and matched != last_chord:
                    chord_counts[matched] = chord_counts.get(matched, 0) + 1
        elif ev.get("type") == "off":
            active.discard(ev.get("note"))
            if len(active) < 3:
                last_chord = None
    return [c for c, _ in sorted(chord_counts.items(), key=lambda x: x[1], reverse=True)[:6]]

# -----------------------------------------------------------------------------
# HTTP REQUEST HANDLER
# -----------------------------------------------------------------------------
class PianoDashboardHandler(BaseHTTPRequestHandler):
    server_version = "PianoManServer/1.1"

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data).encode('utf-8')
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message, status=400):
        self.send_json({"success": False, "error": message}, status=status)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return None
            raw = self.rfile.read(length).decode('utf-8')
            return json.loads(raw)
        except Exception:
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'

        if path == "/api/live":
            self.handle_get_live()
        elif path == "/api/config":
            self.handle_get_config()
        elif path == "/api/progress":
            self.handle_get_progress()
        elif path == "/api/classes":
            self.handle_get_classes()
        elif path == "/api/sessions":
            self.handle_get_sessions(parse_qs(parsed.query))
        elif path.startswith("/api/sessions/"):
            session_id = path[len("/api/sessions/"):]
            self.handle_get_session_by_id(session_id)
        elif path == "/api/songs":
            self.handle_get_songs(parse_qs(parsed.query))
        elif path.startswith("/api/songs/") and path.endswith("/download"):
            song_id = path[len("/api/songs/"):-len("/download")].rstrip('/')
            self.handle_download_song(song_id)
        elif path.startswith("/api/songs/"):
            song_id = path[len("/api/songs/"):]
            self.handle_get_song_by_id(song_id)
        elif path == "/api/player/status":
            self.handle_get_player_status()
        else:
            self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        if path == "/api/config":
            self.handle_post_config()
        elif path == "/api/classes":
            self.handle_post_class()
        elif path == "/api/songs/upload":
            self.handle_post_song_upload()
        elif path.startswith("/api/songs/") and path.endswith("/convert-to-class"):
            song_id = path[len("/api/songs/"):-len("/convert-to-class")].rstrip('/')
            self.handle_convert_song_to_class(song_id)
        elif path == "/api/player/play":
            self.handle_player_play()
        elif path == "/api/player/pause":
            self.handle_player_pause()
        elif path == "/api/player/resume":
            self.handle_player_resume()
        elif path == "/api/player/stop":
            self.handle_player_stop()
        elif path == "/api/player/seek":
            self.handle_player_seek()
        elif path == "/api/player/speed":
            self.handle_player_speed()
        elif path == "/api/player/mute-drums":
            self.handle_player_mute_drums()
        elif path == "/api/tamagotchi/feed":
            self.handle_tamagotchi_feed()
        elif path == "/api/tamagotchi/admin-update":
            self.handle_tamagotchi_admin_update()
        else:
            self.send_error_json(f"Not found: {path}", status=404)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        if path.startswith("/api/classes/"):
            cid = path[len("/api/classes/"):]
            self.handle_put_class(cid)
        elif path.startswith("/api/songs/"):
            sid = path[len("/api/songs/"):]
            self.handle_put_song(sid)
        else:
            self.send_error_json(f"Not found: {path}", status=404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')

        if path.startswith("/api/classes/"):
            cid = path[len("/api/classes/"):]
            self.handle_delete_class(cid)
        elif path.startswith("/api/sessions/"):
            sid = path[len("/api/sessions/"):]
            self.handle_delete_session(sid)
        elif path.startswith("/api/songs/"):
            sid = path[len("/api/songs/"):]
            self.handle_delete_song(sid)
        else:
            self.send_error_json(f"Not found: {path}", status=404)

    # -------------------------------------------------------------------------
    # API HANDLERS: LIVE STATE & STATS
    # -------------------------------------------------------------------------
    def handle_get_live(self):
        live = load_json(LIVE_STATE_FILE, None)
        now = time.time()
        is_fresh = False
        if live and isinstance(live, dict):
            timestamp = live.get("timestamp", 0)
            is_fresh = (now - timestamp) < 4.0

        if not live or not is_fresh:
            live = {
                "player": None,
                "app_mode": "idle",
                "active_class": None,
                "session_active": False,
                "is_playing": False,
                "accumulated_time": 0.0,
                "goal_time": 900,
                "goal_reached": False,
                "connected_port": None,
                "detected_ports": [],
                "active_notes": [],
                "last_recognized_chord": None,
                "chord_counts": {},
                "piano_player": {
                    "is_playing": False,
                    "current_time": 0.0,
                    "duration": 0.0,
                    "speed": 1.0,
                    "song_id": None,
                    "song_title": None
                },
                "online": False,
                "timestamp": now
            }
        else:
            live["online"] = True

        self.send_json(live)

    def handle_get_config(self):
        cfg = load_json(CONFIG_FILE, {
            "goal_minutes": 15,
            "players": ["Eva", "Mara", "Willy"],
            "metronome": {"slow": 60, "normal": 80, "fast": 120}
        })
        self.send_json(cfg)

    def handle_post_config(self):
        body = self.read_json_body()
        if not body or not isinstance(body, dict):
            return self.send_error_json("Invalid JSON payload")

        current = load_json(CONFIG_FILE, {
            "goal_minutes": 15,
            "players": ["Eva", "Mara", "Willy"],
            "metronome": {"slow": 60, "normal": 80, "fast": 120}
        })

        if "goal_minutes" in body:
            try:
                val = int(body["goal_minutes"])
                if 1 <= val <= 300:
                    current["goal_minutes"] = val
            except (ValueError, TypeError):
                return self.send_error_json("goal_minutes must be an integer between 1 and 300")

        if "players" in body and isinstance(body["players"], list):
            players = [str(p).strip() for p in body["players"] if str(p).strip()]
            if players:
                seen = set()
                dedup = []
                for p in players:
                    if p not in seen:
                        seen.add(p)
                        dedup.append(p)
                current["players"] = dedup

        if "metronome" in body and isinstance(body["metronome"], dict):
            m = current.setdefault("metronome", {"slow": 60, "normal": 80, "fast": 120})
            for k in ("slow", "normal", "fast"):
                if k in body["metronome"]:
                    try:
                        bpm = int(body["metronome"][k])
                        if 30 <= bpm <= 280:
                            m[k] = bpm
                    except (ValueError, TypeError):
                        pass

        if save_json(CONFIG_FILE, current):
            self.send_json({"success": True, "config": current})
        else:
            self.send_error_json("Failed to write config file", status=500)

    def handle_get_progress(self):
        progress = load_json(PROGRESS_FILE, {})
        cfg = load_json(CONFIG_FILE, {"players": ["Eva", "Mara", "Willy"], "goal_minutes": 15})
        goal_min = cfg.get("goal_minutes", 15)

        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        summary = {}
        for player in cfg.get("players", []):
            pdata = progress.get(player, {})
            p_date = pdata.get("date")
            p_time = pdata.get("time", 0.0) if p_date == today_str else 0.0
            history = pdata.get("history", [])

            count_last_5, played_last_24h = 0, False
            for d_str in history:
                try:
                    diff = (datetime.date.today() - datetime.datetime.strptime(d_str, "%Y-%m-%d").date()).days
                    if 0 <= diff <= 5: count_last_5 += 1
                    if 0 <= diff <= 1: played_last_24h = True
                except Exception:
                    pass
            stars = 3 if count_last_5 >= 3 else (2 if count_last_5 == 2 else (1 if played_last_24h else 0))

            t_data = tamagotchi.calculate_tamagotchi(player, progress, goal_seconds=goal_min * 60)
            p_stats = tamagotchi.get_student_stats(player, progress_data=progress, goal_seconds=goal_min * 60)

            summary[player] = {
                "today_seconds": round(p_time, 1),
                "today_minutes": round(p_time / 60.0, 1),
                "goal_minutes": goal_min,
                "goal_completed": p_time >= (goal_min * 60),
                "stars": stars,
                "history_days_count": len(history),
                "history": history,
                "tamagotchi": t_data,
                "stats": p_stats
            }

        self.send_json({"students": summary, "date": today_str})

    def handle_tamagotchi_admin_update(self):
        body = self.read_json_body()
        if not body or "player" not in body:
            self.send_error_json("Missing player parameter", status=400)
            return

        player = body["player"]
        progress = load_json(PROGRESS_FILE, {})
        cfg = load_json(CONFIG_FILE, {"goal_minutes": 15})
        goal_seconds = cfg.get("goal_minutes", 15) * 60

        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        if player not in progress:
            progress[player] = {"date": today_str, "time": 0.0, "history": []}

        pdata = progress[player]
        if "tamagotchi" not in pdata:
            pdata["tamagotchi"] = {}

        # 1. Update today's practice time if provided
        if "today_minutes" in body:
            mins = max(0.0, float(body["today_minutes"]))
            pdata["time"] = round(mins * 60.0, 1)
            pdata["date"] = today_str
            if pdata["time"] >= goal_seconds:
                if "history" not in pdata: pdata["history"] = []
                if today_str not in pdata["history"]:
                    pdata["history"].append(today_str)
            else:
                if "history" in pdata and today_str in pdata["history"]:
                    pdata["history"].remove(today_str)

        # 2. Update streak / history if streak was provided
        if "streak" in body:
            target_streak = max(0, int(body["streak"]))
            history_set = set(pdata.get("history", []))
            today_date = datetime.date.today()
            is_done_today = (pdata.get("time", 0.0) >= goal_seconds) or (today_str in history_set)
            end_d = today_date if is_done_today else (today_date - datetime.timedelta(days=1))

            for i in range(target_streak):
                d_str = (end_d - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                history_set.add(d_str)

            pdata["history"] = sorted(list(history_set))
            pdata["tamagotchi"]["forced_streak"] = target_streak

        # 3. Update Buddy Version
        if "version" in body:
            try:
                v = int(body["version"])
                if 1 <= v <= 32:
                    pdata["tamagotchi"]["version"] = v
            except Exception:
                pass

        # 4. Update Mood
        if "mood" in body:
            m = str(body["mood"]).lower()
            if m in ("happy", "hungry", "sad"):
                pdata["tamagotchi"]["forced_mood"] = m
            elif m == "auto":
                pdata["tamagotchi"].pop("forced_mood", None)

        # 5. Update Fed Today
        if "fed_today" in body:
            if body["fed_today"]:
                pdata["tamagotchi"]["fed_date"] = today_str
            else:
                pdata["tamagotchi"]["fed_date"] = ""

        # 6. Update Base Color
        if "base_color" in body:
            col = str(body["base_color"]).strip() if body["base_color"] else ""
            if col.startswith("#"):
                pdata["tamagotchi"]["base_color"] = col
            elif col == "" or col.lower() == "default":
                pdata["tamagotchi"].pop("base_color", None)

        # 7. Reset overrides if requested
        if body.get("reset_overrides"):
            pdata["tamagotchi"].pop("version", None)
            pdata["tamagotchi"].pop("forced_mood", None)
            pdata["tamagotchi"].pop("forced_streak", None)
            pdata["tamagotchi"].pop("base_color", None)

        save_json(PROGRESS_FILE, progress)

        updated_stats = tamagotchi.get_student_stats(player, goal_seconds=goal_seconds)
        self.send_json({
            "success": True,
            "player": player,
            "stats": updated_stats,
            "progress": pdata,
            "tamagotchi": updated_stats["tamagotchi"]
        })

    def handle_tamagotchi_feed(self):
        body = self.read_json_body()
        if not body or "player" not in body:
            self.send_error_json("Missing player parameter", status=400)
            return

        player = body["player"]
        progress = load_json(PROGRESS_FILE, {})
        cfg = load_json(CONFIG_FILE, {"goal_minutes": 15})
        goal_seconds = cfg.get("goal_minutes", 15) * 60

        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")

        t_data = tamagotchi.calculate_tamagotchi(player, progress, goal_seconds=goal_seconds)
        if not t_data["today_completed"]:
            self.send_error_json(f"{player} has not completed today's practice yet", status=400)
            return

        if player not in progress:
            progress[player] = {"date": today_str, "time": 0.0, "history": []}

        if "tamagotchi" not in progress[player]:
            progress[player]["tamagotchi"] = {}

        progress[player]["tamagotchi"]["fed_date"] = today_str
        if t_data.get("can_evolve"):
            progress[player]["tamagotchi"]["version"] = t_data["version"]

        save_json(PROGRESS_FILE, progress)

        updated_t = tamagotchi.calculate_tamagotchi(player, progress, goal_seconds=goal_seconds)
        self.send_json({"success": True, "tamagotchi": updated_t, "player": player})

    def handle_get_classes(self):
        classes = load_json(CLASSES_FILE, [])
        summary = []
        for c in classes:
            events = c.get("midi_events", [])
            dur = int(max([e.get("time", 0) for e in events], default=0)) if events else 0
            summary.append({
                "id": c.get("id"),
                "name": c.get("name", "Untitled Lesson"),
                "chords": c.get("chords", []),
                "duration_seconds": dur,
                "event_count": len(events)
            })
        self.send_json(summary)

    def handle_post_class(self):
        body = self.read_json_body()
        if not body or not isinstance(body, dict):
            return self.send_error_json("Invalid payload")
        name = str(body.get("name", "")).strip()
        if not name:
            return self.send_error_json("Class name is required")

        classes = load_json(CLASSES_FILE, [])
        new_class = {
            "id": str(uuid.uuid4()),
            "name": name,
            "chords": body.get("chords", []),
            "midi_events": body.get("midi_events", [])
        }
        classes.append(new_class)
        if save_json(CLASSES_FILE, classes):
            self.send_json({"success": True, "class": new_class})
        else:
            self.send_error_json("Failed to save class", status=500)

    def handle_put_class(self, cid):
        body = self.read_json_body()
        if not body or "name" not in body:
            return self.send_error_json("New name required")
        new_name = str(body["name"]).strip()
        if not new_name:
            return self.send_error_json("Name cannot be empty")

        classes = load_json(CLASSES_FILE, [])
        target = next((c for c in classes if c.get("id") == cid), None)
        if not target:
            return self.send_error_json("Class not found", status=404)

        target["name"] = new_name
        if save_json(CLASSES_FILE, classes):
            self.send_json({"success": True, "class": target})
        else:
            self.send_error_json("Failed to update class", status=500)

    def handle_delete_class(self, cid):
        classes = load_json(CLASSES_FILE, [])
        orig_len = len(classes)
        classes = [c for c in classes if c.get("id") != cid]
        if len(classes) == orig_len:
            return self.send_error_json("Class not found", status=404)

        if save_json(CLASSES_FILE, classes):
            self.send_json({"success": True})
        else:
            self.send_error_json("Failed to delete class", status=500)

    def handle_get_sessions(self, params):
        sessions = load_json(SESSIONS_FILE, [])
        player_filter = params.get("player", [None])[0]
        mode_filter = params.get("mode", [None])[0]

        filtered = []
        for s in sessions:
            if player_filter and player_filter != "all" and s.get("player") != player_filter:
                continue
            if mode_filter and mode_filter != "all" and s.get("mode") != mode_filter:
                continue

            filtered.append({
                "id": s.get("id"),
                "player": s.get("player"),
                "date": s.get("date"),
                "start_time": s.get("start_time"),
                "end_time": s.get("end_time"),
                "duration_seconds": s.get("duration_seconds", 0),
                "mode": s.get("mode", "free"),
                "class_name": s.get("class_name"),
                "goal_reached": s.get("goal_reached", False),
                "chords_played": s.get("chords_played", {}),
                "total_notes": s.get("total_notes", len(s.get("events", [])))
            })
        self.send_json(filtered)

    def handle_get_session_by_id(self, sid):
        # 1. Check sessions.json
        sessions = load_json(SESSIONS_FILE, [])
        target = next((s for s in sessions if s.get("id") == sid), None)
        if target:
            return self.send_json(target)

        # 2. Check classes.json
        classes = load_json(CLASSES_FILE, [])
        target_class = next((c for c in classes if c.get("id") == sid), None)
        if target_class:
            synth_session = {
                "id": target_class.get("id"),
                "player": "Teacher Lesson",
                "date": "",
                "start_time": 0,
                "duration_seconds": max([e.get("time", 0) for e in target_class.get("midi_events", [])], default=0),
                "mode": "class",
                "class_name": target_class.get("name"),
                "chords_played": {ch.get("name"): 1 for ch in target_class.get("chords", [])},
                "events": target_class.get("midi_events", []),
                "total_notes": len(target_class.get("midi_events", []))
            }
            return self.send_json(synth_session)

        # 3. Check songs.json
        songs = load_json(SONGS_FILE, [])
        target_song = next((s for s in songs if s.get("id") == sid), None)
        if target_song:
            synth_session = {
                "id": target_song.get("id"),
                "player": "Song Library",
                "date": target_song.get("upload_date", ""),
                "start_time": 0,
                "duration_seconds": target_song.get("duration_seconds", 0),
                "mode": "song",
                "class_name": target_song.get("title"),
                "chords_played": {ch: 1 for ch in target_song.get("chords", [])},
                "events": target_song.get("midi_events", []),
                "total_notes": target_song.get("notes_count", len(target_song.get("midi_events", [])))
            }
            return self.send_json(synth_session)

        self.send_error_json("Session not found", status=404)

    def handle_delete_session(self, sid):
        sessions = load_json(SESSIONS_FILE, [])
        orig_len = len(sessions)
        sessions = [s for s in sessions if s.get("id") != sid]
        if len(sessions) == orig_len:
            return self.send_error_json("Session not found", status=404)

        if save_json(SESSIONS_FILE, sessions):
            self.send_json({"success": True})
        else:
            self.send_error_json("Failed to delete session", status=500)

    # -------------------------------------------------------------------------
    # API HANDLERS: SONG REPOSITORY & MIDI UPLOAD
    # -------------------------------------------------------------------------
    def handle_get_songs(self, params):
        songs = load_json(SONGS_FILE, [])
        q = params.get("q", [None])[0]
        result = []
        for s in songs:
            if q and q.lower() not in s.get("title", "").lower() and q.lower() not in s.get("filename", "").lower():
                continue
            result.append({
                "id": s.get("id"),
                "title": s.get("title", "Untitled Song"),
                "composer": s.get("composer", ""),
                "filename": s.get("filename"),
                "file_size": s.get("file_size", 0),
                "duration_seconds": s.get("duration_seconds", 0),
                "notes_count": s.get("notes_count", 0),
                "track_count": s.get("track_count", 1),
                "has_drums": s.get("has_drums", False),
                "drum_notes_count": s.get("drum_notes_count", 0),
                "upload_date": s.get("upload_date", ""),
                "chords": s.get("chords", [])
            })
        self.send_json(result)

    def handle_get_song_by_id(self, sid):
        songs = load_json(SONGS_FILE, [])
        target = next((s for s in songs if s.get("id") == sid), None)
        if not target:
            return self.send_error_json("Song not found", status=404)
        self.send_json(target)

    def handle_download_song(self, sid):
        songs = load_json(SONGS_FILE, [])
        target = next((s for s in songs if s.get("id") == sid), None)
        if not target:
            self.send_error_json("Song not found", status=404)
            return
        filename = target.get("filename")
        filepath = os.path.join(SONGS_DIR, filename)
        if not os.path.exists(filepath):
            self.send_error_json("MIDI file not found on disk", status=404)
            return
        try:
            with open(filepath, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", "audio/midi")
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error_json(str(e), status=500)

    def handle_post_song_upload(self):
        content_type = self.headers.get("Content-Type", "")
        file_bytes = None
        orig_filename = "uploaded_song.mid"
        custom_title = None

        if "application/json" in content_type:
            body = self.read_json_body()
            if not body or "data" not in body:
                return self.send_error_json("Missing 'data' field in JSON payload")
            raw_data = body["data"]
            if "," in raw_data:
                raw_data = raw_data.split(",", 1)[1]
            try:
                file_bytes = base64.b64decode(raw_data)
            except Exception as e:
                return self.send_error_json(f"Invalid base64 payload: {e}")
            orig_filename = body.get("filename", "uploaded_song.mid")
            custom_title = body.get("title")
        else:
            length = int(self.headers.get("Content-Length", 0))
            if length <= 0:
                return self.send_error_json("Empty request body")
            raw_body = self.rfile.read(length)
            
            if "multipart/form-data" in content_type and b"MThd" in raw_body:
                idx = raw_body.find(b"MThd")
                if idx != -1:
                    header_part = raw_body[:idx].decode('utf-8', errors='ignore')
                    m = re.search(r'filename="([^"]+)"', header_part)
                    if m: orig_filename = m.group(1)
                    end_idx = raw_body.rfind(b"\r\n--")
                    file_bytes = raw_body[idx:end_idx] if end_idx > idx else raw_body[idx:]
            elif raw_body.startswith(b"MThd"):
                file_bytes = raw_body
            else:
                return self.send_error_json("Unsupported format. Send JSON with base64 data.")

        if not file_bytes or not file_bytes.startswith(b"MThd"):
            return self.send_error_json("Uploaded file is not a valid Standard MIDI File (Missing 'MThd' header)")

        safe_name = os.path.splitext(os.path.basename(orig_filename))[0]
        safe_name = re.sub(r'[^a-zA-Z0-9_\- ]', '', safe_name).strip() or "song"
        song_id = str(uuid.uuid4())
        save_filename = f"{safe_name}_{song_id[:8]}.mid"
        save_path = os.path.join(SONGS_DIR, save_filename)

        os.makedirs(SONGS_DIR, exist_ok=True)
        try:
            with open(save_path, 'wb') as f:
                f.write(file_bytes)
        except Exception as e:
            return self.send_error_json(f"Failed to save MIDI file: {e}", status=500)

        try:
            events, track_count = parse_midi_file(save_path)
        except Exception as e:
            try: os.remove(save_path)
            except: pass
            return self.send_error_json(f"Could not parse MIDI file: {e}")

        if not events:
            try: os.remove(save_path)
            except: pass
            return self.send_error_json("MIDI file contains no note events")

        title = custom_title.strip() if custom_title and custom_title.strip() else safe_name.replace('_', ' ').title()
        dur = max([e.get("time", 0) for e in events], default=0.0)
        chords = extract_chords_from_events(events)

        has_drums = any(e.get("is_drum") or e.get("channel") == 9 for e in events)
        drum_notes = sum(1 for e in events if (e.get("is_drum") or e.get("channel") == 9) and e.get("type") == "on")
        melody_notes = sum(1 for e in events if not (e.get("is_drum") or e.get("channel") == 9) and e.get("type") == "on")

        new_song = {
            "id": song_id,
            "title": title,
            "filename": save_filename,
            "original_filename": orig_filename,
            "file_size": len(file_bytes),
            "duration_seconds": round(dur, 1),
            "notes_count": melody_notes if has_drums else sum(1 for e in events if e.get("type") == "on"),
            "has_drums": has_drums,
            "drum_notes_count": drum_notes,
            "track_count": track_count,
            "upload_date": time.strftime("%Y-%m-%d %H:%M"),
            "chords": chords,
            "midi_events": events
        }

        songs = load_json(SONGS_FILE, [])
        songs.insert(0, new_song)
        if save_json(SONGS_FILE, songs):
            summary = dict(new_song)
            del summary["midi_events"]
            self.send_json({"success": True, "song": summary})
        else:
            self.send_error_json("Failed to update songs database", status=500)

    def handle_put_song(self, sid):
        body = self.read_json_body()
        if not body or not body.get("title"):
            return self.send_error_json("New title is required")
        new_title = str(body["title"]).strip()
        if not new_title:
            return self.send_error_json("Title cannot be empty")
        songs = load_json(SONGS_FILE, [])
        target = next((s for s in songs if s.get("id") == sid), None)
        if not target:
            return self.send_error_json("Song not found", status=404)
        target["title"] = new_title
        if save_json(SONGS_FILE, songs):
            self.send_json({"success": True, "song": target})
        else:
            self.send_error_json("Failed to update song", status=500)

    def handle_delete_song(self, sid):
        songs = load_json(SONGS_FILE, [])
        target = next((s for s in songs if s.get("id") == sid), None)
        if not target:
            return self.send_error_json("Song not found", status=404)
        songs = [s for s in songs if s.get("id") != sid]
        save_json(SONGS_FILE, songs)
        try:
            fp = os.path.join(SONGS_DIR, target.get("filename", ""))
            if os.path.exists(fp): os.remove(fp)
        except Exception:
            pass
        self.send_json({"success": True})

    def handle_convert_song_to_class(self, sid):
        songs = load_json(SONGS_FILE, [])
        target = next((s for s in songs if s.get("id") == sid), None)
        if not target:
            return self.send_error_json("Song not found", status=404)
        classes = load_json(CLASSES_FILE, [])
        new_class = {
            "id": str(uuid.uuid4()),
            "name": target.get("title", "Song Lesson"),
            "chords": [{"name": c, "shape": []} for c in target.get("chords", [])],
            "midi_events": target.get("midi_events", [])
        }
        classes.append(new_class)
        if save_json(CLASSES_FILE, classes):
            self.send_json({"success": True, "class_id": new_class["id"], "class_name": new_class["name"]})
        else:
            self.send_error_json("Failed to create class from song", status=500)

    # -------------------------------------------------------------------------
    # API HANDLERS: PIANO HARDWARE PLAYBACK
    # -------------------------------------------------------------------------
    def handle_player_play(self):
        body = self.read_json_body() or {}
        song_id = body.get("song_id")
        speed = float(body.get("speed", 1.0))
        mute_drums = bool(body.get("mute_drums", True))
        piano_only = bool(body.get("piano_only", True))
        if not song_id:
            return self.send_error_json("song_id is required")

        target = None
        songs = load_json(SONGS_FILE, [])
        target = next((s for s in songs if s.get("id") == song_id), None)
        if not target:
            classes = load_json(CLASSES_FILE, [])
            c_target = next((c for c in classes if c.get("id") == song_id), None)
            if c_target:
                target = {
                    "id": c_target["id"],
                    "title": c_target["name"],
                    "midi_events": c_target.get("midi_events", [])
                }
        if not target:
            return self.send_error_json("Song or lesson not found", status=404)

        dispatch_piano_command("play_song", song=target, speed=speed, mute_drums=mute_drums, piano_only=piano_only)
        self.send_json({"success": True, "status": "playing", "song_title": target.get("title"), "mute_drums": mute_drums})

    def handle_player_pause(self):
        dispatch_piano_command("pause")
        self.send_json({"success": True, "status": "paused"})

    def handle_player_resume(self):
        dispatch_piano_command("resume")
        self.send_json({"success": True, "status": "playing"})

    def handle_player_stop(self):
        dispatch_piano_command("stop")
        self.send_json({"success": True, "status": "stopped"})

    def handle_player_seek(self):
        body = self.read_json_body() or {}
        pct = float(body.get("percent", 0.0))
        dispatch_piano_command("seek", percent=pct)
        self.send_json({"success": True, "percent": pct})

    def handle_player_speed(self):
        body = self.read_json_body() or {}
        speed = float(body.get("speed", 1.0))
        dispatch_piano_command("speed", speed=speed)
        self.send_json({"success": True, "speed": speed})

    def handle_player_mute_drums(self):
        body = self.read_json_body() or {}
        mute = bool(body.get("mute_drums", True))
        dispatch_piano_command("toggle_mute_drums", mute_drums=mute)
        self.send_json({"success": True, "mute_drums": mute})

    def handle_get_player_status(self):
        live = load_json(LIVE_STATE_FILE, {})
        piano_player = live.get("piano_player", {
            "is_playing": False,
            "current_time": 0.0,
            "duration": 0.0,
            "speed": 1.0,
            "song_id": None,
            "song_title": None
        })
        self.send_json(piano_player)

    # -------------------------------------------------------------------------
    # STATIC FILE SERVING
    # -------------------------------------------------------------------------
    def serve_static(self, path):
        if path == "/":
            path = "/index.html"

        rel_path = path.lstrip('/')
        file_path = os.path.join(WEB_DIR, rel_path)

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            index_path = os.path.join(WEB_DIR, "index.html")
            if os.path.exists(index_path):
                file_path = index_path
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"404 Not Found")
                return

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "text/html" if file_path.endswith(".html") else "application/octet-stream"

        try:
            with open(file_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))

    def log_message(self, format, *args):
        if args and ("api/live" in str(args[0]) or "200" in str(args[1])):
            return
        super().log_message(format, *args)

def run_server(port=8080, host="0.0.0.0"):
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, PianoDashboardHandler)
    print(f"🎵 Piano Studio Dashboard running at http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Piano Studio Dashboard...")
        httpd.server_close()

def start_background_server(port=8080, host="0.0.0.0"):
    thread = threading.Thread(target=run_server, kwargs={"port": port, "host": host}, daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Piano Studio Web Backend & Dashboard Server")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface (default 0.0.0.0)")
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)
