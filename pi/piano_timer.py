import mido
import time
import threading
import subprocess
import queue
import json
import os
import math
import uuid
import tkinter as tk
import tkinter.font as tkfont
import tamagotchi

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progress.json")
CLASSES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "classes.json")
SESSIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.json")
LIVE_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_state.json")
COMMAND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "piano_command.json")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return default

def save_json(path, data):
    try:
        tmp_path = path + ".tmp"
        with open(tmp_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, path)
        return True
    except:
        return False

def save_session_record(session):
    try:
        sessions = load_json(SESSIONS_FILE, [])
        sessions.insert(0, session)
        if len(sessions) > 150:
            sessions = sessions[:150]
        save_json(SESSIONS_FILE, sessions)
    except Exception as e:
        print(f"Error saving session record: {e}")

config = load_json(CONFIG_FILE, {
    "goal_minutes": 15,
    "players": ["Eva", "Mara", "Willy"],
    "metronome": {
        "slow": 60,
        "normal": 80,
        "fast": 120
    }
})
save_json(CONFIG_FILE, config)

GOAL_TIME_SECONDS = config.get("goal_minutes", 15) * 60
PLAYERS = config.get("players", ["Eva", "Mara", "Willy"])
METRONOME_CONFIG = config.get("metronome", {
    "slow": 60,
    "normal": 80,
    "fast": 120
})
INACTIVITY_TIMEOUT_SECONDS = 5 * 60

_saved_brightness = {}

def _write_sysfs(path: str, val: str):
    """Write a value to a sysfs file, falling back to passwordless sudo tee if needed."""
    try:
        with open(path, "w") as f:
            f.write(val)
        return True
    except Exception:
        pass
    try:
        subprocess.run(
            ["sudo", "-n", "tee", path],
            input=val.encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=1.5
        )
        return True
    except Exception:
        return False

def _set_display_power_worker(turn_on: bool):
    # 1. Control all hardware backlights in /sys/class/backlight/* (both brightness and bl_power)
    backlight_base = "/sys/class/backlight"
    if os.path.isdir(backlight_base):
        for dev in os.listdir(backlight_base):
            dev_path = os.path.join(backlight_base, dev)
            bl_power_path = os.path.join(dev_path, "bl_power")
            brightness_path = os.path.join(dev_path, "brightness")
            max_br_path = os.path.join(dev_path, "max_brightness")

            max_br = 255
            if os.path.exists(max_br_path):
                try:
                    with open(max_br_path, "r") as f:
                        max_br = int(f.read().strip())
                except Exception:
                    pass

            if turn_on:
                if os.path.exists(bl_power_path):
                    _write_sysfs(bl_power_path, "0")
                if os.path.exists(brightness_path):
                    target_br = _saved_brightness.get(dev, max_br)
                    if target_br <= 0:
                        target_br = max_br
                    _write_sysfs(brightness_path, str(target_br))
            else:
                if os.path.exists(brightness_path):
                    try:
                        with open(brightness_path, "r") as f:
                            cur_br = int(f.read().strip())
                        if cur_br > 0:
                            _saved_brightness[dev] = cur_br
                    except Exception:
                        pass
                    _write_sysfs(brightness_path, "0")
                if os.path.exists(bl_power_path):
                    _write_sysfs(bl_power_path, "1")
                    _write_sysfs(bl_power_path, "4")

    # 2. Prepare environment with Wayland & X11 display variables
    env = os.environ.copy()
    env.setdefault("DISPLAY", ":0")
    uid = os.getuid() if hasattr(os, "getuid") else 1000
    runtime_dir = env.get("XDG_RUNTIME_DIR", f"/run/user/{uid}")
    if os.path.isdir(runtime_dir):
        env["XDG_RUNTIME_DIR"] = runtime_dir
        if "WAYLAND_DISPLAY" not in env:
            for candidate in ("wayland-1", "wayland-0"):
                if os.path.exists(os.path.join(runtime_dir, candidate)):
                    env["WAYLAND_DISPLAY"] = candidate
                    break

    # 3. Execute Wayland (wlopm), VideoCore (vcgencmd), brightnessctl, and X11 (xset) independently
    if turn_on:
        cmds = [
            ["wlopm", "--on", "*"],
            ["vcgencmd", "display_power", "1"],
            ["brightnessctl", "-r"],
            ["xset", "dpms", "force", "on"],
            ["xset", "s", "reset"],
        ]
    else:
        cmds = [
            [" brightnessctl", "-s", "set", "0"],
            ["wlopm", "--off", "*"],
            ["vcgencmd", "display_power", "0"],
            ["xset", "dpms", "force", "off"],
        ]
        cmds[0][0] = "brightnessctl"

    for cmd in cmds:
        try:
            subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.5
            )
        except Exception:
            pass

def set_display_power(turn_on: bool):
    """Control physical backlight and DPMS power for Raspberry Pi touchscreen."""
    threading.Thread(target=_set_display_power_worker, args=(turn_on,), daemon=True).start()


# ==========================================
# MODERN MUTED SLATE / CHARCOAL DESIGN SYSTEM
# ==========================================
BG_DARK = '#0f141c'          # Main deep charcoal / slate gray background
BG_CARD = '#1a2230'          # Elevated card background (subtly lighter)
BG_CARD_HOVER = '#202a3c'    # Card hover
BG_SURFACE = '#243042'       # Nested surface for cells and controls
BORDER_SUBTLE = '#28364a'    # Soft, non-harsh card outline
BORDER_FOCUS = '#38bdf8'     # Focus / active border

ACCENT_PRIMARY = '#38bdf8'   # Primary accent: soft electric blue
ACCENT_HOVER = '#0ea5e9'     # Pressed / hover accent
ACCENT_MUTED = '#1e3a5f'     # Muted accent background tint
COLOR_SUCCESS = '#2dd4bf'    # Soft mint / teal for goal achieved
COLOR_WARNING = '#fbbf24'    # Warm amber for stars & alerts
COLOR_DANGER = '#fb7185'     # Soft rose for delete / cancel
COLOR_DANGER_BG = '#2a1d24'  # Subtle danger surface
COLOR_INACTIVE = '#475569'   # Muted slate for paused timer ring

TEXT_PRIMARY = '#f8fafc'     # High contrast crisp soft white
TEXT_SECONDARY = '#94a3b8'   # Clean slate gray for subtitles & labels
TEXT_MUTED = '#64748b'       # Subdued caption text
TEXT_DARK = '#0f141c'        # Dark text for solid filled primary buttons

def detect_geometric_font():
    try:
        available = set(tkfont.families())
        for fam in ["SF Pro Display", "SF Pro Text", "Inter", "Roboto", "DejaVu Sans", "Helvetica Neue", "Helvetica", "Arial"]:
            if fam in available:
                return fam
    except Exception:
        pass
    return "Helvetica"

FONT_MAIN = "Helvetica"

state = {
    "selected_player": None, "accumulated_time": 0.0, "last_note_time": 0.0,
    "is_playing": False, "session_active": False, "goal_reached": False,
    "last_update_time": time.time(), "detected_ports": [], "connected_port": None,
    "piano_disconnected_since": time.time(),
    "chord_counts": {}, "chord_shapes": {}, "last_recognized_chord": None
}

midi_queue = queue.Queue()
debug_queue = queue.Queue()
outport_global = None

def midi_listener():
    global outport_global
    inport = None
    connected_in_name = None
    last_health_check = time.time()
    
    while True:
        try:
            now = time.time()
            
            # Periodically query available MIDI ports
            if now - last_health_check >= 1.0 or inport is None:
                last_health_check = now
                try:
                    inputs = mido.get_input_names()
                    valid_inputs = [i for i in inputs if 'Through' not in i]
                except Exception:
                    valid_inputs = []
                state["detected_ports"] = valid_inputs
                
                # Check if active connection is still in valid inputs
                if inport is not None:
                    base_in = connected_in_name.split()[0] if connected_in_name else ""
                    port_still_exists = any(i == connected_in_name or i.split()[0] == base_in for i in valid_inputs)
                    if not port_still_exists:
                        debug_queue.put(f"Piano disconnected ({connected_in_name}). Resetting ports...")
                        try: inport.close()
                        except: pass
                        inport = None
                        connected_in_name = None
                        if outport_global:
                            try: outport_global.close()
                            except: pass
                            outport_global = None
                        state["connected_port"] = None
                        if state.get("piano_disconnected_since") is None:
                            state["piano_disconnected_since"] = time.time()
                        midi_queue.put(('clear_all', None, 'system', 0))
                        time.sleep(0.5)
                        continue

            # Attempt connection if currently disconnected
            if inport is None:
                if not valid_inputs:
                    state["connected_port"] = None
                    if state.get("piano_disconnected_since") is None:
                        state["piano_disconnected_since"] = time.time()
                    if outport_global:
                        try: outport_global.close()
                        except: pass
                        outport_global = None
                    time.sleep(1.0)
                    continue
                
                port_name = valid_inputs[0]
                debug_queue.put(f"Detected MIDI port: {port_name}. Opening connection...")
                
                try:
                    out_names = mido.get_output_names()
                    base_name = port_name.split()[0]
                    match = [n for n in out_names if n.split()[0] == base_name and 'Through' not in n]
                    if match:
                        if outport_global:
                            try: outport_global.close()
                            except: pass
                        outport_global = mido.open_output(match[0])
                        debug_queue.put(f"Connected MIDI Output: {match[0]}")
                except Exception as e:
                    debug_queue.put(f"Output port warning: {e}")
                    outport_global = None
                    
                try:
                    inport = mido.open_input(port_name)
                    connected_in_name = port_name
                    state["connected_port"] = port_name
                    state["piano_disconnected_since"] = None
                    midi_queue.put(('piano_connected', port_name, 'system', 0))
                    debug_queue.put(f"Connected successfully to {port_name}!")
                except Exception as e:
                    debug_queue.put(f"Error opening port {port_name}: {e}")
                    if inport:
                        try: inport.close()
                        except: pass
                    inport = None
                    connected_in_name = None
                    state["connected_port"] = None
                    if state.get("piano_disconnected_since") is None:
                        state["piano_disconnected_since"] = time.time()
                    time.sleep(1.0)
                    continue

            # Read pending MIDI messages
            read_error = False
            try:
                for msg in inport.iter_pending():
                    if msg.type == 'note_on' and msg.velocity > 0:
                        state["last_note_time"] = time.time()
                        state["is_playing"] = True
                        midi_queue.put(('on', msg.note, 'student', msg.velocity))
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        midi_queue.put(('off', msg.note, 'student', 0))
                    elif msg.type == 'control_change' and msg.control in (120, 121, 123):
                        midi_queue.put(('all_off', None, 'student', 0))
            except Exception as e:
                debug_queue.put(f"MIDI read error: {e}")
                read_error = True

            if read_error:
                try: inport.close()
                except: pass
                inport = None
                connected_in_name = None
                if outport_global:
                    try: outport_global.close()
                    except: pass
                    outport_global = None
                state["connected_port"] = None
                if state.get("piano_disconnected_since") is None:
                    state["piano_disconnected_since"] = time.time()
                midi_queue.put(('clear_all', None, 'system', 0))
                time.sleep(1.0)
                continue

            time.sleep(0.005)

        except Exception as e:
            debug_queue.put(f"Listener error: {e}")
            if inport:
                try: inport.close()
                except: pass
                inport = None
            if outport_global:
                try: outport_global.close()
                except: pass
                outport_global = None
            state["connected_port"] = None
            if state.get("piano_disconnected_since") is None:
                state["piano_disconnected_since"] = time.time()
            time.sleep(1.0)

threading.Thread(target=midi_listener, daemon=True).start()

class MetronomeRunner:
    """Unified metronome and tempo engine with configurable speed modes and seamless synchronized count-in."""
    def __init__(self, get_outport):
        self.get_outport = get_outport
        self.is_active = False  # True = Metronome click sound is ON, False = OFF
        self.speed_mode = 'normal'  # 'normal', 'slow', 'fast'
        self.bpm = METRONOME_CONFIG.get('normal', 80)
        self.is_running = False
        self._thread = None
        self._lock = threading.Lock()
        self._count_in_counter = 0
        self._count_in_callback = None
        self._temp_count_in = False

    def get_speed_ratio(self):
        norm = max(1.0, float(METRONOME_CONFIG.get('normal', 80)))
        return float(self.bpm) / norm

    def update_config(self, new_config):
        global METRONOME_CONFIG
        with self._lock:
            METRONOME_CONFIG = new_config
            if self.speed_mode in METRONOME_CONFIG:
                self.bpm = METRONOME_CONFIG[self.speed_mode]

    def set_speed_mode(self, mode):
        with self._lock:
            if mode in METRONOME_CONFIG:
                self.speed_mode = mode
                self.bpm = METRONOME_CONFIG[mode]

    def cycle_speed_mode(self):
        modes = ['normal', 'slow', 'fast']
        current_idx = modes.index(self.speed_mode) if self.speed_mode in modes else 0
        next_mode = modes[(current_idx + 1) % len(modes)]
        self.set_speed_mode(next_mode)
        return next_mode

    def toggle_active(self):
        with self._lock:
            self.is_active = not self.is_active
            if self.is_active:
                if not self.is_running:
                    self._start_thread()
            else:
                if self._count_in_counter <= 0:
                    self.stop()
            return self.is_active

    def set_active(self, active: bool):
        with self._lock:
            self.is_active = active
            if self.is_active:
                if not self.is_running:
                    self._start_thread()
            else:
                if self._count_in_counter <= 0:
                    self.stop()

    def get_speed_label(self):
        bpm = self.bpm
        return f"Speed: {self.speed_mode.capitalize()} ({bpm})"

    def get_active_label(self):
        return "⏱ Metro ON" if self.is_active else "⏱ Metro OFF"

    def _start_thread(self):
        self.is_running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.is_running = False
        outport = self.get_outport()
        if outport:
            try: outport.send(mido.Message('note_off', note=108, velocity=0))
            except Exception: pass

    def count_in_and_trigger(self, count=4, callback=None):
        """Play count beats in exact sync with current tempo, then execute callback on the downbeat."""
        with self._lock:
            self._count_in_counter = count
            self._count_in_callback = callback
            if not self.is_running:
                self._temp_count_in = True
                self._start_thread()
            else:
                self._temp_count_in = False

    def _run(self):
        beat_idx = 0
        while self.is_running:
            # Sound beat on highest piano note (108)
            outport = self.get_outport()
            if outport:
                try: outport.send(mido.Message('note_on', note=108, velocity=100))
                except Exception: pass

            with self._lock:
                if self._count_in_counter > 0:
                    beat_num = 5 - self._count_in_counter
                    midi_queue.put(('metronome_beat', beat_num, 'system', 0))
                else:
                    beat_idx = (beat_idx % 4) + 1
                    midi_queue.put(('metronome_tick', beat_idx, 'system', 0))

            time.sleep(0.08)

            outport = self.get_outport()
            if outport:
                try: outport.send(mido.Message('note_off', note=108, velocity=0))
                except Exception: pass

            beat_sec = 60.0 / max(20.0, float(self.bpm))
            rem = max(0.04, beat_sec - 0.08)
            slices = int(rem / 0.03)
            for _ in range(slices):
                if not self.is_running: break
                time.sleep(0.03)
            if self.is_running:
                time.sleep(rem % 0.03)

            with self._lock:
                if self._count_in_counter > 0:
                    self._count_in_counter -= 1
                    if self._count_in_counter == 0:
                        cb = self._count_in_callback
                        self._count_in_callback = None
                        if cb:
                            threading.Thread(target=cb, daemon=True).start()
                        if not self.is_active:
                            self.is_running = False
                            break

class Recorder:
    def __init__(self):
        self.is_recording = False
        self.events = []
        self.start_time = 0
    def start(self):
        self.is_recording = True
        self.events = []
        self.start_time = time.time()
    def stop(self):
        self.is_recording = False
    def add_event(self, action, note, vel):
        if self.is_recording:
            self.events.append({"time": time.time() - self.start_time, "type": action, "note": note, "vel": vel})

class Player:
    def __init__(self):
        self.is_playing = False
        self.events = []
        self.start_time = 0
        self.offset = 0
        self.speed = 1.0
        self.idx = 0
        self.duration = 0
        self.mute_drums = True
        self.piano_only_channel = True

    def silence(self):
        midi_queue.put(('clear_teacher', None, 'teacher', 0))
        if outport_global:
            for ch in range(16):
                try:
                    outport_global.send(mido.Message('control_change', channel=ch, control=123, value=0))
                    outport_global.send(mido.Message('control_change', channel=ch, control=120, value=0))
                except Exception:
                    pass

    def load(self, events, speed=1.0, mute_drums=True, piano_only_channel=True):
        self.silence()
        self.events = events
        self.duration = max([e['time'] for e in events]) if events else 0
        self.offset = 0
        self.idx = 0
        self.speed = speed
        self.is_playing = False
        self.mute_drums = mute_drums
        self.piano_only_channel = piano_only_channel

    def set_mute_drums(self, mute: bool):
        self.mute_drums = mute

    def set_speed(self, new_speed):
        new_speed = max(0.1, float(new_speed))
        if self.is_playing:
            current_offset = (time.time() - self.start_time) * self.speed
            self.speed = new_speed
            self.start_time = time.time() - (current_offset / self.speed)
        else:
            self.speed = new_speed

    def play(self):
        if not self.is_playing and self.events:
            self.is_playing = True
            self.start_time = time.time() - (self.offset / self.speed)
            threading.Thread(target=self._loop, daemon=True).start()

    def pause(self):
        self.is_playing = False
        if self.events:
            self.offset = (time.time() - self.start_time) * self.speed
        self.silence()

    def seek(self, pct):
        self.silence()
        self.offset = (pct / 100.0) * self.duration
        self.idx = 0
        while self.idx < len(self.events) and self.events[self.idx]['time'] < self.offset:
            self.idx += 1
        if self.is_playing:
            self.start_time = time.time() - (self.offset / self.speed)

    def _loop(self):
        while self.is_playing and self.idx < len(self.events):
            now = (time.time() - self.start_time) * self.speed
            ev = self.events[self.idx]
            if now >= ev['time']:
                ch = ev.get('channel', 0)
                is_drum = ev.get('is_drum', False) or (ch == 9)

                # Skip drum hits when mute_drums is active so they don't sound as loud piano keys
                if is_drum and self.mute_drums:
                    self.idx += 1
                    continue

                if is_drum:
                    target_ch = 9
                elif self.piano_only_channel:
                    target_ch = 0
                else:
                    target_ch = ch

                if outport_global:
                    try:
                        outport_global.send(mido.Message(
                            'note_on' if ev['type'] == 'on' else 'note_off',
                            channel=target_ch,
                            note=ev['note'],
                            velocity=ev['vel']
                        ))
                    except Exception:
                        pass

                # Only illuminate melodic notes on screen/staff
                if not is_drum:
                    midi_queue.put((ev['type'], ev['note'], 'teacher', ev['vel']))

                self.idx += 1
            else:
                time.sleep(0.01)
        if self.idx >= len(self.events):
            self.is_playing = False
            self.silence()

# ==========================================
# TOUCH-AWARE SCROLLABLE CONTAINER
# ==========================================
class TouchScrollFrame(tk.Frame):
    def __init__(self, parent, bg=BG_DARK, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.inner = tk.Frame(self.canvas, bg=bg)
        
        self.scrollbar = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview, bg=BG_SURFACE, troughcolor=BG_DARK, width=10)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor='nw')
        
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        
        self.canvas.bind("<Button-1>", self._on_touch_start)
        self.canvas.bind("<B1-Motion>", self._on_touch_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_touch_end)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))
        
        self._touch_start_y = 0
        self._touch_scroll_start = 0
        self.is_dragging = False

    def _on_inner_configure(self, event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.window_id, width=event.width)

    def _on_touch_start(self, event):
        self._touch_start_y = event.y_root
        self._touch_scroll_start = self.canvas.yview()[0]
        self.is_dragging = False

    def _on_touch_drag(self, event):
        dy = event.y_root - self._touch_start_y
        if abs(dy) > 6:
            self.is_dragging = True
            sr = self.canvas.cget("scrollregion")
            if sr:
                parts = [int(p) for p in sr.split()]
                total_h = max(1, parts[3] - parts[1])
                target = self._touch_scroll_start - (dy / float(total_h))
                self.canvas.yview_moveto(max(0.0, min(1.0, target)))

    def _on_touch_end(self, event):
        self.is_dragging = False

    def _on_mousewheel(self, event):
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            
    def bind_child_touch(self, widget):
        widget.bind("<Button-1>", self._on_touch_start, add="+")
        widget.bind("<B1-Motion>", self._on_touch_drag, add="+")
        widget.bind("<ButtonRelease-1>", self._on_touch_end, add="+")
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"), add="+")
        widget.bind("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"), add="+")
        for child in widget.winfo_children():
            self.bind_child_touch(child)

# ==========================================
# MODERN PILL BUTTON (ZERO TEXT TRUNCATION)
# ==========================================
class PillButton(tk.Canvas):
    def __init__(self, parent, text="", command=None, style='secondary', width=None, height=None, font=None, scale=1.0, scroll_parent=None, **kwargs):
        self.scale = scale
        self.text = text
        self.command = command
        self.style = style
        self.state = tk.NORMAL
        self.font = font or (FONT_MAIN, int(11.5 * scale), "bold")
        self.scroll_parent = scroll_parent
        self.requested_width = width
        self.requested_height = height
        
        self.btn_w, self.btn_h = self._calc_dimensions()
        
        p_bg = parent.cget('bg') if hasattr(parent, 'cget') else BG_DARK
        super().__init__(parent, width=self.btn_w, height=self.btn_h, bg=p_bg, highlightthickness=0, **kwargs)
        
        self.is_hover = False
        self.is_pressed = False
        self._drag_moved = False
        self._touch_start_y = 0
        
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        
        self.redraw()

    def _calc_dimensions(self):
        h = self.requested_height if self.requested_height is not None else int(34 * self.scale)
        try:
            if isinstance(self.font, tuple):
                f_obj = tkfont.Font(family=self.font[0], size=self.font[1], weight=self.font[2] if len(self.font)>2 else 'normal')
            else:
                f_obj = tkfont.Font(font=self.font)
            lines = self.text.split('\n')
            max_line_w = max([f_obj.measure(l) for l in lines]) if lines else 0
        except Exception:
            lines = self.text.split('\n')
            max_line_w = max([len(l) for l in lines]) * int(8.5 * self.scale) if lines else 0
            
        # Generous padding on left and right for pill endcaps to guarantee no truncation
        min_w = max_line_w + int(24 * self.scale)
        if self.requested_width is not None:
            w = max(self.requested_width, min_w)
        else:
            w = max(int(60 * self.scale), min_w)
        return w, h

    def _on_enter(self, e):
        if self.state != tk.DISABLED:
            self.is_hover = True
            self.redraw()

    def _on_leave(self, e):
        self.is_hover = False
        self.is_pressed = False
        self.redraw()

    def _on_press(self, e):
        if self.state != tk.DISABLED:
            self._touch_start_y = e.y_root
            self._drag_moved = False
            self.is_pressed = True
            self.redraw()
            if self.scroll_parent:
                self.scroll_parent._on_touch_start(e)

    def _on_motion(self, e):
        if hasattr(self, '_touch_start_y') and abs(e.y_root - self._touch_start_y) > 8:
            self._drag_moved = True
            if self.is_pressed:
                self.is_pressed = False
                self.redraw()
            if self.scroll_parent:
                self.scroll_parent._on_touch_drag(e)

    def _on_release(self, e):
        if self.scroll_parent:
            self.scroll_parent._on_touch_end(e)
        if self.state != tk.DISABLED and self.is_pressed and not self._drag_moved:
            self.is_pressed = False
            self.redraw()
            if self.command:
                self.command()
        else:
            self.is_pressed = False
            self.redraw()

    def redraw(self):
        self.delete("all")
        w, h = self.btn_w, self.btn_h
        r = min(h / 2.0, 18 * self.scale)
        offset_y = 1 if self.is_pressed else 0
        
        styles = {
            'primary': {
                'fill': ACCENT_PRIMARY if not self.is_hover else ACCENT_HOVER,
                'outline': '',
                'text': TEXT_DARK
            },
            'secondary': {
                'fill': BG_SURFACE if not self.is_hover else '#2c3b52',
                'outline': BORDER_SUBTLE,
                'text': TEXT_PRIMARY
            },
            'danger': {
                'fill': COLOR_DANGER_BG if not self.is_hover else '#3d2532',
                'outline': '#5c2d3a',
                'text': COLOR_DANGER
            },
            'success': {
                'fill': COLOR_SUCCESS if not self.is_hover else '#14b8a6',
                'outline': '',
                'text': TEXT_DARK
            },
            'ghost': {
                'fill': self.cget('bg'),
                'outline': '',
                'text': TEXT_SECONDARY if not self.is_hover else TEXT_PRIMARY
            }
        }
        cfg = styles.get(self.style, styles['secondary'])
        if self.state == tk.DISABLED:
            cfg = {'fill': '#1a2230', 'outline': '#243042', 'text': '#64748b'}
            
        points = [
            1+r, 1+offset_y,       w-1-r, 1+offset_y,
            w-1, 1+offset_y,       w-1, 1+r+offset_y,
            w-1, h-1-r+offset_y,   w-1, h-1+offset_y,
            w-1-r, h-1+offset_y,   1+r, h-1+offset_y,
            1, h-1+offset_y,       1, h-1-r+offset_y,
            1, 1+r+offset_y,       1, 1+offset_y
        ]
        self.create_polygon(points, fill=cfg['fill'], outline=cfg['outline'], width=1, smooth=True)
        self.create_text(w/2, h/2 + offset_y, text=self.text, font=self.font, fill=cfg['text'], justify='center')

    def config(self, **kwargs):
        if 'text' in kwargs:
            self.text = kwargs.pop('text')
            new_w, new_h = self._calc_dimensions()
            self.btn_w = new_w
            self.btn_h = new_h
            self.configure(width=new_w, height=new_h)
        if 'state' in kwargs:
            self.state = kwargs.pop('state')
        if 'style' in kwargs:
            self.style = kwargs.pop('style')
        if 'command' in kwargs:
            self.command = kwargs.pop('command')
        self.redraw()
        
    configure = config

# ==========================================
# MAIN APPLICATION
# ==========================================
class PianoTimerApp:
    def __init__(self, root):
        global FONT_MAIN
        self.root = root
        self.root.title("Piano Practice Timer")
        self.root.attributes('-fullscreen', True)
        self.root.update_idletasks()
        
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if sw <= 1: sw = 1920
        if sh <= 1: sh = 1080
        self.scale = min(sw / 800.0, sh / 480.0)
        
        self.font_family = detect_geometric_font()
        FONT_MAIN = self.font_family
        
        self.f_title = int(22 * self.scale)
        self.f_sub = int(10 * self.scale)
        self.f_btn = int(12.5 * self.scale)
        self.f_grid_name = int(10 * self.scale)
        self.f_grid_count = int(8.5 * self.scale)
        self.f_clef = int(62 * self.scale)
        
        # Sizing balanced for 800x480 touchscreen so piano has full height
        self.piano_h = int(122 * self.scale)
        self.clock_size = int(216 * self.scale)
        self.clock_h = int(195 * self.scale)
        self.mini_w = int(72 * self.scale)
        self.mini_h = int(30 * self.scale)
        self.chords_card_w = int(246 * self.scale)
        self.staff_w = int(230 * self.scale)
        self.staff_h = int(195 * self.scale)
        self.step_y = 8.5 * self.scale
        self.mc_y = 110 * self.scale
        
        self.root.configure(bg=BG_DARK) 
        
        self.app_mode = 'select' 
        self.recorder = Recorder()
        self.player = Player()
        self.metronome_runner = MetronomeRunner(lambda: outport_global)
        self.active_class = None
        self.recorded_chords = []
        self.is_listening_for_chord = False
        self.chord_hold_start = 0
        self.delete_confirm_cid = None
        
        self.drawn_notes = {}
        self.teacher_notes = {}
        self.note_velocities = {}
        self.is_debug_open = False
        self.show_admin_controls = False
        self.secret_combo_start = 0.0
        self.diag_btn = None
        self.exit_btn = None
        
        self.clock_target_extent = 0.0
        self.clock_current_extent = 0.0
        self.confetti_particles = []
        self.fading_notes = {}
        self.active_tamagotchi_views = []
        
        # IN-APP FULL-SCREEN CONTAINERS (ZERO POPUP WINDOWS)
        self.select_frame = tk.Frame(self.root, bg=BG_DARK)
        self.session_frame = tk.Frame(self.root, bg=BG_DARK)
        self.classes_list_frame = tk.Frame(self.root, bg=BG_DARK)
        self.class_select_frame = tk.Frame(self.root, bg=BG_DARK)
        self.record_frame = tk.Frame(self.root, bg=BG_DARK)
        self.keyboard_frame = tk.Frame(self.root, bg=BG_DARK)
        self.recap_frame = tk.Frame(self.root, bg=BG_DARK)
        self.debug_frame = tk.Frame(self.root, bg=BG_DARK)
        self.buddy_detail_frame = tk.Frame(self.root, bg=BG_DARK)
        
        # Screen sleep / power-saving overlay for Pi touchscreen
        self.is_screen_sleeping = False
        self.last_user_touch_time = time.time()
        self.sleep_overlay = tk.Frame(self.root, bg='black', cursor='none')
        self.sleep_overlay.bind("<Button-1>", self.on_sleep_overlay_touch)
        self.root.bind_all("<Button-1>", self.on_any_touch, add="+")

        # Shared bottom piano with full guaranteed height and felt rail
        self.shared_piano_frame = tk.Frame(self.root, height=self.piano_h, bg=BG_DARK)
        self.piano_card = tk.Frame(self.shared_piano_frame, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.piano_card.pack(fill=tk.BOTH, expand=True, padx=int(14*self.scale), pady=(int(4*self.scale), int(6*self.scale)))
        self.piano_canvas = tk.Canvas(self.piano_card, height=self.piano_h, bg=BG_CARD, highlightthickness=0)
        self.piano_canvas.pack(fill=tk.BOTH, expand=True)
        self.piano_canvas.bind('<Configure>', self.on_piano_resize)
        
        self.build_select_screen()
        self.build_session_screen()
        self.build_classes_list_screen()
        self.build_record_screen()
        self.update_metronome_ui()
        self.last_config_mtime = os.path.getmtime(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else 0
        self.current_session_data = None
        self.current_playing_song_id = None
        self.current_playing_song_title = None
        self._last_live_state_save = 0
        self._last_config_check = 0
        
        self.start_web_server()
        
        self.show_select_screen()
        self.update_timer()

    def start_web_server(self):
        try:
            import web_server
            web_server.set_piano_app(self)
            web_server.start_background_server(port=8080)
            print("Web dashboard running on http://0.0.0.0:8080")
        except Exception as e:
            print(f"Could not start background web server: {e}")

    def play_song(self, song_data, speed=1.0, mute_drums=True, piano_only=True):
        if not song_data: return
        self.wake_screen()
        self.current_playing_song_id = song_data.get("id")
        self.current_playing_song_title = song_data.get("title", "Song Playback")
        events = song_data.get("midi_events", [])
        self.player.load(events, speed=speed, mute_drums=mute_drums, piano_only_channel=piano_only)
        self.player.play()

    def pause_song(self):
        self.player.pause()

    def resume_song(self):
        self.player.play()

    def stop_song(self):
        self.player.pause()
        self.player.seek(0)
        self.player.silence()
        self.current_playing_song_id = None
        self.current_playing_song_title = None

    def seek_song(self, pct):
        self.player.seek(pct)

    def set_song_speed(self, speed):
        self.player.set_speed(speed)

    def set_mute_drums(self, mute_drums):
        self.player.set_mute_drums(mute_drums)

    def check_web_commands(self):
        if not os.path.exists(COMMAND_FILE): return
        try:
            cmd = load_json(COMMAND_FILE, None)
            if cmd and not cmd.get("processed"):
                cmd["processed"] = True
                save_json(COMMAND_FILE, cmd)
                action = cmd.get("action")
                if action == "play_song":
                    self.play_song(
                        cmd.get("song"),
                        speed=cmd.get("speed", 1.0),
                        mute_drums=cmd.get("mute_drums", True),
                        piano_only=cmd.get("piano_only", True)
                    )
                elif action == "pause":
                    self.pause_song()
                elif action == "resume":
                    self.resume_song()
                elif action == "stop":
                    self.stop_song()
                elif action == "seek":
                    self.seek_song(cmd.get("percent", 0))
                elif action == "speed":
                    self.set_song_speed(cmd.get("speed", 1.0))
                elif action == "toggle_mute_drums":
                    self.set_mute_drums(cmd.get("mute_drums", True))
        except Exception:
            pass

    def check_reload_config(self):
        global GOAL_TIME_SECONDS, PLAYERS, METRONOME_CONFIG
        try:
            if not os.path.exists(CONFIG_FILE): return
            mtime = os.path.getmtime(CONFIG_FILE)
            if mtime > getattr(self, 'last_config_mtime', 0):
                self.last_config_mtime = mtime
                cfg = load_json(CONFIG_FILE, {})
                if cfg:
                    GOAL_TIME_SECONDS = cfg.get("goal_minutes", 15) * 60
                    PLAYERS = cfg.get("players", ["Eva", "Mara", "Willy"])
                    METRONOME_CONFIG = cfg.get("metronome", METRONOME_CONFIG)
                    if hasattr(self, 'metronome_runner'):
                        self.metronome_runner.update_config(METRONOME_CONFIG)
                    if self.app_mode == 'select':
                        self.build_select_screen()
        except Exception:
            pass

    def sleep_screen(self):
        if not self.is_screen_sleeping:
            self.is_screen_sleeping = True
            self.sleep_overlay.place(x=0, y=0, relwidth=1, relheight=1)
            self.sleep_overlay.lift()
            set_display_power(False)

    def wake_screen(self):
        self.last_user_touch_time = time.time()
        if self.is_screen_sleeping:
            self.is_screen_sleeping = False
            set_display_power(True)
            self.sleep_overlay.place_forget()

    def on_any_touch(self, event=None):
        self.last_user_touch_time = time.time()
        if self.is_screen_sleeping:
            self.wake_screen()

    def on_sleep_overlay_touch(self, event=None):
        self.last_user_touch_time = time.time()
        self.wake_screen()

    def hide_all(self):
        if hasattr(self, 'active_tamagotchi_views'):
            for tv in self.active_tamagotchi_views:
                try:
                    tv.stop_animation()
                except Exception:
                    pass
            self.active_tamagotchi_views = []
        for f in [
            self.select_frame, self.session_frame, self.classes_list_frame,
            self.class_select_frame, self.record_frame, self.keyboard_frame,
            self.recap_frame, self.debug_frame, self.buddy_detail_frame
        ]:
            f.pack_forget()
        if hasattr(self, 'shared_piano_frame'):
            self.shared_piano_frame.pack_forget()
        if hasattr(self, 'playback_controls_frame'):
            self.playback_controls_frame.pack_forget()

    def round_rect(self, canvas, x1, y1, x2, y2, radius=16, **kwargs):
        points = [
            x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1,
            x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius,
            x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2,
            x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1
        ]
        return canvas.create_polygon(points, **kwargs, smooth=True)

    def draw_star(self, canvas, cx, cy, radius, fill='yellow', tags=""):
        points = []
        for i in range(10):
            angle = i * math.pi / 5 - math.pi / 2
            r = radius if i % 2 == 0 else radius * 0.42
            points.append(cx + math.cos(angle) * r)
            points.append(cy + math.sin(angle) * r)
        outline_col = '#f59e0b' if fill == COLOR_WARNING else '#334155'
        return canvas.create_polygon(points, fill=fill, outline=outline_col, width=1, tags=tags)

    def animate_star_pop(self, canvas, cx, cy, final_radius, fill, delay_ms):
        if fill == BORDER_SUBTLE:
            self.draw_star(canvas, cx, cy, final_radius, fill=fill)
            return
        def _pop_step(step):
            canvas.delete(f"star_{cx}_{cy}")
            scales = [0.3, 0.7, 1.25, 1.1, 1.0]
            if step < len(scales):
                r = final_radius * scales[step]
                self.draw_star(canvas, cx, cy, r, fill=fill, tags=f"star_{cx}_{cy}")
                self.root.after(35, lambda: _pop_step(step + 1))
            else:
                self.draw_star(canvas, cx, cy, final_radius, fill=fill, tags=f"star_{cx}_{cy}")
        self.root.after(delay_ms, lambda: _pop_step(0))

    def calculate_stars(self, player):
        progress = load_json(PROGRESS_FILE, {})
        history = progress.get(player, {}).get("history", [])
        import datetime
        today = datetime.date.today()
        count_last_5, played_last_24h = 0, False
        for d_str in history:
            try:
                diff = (today - datetime.datetime.strptime(d_str, "%Y-%m-%d").date()).days
                if 0 <= diff <= 5: count_last_5 += 1
                if 0 <= diff <= 1: played_last_24h = True
            except: pass
        if count_last_5 >= 3: return 3
        if count_last_5 == 2: return 2
        if played_last_24h: return 1
        return 0

    def save_current_progress(self):
        if state["selected_player"] == "Guest" or not state["selected_player"]: return
        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        progress = load_json(PROGRESS_FILE, {})
        if state["selected_player"] not in progress: progress[state["selected_player"]] = {"date": today_str, "time": 0.0, "history": []}
        p = progress[state["selected_player"]]
        if p.get("date") != today_str: p.update({"date": today_str, "time": 0.0})
        p["time"] = max(p.get("time", 0.0), state["accumulated_time"])
        if p["time"] >= GOAL_TIME_SECONDS:
            if "history" not in p: p["history"] = []
            if today_str not in p["history"]: p["history"].append(today_str)
        save_json(PROGRESS_FILE, progress)

    # ==========================================
    # SCREEN 1: SELECT PLAYER (SCROLLABLE HOME)
    # ==========================================
    def build_select_screen(self):
        for widget in self.select_frame.winfo_children(): widget.destroy()
        s = self.scale
        
        top_frame = tk.Frame(self.select_frame, bg=BG_DARK)
        top_frame.pack(fill=tk.X, pady=(int(10*s), int(4*s)), padx=int(22*s))
        
        PillButton(top_frame, text="📖 Classes", style='secondary', scale=s, height=int(36*s), command=self.show_classes_list_screen).pack(side=tk.LEFT, padx=(0, int(8*s)))
        self.diag_btn = PillButton(top_frame, text="⚙ MIDI Diagnostics", style='secondary', scale=s, height=int(36*s), command=self.show_debug_screen)
        self.exit_btn = PillButton(top_frame, text="Exit", style='danger', scale=s, height=int(36*s), command=self.root.destroy)
        
        if self.show_admin_controls:
            self.diag_btn.pack(side=tk.LEFT, padx=(0, int(8*s)))
            self.exit_btn.pack(side=tk.RIGHT)
        
        scroll = TouchScrollFrame(self.select_frame, bg=BG_DARK)
        scroll.pack(fill=tk.BOTH, expand=True, padx=int(20*s), pady=int(4*s))
        
        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        progress = load_json(PROGRESS_FILE, {})
        
        for player in PLAYERS + ["Guest"]:
            row_frame = tk.Frame(scroll.inner, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(18*s), pady=int(8*s))
            row_frame.pack(fill=tk.X, pady=int(5*s))
            scroll.bind_child_touch(row_frame)
            
            tk.Label(row_frame, text=player, font=(self.font_family, int(26*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY, width=6, anchor='w').pack(side=tk.LEFT)
            btn_w, btn_h = int(270*s), int(64*s)
            btn_cvs = tk.Canvas(row_frame, width=btn_w, height=btn_h, bg=BG_CARD, highlightthickness=0)
            btn_cvs.pack(side=tk.LEFT, padx=int(12*s))
            scroll.bind_child_touch(btn_cvs)
            
            r_btn = int(14*s)
            if player == "Guest":
                self.round_rect(btn_cvs, 0, 0, btn_w, btn_h, radius=r_btn, fill=BG_SURFACE, outline=BORDER_SUBTLE)
                btn_cvs.create_text(btn_w/2, btn_h/2, text="Free Play\n(No goal timer)", font=(self.font_family, int(15*s), "bold"), fill=TEXT_PRIMARY, justify='center')
            else:
                t_time = progress.get(player, {}).get("time", 0.0) if progress.get(player, {}).get("date", "") == today_str else 0.0
                pct = min(1.0, t_time / GOAL_TIME_SECONDS)
                self.round_rect(btn_cvs, 0, 0, btn_w, btn_h, radius=r_btn, fill=BG_SURFACE, outline=BORDER_SUBTLE)
                if pct >= 0.99:
                    mins_practiced = int(t_time // 60)
                    self.round_rect(btn_cvs, 0, 0, btn_w, btn_h, radius=r_btn, fill=COLOR_SUCCESS)
                    btn_cvs.create_text(btn_w/2, btn_h/2, text=f"✔ Goal Completed! ({mins_practiced}m)\nTap to keep practicing", font=(self.font_family, int(14*s), "bold"), fill=TEXT_DARK, justify='center')
                elif pct > 0:
                    btn_cvs.create_rectangle(0, 0, btn_w * pct, btn_h, fill=ACCENT_PRIMARY, outline='')
                    btn_cvs.create_text(btn_w/2, btn_h/2, text=f"Continue Practice ({int(pct*100)}%)\n15 min daily goal", font=(self.font_family, int(14*s), "bold"), fill=TEXT_DARK if pct > 0.5 else TEXT_PRIMARY, justify='center')
                else:
                    btn_cvs.create_text(btn_w/2, btn_h/2, text="Start Practice\n15 min daily goal", font=(self.font_family, int(14*s), "bold"), fill=TEXT_PRIMARY, justify='center')
                    
            btn_cvs.bind("<Button-1>", lambda e, p=player: self.start_session(p))
            
            mascot_container = tk.Frame(row_frame, bg=BG_CARD)
            mascot_container.pack(side=tk.LEFT, padx=(int(6*s), 0), fill=tk.BOTH, expand=True)
            scroll.bind_child_touch(mascot_container)
            
            if player != "Guest":
                t_info = tamagotchi.calculate_tamagotchi(player, progress, goal_seconds=GOAL_TIME_SECONDS)
                mascot_cvs = tk.Canvas(mascot_container, width=int(75*s), height=btn_h, bg=BG_CARD, highlightthickness=0)
                mascot_cvs.pack(side=tk.LEFT)
                scroll.bind_child_touch(mascot_cvs)
                
                view_3d = tamagotchi.Tamagotchi3DView(
                    mascot_cvs, cx=int(37*s), cy=int(btn_h/2), scale=0.62*s,
                    version=t_info["version"], mood=t_info["mood"],
                    base_color=t_info.get("base_color")
                )
                view_3d.start_animation(fps=24)
                self.active_tamagotchi_views.append(view_3d)
                
                info_box = tk.Frame(mascot_container, bg=BG_CARD)
                info_box.pack(side=tk.LEFT, padx=(int(6*s), 0), fill=tk.Y)
                scroll.bind_child_touch(info_box)
                
                mood_col = COLOR_SUCCESS if t_info["mood"] == 'happy' else (COLOR_WARNING if t_info["mood"] == 'hungry' else '#94a3b8')
                streak_txt = f"{t_info['streak']}d streak" if t_info['streak'] > 0 else "no streak"
                
                lbl_title = tk.Label(info_box, text=f"Lv.{t_info['version']} {t_info['version_name']}", font=(self.font_family, int(11*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY, anchor='w')
                lbl_title.pack(anchor='w', pady=(int(5*s), 0))
                scroll.bind_child_touch(lbl_title)
                
                lbl_sub = tk.Label(info_box, text=f"{t_info['mood_label']} • {streak_txt}", font=(self.font_family, int(10*s), "bold"), bg=BG_CARD, fg=mood_col, anchor='w')
                lbl_sub.pack(anchor='w', pady=(int(2*s), 0))
                scroll.bind_child_touch(lbl_sub)

                lbl_hint = tk.Label(info_box, text="🔍 Tap for stats →", font=(self.font_family, int(9*s)), bg=BG_CARD, fg=TEXT_MUTED, anchor='w')
                lbl_hint.pack(anchor='w', pady=(int(1*s), 0))
                scroll.bind_child_touch(lbl_hint)

                def _open_buddy(e, p=player):
                    if not getattr(scroll, 'is_dragging', False):
                        self.show_buddy_details(p)

                for w in (mascot_container, mascot_cvs, info_box, lbl_title, lbl_sub, lbl_hint):
                    w.bind("<ButtonRelease-1>", _open_buddy, add="+")
                    try: w.config(cursor="hand2")
                    except Exception: pass
            else:
                guest_cvs = tk.Canvas(mascot_container, width=int(75*s), height=btn_h, bg=BG_CARD, highlightthickness=0)
                guest_cvs.pack(side=tk.LEFT)
                scroll.bind_child_touch(guest_cvs)
                
                guest_view = tamagotchi.Tamagotchi3DView(
                    guest_cvs, cx=int(37*s), cy=int(btn_h/2), scale=0.55*s,
                    version=1, mood='happy'
                )
                guest_view.start_animation(fps=24)
                self.active_tamagotchi_views.append(guest_view)
                
                info_box = tk.Frame(mascot_container, bg=BG_CARD)
                info_box.pack(side=tk.LEFT, padx=(int(6*s), 0), fill=tk.Y)
                scroll.bind_child_touch(info_box)
                
                lbl_g1 = tk.Label(info_box, text="Guest Buddy", font=(self.font_family, int(11*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY, anchor='w')
                lbl_g1.pack(anchor='w', pady=(int(5*s), 0))
                scroll.bind_child_touch(lbl_g1)
                
                lbl_g2 = tk.Label(info_box, text="Free practice", font=(self.font_family, int(10*s)), bg=BG_CARD, fg=TEXT_SECONDARY, anchor='w')
                lbl_g2.pack(anchor='w', pady=(int(2*s), 0))
                scroll.bind_child_touch(lbl_g2)

                lbl_ghint = tk.Label(info_box, text="🔍 Tap for stats →", font=(self.font_family, int(9*s)), bg=BG_CARD, fg=TEXT_MUTED, anchor='w')
                lbl_ghint.pack(anchor='w', pady=(int(1*s), 0))
                scroll.bind_child_touch(lbl_ghint)

                def _open_guest(e):
                    if not getattr(scroll, 'is_dragging', False):
                        self.show_buddy_details("Guest")

                for w in (mascot_container, guest_cvs, info_box, lbl_g1, lbl_g2, lbl_ghint):
                    w.bind("<ButtonRelease-1>", _open_guest, add="+")
                    try: w.config(cursor="hand2")
                    except Exception: pass
                    
        tk.Label(self.select_frame, text="🐾 Mascot Companion: Complete daily practice to feed & evolve your mascot!", font=(self.font_family, int(11*s)), bg=BG_DARK, fg=TEXT_SECONDARY).pack(pady=(int(4*s), int(8*s)), anchor='center')

    def update_select_screen_admin_buttons(self):
        s = self.scale
        if hasattr(self, 'diag_btn') and hasattr(self, 'exit_btn') and self.diag_btn and self.exit_btn:
            if self.show_admin_controls:
                self.diag_btn.pack(side=tk.LEFT, padx=(0, int(8*s)))
                self.exit_btn.pack(side=tk.RIGHT)
            else:
                self.diag_btn.pack_forget()
                self.exit_btn.pack_forget()

    # ==========================================
    # SCREEN: FULL-SCREEN BUDDY SHOWCASE & STATS
    # ==========================================
    def show_buddy_details(self, player):
        self.hide_all()
        for w in self.buddy_detail_frame.winfo_children(): w.destroy()
        s = self.scale
        self.app_mode = 'buddy_details'

        # Load stats
        stats = tamagotchi.get_student_stats(player, goal_seconds=GOAL_TIME_SECONDS)
        t_info = stats["tamagotchi"]

        # 1. Top Navigation Bar
        top_bar = tk.Frame(self.buddy_detail_frame, bg=BG_DARK)
        top_bar.pack(fill=tk.X, pady=(int(10*s), int(6*s)), padx=int(18*s))

        PillButton(
            top_bar, text="← Back to Home", style='secondary', scale=s, height=int(36*s),
            command=self.show_select_screen
        ).pack(side=tk.LEFT)

        tk.Label(
            top_bar, text=f"🐾 {player.upper()}'S COMPANION & STATS",
            font=(self.font_family, int(20*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY
        ).pack(side=tk.LEFT, padx=int(16*s))

        badge_txt = f"Lv.{t_info['version']} {t_info['version_name']}"
        tk.Label(
            top_bar, text=badge_txt,
            font=(self.font_family, int(13*s), "bold"), bg=BG_DARK, fg=COLOR_WARNING
        ).pack(side=tk.RIGHT)

        # 2. Split Body (Left: 3D Buddy Showcase, Right: Stats Panel)
        body = tk.Frame(self.buddy_detail_frame, bg=BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=int(18*s), pady=(0, int(10*s)))

        # Left Column: Big 3D Buddy Showcase Card
        left_card = tk.Frame(body, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(14*s), pady=int(10*s), width=int(320*s))
        left_card.pack(side=tk.LEFT, fill=tk.BOTH, padx=(0, int(10*s)))
        left_card.pack_propagate(False)

        cvs_w, cvs_h = int(290*s), int(250*s)
        buddy_cvs = tk.Canvas(left_card, width=cvs_w, height=cvs_h, bg=BG_CARD, highlightthickness=0)
        buddy_cvs.pack(anchor='center')

        big_buddy = tamagotchi.Tamagotchi3DView(
            buddy_cvs, cx=int(cvs_w / 2), cy=int(cvs_h / 2),
            scale=1.35 * s, version=t_info["version"], mood=t_info["mood"],
            base_color=t_info.get("base_color")
        )
        big_buddy.start_animation(fps=30)
        self.active_tamagotchi_views.append(big_buddy)

        tk.Label(
            left_card, text="★ Tap buddy to interact!",
            font=(self.font_family, int(11*s)), bg=BG_CARD, fg=TEXT_SECONDARY
        ).pack(pady=(int(4*s), int(4*s)))

        mood_pill = tk.Frame(left_card, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(10*s), pady=int(4*s))
        mood_pill.pack(fill=tk.X, pady=int(4*s))

        mood_col = COLOR_SUCCESS if t_info["mood"] == 'happy' else (COLOR_WARNING if t_info["mood"] == 'hungry' else '#94a3b8')
        tk.Label(
            mood_pill, text=f"Mood: {t_info['mood_label']}",
            font=(self.font_family, int(12*s), "bold"), bg=BG_SURFACE, fg=mood_col
        ).pack(side=tk.LEFT)

        tk.Label(
            mood_pill, text=f"🔥 {t_info['streak']}d streak",
            font=(self.font_family, int(12*s), "bold"), bg=BG_SURFACE, fg=TEXT_PRIMARY
        ).pack(side=tk.RIGHT)

        # Right Column: Practice Stats
        right_card = tk.Frame(body, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(18*s), pady=int(12*s))
        right_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(
            right_card, text="PRACTICE MILESTONES & STATS",
            font=(self.font_family, int(12*s), "bold"), bg=BG_CARD, fg=TEXT_SECONDARY, anchor='w'
        ).pack(anchor='w', pady=(0, int(8*s)))

        # Format stats
        tot_secs = stats["total_time_seconds"]
        tot_hours = int(tot_secs // 3600)
        tot_mins = int((tot_secs % 3600) // 60)
        if tot_hours > 0:
            time_str = f"{tot_hours}h {tot_mins:02d}m"
        else:
            time_str = f"{tot_mins} mins"

        notes_wk_str = f"{stats['notes_last_week']:,}"
        sess_str = f"{stats['total_sessions']} sessions ({stats['total_days_completed']} days goal met)"
        
        today_m = int(stats["today_seconds"] // 60)
        today_s = int(stats["today_seconds"] % 60)
        goal_m = int(GOAL_TIME_SECONDS // 60)
        today_pct = min(100, int((stats["today_seconds"] / GOAL_TIME_SECONDS) * 100))

        stat_items = [
            ("🎵 Total Times Practiced", sess_str, "Lifetime sessions and daily goals met"),
            ("🎹 Notes Played Last Week", f"{notes_wk_str} notes", "Piano keys pressed in the last 7 days"),
            ("⏱ Total Practice Time", time_str, "Accumulated lifetime keyboard practice time"),
            ("📅 Today's Progress", f"{today_m}m {today_s:02d}s ({today_pct}%)", f"Daily goal: {goal_m} mins {'(✔ Met)' if today_pct >= 100 else ''}")
        ]

        for title, val, sub in stat_items:
            row = tk.Frame(right_card, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(12*s), pady=int(6*s))
            row.pack(fill=tk.X, pady=int(3*s))

            t_box = tk.Frame(row, bg=BG_SURFACE)
            t_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tk.Label(t_box, text=title, font=(self.font_family, int(11*s), "bold"), bg=BG_SURFACE, fg=TEXT_SECONDARY, anchor='w').pack(anchor='w')
            tk.Label(t_box, text=sub, font=(self.font_family, int(9*s)), bg=BG_SURFACE, fg=TEXT_MUTED, anchor='w').pack(anchor='w')

            tk.Label(row, text=val, font=(self.font_family, int(14*s), "bold"), bg=BG_SURFACE, fg=ACCENT_PRIMARY).pack(side=tk.RIGHT)

        # Top chords row if available
        top_chords = stats.get("top_chords", [])
        if top_chords:
            chords_frame = tk.Frame(right_card, bg=BG_CARD)
            chords_frame.pack(fill=tk.X, pady=(int(8*s), 0))
            tk.Label(chords_frame, text="Top Chords Played:", font=(self.font_family, int(11*s), "bold"), bg=BG_CARD, fg=TEXT_SECONDARY, anchor='w').pack(anchor='w', pady=(0, int(2*s)))
            c_row = tk.Frame(chords_frame, bg=BG_CARD)
            c_row.pack(fill=tk.X)
            for cname, ccount in top_chords[:3]:
                c_pill = tk.Frame(c_row, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(8*s), pady=int(3*s))
                c_pill.pack(side=tk.LEFT, padx=(0, int(6*s)))
                tk.Label(c_pill, text=f"{cname}: {ccount}x", font=(self.font_family, int(10*s), "bold"), bg=BG_SURFACE, fg=TEXT_PRIMARY).pack()

        self.buddy_detail_frame.pack(fill=tk.BOTH, expand=True)

    # ==========================================
    # SCREEN 2: CLASSES LIST (SCROLLABLE & INLINE)
    # ==========================================
    def build_classes_list_screen(self):
        for w in self.classes_list_frame.winfo_children(): w.destroy()
        s = self.scale
        top_frame = tk.Frame(self.classes_list_frame, bg=BG_DARK)
        top_frame.pack(fill=tk.X, pady=(int(12*s), int(4*s)), padx=int(25*s))
        
        PillButton(top_frame, text="← Back", style='secondary', scale=s, height=int(36*s), command=self.show_select_screen).pack(side=tk.RIGHT)
        tk.Label(top_frame, text="Teacher's Classes", font=(self.font_family, int(22*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        
        scroll = TouchScrollFrame(self.classes_list_frame, bg=BG_DARK)
        scroll.pack(expand=True, fill=tk.BOTH, padx=int(30*s), pady=int(6*s))
        classes = load_json(CLASSES_FILE, [])
        if not classes:
            tk.Label(scroll.inner, text="No pre-recorded classes yet.\nTap below to record your first lesson!", font=(self.font_family, int(17*s)), bg=BG_DARK, fg=TEXT_MUTED, justify='center').pack(pady=int(40*s), expand=True)
        for c in classes:
            row = tk.Frame(scroll.inner, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(18*s), pady=int(8*s))
            row.pack(fill=tk.X, pady=int(5*s))
            scroll.bind_child_touch(row)
            
            if getattr(self, 'delete_confirm_cid', None) == c["id"]:
                tk.Label(row, text=f"Delete '{c['name']}'?", font=(self.font_family, int(16*s), "bold"), bg=BG_CARD, fg=COLOR_DANGER).pack(side=tk.LEFT, expand=True, fill=tk.X)
                PillButton(row, text="Confirm Delete", style='danger', scale=s, height=int(32*s), command=lambda cid=c["id"]: self.confirm_delete_class(cid)).pack(side=tk.LEFT, padx=int(4*s))
                PillButton(row, text="Cancel", style='secondary', scale=s, height=int(32*s), command=lambda: setattr(self, 'delete_confirm_cid', None) or self.build_classes_list_screen()).pack(side=tk.LEFT, padx=int(4*s))
            else:
                tk.Label(row, text=c["name"], font=(self.font_family, int(18*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY, anchor='w').pack(side=tk.LEFT, expand=True, fill=tk.X)
                PillButton(row, text="Edit Name", style='secondary', scale=s, height=int(32*s), scroll_parent=scroll, command=lambda cid=c["id"]: self.edit_class(cid)).pack(side=tk.LEFT, padx=int(6*s))
                PillButton(row, text="Delete", style='danger', scale=s, height=int(32*s), scroll_parent=scroll, command=lambda cid=c["id"]: self.delete_class_prompt(cid)).pack(side=tk.LEFT, padx=int(6*s))
            
        PillButton(self.classes_list_frame, text="+ Record New Session", style='primary', scale=s, height=int(42*s), command=self.show_record_screen).pack(pady=(int(6*s), int(12*s)))

    def delete_class_prompt(self, cid):
        self.delete_confirm_cid = cid
        self.build_classes_list_screen()

    def confirm_delete_class(self, cid):
        classes = [c for c in load_json(CLASSES_FILE, []) if c["id"] != cid]
        save_json(CLASSES_FILE, classes)
        self.delete_confirm_cid = None
        self.build_classes_list_screen()

    # ==========================================
    # SCREEN 3: IN-APP ONSCREEN KEYBOARD
    # ==========================================
    def show_onscreen_keyboard(self, prompt_text, initial_value, on_complete, on_cancel):
        self.hide_all()
        for w in self.keyboard_frame.winfo_children(): w.destroy()
        s = self.scale
        
        current_text = tk.StringVar(value=initial_value)
        is_shift = tk.BooleanVar(value=True)
        
        top_bar = tk.Frame(self.keyboard_frame, bg=BG_DARK)
        top_bar.pack(fill=tk.X, padx=int(25*s), pady=(int(12*s), int(4*s)))
        tk.Label(top_bar, text=prompt_text, font=(self.font_family, int(18*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        
        entry_frame = tk.Frame(self.keyboard_frame, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_FOCUS)
        entry_frame.pack(fill=tk.X, padx=int(25*s), pady=int(6*s))
        
        entry_lbl = tk.Label(entry_frame, textvariable=current_text, font=(self.font_family, int(22*s)), bg=BG_SURFACE, fg=TEXT_PRIMARY, anchor='w', padx=int(12*s), pady=int(6*s))
        entry_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        PillButton(entry_frame, text="Clear", style='danger', scale=s, width=int(60*s), height=int(32*s), command=lambda: current_text.set("")).pack(side=tk.RIGHT, padx=int(8*s), pady=int(4*s))
        
        keys_frame = tk.Frame(self.keyboard_frame, bg=BG_DARK)
        keys_frame.pack(fill=tk.BOTH, expand=True, padx=int(20*s), pady=int(6*s))
        
        letter_buttons = []
        def on_key(char): current_text.set(current_text.get() + char)
        def on_backspace():
            txt = current_text.get()
            if txt: current_text.set(txt[:-1])
        def toggle_shift():
            is_shift.set(not is_shift.get())
            update_keyboard_case()
        def update_keyboard_case():
            shift_on = is_shift.get()
            shift_btn.config(bg=ACCENT_PRIMARY if shift_on else BG_SURFACE, fg=TEXT_DARK if shift_on else TEXT_PRIMARY)
            for btn, key_char in letter_buttons:
                display_char = key_char.upper() if shift_on else key_char.lower()
                btn.config(text=display_char, command=lambda c=display_char: on_key(c))
        def finish():
            val = current_text.get().strip()
            if on_complete: on_complete(val)
        def cancel():
            if on_cancel: on_cancel()

        row1_keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '-']
        row2_keys = ['q', 'w', 'e', 'r', 't', 'y', 'u', 'i', 'o', 'p']
        row3_keys = ['a', 's', 'd', 'f', 'g', 'h', 'j', 'k', 'l']
        row4_letters = ['z', 'x', 'c', 'v', 'b', 'n', 'm']

        btn_font = (self.font_family, int(15*s), "bold")

        r1 = tk.Frame(keys_frame, bg=BG_DARK)
        r1.pack(fill=tk.X, pady=int(2*s))
        for k in row1_keys:
            tk.Button(r1, text=k, font=btn_font, bg=BG_SURFACE, fg=TEXT_PRIMARY, activebackground='#2e3d54', relief=tk.FLAT, command=lambda c=k: on_key(c)).pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=int(2*s))

        r2 = tk.Frame(keys_frame, bg=BG_DARK)
        r2.pack(fill=tk.X, pady=int(2*s))
        for k in row2_keys:
            b = tk.Button(r2, text=k.upper(), font=btn_font, bg=BG_SURFACE, fg=TEXT_PRIMARY, activebackground='#2e3d54', relief=tk.FLAT)
            b.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=int(2*s))
            letter_buttons.append((b, k))

        r3 = tk.Frame(keys_frame, bg=BG_DARK)
        r3.pack(fill=tk.X, pady=int(2*s))
        for k in row3_keys:
            b = tk.Button(r3, text=k.upper(), font=btn_font, bg=BG_SURFACE, fg=TEXT_PRIMARY, activebackground='#2e3d54', relief=tk.FLAT)
            b.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=int(2*s))
            letter_buttons.append((b, k))

        r4 = tk.Frame(keys_frame, bg=BG_DARK)
        r4.pack(fill=tk.X, pady=int(2*s))
        shift_btn = tk.Button(r4, text="⇧ Shift", font=btn_font, bg=ACCENT_PRIMARY, fg=TEXT_DARK, activebackground='#0ea5e9', relief=tk.FLAT, command=toggle_shift, width=int(7*s))
        shift_btn.pack(side=tk.LEFT, fill=tk.BOTH, padx=int(2*s))
        for k in row4_letters:
            b = tk.Button(r4, text=k.upper(), font=btn_font, bg=BG_SURFACE, fg=TEXT_PRIMARY, activebackground='#2e3d54', relief=tk.FLAT)
            b.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=int(2*s))
            letter_buttons.append((b, k))
        tk.Button(r4, text="⌫", font=btn_font, bg=COLOR_DANGER_BG, fg=COLOR_DANGER, relief=tk.FLAT, command=on_backspace, width=int(5*s)).pack(side=tk.LEFT, fill=tk.BOTH, padx=int(2*s))

        r5 = tk.Frame(keys_frame, bg=BG_DARK)
        r5.pack(fill=tk.X, pady=int(2*s))
        tk.Button(r5, text="Cancel", font=btn_font, bg=BG_SURFACE, fg=TEXT_SECONDARY, relief=tk.FLAT, command=cancel, width=int(8*s)).pack(side=tk.LEFT, fill=tk.BOTH, padx=int(2*s))
        tk.Button(r5, text="Space", font=btn_font, bg=BG_SURFACE, fg=TEXT_PRIMARY, activebackground='#2e3d54', relief=tk.FLAT, command=lambda: on_key(" ")).pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=int(2*s))
        tk.Button(r5, text="✔ Save", font=btn_font, bg=COLOR_SUCCESS, fg=TEXT_DARK, activebackground='#14b8a6', relief=tk.FLAT, command=finish, width=int(8*s)).pack(side=tk.LEFT, fill=tk.BOTH, padx=int(2*s))

        def on_physical_key(e):
            if e.keysym == 'Return': finish()
            elif e.keysym == 'Escape': cancel()
            elif e.keysym == 'BackSpace': on_backspace()
            elif len(e.char) == 1 and e.char.isprintable(): on_key(e.char)
        self.keyboard_frame.bind('<Key>', on_physical_key)
        self.keyboard_frame.focus_set()

        update_keyboard_case()
        self.keyboard_frame.pack(fill=tk.BOTH, expand=True)

    def edit_class(self, cid):
        classes = load_json(CLASSES_FILE, [])
        target = next((c for c in classes if c["id"] == cid), None)
        if not target: return
        
        def on_name_edited(new_name):
            if new_name.strip():
                target["name"] = new_name.strip()
                save_json(CLASSES_FILE, classes)
            self.show_classes_list_screen()
            
        self.show_onscreen_keyboard(
            prompt_text="Enter new class name:",
            initial_value=target["name"],
            on_complete=on_name_edited,
            on_cancel=self.show_classes_list_screen
        )

    # ==========================================
    # SCREEN 4: RECORDING SCREEN (4 CHORDS MAX)
    # ==========================================
    def build_record_screen(self):
        s = self.scale
        for w in self.record_frame.winfo_children():
            w.destroy()

        # -------------------------------------------------------------
        # TOP BAR: Full width header with prominent CANCEL and SAVE CLASS
        # -------------------------------------------------------------
        top_bar = tk.Frame(self.record_frame, bg=BG_DARK)
        top_bar.pack(fill=tk.X, padx=int(14*s), pady=(int(8*s), int(4*s)))

        title_box = tk.Frame(top_bar, bg=BG_DARK)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            title_box, text="Record New Class",
            font=(self.font_family, int(18*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY
        ).pack(anchor='w')
        tk.Label(
            title_box, text="PLAY PIANO & CHORDS TO RECORD A REUSABLE LESSON",
            font=(self.font_family, int(8.5*s), "bold"), bg=BG_DARK, fg=TEXT_SECONDARY
        ).pack(anchor='w')

        top_actions = tk.Frame(top_bar, bg=BG_DARK)
        top_actions.pack(side=tk.RIGHT)

        self.rec_cancel_btn = PillButton(
            top_actions, text="← Cancel", style='secondary',
            scale=s, height=int(32*s),
            command=lambda: self.stop_metronome() or self.show_classes_list_screen()
        )
        self.rec_cancel_btn.pack(side=tk.LEFT, padx=int(4*s))

        self.rec_save_top_btn = PillButton(
            top_actions, text="✔ Save Class", style='success',
            scale=s, height=int(32*s),
            command=self.save_recording
        )
        self.rec_save_top_btn.pack(side=tk.LEFT, padx=int(4*s))

        # -------------------------------------------------------------
        # MIDDLE TWO-COLUMN WORKSPACE
        # -------------------------------------------------------------
        mid = tk.Frame(self.record_frame, bg=BG_DARK)
        mid.pack(fill=tk.BOTH, expand=True, padx=int(14*s), pady=int(4*s))

        # LEFT CARD: CHORDS (Max 4 in clean 2x2 grid)
        left_card = tk.Frame(
            mid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE,
            padx=int(10*s), pady=int(8*s)
        )
        left_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, int(6*s)))

        chords_header = tk.Frame(left_card, bg=BG_CARD)
        chords_header.pack(fill=tk.X, pady=(0, int(4*s)))
        tk.Label(
            chords_header, text="LESSON CHORDS (MAX 4)",
            font=(self.font_family, int(9.5*s), "bold"), bg=BG_CARD, fg=TEXT_SECONDARY
        ).pack(side=tk.LEFT)
        tk.Label(
            chords_header, text="Hold 2s on piano",
            font=(self.font_family, int(8.5*s)), bg=BG_CARD, fg=TEXT_MUTED
        ).pack(side=tk.RIGHT)

        self.rec_chords_frame = tk.Frame(left_card, bg=BG_CARD)
        self.rec_chords_frame.pack(fill=tk.BOTH, expand=True)

        # RIGHT CARD: RECORDING CONTROLS & STATUS
        right_card = tk.Frame(
            mid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE,
            padx=int(12*s), pady=int(8*s)
        )
        right_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(int(6*s), 0))

        # Big Timer Display
        self.rec_clock_lbl = tk.Label(
            right_card, text="0:00",
            font=(self.font_family, int(36*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY
        )
        self.rec_clock_lbl.pack(pady=(int(4*s), 0))

        # Informative Status Text
        self.rec_status_lbl = tk.Label(
            right_card, text="● Ready to record",
            font=(self.font_family, int(10.5*s), "bold"), bg=BG_CARD, fg=TEXT_SECONDARY
        )
        self.rec_status_lbl.pack(pady=(0, int(6*s)))

        # ROW 1: PRIMARY RECORDING ACTIONS (Start/Stop + Save)
        row1 = tk.Frame(right_card, bg=BG_CARD)
        row1.pack(pady=int(4*s))

        self.rec_start_btn = PillButton(
            row1, text="● Start Recording", style='primary',
            scale=s, height=int(36*s),
            command=self.toggle_recording
        )
        self.rec_start_btn.pack(side=tk.LEFT, padx=int(4*s))

        self.rec_save_btn = PillButton(
            row1, text="✔ Save Class", style='success',
            scale=s, height=int(36*s),
            command=self.save_recording
        )
        self.rec_save_btn.pack(side=tk.LEFT, padx=int(4*s))

        # ROW 2: TEMPO & UTILITIES (Metro + Speed + Clear)
        row2 = tk.Frame(right_card, bg=BG_CARD)
        row2.pack(pady=int(4*s))

        self.rec_metro_btn = PillButton(
            row2, text="⏱ Metro OFF", style='secondary',
            scale=s, height=int(28*s),
            command=self.toggle_metronome
        )
        self.rec_metro_btn.pack(side=tk.LEFT, padx=int(3*s))

        self.rec_speed_btn = PillButton(
            row2, text="Speed: Normal (80)", style='secondary',
            scale=s, height=int(28*s),
            command=self.cycle_speed
        )
        self.rec_speed_btn.pack(side=tk.LEFT, padx=int(3*s))

        self.rec_reset_btn = PillButton(
            row2, text="↺ Clear", style='secondary',
            scale=s, height=int(28*s),
            command=self.reset_recording
        )
        self.rec_reset_btn.pack(side=tk.LEFT, padx=int(3*s))

    def render_record_chords(self):
        if not hasattr(self, 'rec_chords_frame') or not self.rec_chords_frame.winfo_exists():
            return
        for w in self.rec_chords_frame.winfo_children():
            w.destroy()
        s = self.scale
        self.rec_chords_frame.columnconfigure(0, weight=1, minsize=int(100*s))
        self.rec_chords_frame.columnconfigure(1, weight=1, minsize=int(100*s))
        self.rec_chords_frame.rowconfigure(0, weight=1)
        self.rec_chords_frame.rowconfigure(1, weight=1)

        for i in range(4):
            r, c = i // 2, i % 2
            cell = tk.Frame(
                self.rec_chords_frame, bg=BG_SURFACE,
                highlightthickness=1, highlightbackground=BORDER_SUBTLE,
                padx=int(6*s), pady=int(4*s)
            )
            cell.grid(row=r, column=c, padx=int(4*s), pady=int(4*s), sticky="nsew")

            if i < len(self.recorded_chords):
                chord = self.recorded_chords[i]
                cell_top = tk.Frame(cell, bg=BG_SURFACE)
                cell_top.pack(fill=tk.X)
                tk.Label(
                    cell_top, text=chord["name"],
                    font=(self.font_family, int(10*s), "bold"),
                    bg=BG_SURFACE, fg=TEXT_PRIMARY, anchor='w'
                ).pack(side=tk.LEFT, fill=tk.X, expand=True)
                PillButton(
                    cell_top, text="✕", style='danger',
                    scale=s, width=int(24*s), height=int(20*s),
                    command=lambda idx=i: self.remove_recorded_chord(idx)
                ).pack(side=tk.RIGHT)

                cvs = tk.Canvas(cell, width=self.mini_w, height=self.mini_h, bg=BG_CARD, highlightthickness=0)
                cvs.pack(pady=int(2*s))
                self.draw_mini_piano(cvs, self.mini_w, self.mini_h, chord["shape"])
            elif i == len(self.recorded_chords):
                PillButton(
                    cell, text="+ Add Chord", style='secondary',
                    scale=s, height=int(32*s),
                    command=self.add_chord_prompt
                ).pack(expand=True)
            else:
                tk.Label(
                    cell, text=f"Chord {i+1}\n(Optional)",
                    font=(self.font_family, int(8.5*s)),
                    bg=BG_SURFACE, fg=TEXT_MUTED, justify='center'
                ).pack(expand=True)

    def add_chord_prompt(self):
        self.is_listening_for_chord = True
        self.chord_hold_start = 0
        self.rec_status_lbl.config(text="🎹 Play and hold chord on piano for 2s...", fg=COLOR_WARNING)

    def remove_recorded_chord(self, idx):
        if idx < len(self.recorded_chords):
            self.recorded_chords.pop(idx)
            self.render_record_chords()

    def toggle_recording(self):
        if not self.recorder.is_recording:
            self.rec_start_btn.config(text="Starting (4)...", state=tk.DISABLED)
            self.rec_status_lbl.config(text="Count-in in progress...", fg=COLOR_WARNING)
            self.metronome_runner.count_in_and_trigger(4, lambda: self.root.after(0, self._start_rec_actual))
        else:
            self.recorder.stop()
            note_count = len(self.recorder.events) // 2
            self.rec_start_btn.config(text="● Record More", style='primary', state=tk.NORMAL)
            self.rec_status_lbl.config(text=f"Stopped: {note_count} notes. Ready to save.", fg=COLOR_SUCCESS)

    def _start_rec_actual(self):
        self.rec_start_btn.config(text="■ Stop Recording", style='danger', state=tk.NORMAL)
        self.rec_status_lbl.config(text="● RECORDING IN PROGRESS", fg=COLOR_DANGER)
        self.recorder.start()

    def reset_recording(self):
        self.recorder.stop()
        self.recorder.events = []
        self.recorded_chords = []
        self.render_record_chords()
        self.rec_clock_lbl.config(text="0:00")
        self.rec_start_btn.config(text="● Start Recording", style='primary', state=tk.NORMAL)
        self.rec_status_lbl.config(text="● Ready to record", fg=TEXT_SECONDARY)

    def save_recording(self):
        if self.recorder.is_recording:
            self.recorder.stop()
            note_count = len(self.recorder.events) // 2
            self.rec_start_btn.config(text="● Record More", style='primary', state=tk.NORMAL)

        if not self.recorder.events and not self.recorded_chords:
            self.rec_status_lbl.config(text="⚠ Nothing recorded yet! Play piano or add chords first.", fg=COLOR_WARNING)
            return

        def on_name_saved(name):
            if name.strip():
                classes = load_json(CLASSES_FILE, [])
                classes.append({
                    "id": str(uuid.uuid4()),
                    "name": name.strip(),
                    "chords": self.recorded_chords,
                    "midi_events": self.recorder.events
                })
                save_json(CLASSES_FILE, classes)
            self.show_classes_list_screen()

        def on_name_cancelled():
            self.show_record_screen(reset=False)

        self.show_onscreen_keyboard(
            prompt_text="Enter class name:",
            initial_value="",
            on_complete=on_name_saved,
            on_cancel=on_name_cancelled
        )

    # ==========================================
    # SCREEN 5: SESSION SCREEN
    # ==========================================
    def build_session_screen(self):
        s = self.scale
        self.top_bar = tk.Frame(self.session_frame, bg=BG_DARK)
        self.top_bar.pack(side=tk.TOP, fill=tk.X, padx=int(14*s), pady=(int(6*s), int(4*s)))
        
        # Right side: ONLY Select Class and End Session buttons
        self.end_btn = PillButton(self.top_bar, text="End Session", style='danger', scale=s, height=int(34*s), command=self.end_session)
        self.end_btn.pack(side=tk.RIGHT, padx=(int(6*s), 0))

        self.class_btn = PillButton(self.top_bar, text="Select Class", style='secondary', scale=s, height=int(34*s), command=self.open_class_selector)
        self.class_btn.pack(side=tk.RIGHT, padx=int(6*s))

        title_box = tk.Frame(self.top_bar, bg=BG_DARK)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.session_title = tk.Label(title_box, text="practice", font=(self.font_family, int(20*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY)
        self.session_title.pack(anchor='w')
        self.session_subtitle = tk.Label(title_box, text="STUDENT PRACTICE • 15 MIN GOAL", font=(self.font_family, int(9.5*s), "bold"), bg=BG_DARK, fg=TEXT_SECONDARY)
        self.session_subtitle.pack(anchor='w')
        
        # Middle Frame with balanced card height so bottom piano has ample room
        self.middle_frame = tk.Frame(self.session_frame, bg=BG_DARK)
        self.middle_frame.pack(fill=tk.X, padx=int(14*s), pady=int(2*s))
        
        # Card 1: Minimalist Timer Card
        self.clock_canvas = tk.Canvas(self.middle_frame, width=self.clock_size, height=self.clock_h, bg=BG_DARK, highlightthickness=0)
        self.clock_canvas.pack(side=tk.LEFT, expand=True, padx=int(4*s))
        self.arc_id = self.draw_clock_face(self.clock_canvas)
        
        # Card 2: Chords Recognition Card (4 Chords Max)
        self.chords_card = tk.Canvas(self.middle_frame, width=self.chords_card_w, height=self.staff_h, bg=BG_DARK, highlightthickness=0)
        self.chords_card.pack(side=tk.LEFT, expand=True, padx=int(4*s))
        self.draw_chords_card_base()
        
        # Card 3: Live Staff Notation Card
        self.staff_canvas = tk.Canvas(self.middle_frame, width=self.staff_w, height=self.staff_h, bg=BG_DARK, highlightthickness=0)
        self.staff_canvas.pack(side=tk.RIGHT, expand=True, padx=int(4*s))
        self.draw_grand_staff(self.staff_canvas)

        # Bottom Controls Toolbar (Always visible right above the piano keys)
        self.playback_controls_frame = tk.Frame(self.session_frame, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(12*s), pady=int(2*s))
        
        # Subframe for Class Playback (Play/Pause, Slider, Restart) - visible during class
        self.class_controls_subframe = tk.Frame(self.playback_controls_frame, bg=BG_CARD)
        
        self.cp_play_btn = PillButton(self.class_controls_subframe, text="Pause", style='primary', scale=s, height=int(28*s), command=self.toggle_playback)
        self.cp_play_btn.pack(side=tk.LEFT, padx=int(4*s))
        
        self.cp_slider = tk.Scale(self.class_controls_subframe, from_=0, to=100, orient=tk.HORIZONTAL, bg=BG_CARD, fg=TEXT_SECONDARY, highlightthickness=0, troughcolor=BG_SURFACE, activebackground=ACCENT_PRIMARY, length=int(200*s), showvalue=0)
        self.cp_slider.bind("<ButtonRelease-1>", lambda e: self.player.seek(float(self.cp_slider.get())))
        self.cp_slider.pack(side=tk.LEFT, padx=int(4*s))
        
        self.btn_restart = PillButton(self.class_controls_subframe, text="Restart", style='secondary', scale=s, height=int(28*s), command=self.restart_class)
        self.btn_restart.pack(side=tk.LEFT, padx=int(4*s))

        # Subframe for Speed & Metronome controls - ALWAYS visible at the bottom
        self.tempo_controls_subframe = tk.Frame(self.playback_controls_frame, bg=BG_CARD)
        self.tempo_controls_subframe.pack(side=tk.RIGHT)
        
        self.speed_btn = PillButton(self.tempo_controls_subframe, text="Speed: Normal (80)", style='secondary', scale=s, height=int(28*s), command=self.cycle_speed)
        self.speed_btn.pack(side=tk.LEFT, padx=int(4*s))

        self.metro_btn = PillButton(self.tempo_controls_subframe, text="⏱ Metro OFF", style='secondary', scale=s, height=int(28*s), command=self.toggle_metronome)
        self.metro_btn.pack(side=tk.LEFT, padx=int(4*s))

    def cycle_speed(self):
        self.metronome_runner.cycle_speed_mode()
        ratio = self.metronome_runner.get_speed_ratio()
        self.player.set_speed(ratio)
        self.update_metronome_ui()

    def toggle_metronome(self):
        self.metronome_runner.toggle_active()
        self.update_metronome_ui()

    def update_metronome_ui(self):
        speed_txt = self.metronome_runner.get_speed_label()
        speed_style = 'secondary' if self.metronome_runner.speed_mode == 'normal' else 'primary'
        
        metro_txt = self.metronome_runner.get_active_label()
        metro_style = 'primary' if self.metronome_runner.is_active else 'secondary'
        
        if hasattr(self, 'speed_btn'):
            self.speed_btn.config(text=speed_txt, style=speed_style)
        if hasattr(self, 'metro_btn'):
            self.metro_btn.config(text=metro_txt, style=metro_style)
            
        if hasattr(self, 'rec_speed_btn'):
            self.rec_speed_btn.config(text=speed_txt, style=speed_style)
        if hasattr(self, 'rec_metro_btn'):
            self.rec_metro_btn.config(text=metro_txt, style=metro_style)

    def stop_metronome(self):
        if hasattr(self, 'metronome_runner'):
            self.metronome_runner.set_active(False)
        self.update_metronome_ui()

    def build_debug_screen(self):
        s = self.scale
        tk.Label(self.debug_frame, text="MIDI Diagnostics", font=(self.font_family, int(26*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY).pack(pady=int(14*s))
        self.ports_lbl = tk.Label(self.debug_frame, text="Detected USB Ports: None", font=(self.font_family, self.f_btn), bg=BG_DARK, fg=COLOR_SUCCESS)
        self.ports_lbl.pack(pady=int(4*s))
        self.conn_lbl = tk.Label(self.debug_frame, text="Connected To: None", font=(self.font_family, self.f_btn), bg=BG_DARK, fg=COLOR_DANGER)
        self.conn_lbl.pack(pady=int(4*s))
        self.log_text = tk.Text(self.debug_frame, height=12, width=80, bg=BG_CARD, fg=TEXT_PRIMARY, font=("Courier", int(12*s)), highlightthickness=1, highlightbackground=BORDER_SUBTLE)
        self.log_text.pack(pady=int(10*s))
        PillButton(self.debug_frame, text="Go Back", style='secondary', scale=s, height=int(40*s), command=self.show_select_screen).pack(pady=int(14*s))

    # ==========================================
    # TIMER COMPONENT: FITS COMFORTABLY INSIDE CIRCLE
    # ==========================================
    def draw_clock_face(self, canvas):
        canvas.delete("all")
        s = self.scale
        w = self.clock_size
        h = self.clock_h
        r_card = int(16 * s)
        
        self.round_rect(canvas, 0, int(2*s), w, h, radius=r_card, fill='#080c12', outline='')
        self.round_rect(canvas, 0, 0, w, h-int(2*s), radius=r_card, fill=BG_CARD, outline=BORDER_SUBTLE, width=1)
        canvas.create_text(w/2, int(15*s), text="PRACTICE TIMER", font=(self.font_family, int(10*s), "bold"), fill=TEXT_SECONDARY)
        
        # Circle radius 60 gives ample diameter (120px) so 15:00 (50px) never touches ring
        cx, cy = w/2, int(88*s)
        r = int(60*s)
        self.clock_center = (cx, cy)
        self.clock_radius = r
        
        canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill='', outline=BG_SURFACE, width=max(2, int(6*s)))
        
        self.arc_id = canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=90, extent=-359.9, style=tk.ARC,
            outline=ACCENT_PRIMARY, width=max(2, int(6*s))
        )
        
        # Countdown font size 20 bold fits with >35px margin on both sides!
        self.clock_time_text = canvas.create_text(
            cx, cy - int(4*s), text="15:00",
            font=(self.font_family, int(20*s), "bold"), fill=TEXT_PRIMARY
        )
        self.clock_sub_text = canvas.create_text(
            cx, cy + int(16*s), text="15M GOAL",
            font=(self.font_family, int(8.5*s), "bold"), fill=TEXT_MUTED
        )
        
        pill_w = int(105*s)
        pill_h = int(22*s)
        px1, py1 = (w - pill_w)/2, h - int(28*s)
        px2, py2 = px1 + pill_w, py1 + pill_h
        self.status_pill_rect = self.round_rect(canvas, px1, py1, px2, py2, radius=int(11*s), fill='#182330', outline=BORDER_SUBTLE, width=1)
        self.status_pill_text = canvas.create_text(w/2, py1 + pill_h/2, text="● PAUSED", font=(self.font_family, int(9.5*s), "bold"), fill=TEXT_SECONDARY)
        
        return self.arc_id

    def animate_metronome_beat(self, beat_num):
        if self.app_mode == 'record' and hasattr(self, 'rec_status_lbl'):
            self.rec_status_lbl.config(text=f"COUNT-IN: Beat {beat_num} of 4...", fg=COLOR_WARNING)
        if not hasattr(self, 'clock_canvas') or not hasattr(self, 'clock_center'): return
        s = self.scale
        cx, cy = self.clock_center
        self.clock_canvas.delete("metro_anim")
        
        r_badge = int(self.clock_radius * 0.72)
        self.clock_canvas.create_oval(cx - r_badge, cy - r_badge, cx + r_badge, cy + r_badge, fill=BG_CARD, outline=ACCENT_PRIMARY, width=max(2, int(2.5*s)), tags="metro_anim")
        col = COLOR_SUCCESS if beat_num == 1 else ACCENT_PRIMARY
        self.clock_canvas.create_text(cx, cy - int(4*s), text=str(beat_num), font=(self.font_family, int(30*s), "bold"), fill=col, tags="metro_anim")
        
        self.root.after(320, lambda: self.clock_canvas.delete("metro_anim"))

    # ==========================================
    # CHORDS GRID CARD (CLEAN 4-CHORD 2X2 GRID)
    # ==========================================
    def draw_chords_card_base(self):
        self.chords_card.delete("all")
        s = self.scale
        w = self.chords_card_w
        h = self.staff_h
        r_card = int(16 * s)
        
        self.round_rect(self.chords_card, 0, int(2*s), w, h, radius=r_card, fill='#080c12', outline='')
        self.round_rect(self.chords_card, 0, 0, w, h-int(2*s), radius=r_card, fill=BG_CARD, outline=BORDER_SUBTLE, width=1)
        card_title = "CHORD RECOGNITION" if self.app_mode == 'free' else "CLASS CHORDS"
        self.chords_card_title_id = self.chords_card.create_text(w/2, int(15*s), text=card_title, font=(self.font_family, int(10*s), "bold"), fill=TEXT_SECONDARY)
        
        # 2x2 Grid container inside the card
        grid_container = tk.Frame(self.chords_card, bg=BG_CARD)
        self.chords_card.create_window(w/2, int(106*s), window=grid_container)
        grid_container.columnconfigure(0, weight=1, minsize=int(114*s))
        grid_container.columnconfigure(1, weight=1, minsize=int(114*s))
        
        self.chord_cells = []
        for i in range(4):
            r, c = i // 2, i % 2
            cell = tk.Frame(grid_container, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(6*s), pady=int(3*s))
            cell.grid(row=r, column=c, padx=int(4*s), pady=int(3*s), sticky="nsew")
            name_lbl = tk.Label(cell, text="", font=(self.font_family, int(9.5*s), "bold"), bg=BG_SURFACE, fg=TEXT_PRIMARY, wraplength=int(112*s), justify='center')
            name_lbl.pack(fill=tk.X, expand=True)
            cvs = tk.Canvas(cell, width=self.mini_w, height=self.mini_h, bg=BG_CARD, highlightthickness=0)
            cvs.pack(pady=int(1*s))
            count_lbl = tk.Label(cell, text="", font=(self.font_family, int(8.5*s)), bg=BG_SURFACE, fg=TEXT_SECONDARY)
            count_lbl.pack()
            self.chord_cells.append({"frame": cell, "name": name_lbl, "canvas": cvs, "count": count_lbl})

    # ==========================================
    # GRAND STAFF: CLASSIC CLEFS
    # ==========================================
    def draw_grand_staff(self, canvas):
        canvas.delete("all")
        s = self.scale
        w = self.staff_w
        h = self.staff_h
        r_card = int(16 * s)
        
        self.round_rect(canvas, 0, int(2*s), w, h, radius=r_card, fill='#080c12', outline='')
        self.round_rect(canvas, 0, 0, w, h-int(2*s), radius=r_card, fill=BG_CARD, outline=BORDER_SUBTLE, width=1)
        canvas.create_text(w/2, int(15*s), text="LIVE NOTATION", font=(self.font_family, int(10*s), "bold"), fill=TEXT_SECONDARY)
        
        line_x1 = int(16 * s)
        line_x2 = w - int(16 * s)
        
        # Treble staff lines: 25, 42, 59, 76 (G), 93 (E)
        for y in [25, 42, 59, 76, 93]:
            canvas.create_line(line_x1, y*s, line_x2, y*s, fill='#334155', width=max(1, int(1.2*s)), tags="staff_base")
            
        # Bass staff lines: 127, 144 (F), 161, 178, 195
        for y in [127, 144, 161, 178, 195]:
            canvas.create_line(line_x1, y*s, line_x2, y*s, fill='#334155', width=max(1, int(1.2*s)), tags="staff_base")
            
        # Middle C dashed guide line (y = 110*s)
        canvas.create_line(line_x1 + int(35*s), self.mc_y, line_x2 - int(35*s), self.mc_y, fill='#222c3d', width=1, dash=(4, 4), tags="staff_base")
        
        # Initial non-vectorial Treble clef design using musical character
        canvas.create_text(int(36*s), int(60*s), text="𝄞", font=("Helvetica", self.f_clef), fill=TEXT_PRIMARY, tags="staff_base")
        
        # Bass clef
        self.draw_vector_bass_clef(canvas, cx=int(32*s), y_f=144*s, scale=s, color=TEXT_PRIMARY)

    def draw_vector_bass_clef(self, canvas, cx, y_f, scale, color=TEXT_PRIMARY):
        s = scale
        dot_f = 4.0 * s
        canvas.create_oval(cx - dot_f, y_f - dot_f, cx + dot_f, y_f + dot_f, fill=color, outline='', tags="staff_base")
        
        curve = [
            cx, y_f - 3*s,
            cx + 8*s, y_f - 14*s,
            cx + 18*s, y_f - 12*s,
            cx + 20*s, y_f + 2*s,
            cx + 15*s, y_f + 14*s,
            cx + 8*s, y_f + 24*s,
            cx + 2*s, y_f + 28*s
        ]
        canvas.create_line(curve, fill=color, width=max(2, int(2.4*s)), smooth=True, tags="staff_base")
        
        dr = 2.5 * s
        canvas.create_oval(cx + 26*s - dr, y_f - 8*s - dr, cx + 26*s + dr, y_f - 8*s + dr, fill=color, outline='', tags="staff_base")
        canvas.create_oval(cx + 26*s - dr, y_f + 8*s - dr, cx + 26*s + dr, y_f + 8*s + dr, fill=color, outline='', tags="staff_base")

    # ==========================================
    # PIANO KEYBOARD (BALANCED PROPORTIONS & FELT RAIL)
    # ==========================================
    def on_piano_resize(self, event):
        w, h = event.width, event.height
        if w <= 1 or h <= 1: return
        self.piano_rects = {}
        self.piano_canvas.delete("all")
        
        white_w = w / 52.0
        black_w = white_w * 0.58
        black_h = h * 0.62
        
        # 1. White keys (piano ivory)
        white_idx = 0
        for note in range(21, 109):
            if (note % 12) in [0, 2, 4, 5, 7, 9, 11]:
                x1, x2 = white_idx * white_w, (white_idx + 1) * white_w
                rect = self.piano_canvas.create_rectangle(
                    x1, 0, x2, h - 2,
                    fill='#fdfdfd', outline='#cbd5e1', width=1
                )
                self.piano_rects[note] = {"rect": rect, "is_black": False, "coords": (x1, 0, x2, h - 2)}
                white_idx += 1
                
        # Keybed base rail underneath keys
        self.piano_canvas.create_line(0, h - 1, w, h - 1, fill='#1e2430', width=2)
        
        # 2. Black keys (ebony matte with top highlight)
        white_idx = 0
        for note in range(21, 109):
            if (note % 12) in [0, 2, 4, 5, 7, 9, 11]:
                white_idx += 1
            else:
                xc = white_idx * white_w
                x1, x2 = xc - black_w/2, xc + black_w/2
                rect = self.piano_canvas.create_rectangle(
                    x1, 0, x2, black_h,
                    fill='#181920', outline='#0a0b10', width=1
                )
                self.piano_canvas.create_line(x1 + 1, 2, x2 - 1, 2, fill='#333745', width=1)
                self.piano_rects[note] = {"rect": rect, "is_black": True, "coords": (x1, 0, x2, black_h)}
                
        # Red felt rail along top of keyboard bed
        self.piano_canvas.create_line(0, 0, w, 0, fill='#4a1525', width=2)

    def draw_mini_piano(self, canvas, w, h, highlight_keys):
        canvas.delete("all")
        white_w = w / 14.0
        black_w, black_h = white_w * 0.58, h * 0.62
        white_idx = 0
        for i in range(24):
            if (i % 12) in [0, 2, 4, 5, 7, 9, 11]:
                fill_col = ACCENT_PRIMARY if i in highlight_keys else '#fdfdfd'
                canvas.create_rectangle(white_idx*white_w, 0, (white_idx+1)*white_w, h, fill=fill_col, outline=BORDER_SUBTLE, width=1)
                white_idx += 1
        white_idx = 0
        for i in range(24):
            if (i % 12) in [0, 2, 4, 5, 7, 9, 11]: white_idx += 1
            else:
                xc = white_idx * white_w
                fill_col = '#0ea5e9' if i in highlight_keys else '#181920'
                canvas.create_rectangle(xc - black_w/2, 0, xc + black_w/2, black_h, fill=fill_col, outline=BG_DARK, width=1)

    def draw_note(self, note, canvas, color=ACCENT_PRIMARY, source='student'):
        octave = (note // 12) - 1
        pitch_class = note % 12
        diatonic_step = [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6][pitch_class]
        is_sharp = [False, True, False, True, False, False, True, False, True, False, True, False][pitch_class]
        s = self.scale
        y = self.mc_y - (((octave - 4) * 7 + diatonic_step) * self.step_y)
        base_x = 115 * s
        x = base_x + (14*s if diatonic_step % 2 != 0 else 0)
        tag = (f"note_{note}_{source}", f"{source}_note", "note_item")
        
        if y < 25*s:
            for ly in range(int(8*s), int(y) - int(4*s), int(-17*s)):
                canvas.create_line(base_x-10*s, ly, base_x+30*s, ly, fill=TEXT_SECONDARY, width=max(1, int(s)), tags=tag)
        elif y > 195*s:
            for ly in range(int(212*s), int(y) + int(4*s), int(17*s)):
                canvas.create_line(base_x-10*s, ly, base_x+30*s, ly, fill=TEXT_SECONDARY, width=max(1, int(s)), tags=tag)
        elif abs(y - self.mc_y) < 1:
            canvas.create_line(base_x-10*s, self.mc_y, base_x+30*s, self.mc_y, fill=TEXT_SECONDARY, width=max(1, int(s)), tags=tag)
                
        if is_sharp:
            canvas.create_text(base_x-18*s, y, text="♯", font=(self.font_family, int(15*s), "bold"), fill=TEXT_PRIMARY, tags=tag)
        canvas.create_oval(x, y-5*s, x+15*s, y+5*s, fill=color, outline=BG_DARK, width=1, tags=(tag + (f"oval_{note}_{source}",)))

    def fade_note_head(self, note, source):
        if not hasattr(self, 'staff_canvas'): return
        oval_tag = f"oval_{note}_{source}"
        fade_tag = f"fade_{note}_{source}_{int(time.time()*1000)}"
        self.staff_canvas.dtag(oval_tag, oval_tag)
        self.staff_canvas.addtag_withtag(fade_tag, oval_tag)
        
        self.staff_canvas.delete(f"note_{note}_{source}")
        
        self.root.after(40, lambda: self.staff_canvas.itemconfig(fade_tag, fill=ACCENT_MUTED))
        self.root.after(90, lambda: self.staff_canvas.itemconfig(fade_tag, fill=BG_CARD))
        self.root.after(140, lambda: self.staff_canvas.delete(fade_tag))

    def clear_all_notes(self):
        if hasattr(self, 'staff_canvas'):
            self.staff_canvas.delete("note_item")
        self.drawn_notes.clear()
        self.teacher_notes.clear()
        self.note_velocities.clear()
        while not midi_queue.empty():
            try: midi_queue.get_nowait()
            except: break
        if hasattr(self, 'piano_rects'):
            self.update_piano_colors()
            
    def update_piano_colors(self):
        if not hasattr(self, 'piano_rects'): return
        active_student = list(self.drawn_notes.keys())
        active_teacher = list(self.teacher_notes.keys())
        chord_name, chord_notes = self.identify_chord_advanced(active_student)
        
        if chord_name and chord_name != state["last_recognized_chord"]:
            if self.app_mode == 'class':
                if self.active_class and chord_name in [c["name"] for c in self.active_class["chords"]]:
                    state["chord_counts"][chord_name] += 1
            else:
                state["chord_counts"][chord_name] = state["chord_counts"].get(chord_name, 0) + 1
            state["chord_shapes"][chord_name] = set(n - (min(chord_notes)//12)*12 for n in chord_notes)
            state["last_recognized_chord"] = chord_name
            if getattr(self, 'current_session_data', None):
                cp = self.current_session_data.setdefault("chords_played", {})
                cp[chord_name] = cp.get(chord_name, 0) + 1
            self.update_chord_grid(pulse_chord=chord_name)
        elif not chord_name:
            state["last_recognized_chord"] = None

        for note, kdata in self.piano_rects.items():
            rect = kdata["rect"]
            is_black = kdata["is_black"]
            
            if note in active_teacher:
                self.piano_canvas.itemconfig(rect, fill='#818cf8', outline='#6366f1')
            elif note in active_student:
                if chord_name and note in chord_notes:
                    col = '#f43f5e' if not is_black else '#e11d48'
                    outline_col = '#be123c'
                else:
                    col = ACCENT_PRIMARY if not is_black else '#0284c7'
                    outline_col = '#0369a1'
                self.piano_canvas.itemconfig(rect, fill=col, outline=outline_col)
            else:
                fill_col = '#181920' if is_black else '#fdfdfd'
                outline_col = '#0a0b10' if is_black else '#cbd5e1'
                self.piano_canvas.itemconfig(rect, fill=fill_col, outline=outline_col)

    def pulse_chord_cell(self, cell):
        cell["frame"].config(highlightbackground=ACCENT_PRIMARY, bg='#1a344d')
        cell["name"].config(fg=ACCENT_PRIMARY, bg='#1a344d')
        cell["count"].config(fg=TEXT_PRIMARY, bg='#1a344d')
        def _reset():
            cell["frame"].config(highlightbackground=BORDER_SUBTLE, bg=BG_SURFACE)
            cell["name"].config(fg=TEXT_PRIMARY, bg=BG_SURFACE)
            cell["count"].config(fg=TEXT_SECONDARY, bg=BG_SURFACE)
        self.root.after(220, _reset)

    # 4 chords maximum in Practice Screen
    def update_chord_grid(self, pulse_chord=None):
        if self.app_mode == 'class':
            for i in range(4):
                if i < len(self.active_class["chords"]):
                    cname = self.active_class["chords"][i]["name"]
                    self.chord_cells[i]["count"].config(text=f"{state['chord_counts'].get(cname, 0)} times")
                    if pulse_chord and cname == pulse_chord:
                        self.pulse_chord_cell(self.chord_cells[i])
            return
            
        sorted_chords = sorted(state["chord_counts"].items(), key=lambda x: x[1], reverse=True)[:4]
        for i in range(4):
            if i < len(sorted_chords):
                name, count = sorted_chords[i]
                self.chord_cells[i]["name"].config(text=name)
                self.chord_cells[i]["count"].config(text=f"{count} times")
                self.draw_mini_piano(self.chord_cells[i]["canvas"], self.mini_w, self.mini_h, state["chord_shapes"][name])
                if pulse_chord and name == pulse_chord:
                    self.pulse_chord_cell(self.chord_cells[i])
            else:
                self.chord_cells[i]["name"].config(text="")
                self.chord_cells[i]["count"].config(text="")
                self.chord_cells[i]["canvas"].delete("all")

    def identify_chord_advanced(self, active_notes):
        if not active_notes: return None, []
        NOTES = ["C (Do)", "C# (Do#)", "D (Re)", "D# (Re#)", "E (Mi)", "F (Fa)", "F# (Fa#)", "G (Sol)", "G# (Sol#)", "A (La)", "A# (La#)", "B (Si)"]
        CHORDS = {
            frozenset([0, 4, 7]): " Mayor", frozenset([0, 3, 7]): " Menor",
            frozenset([0, 3, 6]): " Dim", frozenset([0, 4, 8]): " Aug",
            frozenset([0, 4, 7, 10]): "7", frozenset([0, 4, 7, 11]): "maj7",
            frozenset([0, 3, 7, 10]): "m7", frozenset([0, 3, 6, 10]): "m7b5",
            frozenset([0, 3, 6, 9]): "dim7", frozenset([0, 4, 7, 9]): "6",
            frozenset([0, 3, 7, 9]): "m6", frozenset([0, 5, 7]): "sus4", frozenset([0, 2, 7]): "sus2",
        }
        def match_chord(notes_list):
            if len(notes_list) < 3: return None
            bass_pc = min(notes_list) % 12
            pcs = set(n % 12 for n in notes_list)
            rel = frozenset((p - bass_pc) % 12 for p in pcs)
            if rel in CHORDS: return NOTES[bass_pc] + CHORDS[rel]
            for root in pcs:
                if root == bass_pc: continue
                rel = frozenset((p - root) % 12 for p in pcs)
                if rel in CHORDS: return f"{NOTES[root]}{CHORDS[rel]}/{NOTES[bass_pc]}"
            return None
        c = match_chord(active_notes)
        if c: return c, active_notes
        rh = [n for n in active_notes if n >= 60]
        if len(rh) >= 3:
            c = match_chord(rh)
            if c: return c, rh
        lh = [n for n in active_notes if n < 60]
        if len(lh) >= 3:
            c = match_chord(lh)
            if c: return c, lh
        return None, []

    def show_select_screen(self):
        self.stop_metronome()
        self.clear_all_notes()
        if getattr(self, 'current_session_data', None) and self.current_session_data.get("events"):
            sess = self.current_session_data
            now = time.time()
            sess["end_time"] = now
            sess["duration_seconds"] = round(now - sess["start_time"], 1)
            sess["accumulated_practice_time"] = round(state.get("accumulated_time", 0.0), 1)
            sess["total_notes"] = sum(1 for e in sess["events"] if e.get("type") == "on")
            sess["chords_played"] = state.get("chord_counts", {})
            sess["goal_reached"] = state.get("goal_reached", False)
            save_session_record(sess)
            self.current_session_data = None
        self.hide_all()
        self.app_mode = 'select'
        self.build_select_screen()
        self.select_frame.pack(fill=tk.BOTH, expand=True)
        
    def show_debug_screen(self):
        self.hide_all()
        self.debug_frame.pack(fill=tk.BOTH, expand=True)
        self.is_debug_open = True

    def show_classes_list_screen(self):
        self.stop_metronome()
        self.clear_all_notes()
        self.hide_all()
        self.app_mode = 'classes_list'
        self.build_classes_list_screen()
        self.classes_list_frame.pack(fill=tk.BOTH, expand=True)

    def show_record_screen(self, reset=True):
        self.clear_all_notes()
        self.hide_all()
        self.app_mode = 'record'
        if reset:
            self.recorded_chords = []
            self.recorder.stop()
            self.recorder.events = []
            if hasattr(self, 'rec_clock_lbl'):
                self.rec_clock_lbl.config(text="0:00")
            if hasattr(self, 'rec_start_btn'):
                self.rec_start_btn.config(text="● Start Recording", style='primary', state=tk.NORMAL)
            if hasattr(self, 'rec_status_lbl'):
                self.rec_status_lbl.config(text="● Ready to record", fg=TEXT_SECONDARY)
        else:
            note_count = len(self.recorder.events) // 2
            if hasattr(self, 'rec_start_btn'):
                self.rec_start_btn.config(text="● Record More", style='primary', state=tk.NORMAL)
            if hasattr(self, 'rec_status_lbl'):
                self.rec_status_lbl.config(text=f"Ready to save ({note_count} notes)", fg=COLOR_SUCCESS)

        self.render_record_chords()
        self.update_metronome_ui()
        self.record_frame.pack(fill=tk.BOTH, expand=True)
        self.shared_piano_frame.pack(in_=self.record_frame, side=tk.BOTTOM, fill=tk.X)

    def start_session(self, player):
        self.hide_all()
        self.app_mode = 'free'
        state["selected_player"] = player
        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        p = load_json(PROGRESS_FILE, {}).get(player, {})
        state["accumulated_time"] = p.get("time", 0.0) if player != "Guest" and p.get("date") == today_str else 0.0
        state["last_note_time"] = time.time()
        state["is_playing"] = False
        state["session_active"] = True
        state["goal_reached"] = (state["accumulated_time"] >= GOAL_TIME_SECONDS)
        state["last_update_time"] = time.time()
        state["last_save_time"] = time.time()
        state["chord_counts"] = {}
        state["chord_shapes"] = {}
        state["last_recognized_chord"] = None
        
        self.current_session_data = {
            "id": str(uuid.uuid4()),
            "player": player,
            "date": today_str,
            "start_time": time.time(),
            "mode": self.app_mode,
            "class_name": self.active_class["name"] if self.active_class else None,
            "events": [],
            "chords_played": {},
            "goal_reached": state["goal_reached"]
        }
        
        self.session_title.config(text=f"{state['selected_player']}'s Practice")
        if state["goal_reached"]:
            self.session_subtitle.config(text="FREE PRACTICE • GOAL COMPLETED", fg=COLOR_SUCCESS)
        else:
            self.session_subtitle.config(text="FREE PRACTICE • 15 MIN GOAL", fg=TEXT_SECONDARY)
        self.class_btn.config(text="Select Class")
        self.end_btn.config(text="End Session", command=self.end_session)
        
        # Show bottom bar with Speed and Metro controls right above piano
        self.class_controls_subframe.pack_forget()
        self.tempo_controls_subframe.pack(side=tk.RIGHT, padx=int(8*self.scale))
        
        self.update_chord_grid()
        self.clear_all_notes()
        if hasattr(self, 'piano_rects'): self.update_piano_colors()
        self.root.configure(bg=BG_DARK)
        
        self.session_frame.pack(fill=tk.BOTH, expand=True)
        self.shared_piano_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)
        self.playback_controls_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)

    # ==========================================
    # SCREEN 6: IN-APP CLASS SELECTION SCREEN
    # ==========================================
    def open_class_selector(self):
        self.hide_all()
        self.build_class_select_screen()
        self.class_select_frame.pack(fill=tk.BOTH, expand=True)

    def build_class_select_screen(self):
        for w in self.class_select_frame.winfo_children(): w.destroy()
        s = self.scale
        
        top_bar = tk.Frame(self.class_select_frame, bg=BG_DARK)
        top_bar.pack(fill=tk.X, padx=int(25*s), pady=(int(12*s), int(4*s)))
        tk.Label(top_bar, text="Select Practice Mode", font=(self.font_family, int(22*s), "bold"), bg=BG_DARK, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        PillButton(top_bar, text="← Back to Practice", style='secondary', scale=s, height=int(36*s), command=self.resume_session).pack(side=tk.RIGHT)
        
        scroll = TouchScrollFrame(self.class_select_frame, bg=BG_DARK)
        scroll.pack(fill=tk.BOTH, expand=True, padx=int(30*s), pady=int(6*s))
        
        # Free practice row
        free_row = tk.Frame(scroll.inner, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(18*s), pady=int(10*s))
        free_row.pack(fill=tk.X, pady=int(5*s))
        scroll.bind_child_touch(free_row)
        
        free_info = tk.Frame(free_row, bg=BG_CARD)
        free_info.pack(side=tk.LEFT, expand=True, fill=tk.X)
        tk.Label(free_info, text="🎹 Free Practice", font=(self.font_family, int(18*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY, anchor='w').pack(anchor='w')
        tk.Label(free_info, text="Practice independently with real-time notation and chord detection", font=(self.font_family, int(11*s)), bg=BG_CARD, fg=TEXT_SECONDARY, anchor='w').pack(anchor='w')
        
        PillButton(free_row, text="Select", style='primary', scale=s, height=int(34*s), scroll_parent=scroll, command=lambda: self.on_class_selected("Free Practice")).pack(side=tk.RIGHT, padx=int(6*s))
        
        classes = load_json(CLASSES_FILE, [])
        for c in classes:
            c_row = tk.Frame(scroll.inner, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(18*s), pady=int(10*s))
            c_row.pack(fill=tk.X, pady=int(5*s))
            scroll.bind_child_touch(c_row)
            
            c_info = tk.Frame(c_row, bg=BG_CARD)
            c_info.pack(side=tk.LEFT, expand=True, fill=tk.X)
            tk.Label(c_info, text=f"📖 {c['name']}", font=(self.font_family, int(18*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY, anchor='w').pack(anchor='w')
            chords_count = len(c.get("chords", []))
            dur_sec = int(max([e['time'] for e in c.get('midi_events', [])], default=0))
            dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}"
            tk.Label(c_info, text=f"{chords_count} Chords • {dur_str} Duration • With teacher accompaniment", font=(self.font_family, int(11*s)), bg=BG_CARD, fg=TEXT_SECONDARY, anchor='w').pack(anchor='w')
            
            PillButton(c_row, text="Practice Class", style='primary', scale=s, height=int(34*s), scroll_parent=scroll, command=lambda cid=c["id"]: self.on_class_selected(cid)).pack(side=tk.RIGHT, padx=int(6*s))

    def resume_session(self):
        self.hide_all()
        self.session_frame.pack(fill=tk.BOTH, expand=True)
        self.shared_piano_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)
        self.playback_controls_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)

    def on_class_selected(self, class_id):
        self.hide_all()
        self.session_frame.pack(fill=tk.BOTH, expand=True)
        self.shared_piano_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)
        
        if class_id == "Free Practice":
            if getattr(self, 'current_session_data', None):
                self.current_session_data["mode"] = 'free'
                self.current_session_data["class_name"] = None
            self.class_btn.config(text="Select Class")
            self.app_mode = 'free'
            self.player.pause()
            self.session_title.config(text=f"{state['selected_player']}'s Practice")
            if state["goal_reached"]:
                self.session_subtitle.config(text="FREE PRACTICE • GOAL COMPLETED", fg=COLOR_SUCCESS)
            else:
                self.session_subtitle.config(text="FREE PRACTICE • 15 MIN GOAL", fg=TEXT_SECONDARY)
            if hasattr(self, 'chords_card_title_id'):
                self.chords_card.itemconfig(self.chords_card_title_id, text="CHORD RECOGNITION")
            self.class_controls_subframe.pack_forget()
            self.tempo_controls_subframe.pack(side=tk.RIGHT, padx=int(8*self.scale))
            self.playback_controls_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)
            self.clear_all_notes()
            state["chord_counts"] = {}
            state["chord_shapes"] = {}
            state["last_recognized_chord"] = None
            self.update_chord_grid()
        else:
            c = next((x for x in load_json(CLASSES_FILE, []) if x["id"] == class_id), None)
            if not c: return
            btn_txt = c["name"]
            if len(btn_txt) > 18:
                btn_txt = btn_txt[:16] + "..."
            self.class_btn.config(text=btn_txt)
            self.active_class = c
            self.app_mode = 'class'
            if getattr(self, 'current_session_data', None):
                self.current_session_data["mode"] = 'class'
                self.current_session_data["class_name"] = c["name"]
            self.player.load(c["midi_events"], speed=self.metronome_runner.get_speed_ratio())
            
            self.session_title.config(text=f"{state['selected_player']}'s Practice")
            if state["goal_reached"]:
                self.session_subtitle.config(text=f"CLASS: {c['name'].upper()} • GOAL COMPLETED", fg=COLOR_SUCCESS)
            else:
                self.session_subtitle.config(text=f"CLASS: {c['name'].upper()} • 15 MIN GOAL", fg=TEXT_SECONDARY)
            if hasattr(self, 'chords_card_title_id'):
                self.chords_card.itemconfig(self.chords_card_title_id, text="CLASS CHORDS")
            self.class_controls_subframe.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.tempo_controls_subframe.pack(side=tk.RIGHT)
            self.playback_controls_frame.pack(in_=self.session_frame, side=tk.BOTTOM, fill=tk.X)
            
            for i in range(4):
                if i < len(c["chords"]):
                    chord = c["chords"][i]
                    self.chord_cells[i]["name"].config(text=chord["name"])
                    self.chord_cells[i]["count"].config(text="0 times")
                    self.draw_mini_piano(self.chord_cells[i]["canvas"], self.mini_w, self.mini_h, chord["shape"])
                    state["chord_counts"][chord["name"]] = 0
                else:
                    self.chord_cells[i]["name"].config(text="")
                    self.chord_cells[i]["count"].config(text="")
                    self.chord_cells[i]["canvas"].delete("all")
                    
            self.clear_all_notes()
            self.cp_play_btn.config(text="Pause")
            self.metronome_runner.count_in_and_trigger(4, lambda: self.root.after(0, self.player.play))

    def trigger_goal_celebration(self):
        try:
            s = self.scale
            colors = [ACCENT_PRIMARY, COLOR_SUCCESS, COLOR_WARNING, COLOR_DANGER, '#cba6f7', '#ffffff', '#38bdf8', '#34d399']
            import random, math

            if hasattr(self, 'session_subtitle'):
                mode_prefix = f"CLASS: {self.active_class['name'].upper()} • " if (self.app_mode == 'class' and self.active_class) else "FREE PRACTICE • "
                self.session_subtitle.config(text=f"{mode_prefix}★ GOAL ACHIEVED! COUNTING UP", fg=COLOR_SUCCESS)

            # Particles for clock_canvas
            particles_clock = []
            if hasattr(self, 'clock_center'):
                cx, cy = self.clock_center
                for _ in range(40):
                    angle = random.uniform(0, 2 * math.pi)
                    spd = random.uniform(2.0, 5.5) * s
                    particles_clock.append({
                        "x": cx + math.cos(angle) * random.uniform(5, 25) * s,
                        "y": cy + math.sin(angle) * random.uniform(5, 25) * s,
                        "vx": spd * math.cos(angle),
                        "vy": spd * math.sin(angle) - random.uniform(1.5, 4.0) * s,
                        "size": random.randint(int(5*s), int(10*s)),
                        "color": random.choice(colors),
                        "is_oval": random.choice([True, False])
                    })

            # Particles for staff_canvas
            particles_staff = []
            if hasattr(self, 'staff_canvas'):
                w_st = getattr(self, 'staff_w', int(230*s))
                for _ in range(30):
                    particles_staff.append({
                        "x": random.randint(int(10*s), max(int(20*s), w_st - int(10*s))),
                        "y": random.randint(int(-30*s), int(20*s)),
                        "vx": random.uniform(-1.8, 1.8) * s,
                        "vy": random.uniform(1.5, 4.5) * s,
                        "size": random.randint(int(4*s), int(8*s)),
                        "color": random.choice(colors),
                        "is_oval": random.choice([True, False])
                    })

            def _step(frame):
                try:
                    if not state.get("session_active") or self.app_mode not in ['free', 'class']:
                        if hasattr(self, 'clock_canvas'): self.clock_canvas.delete("goal_confetti")
                        if hasattr(self, 'staff_canvas'): self.staff_canvas.delete("goal_confetti")
                        return

                    if hasattr(self, 'clock_canvas'):
                        self.clock_canvas.delete("goal_confetti")
                    if hasattr(self, 'staff_canvas'):
                        self.staff_canvas.delete("goal_confetti")

                    if frame < 65:
                        if hasattr(self, 'clock_canvas'):
                            for p in particles_clock:
                                p["x"] += p["vx"]
                                p["y"] += p["vy"]
                                p["vy"] += 0.20 * s
                                p["vx"] *= 0.98
                                sz = p["size"]
                                if p["is_oval"]:
                                    self.clock_canvas.create_oval(p["x"], p["y"], p["x"]+sz, p["y"]+sz, fill=p["color"], outline='', tags="goal_confetti")
                                else:
                                    self.clock_canvas.create_rectangle(p["x"], p["y"], p["x"]+sz, p["y"]+sz*0.6, fill=p["color"], outline='', tags="goal_confetti")

                        if hasattr(self, 'staff_canvas'):
                            for p in particles_staff:
                                p["x"] += p["vx"]
                                p["y"] += p["vy"]
                                p["vy"] += 0.15 * s
                                p["vx"] *= 0.98
                                sz = p["size"]
                                if p["is_oval"]:
                                    self.staff_canvas.create_oval(p["x"], p["y"], p["x"]+sz, p["y"]+sz, fill=p["color"], outline='', tags="goal_confetti")
                                else:
                                    self.staff_canvas.create_rectangle(p["x"], p["y"], p["x"]+sz, p["y"]+sz*0.6, fill=p["color"], outline='', tags="goal_confetti")

                        self.root.after(35, lambda: _step(frame + 1))
                    else:
                        if hasattr(self, 'clock_canvas'): self.clock_canvas.delete("goal_confetti")
                        if hasattr(self, 'staff_canvas'): self.staff_canvas.delete("goal_confetti")
                except Exception:
                    pass

            _step(0)
        except Exception:
            pass

    def play_fanfare(self):
        def _fanfare_thread():
            global outport_global
            if not outport_global: return
            fanfare_notes = [72, 76, 79, 84]  # C5, E5, G5, C6
            for n in fanfare_notes:
                try:
                    outport_global.send(mido.Message('note_on', note=n, velocity=95, channel=0))
                    time.sleep(0.12)
                    outport_global.send(mido.Message('note_off', note=n, velocity=0, channel=0))
                except Exception:
                    pass
        threading.Thread(target=_fanfare_thread, daemon=True).start()

    # ==========================================
    # SCREEN 7: IN-APP RECAP SUMMARY
    # ==========================================
    def show_session_recap(self):
        self.hide_all()
        for w in self.recap_frame.winfo_children(): w.destroy()
        s = self.scale
        
        # Outer container fitting safely inside 800x480 screen
        card = tk.Frame(self.recap_frame, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(22*s), pady=int(12*s))
        card.pack(fill=tk.BOTH, expand=True, padx=int(24*s), pady=int(12*s))
        
        pname = state["selected_player"] or "Pianist"
        
        # 1. Top Header Row with title and an immediate, guaranteed visible Done button
        header_row = tk.Frame(card, bg=BG_CARD)
        header_row.pack(fill=tk.X, pady=(0, int(6*s)))
        
        tk.Label(header_row, text=f"Great Practice, {pname}!", font=(self.font_family, int(20*s), "bold"), bg=BG_CARD, fg=TEXT_PRIMARY).pack(side=tk.LEFT)
        PillButton(header_row, text="✔ Done", command=self.show_select_screen, style='primary', scale=s, height=int(32*s)).pack(side=tk.RIGHT)
        
        # 2. Main Celebration & Stats Stage Card
        stage_frame = tk.Frame(card, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(12*s), pady=int(8*s))
        stage_frame.pack(fill=tk.X, pady=int(4*s))

        import datetime
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        progress = load_json(PROGRESS_FILE, {})
        pdata = progress.get(pname, {})
        
        practice_finished = (state["accumulated_time"] >= GOAL_TIME_SECONDS) or (pdata.get("time", 0.0) >= GOAL_TIME_SECONDS) or (today_str in pdata.get("history", []))
        
        mins = int(state["accumulated_time"] // 60)
        secs = int(state["accumulated_time"] % 60)
        pct = min(100, int((state["accumulated_time"] / GOAL_TIME_SECONDS) * 100))
        time_text = f"Time Practiced: {mins}m {secs:02d}s ({pct}% of Goal)"

        if pname != "Guest":
            t_data = tamagotchi.calculate_tamagotchi(pname, progress, goal_seconds=GOAL_TIME_SECONDS)
            fed_today = t_data.get("fed_today", False)
            can_evolve = t_data.get("can_evolve", False)
            
            show_apple = practice_finished and (not fed_today)
            initial_version = t_data["prev_version"] if (show_apple and can_evolve) else t_data["version"]
            
            # Left: 3D Animated Canvas
            cvs_w, cvs_h = int(180*s), int(96*s)
            mascot_cvs = tk.Canvas(stage_frame, width=cvs_w, height=cvs_h, bg=BG_SURFACE, highlightthickness=0)
            mascot_cvs.pack(side=tk.LEFT, padx=(0, int(12*s)))
            
            view_3d = tamagotchi.Tamagotchi3DView(
                mascot_cvs, cx=int(56*s), cy=int(cvs_h/2), scale=0.76*s,
                version=initial_version, mood='happy' if practice_finished else t_data['mood'],
                show_apple=show_apple, can_evolve=can_evolve,
                base_color=t_data.get("base_color")
            )
            view_3d.start_animation(fps=30)
            self.active_tamagotchi_views.append(view_3d)
            
            # Right: Interactive text, time practiced, and action
            info_col = tk.Frame(stage_frame, bg=BG_SURFACE)
            info_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            tk.Label(info_col, text=time_text, font=(self.font_family, int(13*s), "bold"), bg=BG_SURFACE, fg=ACCENT_PRIMARY, anchor='w').pack(anchor='w', pady=(int(1*s), int(3*s)))
            
            if show_apple:
                title_lbl = tk.Label(info_col, text="★ YOU EARNED AN APPLE!", font=(self.font_family, int(13*s), "bold"), bg=BG_SURFACE, fg=COLOR_WARNING, anchor='w')
                title_lbl.pack(anchor='w', pady=(int(1*s), 0))
                sub_lbl = tk.Label(info_col, text="Touch the 3D apple or button to feed your buddy!", font=(self.font_family, int(10*s)), bg=BG_SURFACE, fg=TEXT_PRIMARY, anchor='w')
                sub_lbl.pack(anchor='w', pady=(int(1*s), int(4*s)))
                
                feed_btn = PillButton(info_col, text="★ Tap to Feed Apple", style='warning', scale=s*0.82, height=int(28*s), command=view_3d.feed_apple)
                feed_btn.pack(anchor='w')
                
                def on_fed():
                    p_curr = load_json(PROGRESS_FILE, {})
                    if pname in p_curr:
                        p_curr[pname].setdefault("tamagotchi", {})["fed_date"] = today_str
                        save_json(PROGRESS_FILE, p_curr)
                    title_lbl.config(text="Nom nom nom! Happy Dance!", fg=COLOR_SUCCESS)
                    sub_lbl.config(text="Buddy is full and overjoyed!", fg=TEXT_PRIMARY)
                    try: feed_btn.pack_forget()
                    except Exception: pass
                    
                def on_evolved(new_v):
                    p_curr = load_json(PROGRESS_FILE, {})
                    if pname in p_curr:
                        p_curr[pname].setdefault("tamagotchi", {})["version"] = new_v
                        save_json(PROGRESS_FILE, p_curr)
                    new_name = tamagotchi.VERSION_NAMES.get(new_v, f"Level {new_v}")
                    title_lbl.config(text=f"★ EVOLVED TO {new_name.upper()}!", fg='#fbbf24')
                    sub_lbl.config(text=f"Streak: {t_data['streak']} days! Level Up!", fg=TEXT_PRIMARY)
                    self.play_fanfare()
                    
                view_3d.on_fed = on_fed
                view_3d.on_evolved = on_evolved
                
            elif fed_today:
                title_lbl = tk.Label(info_col, text=f"★ Lv.{t_data['version']} {t_data['version_name']}", font=(self.font_family, int(13*s), "bold"), bg=BG_SURFACE, fg=ACCENT_PRIMARY, anchor='w')
                title_lbl.pack(anchor='w', pady=(int(4*s), 0))
                sub_lbl = tk.Label(info_col, text=f"Buddy is full & happy! • {t_data['streak']}d streak", font=(self.font_family, int(10*s), "bold"), bg=BG_SURFACE, fg=COLOR_SUCCESS, anchor='w')
                sub_lbl.pack(anchor='w', pady=(int(2*s), 0))
            else:
                title_lbl = tk.Label(info_col, text="★ Mascot is Still Hungry", font=(self.font_family, int(13*s), "bold"), bg=BG_SURFACE, fg=COLOR_WARNING, anchor='w')
                title_lbl.pack(anchor='w', pady=(int(4*s), 0))
                rem_mins = max(1, int((GOAL_TIME_SECONDS - state["accumulated_time"]) // 60))
                sub_lbl = tk.Label(info_col, text=f"Practice {rem_mins} more min to feed & evolve!", font=(self.font_family, int(10*s)), bg=BG_SURFACE, fg=TEXT_SECONDARY, anchor='w')
                sub_lbl.pack(anchor='w', pady=(int(2*s), 0))
        else:
            # Guest mode
            cvs_w, cvs_h = int(140*s), int(90*s)
            mascot_cvs = tk.Canvas(stage_frame, width=cvs_w, height=cvs_h, bg=BG_SURFACE, highlightthickness=0)
            mascot_cvs.pack(side=tk.LEFT, padx=(0, int(12*s)))
            view_3d = tamagotchi.Tamagotchi3DView(mascot_cvs, cx=int(65*s), cy=int(cvs_h/2), scale=0.7*s, version=1, mood='happy')
            view_3d.start_animation(fps=24)
            self.active_tamagotchi_views.append(view_3d)
            info_col = tk.Frame(stage_frame, bg=BG_SURFACE)
            info_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            tk.Label(info_col, text=time_text, font=(self.font_family, int(13*s), "bold"), bg=BG_SURFACE, fg=ACCENT_PRIMARY, anchor='w').pack(anchor='w', pady=(int(1*s), int(3*s)))
            tk.Label(info_col, text="Guest Practice Complete!", font=(self.font_family, int(13*s), "bold"), bg=BG_SURFACE, fg=TEXT_PRIMARY, anchor='w').pack(anchor='w', pady=(int(2*s), 0))
            tk.Label(info_col, text="Choose a student profile to track streaks & mascots!", font=(self.font_family, int(10*s)), bg=BG_SURFACE, fg=TEXT_SECONDARY, anchor='w').pack(anchor='w', pady=(int(2*s), 0))

        # 3. Top Chords Played (compact single row)
        sorted_chords = sorted(state["chord_counts"].items(), key=lambda x: x[1], reverse=True)[:3]
        if sorted_chords:
            chords_row = tk.Frame(card, bg=BG_CARD)
            chords_row.pack(fill=tk.X, pady=(int(6*s), int(4*s)))
            tk.Label(chords_row, text="Top Chords:", font=(self.font_family, int(11*s), "bold"), bg=BG_CARD, fg=TEXT_MUTED).pack(side=tk.LEFT, padx=(0, int(8*s)))
            for name, count in sorted_chords:
                c_card = tk.Frame(chords_row, bg=BG_SURFACE, highlightthickness=1, highlightbackground=BORDER_SUBTLE, padx=int(10*s), pady=int(3*s))
                c_card.pack(side=tk.LEFT, padx=int(4*s))
                tk.Label(c_card, text=f"{name}: {count}x", font=(self.font_family, int(11*s), "bold"), bg=BG_SURFACE, fg=TEXT_PRIMARY).pack()

        # 4. Big Primary Done Button at bottom (guaranteed spacious and visible)
        PillButton(card, text="✔ Done - Back to Home", command=self.show_select_screen, style='primary', scale=s, height=int(38*s)).pack(pady=(int(8*s), int(2*s)))
        self.recap_frame.pack(fill=tk.BOTH, expand=True)
        self.recap_frame.pack(fill=tk.BOTH, expand=True)

    def end_session(self):
        self.stop_metronome()
        self.save_current_progress()
        self.player.pause()
        self.clear_all_notes()
        state["session_active"] = False
        if hasattr(self, 'session_subtitle'):
            self.session_subtitle.config(text="STUDENT PRACTICE • 15 MIN GOAL", fg=TEXT_SECONDARY)
        if getattr(self, 'current_session_data', None) and self.current_session_data.get("events"):
            sess = self.current_session_data
            now = time.time()
            sess["end_time"] = now
            sess["duration_seconds"] = round(now - sess["start_time"], 1)
            sess["accumulated_practice_time"] = round(state.get("accumulated_time", 0.0), 1)
            sess["total_notes"] = sum(1 for e in sess["events"] if e.get("type") == "on")
            sess["chords_played"] = state.get("chord_counts", {})
            sess["goal_reached"] = state.get("goal_reached", False)
            save_session_record(sess)
            self.current_session_data = None
        if state["accumulated_time"] >= 15.0:
            self.show_session_recap()
        else:
            self.show_select_screen()

    def toggle_playback(self):
        if self.player.is_playing:
            self.player.pause()
            self.cp_play_btn.config(text="Play")
        else:
            self.player.play()
            self.cp_play_btn.config(text="Pause")

    def restart_class(self):
        self.player.pause()
        self.player.seek(0)
        self.player.set_speed(self.metronome_runner.get_speed_ratio())
        self.clear_all_notes()
        self.cp_play_btn.config(text="Pause")
        self.metronome_runner.count_in_and_trigger(4, lambda: self.root.after(0, self.player.play))

    # ==========================================
    # MAIN LOOP & ANIMATIONS
    # ==========================================
    def update_timer(self):
        try:
            self._update_timer_tick()
        except Exception as e:
            debug_queue.put(f"update_timer error: {e}")
        finally:
            self.root.after(45, self.update_timer)

    def _update_timer_tick(self):
        current_time = time.time()
        delta = current_time - state["last_update_time"]
        state["last_update_time"] = current_time

        # Sleep Raspberry Pi screen after 60s of piano disconnection and no touches
        if state.get("connected_port") is None:
            discon_since = state.get("piano_disconnected_since") or current_time
            if (current_time - discon_since >= 60.0) and (current_time - self.last_user_touch_time >= 60.0):
                if not self.is_screen_sleeping:
                    self.sleep_screen()
        else:
            if self.is_screen_sleeping:
                self.wake_screen()
        
        if self.is_debug_open:
            self.ports_lbl.config(text="Detected USB Ports: " + (", ".join(state["detected_ports"]) if state["detected_ports"] else "None"))
            self.conn_lbl.config(text=f"Connected To: {state['connected_port'] or 'None'}", fg=COLOR_SUCCESS if state["connected_port"] else COLOR_DANGER)
            while not debug_queue.empty():
                self.log_text.insert(tk.END, debug_queue.get_nowait() + "\n")
                self.log_text.see(tk.END)
                if float(self.log_text.index('end-1c').split('.')[0]) > 40: self.log_text.delete('1.0', '2.0')
                    
        needs_color_update = False
        while not midi_queue.empty():
            action, note, source, vel = midi_queue.get_nowait()
            if action == 'piano_connected':
                self.wake_screen()
                continue
            elif action == 'metronome_beat':
                self.animate_metronome_beat(note)
                continue
            elif action == 'metronome_tick':
                continue
            elif action == 'clear_all':
                self.clear_all_notes()
                needs_color_update = True
                continue
            elif action == 'clear_teacher':
                if hasattr(self, 'staff_canvas'):
                    self.staff_canvas.delete("teacher_note")
                self.teacher_notes.clear()
                needs_color_update = True
                continue
            elif action == 'all_off':
                if hasattr(self, 'staff_canvas'):
                    self.staff_canvas.delete("student_note")
                self.drawn_notes.clear()
                needs_color_update = True
                continue

            if source == 'teacher':
                if action == 'on':
                    if hasattr(self, 'staff_canvas'):
                        self.staff_canvas.delete(f"note_{note}_teacher")
                    self.teacher_notes[note] = current_time
                    self.note_velocities[note] = vel
                    self.draw_note(note, self.staff_canvas, color='#818cf8', source='teacher')
                elif action == 'off':
                    self.fade_note_head(note, 'teacher')
                    if note in self.teacher_notes:
                        del self.teacher_notes[note]
            else:
                if action == 'on':
                    if self.is_screen_sleeping:
                        self.wake_screen()
                    if hasattr(self, 'staff_canvas'):
                        self.staff_canvas.delete(f"note_{note}_student")
                    self.drawn_notes[note] = current_time
                    self.note_velocities[note] = vel
                    state["last_note_time"] = current_time
                    state["is_playing"] = True
                    self.draw_note(note, self.staff_canvas, color=ACCENT_PRIMARY, source='student')
                    self.recorder.add_event('on', note, vel)
                    if self.app_mode in ['free', 'class'] and getattr(self, 'current_session_data', None):
                        rel_time = round(current_time - self.current_session_data["start_time"], 3)
                        self.current_session_data["events"].append({
                            "time": rel_time,
                            "type": "on",
                            "note": note,
                            "vel": vel
                        })
                elif action == 'off':
                    self.fade_note_head(note, 'student')
                    if note in self.drawn_notes:
                        del self.drawn_notes[note]
                        state["last_note_time"] = current_time
                    self.recorder.add_event('off', note, 0)
                    if self.app_mode in ['free', 'class'] and getattr(self, 'current_session_data', None):
                        rel_time = round(current_time - self.current_session_data["start_time"], 3)
                        self.current_session_data["events"].append({
                            "time": rel_time,
                            "type": "off",
                            "note": note,
                            "vel": 0
                        })
            needs_color_update = True

        if self.drawn_notes:
            stuck_student = []
            for n, t in list(self.drawn_notes.items()):
                if self.app_mode == 'select' and n in (21, 28, 36, 96, 103, 108):
                    continue
                if current_time - t > 60.0:
                    stuck_student.append(n)
            for n in stuck_student:
                if hasattr(self, 'staff_canvas'):
                    self.staff_canvas.delete(f"note_{n}_student")
                if n in self.drawn_notes:
                    del self.drawn_notes[n]
                needs_color_update = True

        # Check secret piano key combination on main select screen:
        # First (A0=21) and last (C8=108) keys of keyboard held for > 3 seconds
        if self.app_mode == 'select':
            held = set(self.drawn_notes.keys())
            is_combo = (21 in held and 108 in held) or (len(held) == 2 and min(held) in (21, 28, 36) and max(held) in (96, 103, 108))
            if is_combo:
                if self.secret_combo_start == 0.0:
                    self.secret_combo_start = current_time
                elif self.secret_combo_start > 0.0 and (current_time - self.secret_combo_start >= 3.0):
                    self.show_admin_controls = not self.show_admin_controls
                    self.secret_combo_start = -1.0  # Lock so it toggles once per hold
                    self.update_select_screen_admin_buttons()
            else:
                self.secret_combo_start = 0.0

        if self.teacher_notes and not self.player.is_playing:
            if hasattr(self, 'staff_canvas'):
                self.staff_canvas.delete("teacher_note")
            self.teacher_notes.clear()
            needs_color_update = True
                
        if needs_color_update: self.update_piano_colors()
        
        if self.app_mode == 'record':
            if self.is_listening_for_chord:
                active = list(self.drawn_notes.keys())
                if len(active) >= 3:
                    if not self.chord_hold_start:
                        self.chord_hold_start = current_time
                        self.held_chord_notes = set(active)
                    else:
                        if set(active) == self.held_chord_notes:
                            held_time = current_time - self.chord_hold_start
                            if held_time >= 2.0:
                                name, _ = self.identify_chord_advanced(active)
                                if not name: name = "Custom Chord"
                                shape = list(set(n - (min(active) // 12) * 12 for n in active))
                                self.recorded_chords.append({"name": name, "shape": shape})
                                self.is_listening_for_chord = False
                                self.chord_hold_start = 0
                                self.rec_status_lbl.config(text=f"✔ Added chord: {name}!", fg=COLOR_SUCCESS)
                                self.render_record_chords()
                            elif held_time > 0.3:
                                self.rec_status_lbl.config(text=f"🎹 Holding chord... ({held_time:.1f}s / 2.0s)", fg=COLOR_WARNING)
                        else:
                            self.chord_hold_start = current_time
                            self.held_chord_notes = set(active)
                else: self.chord_hold_start = 0

            if self.recorder.is_recording:
                elapsed = int(current_time - self.recorder.start_time)
                self.rec_clock_lbl.config(text=f"{elapsed // 60}:{elapsed % 60:02d}")
                notes_cnt = len(self.recorder.events) // 2
                self.rec_status_lbl.config(text=f"● RECORDING ({notes_cnt} notes)", fg=COLOR_DANGER)

        if self.app_mode == 'class':
            if self.player.is_playing:
                now = (current_time - self.player.start_time) * self.player.speed
                pct = min(100, (now / self.player.duration * 100) if self.player.duration else 0)
                self.cp_slider.set(pct)
        
        # ACTIVE PRACTICE SESSION TIMER LOGIC
        if self.app_mode in ['free', 'class'] and state["session_active"]:
            if self.drawn_notes:
                state["last_note_time"] = current_time
                state["is_playing"] = True
            elif current_time - state["last_note_time"] > 2.0:
                state["is_playing"] = False
            if state["is_playing"]: 
                state["accumulated_time"] += delta
                if current_time - state.get("last_save_time", 0) > 10.0:
                    state["last_save_time"] = current_time
                    self.save_current_progress()
            
            is_guest = (state["selected_player"] == "Guest")
            acc_time = state["accumulated_time"]
            
            if is_guest:
                mins = int(acc_time // 60)
                secs = int(acc_time % 60)
                time_str = f"{mins}:{secs:02d}"
                sub_txt = "FREE PLAY"
                sub_col = TEXT_MUTED
                arc_col = ACCENT_PRIMARY if state["is_playing"] else COLOR_INACTIVE
                status_txt = "● ACTIVE" if state["is_playing"] else "● PAUSED"
                status_fill = '#152e3d' if state["is_playing"] else '#1e2633'
                status_col = ACCENT_PRIMARY if state["is_playing"] else TEXT_SECONDARY
                target_extent = - min(359.9, (acc_time / float(GOAL_TIME_SECONDS)) * 359.9)
                
            elif acc_time >= GOAL_TIME_SECONDS:
                if not state["goal_reached"]:
                    state["goal_reached"] = True
                    if getattr(self, 'current_session_data', None):
                        self.current_session_data["goal_reached"] = True
                    self.save_current_progress()
                    self.trigger_goal_celebration()
                    
                mins = int(acc_time // 60)
                secs = int(acc_time % 60)
                time_str = f"{mins}:{secs:02d}"
                
                overtime_min = int((acc_time - GOAL_TIME_SECONDS) // 60)
                if overtime_min > 0:
                    sub_txt = f"+{overtime_min}M OVER GOAL"
                else:
                    sub_txt = "COUNTING UP"
                    
                sub_col = COLOR_SUCCESS
                arc_col = COLOR_SUCCESS
                status_txt = f"✔ ACTIVE ({mins}m)" if state["is_playing"] else "✔ GOAL MET"
                status_fill = '#133830'
                status_col = COLOR_SUCCESS
                target_extent = -359.9
                
            else:
                rem_sec = max(0.0, GOAL_TIME_SECONDS - acc_time)
                mins = int(rem_sec // 60)
                secs = int(rem_sec % 60)
                time_str = f"{mins}:{secs:02d}"
                sub_txt = "15M GOAL"
                sub_col = TEXT_MUTED
                
                pct_rem = rem_sec / float(GOAL_TIME_SECONDS)
                target_extent = - (pct_rem * 359.9)
                
                if state["is_playing"]:
                    arc_col = ACCENT_PRIMARY
                    status_txt = "● ACTIVE"
                    status_fill = '#152e3d'
                    status_col = ACCENT_PRIMARY
                else:
                    arc_col = COLOR_INACTIVE
                    status_txt = "● PAUSED"
                    status_fill = '#1e2633'
                    status_col = TEXT_SECONDARY

            self.clock_target_extent = target_extent
            self.clock_current_extent += (self.clock_target_extent - self.clock_current_extent) * 0.22
            self.clock_canvas.itemconfig(self.arc_id, extent=self.clock_current_extent, outline=arc_col)
            
            self.clock_canvas.itemconfig(self.clock_time_text, text=time_str)
            self.clock_canvas.itemconfig(self.clock_sub_text, text=sub_txt, fill=sub_col)
            self.clock_canvas.itemconfig(self.status_pill_rect, fill=status_fill)
            self.clock_canvas.itemconfig(self.status_pill_text, text=status_txt, fill=status_col)
                
            if current_time - state["last_note_time"] > INACTIVITY_TIMEOUT_SECONDS and state["accumulated_time"] > 0:
                self.end_session()

        self.check_web_commands()

        # Periodic live state flush for web dashboard (~4 times a second)
        if current_time - getattr(self, '_last_live_state_save', 0) >= 0.25:
            self._last_live_state_save = current_time
            now_player_time = 0.0
            if self.player.is_playing:
                now_player_time = round((current_time - self.player.start_time) * self.player.speed, 2)
            elif self.player.events:
                now_player_time = round(self.player.offset, 2)

            live_dict = {
                "timestamp": current_time,
                "player": state.get("selected_player"),
                "app_mode": self.app_mode,
                "active_class": self.active_class.get("name") if self.active_class else None,
                "session_active": state.get("session_active", False),
                "is_playing": state.get("is_playing", False),
                "accumulated_time": round(state.get("accumulated_time", 0.0), 1),
                "goal_time": GOAL_TIME_SECONDS,
                "goal_reached": state.get("goal_reached", False),
                "connected_port": state.get("connected_port"),
                "detected_ports": state.get("detected_ports", []),
                "active_notes": list(self.drawn_notes.keys()),
                "teacher_notes": list(self.teacher_notes.keys()),
                "last_recognized_chord": state.get("last_recognized_chord"),
                "chord_counts": state.get("chord_counts", {}),
                "metronome_state": self.metronome_runner.speed_mode if self.metronome_runner.is_active else "off",
                "metronome_bpm": self.metronome_runner.bpm,
                "piano_player": {
                    "is_playing": self.player.is_playing,
                    "current_time": now_player_time,
                    "duration": round(self.player.duration, 2),
                    "speed": round(self.player.speed, 2),
                    "song_id": getattr(self, "current_playing_song_id", None),
                    "song_title": getattr(self, "current_playing_song_title", None),
                    "mute_drums": getattr(self.player, "mute_drums", True)
                }
            }
            save_json(LIVE_STATE_FILE, live_dict)

        # Periodic config check (~once per second)
        if current_time - getattr(self, '_last_config_check', 0) >= 1.0:
            self._last_config_check = current_time
            self.check_reload_config()

if __name__ == "__main__":
    root = tk.Tk()
    root.bind('<Escape>', lambda e: root.destroy())
    PianoTimerApp(root)
    root.mainloop()
