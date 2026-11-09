"""
Tamagotchi Companion Module for Piano Practice Timer.
Replaces the star reward system with a per-student 3D animated companion.

Moods:
1. Sad: When the student hasn't played in the last 3 days.
2. Hungry: When the student hasn't finished its daily practice.
3. Happy: If the student has played its daily practice.

Versions (Evolution Levels):
1. Blob with a face: Has not finished practice during last 3 days (Level 1, 0 stars).
2. Blob with a face and an antenna with a star: Finished practice during last day (Level 2, 1-day streak).
3. Blob with 2 stars: Finished practice for last 2 consecutive days (Level 3, 2-day streak).
4. Star with a face: Finished practice for last 3 consecutive days (Level 4, 3-day streak).
5. Rainbow star with a face: Finished practice for last 4+ days (Level 5, 4+ day streak).

Downgrade:
If the character finished the day hungry, it automatically downgrades to the previous version.

Celebration & Evolution:
On summary page, student receives an apple. Touching it feeds the mascot, plays a happy dance,
and if goal promoted them to next version, plays an evolution transformation animation.
"""

import math
import time
import colorsys
import datetime
try:
    import tkinter as tk
except ImportError:
    class _MockTk:
        ARC = "arc"
        CHORD = "chord"
        PIESLICE = "pieslice"
        Canvas = object
    tk = _MockTk()

# =============================================================================
# DATA & BUSINESS LOGIC
# =============================================================================

VERSION_NAMES = {
    1: "Baby Bean (Do)",
    2: "Sprout Note (Re)",
    3: "Starlet Antenna (Mi)",
    4: "Clef Tuft (Fa)",
    5: "Little Bell (Sol)",
    6: "Metronome Pup",
    7: "Keyboard Cat",
    8: "Clef Bunny",
    9: "Jazz Frog",
    10: "Drummer Hamster",
    11: "Boombox Bot",
    12: "Music Box Piggy",
    13: "Vinyl DJ Penguin",
    14: "Accordion Armadillo",
    15: "Synthwave Glow-Cube",
    16: "Amadeus Bear",
    17: "Rocker Hedgehog",
    18: "Grand Piano Turtle",
    19: "Opera Owl",
    20: "Golden Baton Maestro",
    21: "Melody Sprite",
    22: "Chime Golem",
    23: "Harp-Winged Pegasus",
    24: "Crescendo Phoenix",
    25: "Crystal Dragonette",
    26: "Starlight Seraph",
    27: "Saturn's Organist",
    28: "Nebula Phoenix",
    29: "Chrono Metronome",
    30: "Grand Rainbow Virtuoso",
    31: "Apollo's Sun-King Lyre",
    32: "Omnichord Celestial Sovereign"
}

VERSION_COLORS = {
    1: "#38bdf8",   # Baby Bean (Sky Blue)
    2: "#0284c7",   # Sprout Note (Azure)
    3: "#059669",   # Starlet Antenna (Emerald)
    4: "#10b981",   # Clef Tuft (Mint)
    5: "#f59e0b",   # Little Bell (Golden)
    6: "#d97706",   # Metronome Pup (Caramel)
    7: "#f43f5e",   # Keyboard Cat (Coral Rose)
    8: "#a855f7",   # Clef Bunny (Lavender Violet)
    9: "#22c55e",   # Jazz Frog (Smooth Green)
    10: "#fb923c",  # Drummer Hamster (Tangerine)
    11: "#64748b",  # Boombox Bot (Steel Slate)
    12: "#f472b6",  # Music Box Piggy (Ballet Pink)
    13: "#1e293b",  # Vinyl DJ Penguin (Tuxedo Obsidian)
    14: "#b45309",  # Accordion Armadillo (Steampunk Bronze)
    15: "#ec4899",  # Synthwave Glow-Cube (Neon Magenta)
    16: "#e11d48",  # Amadeus Bear (Crimson Velvet)
    17: "#8b5cf6",  # Rocker Hedgehog (Electric Purple)
    18: "#0d9488",  # Grand Piano Turtle (Ocean Teal)
    19: "#6366f1",  # Opera Owl (Midnight Indigo)
    20: "#eab308",  # Golden Baton Maestro (Maestro Gold)
    21: "#38bdf8",  # Melody Sprite (Fairy Cyan)
    22: "#78716c",  # Chime Golem (Ancient Moss Stone)
    23: "#f8fafc",  # Harp-Winged Pegasus (Pearl White)
    24: "#ef4444",  # Crescendo Phoenix (Blazing Scarlet)
    25: "#06b6d4",  # Crystal Dragonette (Radiant Crystal)
    26: "#facc15",  # Starlight Seraph (Solar Gold)
    27: "#818cf8",  # Saturn's Organist (Cosmic Periwinkle)
    28: "#c084fc",  # Nebula Phoenix (Nebula Violet)
    29: "#d97706",  # Chrono Metronome (Antique Clockwork)
    30: "#ec4899",  # Grand Rainbow Virtuoso (Rainbow Diamond)
    31: "#fbbf24",  # Apollo's Sun-King Lyre (Sun Radiance)
    32: "#a855f7"   # Omnichord Sovereign (Cosmic Aurora)
}

def calculate_tamagotchi(player, progress_data=None, today=None, goal_seconds=900):
    """
    Computes Tamagotchi mascot status for a given student according to exact rules.
    """
    if today is None:
        today = datetime.date.today()
    if progress_data is None:
        progress_data = {}
        
    pdata = progress_data.get(player, {})
    history_list = pdata.get("history", [])
    today_str = today.strftime("%Y-%m-%d")
    
    # Check if student completed today's practice
    p_date = pdata.get("date")
    p_time = pdata.get("time", 0.0) if p_date == today_str else 0.0
    today_completed = (today_str in history_list) or (p_time >= goal_seconds)
    
    # Parse history dates into datetime.date objects, sorted unique
    completed_dates = set()
    for d_str in history_list:
        try:
            completed_dates.add(datetime.datetime.strptime(d_str, "%Y-%m-%d").date())
        except Exception:
            pass
    if today_completed:
        completed_dates.add(today)
        
    # Calculate days since last completed practice
    if completed_dates:
        latest_date = max(completed_dates)
        days_since_practice = (today - latest_date).days
    else:
        latest_date = None
        days_since_practice = 999
        
    # -------------------------------------------------------------
    # MOOD LOGIC:
    # 1. Sad when student hasn't played in the last 3 days
    # 2. Hungry when student hasn't finished daily practice
    # 3. Happy if student has played its daily practice
    # -------------------------------------------------------------
    if today_completed:
        mood = 'happy'
        mood_label = 'Happy'
    elif days_since_practice >= 3:
        mood = 'sad'
        mood_label = 'Sad'
    else:
        mood = 'hungry'
        mood_label = 'Hungry'
        
    # -------------------------------------------------------------
    # STREAK & VERSION PROGRESSION LOGIC (32 LEVELS):
    # Streak 0: Level 1 (Baby Bean)
    # Streak 1: Level 2 (Sprout Note)
    # Streak 2: Level 3 (Starlet Antenna)
    # ...
    # Streak 31+: Level 32 (Omnichord Celestial Sovereign)
    # -------------------------------------------------------------
    if today_completed:
        # Consecutive days ending TODAY
        streak = 0
        check_date = today
        while check_date in completed_dates:
            streak += 1
            check_date -= datetime.timedelta(days=1)
            
        version = min(32, max(1, streak + 1))
            
        # Also compute what previous version was before today's completion
        # to determine if an evolution animation should play
        prev_streak = 0
        prev_check = today - datetime.timedelta(days=1)
        while prev_check in completed_dates:
            prev_streak += 1
            prev_check -= datetime.timedelta(days=1)
            
        prev_version = min(32, max(1, prev_streak + 1))
        can_evolve = (version > prev_version)
    else:
        # Today is NOT finished yet
        prev_version = 1
        can_evolve = False
        
        if days_since_practice >= 3:
            version = 1
            streak = 0
        elif days_since_practice == 1:
            # Yesterday was completed. Streak ending yesterday:
            streak = 0
            check_date = today - datetime.timedelta(days=1)
            while check_date in completed_dates:
                streak += 1
                check_date -= datetime.timedelta(days=1)
                
            version = min(32, max(1, streak + 1))
        elif days_since_practice == 2:
            # 2 days ago was completed, yesterday was missed (finished hungry -> downgraded 1 level!)
            streak = 0
            check_date = today - datetime.timedelta(days=2)
            while check_date in completed_dates:
                streak += 1
                check_date -= datetime.timedelta(days=1)
                
            base_v = min(32, max(1, streak + 1))
            version = max(1, base_v - 1)
        else:
            version = 1
            streak = 0
            
    # Check if fed today
    tamagotchi_saved = pdata.get("tamagotchi", {})
    fed_today = (tamagotchi_saved.get("fed_date") == today_str)

    # Admin overrides from admin panel
    if tamagotchi_saved.get("version"):
        try:
            v_ov = int(tamagotchi_saved["version"])
            if 1 <= v_ov <= 32:
                version = v_ov
        except Exception:
            pass

    if tamagotchi_saved.get("forced_mood"):
        fm = tamagotchi_saved["forced_mood"]
        if fm in ('happy', 'hungry', 'sad'):
            mood = fm
            mood_label = {'happy': 'Happy', 'hungry': 'Hungry', 'sad': 'Sad'}.get(fm, mood_label)

    if tamagotchi_saved.get("forced_streak") is not None:
        try:
            streak = int(tamagotchi_saved["forced_streak"])
        except Exception:
            pass
    
    return {
        "version": version,
        "prev_version": prev_version if today_completed else version,
        "can_evolve": can_evolve,
        "version_name": VERSION_NAMES.get(version, "Blob with a Face"),
        "mood": mood,
        "mood_label": mood_label,
        "streak": streak,
        "days_since_practice": days_since_practice,
        "today_completed": today_completed,
        "fed_today": fed_today,
        "time_practiced_today": p_time,
        "forced_version": tamagotchi_saved.get("version"),
        "forced_mood": tamagotchi_saved.get("forced_mood"),
        "base_color": tamagotchi_saved.get("base_color")
    }


def get_student_stats(player, sessions=None, progress_data=None, today=None, goal_seconds=900):
    """
    Computes aggregated lifetime and weekly statistics for a student:
    - Total times practiced (session count + history days)
    - Notes played in the last week
    - Total practice time accumulated
    - Top chords
    - Tamagotchi companion status
    """
    if today is None:
        today = datetime.date.today()
    if progress_data is None:
        try:
            import os, json
            base_dir = os.path.dirname(os.path.abspath(__file__))
            pfile = os.path.join(base_dir, "progress.json")
            if os.path.exists(pfile):
                with open(pfile, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
            else:
                progress_data = {}
        except Exception:
            progress_data = {}

    if sessions is None:
        try:
            import os, json
            base_dir = os.path.dirname(os.path.abspath(__file__))
            sfile = os.path.join(base_dir, "sessions.json")
            if os.path.exists(sfile):
                with open(sfile, 'r', encoding='utf-8') as f:
                    sessions = json.load(f)
            else:
                sessions = []
        except Exception:
            sessions = []

    pdata = progress_data.get(player, {})
    history = pdata.get("history", [])
    today_str = today.strftime("%Y-%m-%d")

    # Filter sessions for this student
    p_sessions = [s for s in sessions if s.get("player") == player]
    total_sessions = len(p_sessions)
    total_days_completed = len(history)

    # Total practice time
    sess_time = sum(s.get("duration_seconds", s.get("accumulated_practice_time", 0.0)) for s in p_sessions)
    hist_est_time = len(history) * goal_seconds
    today_time = pdata.get("time", 0.0) if pdata.get("date") == today_str else 0.0
    total_time_seconds = max(sess_time, hist_est_time + today_time)

    # Notes in last week (7 days)
    now_ts = time.time()
    week_ago_ts = now_ts - 7 * 86400
    recent_sessions = [s for s in p_sessions if s.get("start_time", 0) >= week_ago_ts or s.get("end_time", 0) >= week_ago_ts]

    notes_last_week = 0
    for s in recent_sessions:
        if "total_notes" in s:
            notes_last_week += s["total_notes"]
        elif "events" in s:
            notes_last_week += len([e for e in s["events"] if e.get("type") == "on"])

    total_notes_lifetime = 0
    chord_counts = {}
    for s in p_sessions:
        if "total_notes" in s:
            total_notes_lifetime += s["total_notes"]
        elif "events" in s:
            total_notes_lifetime += len([e for e in s["events"] if e.get("type") == "on"])

        for c, count in s.get("chords_played", {}).items():
            chord_counts[c] = chord_counts.get(c, 0) + count

    sorted_chords = sorted(chord_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    t_info = calculate_tamagotchi(player, progress_data, today=today, goal_seconds=goal_seconds)

    return {
        "player": player,
        "total_sessions": total_sessions,
        "total_days_completed": total_days_completed,
        "total_time_seconds": round(total_time_seconds, 1),
        "notes_last_week": notes_last_week,
        "total_notes": total_notes_lifetime,
        "today_seconds": round(today_time, 1),
        "top_chords": sorted_chords,
        "tamagotchi": t_info
    }


# =============================================================================
# 3D VECTOR MATH & PROJECTION
# =============================================================================

def rotate_point_3d(x, y, z, roll=0.0, pitch=0.0, yaw=0.0):
    """Rotates a 3D point by Roll (Z), Pitch (X), and Yaw (Y) in radians."""
    # Yaw around Y
    if yaw != 0.0:
        cy, sy = math.cos(yaw), math.sin(yaw)
        x, z = x * cy + z * sy, -x * sy + z * cy
    # Pitch around X
    if pitch != 0.0:
        cx, sx = math.cos(pitch), math.sin(pitch)
        y, z = y * cx - z * sx, y * sx + z * cx
    # Roll around Z
    if roll != 0.0:
        cz, sz = math.cos(roll), math.sin(roll)
        x, y = x * cz - y * sz, x * sz + y * cz
    return x, y, z

def project_3d(x, y, z, cx, cy, f=180.0, d=260.0):
    """Perspective projection from 3D to 2D canvas coordinates."""
    denom = z + d
    if denom <= 1.0: denom = 1.0
    px = cx + (x * f) / denom
    py = cy - (y * f) / denom
    return px, py

def shade_color(hex_color, intensity):
    """Adjusts hex color brightness by light intensity factor (0.15 to 1.35)."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r = min(255, max(0, int(r * intensity)))
        g = min(255, max(0, int(g * intensity)))
        b = min(255, max(0, int(b * intensity)))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color

def rainbow_color(offset, intensity=1.0):
    """Generates vibrant prismatic rainbow hex color from offset angle."""
    hue = (offset % 1.0)
    r, g, b = colorsys.hls_to_rgb(hue, 0.58, 0.95)
    r = min(255, max(0, int(r * 255 * intensity)))
    g = min(255, max(0, int(g * 255 * intensity)))
    b = min(255, max(0, int(b * 255 * intensity)))
    return f"#{r:02x}{g:02x}{b:02x}"


# =============================================================================
# 3D MESH GENERATORS
# =============================================================================

def make_blob_mesh(rx=36, ry=34, rz=32, rings=6, slices=10):
    """Generates a 3D faceted ellipsoid blob mesh."""
    verts = [(0.0, ry, 0.0)]
    for i in range(1, rings):
        phi = math.pi * i / rings
        y = ry * math.cos(phi)
        r = math.sin(phi)
        for j in range(slices):
            theta = 2 * math.pi * j / slices
            x = rx * r * math.cos(theta)
            z = rz * r * math.sin(theta)
            verts.append((x, y, z))
    verts.append((0.0, -ry, 0.0))
    
    faces = []
    # North pole cap
    for j in range(slices):
        nxt = (j + 1) % slices
        faces.append([0, 1 + j, 1 + nxt])
    # Middle bands
    for i in range(rings - 2):
        row1 = 1 + i * slices
        row2 = 1 + (i + 1) * slices
        for j in range(slices):
            nxt = (j + 1) % slices
            faces.append([row1 + j, row2 + j, row2 + nxt, row1 + nxt])
    # South pole cap
    south_idx = len(verts) - 1
    last_row = 1 + (rings - 2) * slices
    for j in range(slices):
        nxt = (j + 1) % slices
        faces.append([south_idx, last_row + nxt, last_row + j])
        
    return verts, faces

def make_star_mesh(r_out=42, r_in=18, depth=12, bevel=6):
    """Generates an extruded, beveled 3D 5-pointed star mesh."""
    verts = []
    # Front center vertex 0
    verts.append((0.0, 0.0, depth/2 + bevel))
    # 10 front perimeter vertices 1..10
    for i in range(10):
        ang = math.pi/2 - i * (math.pi / 5)
        r = r_out if (i % 2 == 0) else r_in
        verts.append((r * math.cos(ang), r * math.sin(ang), depth/2))
    # Back center vertex 11
    verts.append((0.0, 0.0, -depth/2 - bevel))
    # 10 back perimeter vertices 12..21
    for i in range(10):
        ang = math.pi/2 - i * (math.pi / 5)
        r = r_out if (i % 2 == 0) else r_in
        verts.append((r * math.cos(ang), r * math.sin(ang), -depth/2))
        
    faces = []
    # Front triangles
    for i in range(10):
        v1 = 1 + i
        v2 = 1 + ((i + 1) % 10)
        faces.append([0, v1, v2])
    # Back triangles
    for i in range(10):
        v1 = 12 + i
        v2 = 12 + ((i + 1) % 10)
        faces.append([11, v2, v1])
    # Side edge quads
    for i in range(10):
        f1 = 1 + i
        f2 = 1 + ((i + 1) % 10)
        b1 = 12 + i
        b2 = 12 + ((i + 1) % 10)
        faces.append([f1, f2, b2, b1])
        
    return verts, faces

def make_small_star_mesh(r_out=14, r_in=6, depth=5):
    """Generates an accessory orbiting/antenna 3D star."""
    return make_star_mesh(r_out=r_out, r_in=r_in, depth=depth, bevel=3)

def make_apple_mesh(radius=15):
    """Generates a 3D red apple mesh with indented dimples."""
    verts, faces = make_blob_mesh(rx=radius, ry=radius*0.9, rz=radius, rings=5, slices=8)
    return verts, faces

def make_cube_mesh(w=34, h=34, d=34):
    """Generates a 3D box mesh for robot and gadget companions."""
    hw, hh, hd = w/2, h/2, d/2
    verts = [
        (-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd),
        (-hw, -hh,  hd), (hw, -hh,  hd), (hw, hh,  hd), (-hw, hh,  hd)
    ]
    faces = [
        [4, 5, 6, 7],  # Front (+Z)
        [1, 0, 3, 2],  # Back (-Z)
        [0, 4, 7, 3],  # Left (-X)
        [5, 1, 2, 6],  # Right (+X)
        [7, 6, 2, 3],  # Top (+Y)
        [0, 1, 5, 4]   # Bottom (-Y)
    ]
    return verts, faces

def make_cone_bell_mesh(r_base=34, r_top=14, h=34, slices=10):
    """Generates a flared bell / musical horn mesh."""
    verts = []
    for i in range(slices):
        ang = (2 * math.pi * i) / slices
        verts.append((r_base * math.cos(ang), -h/2, r_base * math.sin(ang)))
    for i in range(slices):
        ang = (2 * math.pi * i) / slices
        verts.append((r_top * math.cos(ang), h/2, r_top * math.sin(ang)))
    top_c = len(verts)
    verts.append((0, h/2 + 5, 0))
    bot_c = len(verts)
    verts.append((0, -h/2, 0))
    
    faces = []
    for i in range(slices):
        nxt = (i + 1) % slices
        faces.append([i, nxt, slices + nxt, slices + i])
    for i in range(slices):
        nxt = (i + 1) % slices
        faces.append([top_c, slices + i, slices + nxt])
    for i in range(slices):
        nxt = (i + 1) % slices
        faces.append([bot_c, nxt, i])
    return verts, faces

def make_wing_mesh(w=32, h=20, depth=4):
    """Generates a beveled feather/dragon wing mesh."""
    hd = depth / 2
    verts = [
        (0, 0, hd), (w*0.5, h*0.4, hd), (w, h*0.85, hd),
        (w*0.75, h*0.25, hd), (w*0.5, -h*0.2, hd), (0, -h*0.3, hd),
        (0, 0, -hd), (w*0.5, h*0.4, -hd), (w, h*0.85, -hd),
        (w*0.75, h*0.25, -hd), (w*0.5, -h*0.2, -hd), (0, -h*0.3, -hd)
    ]
    faces = [
        [0, 1, 2, 3, 4, 5],
        [11, 10, 9, 8, 7, 6]
    ]
    for i in range(6):
        nxt = (i + 1) % 6
        faces.append([i, nxt, 6 + nxt, 6 + i])
    return verts, faces

def make_ring_mesh(r_inner=42, r_outer=54, slices=16):
    """Generates a planar ring mesh for celestial halos and piano key bands."""
    verts = []
    for i in range(slices):
        ang = (2 * math.pi * i) / slices
        verts.append((r_inner * math.cos(ang), 0, r_inner * math.sin(ang)))
        verts.append((r_outer * math.cos(ang), 0, r_outer * math.sin(ang)))
    faces = []
    for i in range(slices):
        nxt = (i + 1) % slices
        i0, o0 = i * 2, i * 2 + 1
        i1, o1 = nxt * 2, nxt * 2 + 1
        faces.append([i0, o0, o1, i1])
    return verts, faces


# =============================================================================
# TAMAGOTCHI 3D CANVAS VIEW
# =============================================================================

class Tamagotchi3DView:
    """
    Renders and animates an interactive 3D Tamagotchi companion on a Tkinter Canvas.
    Supports 32 progressive levels with idle animation, feeding, happy dance, and evolution sequences.
    """
    def __init__(self, canvas, cx=60, cy=50, scale=1.0, version=1, mood='happy',
                 show_apple=False, on_fed=None, on_evolved=None, can_evolve=False, base_color=None):
        self.canvas = canvas
        self.cx = cx
        self.cy = cy
        self.scale = scale
        self.version = max(1, min(32, int(version)))
        self.target_version = self.version
        self.mood = mood  # 'sad', 'hungry', 'happy'
        self.base_color = base_color
        
        self.show_apple = show_apple
        self.can_evolve = can_evolve
        self.apple_eaten = False
        self.on_fed = on_fed
        self.on_evolved = on_evolved
        
        # State machine: 'idle', 'feeding', 'dance', 'evolve'
        self.state = 'idle'
        self.state_timer = 0.0
        self.t = 0.0
        self.is_running = False
        
        # Animation parameters
        self.yaw = 0.0
        self.pitch = 0.0
        self.roll = 0.0
        self.squish_y = 1.0
        self.squish_x = 1.0
        self.bounce_y = 0.0
        
        # Apple animation state
        self.apple_x = self.cx + int(68 * self.scale)
        self.apple_y = self.cy + int(10 * self.scale)
        self.apple_yaw = 0.0
        self.apple_scale = 1.0
        
        # Particles
        self.particles = []
        
        # Eye blink cycle
        self.blink_phase = 0.0
        
        # Pre-generate 3D meshes
        self._blob_verts, self._blob_faces = make_blob_mesh(rx=34*scale, ry=32*scale, rz=30*scale)
        self._star_verts, self._star_faces = make_star_mesh(r_out=38*scale, r_in=17*scale, depth=12*scale, bevel=6*scale)
        self._small_star_verts, self._small_star_faces = make_small_star_mesh(r_out=12*scale, r_in=5*scale, depth=4*scale)
        self._apple_verts, self._apple_faces = make_apple_mesh(radius=13*scale)
        self._cube_verts, self._cube_faces = make_cube_mesh(34*scale, 34*scale, 34*scale)
        self._bell_verts, self._bell_faces = make_cone_bell_mesh(34*scale, 14*scale, 34*scale)
        self._wing_verts, self._wing_faces = make_wing_mesh(32*scale, 20*scale)
        self._ring_verts, self._ring_faces = make_ring_mesh(40*scale, 54*scale)
        
        # Base colors per version (32 levels)
        self.version_colors = VERSION_COLORS
        
        # Light vector: Shining from front-top-right (towards character from viewer side)
        lx, ly, lz = 0.35, 0.65, 0.85
        mag = math.sqrt(lx*lx + ly*ly + lz*lz)
        self.light_vec = (lx/mag, ly/mag, lz/mag)
        
        # Bind canvas touch
        if self.canvas is not None and hasattr(self.canvas, "bind"):
            self.canvas.bind("<Button-1>", self._on_canvas_click, add="+")
        
    def set_companion(self, version, mood, show_apple=False, can_evolve=False, base_color=None):
        """Updates companion version and mood."""
        self.version = max(1, min(32, int(version)))
        self.target_version = self.version
        self.mood = mood
        if base_color is not None:
            self.base_color = base_color
        self.show_apple = show_apple
        self.can_evolve = can_evolve
        self.apple_eaten = False
        self.apple_x = self.cx + int(68 * self.scale)
        self.apple_y = self.cy + int(10 * self.scale)
        self.apple_scale = 1.0
        
    def start_animation(self, fps=30):
        """Starts real-time 3D animation loop."""
        if self.is_running: return
        self.is_running = True
        self.frame_delay = max(15, int(1000 / fps))
        self._step()
        
    def stop_animation(self):
        """Pauses animation loop."""
        self.is_running = False

    def _on_canvas_click(self, event):
        """Handles touch clicks on the mascot or apple."""
        ex, ey = event.x, event.y
        # Check if apple was tapped (forgiving radius for touchscreen)
        if self.show_apple and not self.apple_eaten and self.state == 'idle':
            dist_apple = math.hypot(ex - self.apple_x, ey - self.apple_y)
            if dist_apple <= max(45.0, 50.0 * self.scale):
                self.feed_apple()
                return
                
        # Check if mascot was tapped
        dist_mascot = math.hypot(ex - self.cx, ey - (self.cy - self.bounce_y))
        if dist_mascot <= max(45.0, 55.0 * self.scale):
            self._mascot_poke_reaction()

    def _mascot_poke_reaction(self):
        """Cute bounce and heart burst when mascot is touched."""
        if self.state == 'idle':
            self.bounce_y = 16.0 * self.scale
            self.squish_y = 1.25
            self.squish_x = 0.82
            # Add sparkle particles
            for _ in range(5):
                ang = 2 * math.pi * (_ / 5)
                self.particles.append({
                    "x": self.cx + math.cos(ang) * 15 * self.scale,
                    "y": self.cy - self.bounce_y + math.sin(ang) * 15 * self.scale,
                    "vx": math.cos(ang) * 1.8,
                    "vy": math.sin(ang) * 1.8 - 1.2,
                    "life": 1.0,
                    "color": "#fbbf24",
                    "text": "★"
                })

    def feed_apple(self):
        """Triggers the apple eating and celebration dance sequence."""
        if self.state != 'idle' or self.apple_eaten: return
        self.state = 'feeding'
        self.state_timer = 0.0

    # -------------------------------------------------------------------------
    # ANIMATION STEP LOOP
    # -------------------------------------------------------------------------
    def _step(self):
        if not self.is_running: return
        try:
            if not self.canvas.winfo_exists():
                self.is_running = False
                return
        except Exception:
            self.is_running = False
            return

        dt = 0.035
        self.t += dt
        
        # State machine updates
        if self.state == 'idle':
            # Idle breathing and bobbing
            if self.mood == 'sad':
                self.bounce_y = math.sin(self.t * 1.5) * 2.0 * self.scale - (4.0 * self.scale)
                self.yaw = math.sin(self.t * 0.8) * 0.12
                self.pitch = 0.15  # Drooping forward
                self.squish_y = 0.94 + math.sin(self.t * 1.5) * 0.03
                self.squish_x = 1.04
                # Occasional tear drop
                if int(self.t * 10) % 45 == 0:
                    self.particles.append({
                        "x": self.cx - 10 * self.scale, "y": self.cy + 2 * self.scale,
                        "vx": -0.2, "vy": 1.5, "life": 1.0, "color": "#38bdf8", "text": "•"
                    })
            elif self.mood == 'hungry':
                self.bounce_y = math.sin(self.t * 2.2) * 3.5 * self.scale
                self.yaw = math.sin(self.t * 1.2) * 0.18
                self.pitch = 0.05
                self.squish_y = 1.0 + math.cos(self.t * 2.2) * 0.04
                self.squish_x = 1.0 / math.sqrt(self.squish_y)
            else: # happy
                self.bounce_y = math.sin(self.t * 3.0) * 5.5 * self.scale
                self.yaw = math.sin(self.t * 1.8) * 0.28
                self.pitch = -0.05  # Cheerful chin up
                self.squish_y = 1.0 + math.cos(self.t * 3.0) * 0.07
                self.squish_x = 1.0 / math.sqrt(self.squish_y)
                
            # Apple bobbing
            if self.show_apple and not self.apple_eaten:
                self.apple_y = self.cy + int(math.sin(self.t * 3.0) * 5 * self.scale)
                self.apple_yaw += 0.04
                
        elif self.state == 'feeding':
            self.state_timer += dt
            progress = min(1.0, self.state_timer / 0.8)
            # Apple moves from its position to mascot's mouth
            target_x = self.cx + 8 * self.scale
            target_y = self.cy - self.bounce_y + 8 * self.scale
            self.apple_x = self.apple_x + (target_x - self.apple_x) * 0.16
            self.apple_y = self.apple_y + (target_y - self.apple_y) * 0.16
            self.apple_scale = max(0.01, 1.0 - progress * 0.9)
            self.apple_yaw += 0.12
            
            # Mascot leans toward apple with open mouth
            self.pitch = -0.15
            self.yaw = 0.25
            
            if progress >= 1.0:
                self.apple_eaten = True
                self.state = 'dance'
                self.state_timer = 0.0
                self.mood = 'happy'
                if self.on_fed:
                    try: self.on_fed()
                    except Exception: pass
                # Crunch burst particles
                for _ in range(8):
                    ang = 2 * math.pi * (_ / 8)
                    self.particles.append({
                        "x": target_x, "y": target_y,
                        "vx": math.cos(ang) * 2.4, "vy": math.sin(ang) * 2.4 - 1.0,
                        "life": 1.0, "color": "#ef4444" if _ % 2 == 0 else "#fbbf24",
                        "text": "★" if _ % 2 == 0 else "✦"
                    })
                    
        elif self.state == 'dance':
            self.state_timer += dt
            # High-energy 3D joyful happy dance!
            self.bounce_y = abs(math.sin(self.state_timer * 10.0)) * 22.0 * self.scale
            self.yaw += 0.35  # Rapid spinning dance
            self.pitch = math.sin(self.state_timer * 8.0) * 0.2
            self.roll = math.cos(self.state_timer * 7.0) * 0.18
            self.squish_y = 1.0 + math.cos(self.state_timer * 10.0) * 0.15
            self.squish_x = 1.0 / math.sqrt(self.squish_y)
            
            # Continuous celebratory heart and sparkle particles
            if int(self.state_timer * 20) % 3 == 0:
                self.particles.append({
                    "x": self.cx + (math.sin(self.t * 8) * 25 * self.scale),
                    "y": self.cy - self.bounce_y - 15 * self.scale,
                    "vx": (math.sin(self.t * 5) * 1.5),
                    "vy": -2.5,
                    "life": 1.0,
                    "color": "#fb7185" if int(self.t*10)%2==0 else "#fbbf24",
                    "text": "♥" if int(self.t*10)%2==0 else "★"
                })
                
            if self.state_timer >= 2.6:
                if getattr(self, 'can_evolve', False) and self.version < 32:
                    self.state = 'evolve'
                    self.state_timer = 0.0
                else:
                    self.state = 'idle'
                    self.roll = 0.0
                    
        elif self.state == 'evolve':
            self.state_timer += dt
            # Evolution transformation sequence!
            # Vibration / glowing expansion
            self.bounce_y = 12.0 * self.scale + math.sin(self.state_timer * 35.0) * 4.0 * self.scale
            self.yaw += 0.45
            self.pitch = math.sin(self.state_timer * 12.0) * 0.15
            
            # Swirling aura particles
            orb_r = (30.0 + self.state_timer * 20.0) * self.scale
            ang = self.state_timer * 12.0
            self.particles.append({
                "x": self.cx + math.cos(ang) * orb_r,
                "y": self.cy - self.bounce_y + math.sin(ang) * (orb_r * 0.4),
                "vx": 0, "vy": -1.2,
                "life": 0.8, "color": "#facc15", "text": "★"
            })
            
            if self.state_timer >= 1.8:
                # Evolve to next level!
                self.version = min(32, self.version + 1)
                self.can_evolve = False
                self.state = 'idle'
                self.roll = 0.0
                if self.on_evolved:
                    try: self.on_evolved(self.version)
                    except Exception: pass
                # Big celebration burst
                for _ in range(16):
                    ang_b = 2 * math.pi * (_ / 16)
                    self.particles.append({
                        "x": self.cx, "y": self.cy - self.bounce_y,
                        "vx": math.cos(ang_b) * 4.5, "vy": math.sin(ang_b) * 4.5 - 2.0,
                        "life": 1.2, "color": rainbow_color(_ / 16), "text": "★"
                    })

        # Update particles
        alive_p = []
        for p in self.particles:
            p["x"] += p["vx"] * self.scale
            p["y"] += p["vy"] * self.scale
            p["vy"] += 0.08  # Gravity
            p["life"] -= dt * 1.2
            if p["life"] > 0:
                alive_p.append(p)
        self.particles = alive_p
        
        # Render full 3D scene
        self.render()
        
        self.canvas.after(self.frame_delay, self._step)

    # -------------------------------------------------------------------------
    # 3D SCENE RENDERER & ACCESSORIES
    # -------------------------------------------------------------------------
    def _render_accessories(self, elements, cy_offset, is_star_body):
        s = self.scale
        v = self.version
        t = self.t
        roll, pitch, yaw = self.roll, self.pitch, self.yaw
        squish_y = self.squish_y
        
        # Level 2: Sprout Note (Re)
        if v == 2:
            sway = math.sin(t * 3.2) * 5.0 * s
            h_top = rotate_point_3d(0, 30*s*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            tip = rotate_point_3d(sway, (52 + math.sin(t*3.2)*2)*s*squish_y, 4*s, roll=roll, pitch=pitch, yaw=yaw)
            p_h = project_3d(h_top[0], h_top[1] + cy_offset, h_top[2], self.cx, self.cy)
            p_t = project_3d(tip[0], tip[1] + cy_offset, tip[2], self.cx, self.cy)
            elements.append(((h_top[2]+tip[2])/2, 'line', p_h[0], p_h[1], p_t[0], p_t[1], '#10b981', max(2, int(3*s))))
            leaf_pts = [p_t[0], p_t[1], p_t[0] + int(12*s), p_t[1] - int(5*s), p_t[0] + int(8*s), p_t[1] + int(8*s)]
            elements.append((tip[2] + 2, 'poly', leaf_pts, '#22c55e'))

        # Level 3: Starlet Antenna (Mi)
        elif v == 3:
            h_top = rotate_point_3d(0, 32*s*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            tip = rotate_point_3d(0, (54 + math.sin(t*4)*3)*s*squish_y, 4*s, roll=roll, pitch=pitch, yaw=yaw)
            p_h = project_3d(h_top[0], h_top[1] + cy_offset, h_top[2], self.cx, self.cy)
            p_t = project_3d(tip[0], tip[1] + cy_offset, tip[2], self.cx, self.cy)
            elements.append(((h_top[2]+tip[2])/2, 'line', p_h[0], p_h[1], p_t[0], p_t[1], '#38bdf8', max(2, int(2.5*s))))
            star_yaw = t * 4.5
            for f in self._small_star_faces:
                poly_pts, avg_sz = [], 0.0
                for idx in f:
                    sx, sy, sz = rotate_point_3d(*self._small_star_verts[idx], yaw=star_yaw)
                    sx += tip[0]; sy += tip[1] + cy_offset; sz += tip[2]
                    px, py = project_3d(sx, sy, sz, self.cx, self.cy)
                    poly_pts.extend([px, py]); avg_sz += sz
                elements.append((avg_sz / len(f), 'poly', poly_pts, '#fbbf24'))

        # Level 4: Clef Tuft (Fa)
        elif v == 4:
            c_top = rotate_point_3d(0, 32*s*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            c_mid = rotate_point_3d(math.sin(t*2.5)*3*s, 50*s*squish_y, 3*s, roll=roll, pitch=pitch, yaw=yaw)
            c_curl = rotate_point_3d(math.sin(t*2.5)*3*s + 8*s, 44*s*squish_y, 4*s, roll=roll, pitch=pitch, yaw=yaw)
            p_top = project_3d(c_top[0], c_top[1]+cy_offset, c_top[2], self.cx, self.cy)
            p_mid = project_3d(c_mid[0], c_mid[1]+cy_offset, c_mid[2], self.cx, self.cy)
            p_curl = project_3d(c_curl[0], c_curl[1]+cy_offset, c_curl[2], self.cx, self.cy)
            elements.append((c_top[2], 'line', p_top[0], p_top[1], p_mid[0], p_mid[1], '#10b981', max(2, int(3.5*s))))
            elements.append((c_mid[2], 'line', p_mid[0], p_mid[1], p_curl[0], p_curl[1], '#34d399', max(2, int(3*s))))
            for side in [-1, 1]:
                paw = rotate_point_3d(side * 14 * s, -22 * s * squish_y, 22 * s, roll=roll, pitch=pitch, yaw=yaw)
                p_paw = project_3d(paw[0], paw[1]+cy_offset, paw[2], self.cx, self.cy)
                elements.append((paw[2], 'cheeks', p_paw[0], p_paw[1], p_paw[0], p_paw[1], 4.5*s))

        # Level 5: Little Bell (Sol)
        elif v == 5:
            loop_p = rotate_point_3d(0, 24*s*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            p_l = project_3d(loop_p[0], loop_p[1]+cy_offset, loop_p[2], self.cx, self.cy)
            elements.append((loop_p[2], 'cheeks', p_l[0], p_l[1], p_l[0], p_l[1], 5*s))
            clap_x = math.sin(t * 3.5) * 8.0 * s
            clap = rotate_point_3d(clap_x, -26*s*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            p_c = project_3d(clap[0], clap[1]+cy_offset, clap[2], self.cx, self.cy)
            elements.append((clap[2], 'cheeks', p_c[0], p_c[1], p_c[0], p_c[1], 4*s))

        # Level 6: Metronome Pup
        elif v == 6:
            for side in [-1, 1]:
                ear_base = rotate_point_3d(side * 28 * s, 14 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                ear_tip = rotate_point_3d(side * 36 * s, (2 + math.sin(t*3)*3) * s * squish_y, 6*s, roll=roll, pitch=pitch, yaw=yaw)
                p_eb = project_3d(ear_base[0], ear_base[1]+cy_offset, ear_base[2], self.cx, self.cy)
                p_et = project_3d(ear_tip[0], ear_tip[1]+cy_offset, ear_tip[2], self.cx, self.cy)
                elements.append(((ear_base[2]+ear_tip[2])/2, 'line', p_eb[0], p_eb[1], p_et[0], p_et[1], '#b45309', max(3, int(6*s))))
            pend_ang = math.sin(t * 4.0) * 0.45
            tail_base = rotate_point_3d(0, -14 * s * squish_y, -26 * s, roll=roll, pitch=pitch, yaw=yaw)
            tail_tip = rotate_point_3d(math.sin(pend_ang)*28*s, (-14 + math.cos(pend_ang)*28)*s*squish_y, -26*s, roll=roll, pitch=pitch, yaw=yaw)
            p_tb = project_3d(tail_base[0], tail_base[1]+cy_offset, tail_base[2], self.cx, self.cy)
            p_tt = project_3d(tail_tip[0], tail_tip[1]+cy_offset, tail_tip[2], self.cx, self.cy)
            elements.append(((tail_base[2]+tail_tip[2])/2, 'line', p_tb[0], p_tb[1], p_tt[0], p_tt[1], '#f59e0b', max(2, int(3*s))))
            elements.append((tail_tip[2]+1, 'cheeks', p_tt[0], p_tt[1], p_tt[0], p_tt[1], 4*s))

        # Level 7: Keyboard Cat
        elif v == 7:
            for side in [-1, 1]:
                e_base = rotate_point_3d(side * 20 * s, 26 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                e_tip = rotate_point_3d(side * 26 * s, 44 * s * squish_y, 2*s, roll=roll, pitch=pitch, yaw=yaw)
                p_eb = project_3d(e_base[0], e_base[1]+cy_offset, e_base[2], self.cx, self.cy)
                p_et = project_3d(e_tip[0], e_tip[1]+cy_offset, e_tip[2], self.cx, self.cy)
                elements.append((e_tip[2], 'line', p_eb[0], p_eb[1], p_et[0], p_et[1], '#fb7185', max(3, int(5*s))))
            bow = rotate_point_3d(0, -10 * s * squish_y, 28 * s, roll=roll, pitch=pitch, yaw=yaw)
            p_b = project_3d(bow[0], bow[1]+cy_offset, bow[2], self.cx, self.cy)
            bow_pts = [p_b[0]-int(10*s), p_b[1]-int(5*s), p_b[0]+int(10*s), p_b[1]+int(5*s), p_b[0]+int(10*s), p_b[1]-int(5*s), p_b[0]-int(10*s), p_b[1]+int(5*s)]
            elements.append((bow[2]+2, 'poly', bow_pts, '#ef4444'))
            for k in range(-3, 4):
                pk = rotate_point_3d(k * 5.5 * s, -18 * s * squish_y, 29 * s, roll=roll, pitch=pitch, yaw=yaw)
                ppk = project_3d(pk[0], pk[1]+cy_offset, pk[2], self.cx, self.cy)
                elements.append((pk[2]+3, 'cheeks', ppk[0], ppk[1], ppk[0], ppk[1], 2.2*s))

        # Level 8: Clef Bunny
        elif v == 8:
            for side in [-1, 1]:
                eb = rotate_point_3d(side * 14 * s, 26 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                et = rotate_point_3d(side * (18 + math.sin(t*2)*2) * s, 60 * s * squish_y, 4*s, roll=roll, pitch=pitch, yaw=yaw)
                peb = project_3d(eb[0], eb[1]+cy_offset, eb[2], self.cx, self.cy)
                pet = project_3d(et[0], et[1]+cy_offset, et[2], self.cx, self.cy)
                elements.append(((eb[2]+et[2])/2, 'line', peb[0], peb[1], pet[0], pet[1], '#c084fc', max(3, int(6*s))))
            tf = rotate_point_3d(32 * s, -2 * s * squish_y, 16 * s, roll=roll, pitch=pitch, yaw=yaw)
            ptf = project_3d(tf[0], tf[1]+cy_offset, tf[2], self.cx, self.cy)
            elements.append((tf[2], 'line', ptf[0], ptf[1]+int(12*s), ptf[0], ptf[1]-int(10*s), '#facc15', max(2, int(2.5*s))))
            elements.append((tf[2]+1, 'line', ptf[0]-int(4*s), ptf[1]-int(16*s), ptf[0]+int(4*s), ptf[1]-int(16*s), '#facc15', max(2, int(2.5*s))))

        # Level 9: Jazz Frog
        elif v == 9:
            for side in [-1, 1]:
                eye_orb = rotate_point_3d(side * 18 * s, 26 * s * squish_y, 10 * s, roll=roll, pitch=pitch, yaw=yaw)
                pe = project_3d(eye_orb[0], eye_orb[1]+cy_offset, eye_orb[2], self.cx, self.cy)
                elements.append((eye_orb[2], 'cheeks', pe[0], pe[1], pe[0], pe[1], 7*s))
            for side in [-1, 1]:
                g = rotate_point_3d(side * 11 * s, 6 * s * squish_y, 29 * s, roll=roll, pitch=pitch, yaw=yaw)
                pg = project_3d(g[0], g[1]+cy_offset, g[2], self.cx, self.cy)
                elements.append((g[2]+5, 'cheeks', pg[0], pg[1], pg[0], pg[1], 5*s))
            sax = rotate_point_3d(30 * s, -12 * s * squish_y, 14 * s, roll=roll, pitch=pitch, yaw=yaw)
            ps = project_3d(sax[0], sax[1]+cy_offset, sax[2], self.cx, self.cy)
            elements.append((sax[2], 'cheeks', ps[0], ps[1], ps[0], ps[1], 8*s))

        # Level 10: Drummer Hamster
        elif v == 10:
            for side in [-1, 1]:
                ear = rotate_point_3d(side * 24 * s, 26 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                pe = project_3d(ear[0], ear[1]+cy_offset, ear[2], self.cx, self.cy)
                elements.append((ear[2], 'cheeks', pe[0], pe[1], pe[0], pe[1], 6.5*s))
            h1 = rotate_point_3d(-24 * s, 14 * s * squish_y, 22 * s, roll=roll, pitch=pitch, yaw=yaw)
            h2 = rotate_point_3d(24 * s, 14 * s * squish_y, 22 * s, roll=roll, pitch=pitch, yaw=yaw)
            ph1 = project_3d(h1[0], h1[1]+cy_offset, h1[2], self.cx, self.cy)
            ph2 = project_3d(h2[0], h2[1]+cy_offset, h2[2], self.cx, self.cy)
            elements.append(((h1[2]+h2[2])/2 + 2, 'line', ph1[0], ph1[1], ph2[0], ph2[1], '#ef4444', max(2, int(4*s))))
            drum = rotate_point_3d(0, -22 * s * squish_y, 26 * s, roll=roll, pitch=pitch, yaw=yaw)
            pd = project_3d(drum[0], drum[1]+cy_offset, drum[2], self.cx, self.cy)
            elements.append((drum[2]+3, 'cheeks', pd[0], pd[1], pd[0], pd[1], 9*s))
            for side in [-1, 1]:
                tap = math.sin(t * 12.0 + side * 1.5) * 5.0 * s
                s1 = rotate_point_3d(side * 14 * s, (-10 + tap) * s * squish_y, 28 * s, roll=roll, pitch=pitch, yaw=yaw)
                s2 = rotate_point_3d(side * 4 * s, -20 * s * squish_y, 27 * s, roll=roll, pitch=pitch, yaw=yaw)
                ps1 = project_3d(s1[0], s1[1]+cy_offset, s1[2], self.cx, self.cy)
                ps2 = project_3d(s2[0], s2[1]+cy_offset, s2[2], self.cx, self.cy)
                elements.append(((s1[2]+s2[2])/2 + 4, 'line', ps1[0], ps1[1], ps2[0], ps2[1], '#fbbf24', max(1, int(2*s))))

        # Level 11: Boombox Bot
        elif v == 11:
            for side in [-1, 1]:
                spk = rotate_point_3d(side * 24 * s, 4 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                psp = project_3d(spk[0], spk[1]+cy_offset, spk[2], self.cx, self.cy)
                elements.append((spk[2], 'cheeks', psp[0], psp[1], psp[0], psp[1], 7*s))
            eq_cols = ['#22c55e', '#eab308', '#ef4444']
            for bi in range(3):
                bx = (-8 + bi * 8) * s
                bh = (6 + abs(math.sin(t * 8.0 + bi)) * 12.0) * s
                b1 = rotate_point_3d(bx, -18 * s * squish_y, 20 * s, roll=roll, pitch=pitch, yaw=yaw)
                b2 = rotate_point_3d(bx, (-18 + bh) * s * squish_y, 20 * s, roll=roll, pitch=pitch, yaw=yaw)
                pb1 = project_3d(b1[0], b1[1]+cy_offset, b1[2], self.cx, self.cy)
                pb2 = project_3d(b2[0], b2[1]+cy_offset, b2[2], self.cx, self.cy)
                elements.append((b1[2]+2, 'line', pb1[0], pb1[1], pb2[0], pb2[1], eq_cols[bi], max(2, int(3*s))))

        # Level 12: Music Box Piggy
        elif v == 12:
            snout = rotate_point_3d(0, -2 * s * squish_y, 30 * s, roll=roll, pitch=pitch, yaw=yaw)
            psn = project_3d(snout[0], snout[1]+cy_offset, snout[2], self.cx, self.cy)
            elements.append((snout[2]+2, 'cheeks', psn[0], psn[1], psn[0], psn[1], 7*s))
            key_ang = t * 3.5
            k1 = rotate_point_3d(0, 10 * s * squish_y, -28 * s, roll=roll, pitch=pitch, yaw=yaw)
            k2 = rotate_point_3d(math.cos(key_ang)*14*s, (10 + math.sin(key_ang)*14)*s*squish_y, -34*s, roll=roll, pitch=pitch, yaw=yaw)
            pk1 = project_3d(k1[0], k1[1]+cy_offset, k1[2], self.cx, self.cy)
            pk2 = project_3d(k2[0], k2[1]+cy_offset, k2[2], self.cx, self.cy)
            elements.append((k1[2], 'line', pk1[0], pk1[1], pk2[0], pk2[1], '#f59e0b', max(2, int(4*s))))
            tu1 = rotate_point_3d(-26 * s, -18 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            tu2 = rotate_point_3d(26 * s, -18 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            ptu1 = project_3d(tu1[0], tu1[1]+cy_offset, tu1[2], self.cx, self.cy)
            ptu2 = project_3d(tu2[0], tu2[1]+cy_offset, tu2[2], self.cx, self.cy)
            elements.append((tu1[2]+1, 'line', ptu1[0], ptu1[1], ptu2[0], ptu2[1], '#f472b6', max(3, int(6*s))))

        # Level 13: Vinyl DJ Penguin
        elif v == 13:
            bk = rotate_point_3d(0, -2 * s * squish_y, 30 * s, roll=roll, pitch=pitch, yaw=yaw)
            pbk = project_3d(bk[0], bk[1]+cy_offset, bk[2], self.cx, self.cy)
            elements.append((bk[2]+3, 'cheeks', pbk[0], pbk[1], pbk[0], pbk[1], 5*s))
            for side in [-1, 1]:
                hp = rotate_point_3d(side * 28 * s, 10 * s * squish_y, 4 * s, roll=roll, pitch=pitch, yaw=yaw)
                php = project_3d(hp[0], hp[1]+cy_offset, hp[2], self.cx, self.cy)
                elements.append((hp[2]+1, 'cheeks', php[0], php[1], php[0], php[1], 7*s))
            disc = rotate_point_3d(0, -22 * s * squish_y, 26 * s, roll=roll, pitch=pitch, yaw=yaw)
            pdisc = project_3d(disc[0], disc[1]+cy_offset, disc[2], self.cx, self.cy)
            elements.append((disc[2]+3, 'cheeks', pdisc[0], pdisc[1], pdisc[0], pdisc[1], 10*s))

        # Level 14: Accordion Armadillo
        elif v == 14:
            for side in [-1, 1]:
                pipe1 = rotate_point_3d(side * 18 * s, 20 * s * squish_y, -10 * s, roll=roll, pitch=pitch, yaw=yaw)
                pipe2 = rotate_point_3d(side * 18 * s, 36 * s * squish_y, -10 * s, roll=roll, pitch=pitch, yaw=yaw)
                pp1 = project_3d(pipe1[0], pipe1[1]+cy_offset, pipe1[2], self.cx, self.cy)
                pp2 = project_3d(pipe2[0], pipe2[1]+cy_offset, pipe2[2], self.cx, self.cy)
                elements.append((pipe1[2], 'line', pp1[0], pp1[1], pp2[0], pp2[1], '#d97706', max(2, int(4*s))))

        # Level 15: Synthwave Glow-Cube
        elif v == 15:
            ring_yaw = t * 2.5
            for f in self._ring_faces:
                poly_pts, avg_rz = [], 0.0
                for idx in f:
                    rx, ry, rz = rotate_point_3d(*self._ring_verts[idx], yaw=ring_yaw, pitch=0.45)
                    px, py = project_3d(rx, ry + cy_offset, rz, self.cx, self.cy)
                    poly_pts.extend([px, py]); avg_rz += rz
                elements.append((avg_rz / len(f), 'poly', poly_pts, '#06b6d4'))

        # Level 16: Amadeus Bear
        elif v == 16:
            for side in [-1, 1]:
                wig = rotate_point_3d(side * 28 * s, 14 * s * squish_y, 4 * s, roll=roll, pitch=pitch, yaw=yaw)
                pwig = project_3d(wig[0], wig[1]+cy_offset, wig[2], self.cx, self.cy)
                elements.append((wig[2], 'cheeks', pwig[0], pwig[1], pwig[0], pwig[1], 8*s))
            q1 = rotate_point_3d(28 * s, -6 * s * squish_y, 18 * s, roll=roll, pitch=pitch, yaw=yaw)
            q2 = rotate_point_3d((28 + math.sin(t*5)*8) * s, (16 + math.cos(t*5)*8) * s * squish_y, 22 * s, roll=roll, pitch=pitch, yaw=yaw)
            pq1 = project_3d(q1[0], q1[1]+cy_offset, q1[2], self.cx, self.cy)
            pq2 = project_3d(q2[0], q2[1]+cy_offset, q2[2], self.cx, self.cy)
            elements.append((q1[2]+2, 'line', pq1[0], pq1[1], pq2[0], pq2[1], '#facc15', max(2, int(3*s))))

        # Level 17: Rocker Hedgehog
        elif v == 17:
            for spk_x in [-18, -6, 6, 18]:
                spk_base = rotate_point_3d(spk_x * s, 26 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                spk_tip = rotate_point_3d(spk_x * 1.3 * s, 46 * s * squish_y, -4 * s, roll=roll, pitch=pitch, yaw=yaw)
                psb = project_3d(spk_base[0], spk_base[1]+cy_offset, spk_base[2], self.cx, self.cy)
                pst = project_3d(spk_tip[0], spk_tip[1]+cy_offset, spk_tip[2], self.cx, self.cy)
                elements.append(((spk_base[2]+spk_tip[2])/2, 'line', psb[0], psb[1], pst[0], pst[1], '#a855f7', max(3, int(5*s))))

        # Level 18: Grand Piano Turtle
        elif v == 18:
            for side in [-1, 1]:
                flp = rotate_point_3d(side * 30 * s, -12 * s * squish_y, 8 * s, roll=roll, pitch=pitch, yaw=yaw)
                pfl = project_3d(flp[0], flp[1]+cy_offset, flp[2], self.cx, self.cy)
                elements.append((flp[2], 'cheeks', pfl[0], pfl[1], pfl[0], pfl[1], 7.5*s))
            pst1 = rotate_point_3d(14 * s, 4 * s * squish_y, -20 * s, roll=roll, pitch=pitch, yaw=yaw)
            pst2 = rotate_point_3d(14 * s, 26 * s * squish_y, -20 * s, roll=roll, pitch=pitch, yaw=yaw)
            ppst1 = project_3d(pst1[0], pst1[1]+cy_offset, pst1[2], self.cx, self.cy)
            ppst2 = project_3d(pst2[0], pst2[1]+cy_offset, pst2[2], self.cx, self.cy)
            elements.append((pst1[2], 'line', ppst1[0], ppst1[1], ppst2[0], ppst2[1], '#f59e0b', max(2, int(2.5*s))))

        # Level 19: Opera Owl
        elif v == 19:
            mono = rotate_point_3d(10 * s, 4 * s * squish_y, 29 * s, roll=roll, pitch=pitch, yaw=yaw)
            pmn = project_3d(mono[0], mono[1]+cy_offset, mono[2], self.cx, self.cy)
            elements.append((mono[2]+3, 'cheeks', pmn[0], pmn[1], pmn[0], pmn[1], 6.5*s))
            ch2 = rotate_point_3d(14 * s, -14 * s * squish_y, 28 * s, roll=roll, pitch=pitch, yaw=yaw)
            pch2 = project_3d(ch2[0], ch2[1]+cy_offset, ch2[2], self.cx, self.cy)
            elements.append((mono[2]+3, 'line', pmn[0], pmn[1], pch2[0], pch2[1], '#fbbf24', max(1, int(1.5*s))))

        # Level 20: Golden Baton Maestro
        elif v == 20:
            for side in [-1, 1]:
                bt1 = rotate_point_3d(side * 28 * s, -8 * s * squish_y, 16 * s, roll=roll, pitch=pitch, yaw=yaw)
                bt2 = rotate_point_3d(side * (30 + math.sin(t*4 + side)*10) * s, (12 + math.cos(t*4 + side)*10) * s * squish_y, 22 * s, roll=roll, pitch=pitch, yaw=yaw)
                pbt1 = project_3d(bt1[0], bt1[1]+cy_offset, bt1[2], self.cx, self.cy)
                pbt2 = project_3d(bt2[0], bt2[1]+cy_offset, bt2[2], self.cx, self.cy)
                elements.append(((bt1[2]+bt2[2])/2 + 2, 'line', pbt1[0], pbt1[1], pbt2[0], pbt2[1], '#fef08a', max(2, int(2.5*s))))

        # Level 21: Melody Sprite
        elif v == 21:
            wing_flap = math.sin(t * 12.0) * 0.4
            for side in [-1, 1]:
                for f in self._wing_faces:
                    poly_pts, avg_wz = [], 0.0
                    for idx in f:
                        wx, wy, wz = self._wing_verts[idx]
                        wx *= side
                        wx, wy, wz = rotate_point_3d(wx, wy, wz, yaw=side * wing_flap, roll=roll, pitch=pitch)
                        wx += side * 18 * s; wy += 6 * s * squish_y + cy_offset; wz -= 12 * s
                        px, py = project_3d(wx, wy, wz, self.cx, self.cy)
                        poly_pts.extend([px, py]); avg_wz += wz
                    elements.append((avg_wz / len(f), 'poly', poly_pts, '#67e8f9'))

        # Level 22: Chime Golem
        elif v == 22:
            for i, cx in enumerate([-24, -16, 16, 24]):
                sw = math.sin(t * 3.0 + i) * 3.0 * s
                ch1 = rotate_point_3d(cx * s, 12 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                ch2 = rotate_point_3d((cx + sw) * s, -16 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                pch1 = project_3d(ch1[0], ch1[1]+cy_offset, ch1[2], self.cx, self.cy)
                pch2 = project_3d(ch2[0], ch2[1]+cy_offset, ch2[2], self.cx, self.cy)
                elements.append((ch1[2], 'line', pch1[0], pch1[1], pch2[0], pch2[1], '#fbbf24', max(2, int(3*s))))

        # Level 23: Harp-Winged Pegasus
        elif v == 23:
            hn1 = rotate_point_3d(0, 28 * s * squish_y, 14 * s, roll=roll, pitch=pitch, yaw=yaw)
            hn2 = rotate_point_3d(0, 48 * s * squish_y, 20 * s, roll=roll, pitch=pitch, yaw=yaw)
            phn1 = project_3d(hn1[0], hn1[1]+cy_offset, hn1[2], self.cx, self.cy)
            phn2 = project_3d(hn2[0], hn2[1]+cy_offset, hn2[2], self.cx, self.cy)
            elements.append((hn1[2], 'line', phn1[0], phn1[1], phn2[0], phn2[1], '#facc15', max(3, int(5*s))))
            wing_flap = math.sin(t * 3.5) * 0.25
            for side in [-1, 1]:
                for f in self._wing_faces:
                    poly_pts, avg_wz = [], 0.0
                    for idx in f:
                        wx, wy, wz = self._wing_verts[idx]
                        wx *= side
                        wx, wy, wz = rotate_point_3d(wx, wy, wz, yaw=side * wing_flap, roll=roll, pitch=pitch)
                        wx += side * 22 * s; wy += 8 * s * squish_y + cy_offset; wz -= 8 * s
                        px, py = project_3d(wx, wy, wz, self.cx, self.cy)
                        poly_pts.extend([px, py]); avg_wz += wz
                    elements.append((avg_wz / len(f), 'poly', poly_pts, '#f8fafc'))

        # Level 24: Crescendo Phoenix
        elif v == 24:
            fc1 = rotate_point_3d(0, 30 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
            fc2 = rotate_point_3d(math.sin(t*5)*6*s, 54 * s * squish_y, -6 * s, roll=roll, pitch=pitch, yaw=yaw)
            pfc1 = project_3d(fc1[0], fc1[1]+cy_offset, fc1[2], self.cx, self.cy)
            pfc2 = project_3d(fc2[0], fc2[1]+cy_offset, fc2[2], self.cx, self.cy)
            elements.append((fc1[2], 'line', pfc1[0], pfc1[1], pfc2[0], pfc2[1], '#fbbf24', max(3, int(6*s))))
            wing_flap = math.sin(t * 4.5) * 0.35
            for side in [-1, 1]:
                for f in self._wing_faces:
                    poly_pts, avg_wz = [], 0.0
                    for idx in f:
                        wx, wy, wz = self._wing_verts[idx]
                        wx *= side
                        wx, wy, wz = rotate_point_3d(wx, wy, wz, yaw=side * wing_flap, roll=roll, pitch=pitch)
                        wx += side * 22 * s; wy += 8 * s * squish_y + cy_offset; wz -= 6 * s
                        px, py = project_3d(wx, wy, wz, self.cx, self.cy)
                        poly_pts.extend([px, py]); avg_wz += wz
                    elements.append((avg_wz / len(f), 'poly', poly_pts, '#ef4444'))

        # Level 25: Crystal Dragonette
        elif v == 25:
            for side in [-1, 1]:
                h1 = rotate_point_3d(side * 14 * s, 26 * s * squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                h2 = rotate_point_3d(side * 24 * s, 48 * s * squish_y, 4 * s, roll=roll, pitch=pitch, yaw=yaw)
                ph1 = project_3d(h1[0], h1[1]+cy_offset, h1[2], self.cx, self.cy)
                ph2 = project_3d(h2[0], h2[1]+cy_offset, h2[2], self.cx, self.cy)
                elements.append((h1[2], 'line', ph1[0], ph1[1], ph2[0], ph2[1], '#06b6d4', max(2, int(4*s))))

        # Level 26: Starlight Seraph
        elif v == 26:
            for pair_idx, y_pos in enumerate([-8, 6, 20]):
                wing_flap = math.sin(t * 4.0 + pair_idx * 0.8) * 0.35
                for side in [-1, 1]:
                    for f in self._wing_faces:
                        poly_pts, avg_wz = [], 0.0
                        for idx in f:
                            wx, wy, wz = self._wing_verts[idx]
                            wx *= side * 0.9; wy *= 0.85
                            wx, wy, wz = rotate_point_3d(wx, wy, wz, yaw=side * wing_flap, roll=roll, pitch=pitch)
                            wx += side * 20 * s; wy += y_pos * s * squish_y + cy_offset; wz -= 8 * s
                            px, py = project_3d(wx, wy, wz, self.cx, self.cy)
                            poly_pts.extend([px, py]); avg_wz += wz
                        elements.append((avg_wz / len(f), 'poly', poly_pts, '#facc15'))

        # Level 27: Saturn's Organist
        elif v == 27:
            ring_yaw = t * 1.8
            for f_idx, f in enumerate(self._ring_faces):
                poly_pts, avg_rz = [], 0.0
                for idx in f:
                    rx, ry, rz = rotate_point_3d(*self._ring_verts[idx], yaw=ring_yaw, pitch=0.48, roll=0.15)
                    px, py = project_3d(rx, ry + cy_offset, rz, self.cx, self.cy)
                    poly_pts.extend([px, py]); avg_rz += rz
                key_col = '#0f172a' if (f_idx % 2 == 0) else '#f8fafc'
                elements.append((avg_rz / len(f), 'poly', poly_pts, key_col))

        # Level 28: Nebula Phoenix
        elif v == 28:
            wing_flap = math.sin(t * 3.8) * 0.38
            for side in [-1, 1]:
                for f in self._wing_faces:
                    poly_pts, avg_wz = [], 0.0
                    for idx in f:
                        wx, wy, wz = self._wing_verts[idx]
                        wx *= side * 1.1; wy *= 1.1
                        wx, wy, wz = rotate_point_3d(wx, wy, wz, yaw=side * wing_flap, roll=roll, pitch=pitch)
                        wx += side * 22 * s; wy += 8 * s * squish_y + cy_offset; wz -= 8 * s
                        px, py = project_3d(wx, wy, wz, self.cx, self.cy)
                        poly_pts.extend([px, py]); avg_wz += wz
                    col = '#c084fc' if side == 1 else '#38bdf8'
                    elements.append((avg_wz / len(f), 'poly', poly_pts, col))

        # Level 29: Chrono Metronome
        elif v == 29:
            p_ang = math.sin(t * 3.5) * 0.42
            sc1 = rotate_point_3d(0, 20 * s * squish_y, -18 * s, roll=roll, pitch=pitch, yaw=yaw)
            sc2 = rotate_point_3d(math.sin(p_ang)*38*s, (20 - math.cos(p_ang)*38)*s*squish_y, -18*s, roll=roll, pitch=pitch, yaw=yaw)
            psc1 = project_3d(sc1[0], sc1[1]+cy_offset, sc1[2], self.cx, self.cy)
            psc2 = project_3d(sc2[0], sc2[1]+cy_offset, sc2[2], self.cx, self.cy)
            elements.append((sc1[2], 'line', psc1[0], psc1[1], psc2[0], psc2[1], '#d97706', max(2, int(4*s))))
            elements.append((sc2[2]+1, 'cheeks', psc2[0], psc2[1], psc2[0], psc2[1], 5*s))

        # Level 30: Grand Rainbow Virtuoso
        elif v == 30:
            tiara = rotate_point_3d(0, 36 * s * squish_y, 8 * s, roll=roll, pitch=pitch, yaw=yaw)
            ptia = project_3d(tiara[0], tiara[1]+cy_offset, tiara[2], self.cx, self.cy)
            elements.append((tiara[2]+2, 'cheeks', ptia[0], ptia[1], ptia[0], ptia[1], 8*s))
            orbit_r = 48.0 * s
            for idx_star, sign in enumerate([1.0, -1.0]):
                ang = t * 2.5 * sign + (idx_star * math.pi)
                ox = math.cos(ang) * orbit_r
                oz = math.sin(ang) * (orbit_r * 0.75)
                oy = math.sin(ang * 2.0) * (8.0 * s)
                star_yaw = t * 4.0 * sign
                for f in self._small_star_faces:
                    poly_pts, avg_sz = [], 0.0
                    for idx in f:
                        sx, sy, sz = rotate_point_3d(*self._small_star_verts[idx], yaw=star_yaw)
                        sx += ox; sy += oy + cy_offset; sz += oz
                        px, py = project_3d(sx, sy, sz, self.cx, self.cy)
                        poly_pts.extend([px, py]); avg_sz += sz
                    elements.append((avg_sz / len(f), 'poly', poly_pts, rainbow_color(t*0.5 + idx_star*0.5)))

        # Level 31: Apollo's Sun-King Lyre
        elif v == 31:
            for i in range(8):
                ang = (2 * math.pi * i) / 8 + t * 0.8
                r1 = 34.0 * s
                r2 = (44.0 + math.sin(t*6 + i)*6.0) * s
                ray1 = rotate_point_3d(math.cos(ang)*r1, math.sin(ang)*r1*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                ray2 = rotate_point_3d(math.cos(ang)*r2, math.sin(ang)*r2*squish_y, 0, roll=roll, pitch=pitch, yaw=yaw)
                pray1 = project_3d(ray1[0], ray1[1]+cy_offset, ray1[2], self.cx, self.cy)
                pray2 = project_3d(ray2[0], ray2[1]+cy_offset, ray2[2], self.cx, self.cy)
                elements.append((ray1[2], 'line', pray1[0], pray1[1], pray2[0], pray2[1], '#facc15', max(2, int(3.5*s))))
            lyre = rotate_point_3d(0, -14 * s * squish_y, 28 * s, roll=roll, pitch=pitch, yaw=yaw)
            ply = project_3d(lyre[0], lyre[1]+cy_offset, lyre[2], self.cx, self.cy)
            elements.append((lyre[2]+2, 'cheeks', ply[0], ply[1], ply[0], ply[1], 10*s))

        # Level 32: Omnichord Celestial Sovereign
        elif v == 32:
            for ring_idx, (r_pitch, r_roll, speed) in enumerate([(0.0, 0.0, 2.2), (1.57, 0.0, -1.8), (0.78, 0.78, 2.6)]):
                r_yaw = t * speed
                for f_idx, f in enumerate(self._ring_faces):
                    poly_pts, avg_rz = [], 0.0
                    for idx in f:
                        rx, ry, rz = rotate_point_3d(*self._ring_verts[idx], yaw=r_yaw, pitch=r_pitch, roll=r_roll)
                        px, py = project_3d(rx, ry + cy_offset, rz, self.cx, self.cy)
                        poly_pts.extend([px, py]); avg_rz += rz
                    col = '#fbbf24' if (f_idx % 2 == 0) else '#a855f7'
                    elements.append((avg_rz / len(f), 'poly', poly_pts, col))

    # -------------------------------------------------------------------------
    # 3D SCENE RENDERER
    # -------------------------------------------------------------------------
    def render(self):
        """Draws all 3D meshes, facial features, accessories, and particles."""
        if not self.canvas:
            return
        self.canvas.delete("tamagotchi_3d")
        
        # Draw soft shadow under mascot
        shadow_w = int(32 * self.scale * (1.0 + self.bounce_y / 50.0))
        shadow_h = int(10 * self.scale)
        shadow_y = self.cy + int(36 * self.scale)
        self.canvas.create_oval(
            self.cx - shadow_w, shadow_y - shadow_h,
            self.cx + shadow_w, shadow_y + shadow_h,
            fill="#0b1017", outline="", tags="tamagotchi_3d"
        )
        
        # Determine base mesh and color
        is_star_body = (self.version in (20, 30))
        is_cube_body = (self.version in (11, 14, 15))
        is_bell_body = (self.version == 5)

        if is_star_body:
            base_verts = self._star_verts
            base_faces = self._star_faces
        elif is_cube_body:
            base_verts = self._cube_verts
            base_faces = self._cube_faces
        elif is_bell_body:
            base_verts = self._bell_verts
            base_faces = self._bell_faces
        else:
            base_verts = self._blob_verts
            base_faces = self._blob_faces

        base_hex = self.base_color or self.version_colors.get(self.version, "#38bdf8")
        
        # Transform main body vertices
        transformed_verts = []
        cy_offset = self.bounce_y
        for vx, vy, vz in base_verts:
            # Apply organic squish & stretch
            vx_s = vx * self.squish_x
            vy_s = vy * self.squish_y
            vz_s = vz * self.squish_x
            rx, ry, rz = rotate_point_3d(vx_s, vy_s, vz_s, roll=self.roll, pitch=self.pitch, yaw=self.yaw)
            transformed_verts.append((rx, ry + cy_offset, rz))
            
        # Collect all 3D drawable elements for depth sorting
        elements = []
        
        # 1. Main body faces
        for face_idx, face in enumerate(base_faces):
            p0 = transformed_verts[face[0]]
            p1 = transformed_verts[face[1]]
            p2 = transformed_verts[face[2]]
            
            # Normal calculation: (p1 - p0) x (p2 - p0)
            ax, ay, az = p1[0]-p0[0], p1[1]-p0[1], p1[2]-p0[2]
            bx, by, bz = p2[0]-p0[0], p2[1]-p0[1], p2[2]-p0[2]
            nx = ay*bz - az*by
            ny = az*bx - ax*bz
            nz = ax*by - ay*bx
            norm_len = math.sqrt(nx*nx + ny*ny + nz*nz) or 1.0
            nx, ny, nz = nx/norm_len, ny/norm_len, nz/norm_len
            
            # Skip back-facing facets for efficiency
            if nz <= -0.15: continue
            
            # Average depth for Painter's sorting
            avg_z = sum(transformed_verts[i][2] for i in face) / len(face)
            
            # Lighting: Ambient + directional diffuse for bright, cheerful 3D look
            ambient = 0.52
            diffuse = max(0.0, nx*self.light_vec[0] + ny*self.light_vec[1] + nz*self.light_vec[2])
            dot_light = min(1.30, ambient + diffuse * 0.65)
            
            # Color
            if (self.version in (15, 24, 28, 30, 32)) and not self.base_color:
                if self.version in (30, 32):
                    col_offset = (self.t * 0.7) + (face_idx / len(base_faces))
                    face_col = rainbow_color(col_offset, dot_light)
                elif self.version in (15, 28):
                    col_offset = (self.t * 0.4) + (face_idx / len(base_faces)) * 0.35
                    face_col = rainbow_color(col_offset + 0.65, dot_light)
                elif self.version == 24:
                    col_offset = 0.05 + 0.08 * math.sin(self.t * 4.0 + face_idx)
                    face_col = rainbow_color(col_offset, dot_light)
                else:
                    face_col = shade_color(base_hex, dot_light)
            else:
                face_col = shade_color(base_hex, dot_light)
                
            # 2D projection
            poly_2d = []
            for i in face:
                v = transformed_verts[i]
                px, py = project_3d(v[0], v[1], v[2], self.cx, self.cy)
                poly_2d.extend([px, py])
                
            elements.append((avg_z, 'poly', poly_2d, face_col))
            
        # 2. Accessories per version
        self._render_accessories(elements, cy_offset, is_star_body)
                    
        # 3. 3D Face (Eyes, Cheeks, Mouth)
        # Position face on front of character
        face_z = 28.0 * self.scale if not is_star_body else 16.0 * self.scale
        face_y = 4.0 * self.scale
        
        # Left and Right eye 3D positions
        eye_lx, eye_ly, eye_lz = rotate_point_3d(-10.0*self.scale, face_y, face_z, roll=self.roll, pitch=self.pitch, yaw=self.yaw)
        eye_rx, eye_ry, eye_rz = rotate_point_3d(+10.0*self.scale, face_y, face_z, roll=self.roll, pitch=self.pitch, yaw=self.yaw)
        
        # Only render face if facing viewer
        if (eye_lz + eye_rz) / 2 > -5.0:
            pel_x, pel_y = project_3d(eye_lx, eye_ly + cy_offset, eye_lz, self.cx, self.cy)
            per_x, per_y = project_3d(eye_rx, eye_ry + cy_offset, eye_rz, self.cx, self.cy)
            eye_r = max(2.0, 3.5 * self.scale)
            
            # Blinking logic (blink every 3.5s for 150ms)
            is_blink = (int(self.t * 10) % 36 in (0, 1)) or (self.state == 'dance' and int(self.t*15)%4 in (0,1))
            
            if is_blink or (self.mood == 'happy' and self.state != 'feeding'):
                # Smiling eyes `^ ^` or happy blink
                elements.append(((eye_lz+eye_rz)/2, 'happy_eyes', pel_x, pel_y, per_x, per_y, eye_r))
            else:
                # Open glossy eyes
                elements.append(((eye_lz+eye_rz)/2, 'oval_eyes', pel_x, pel_y, per_x, per_y, eye_r))
                
            # Cheeks
            chk_lx, chk_ly, chk_lz = rotate_point_3d(-18.0*self.scale, face_y - 6*self.scale, face_z - 3*self.scale, roll=self.roll, pitch=self.pitch, yaw=self.yaw)
            chk_rx, chk_ry, chk_rz = rotate_point_3d(+18.0*self.scale, face_y - 6*self.scale, face_z - 3*self.scale, roll=self.roll, pitch=self.pitch, yaw=self.yaw)
            pcl_x, pcl_y = project_3d(chk_lx, chk_ly + cy_offset, chk_lz, self.cx, self.cy)
            pcr_x, pcr_y = project_3d(chk_rx, chk_ry + cy_offset, chk_rz, self.cx, self.cy)
            elements.append(((chk_lz+chk_rz)/2, 'cheeks', pcl_x, pcl_y, pcr_x, pcr_y, 4.0 * self.scale))
            
            # Mouth
            m_open = (self.state == 'feeding') or (self.mood == 'hungry' and not self.apple_eaten)
            mouth_y = face_y - (9.0 * self.scale)
            mx, my, mz = rotate_point_3d(0.0, mouth_y, face_z + 1.0, roll=self.roll, pitch=self.pitch, yaw=self.yaw)
            pm_x, pm_y = project_3d(mx, my + cy_offset, mz, self.cx, self.cy)
            elements.append((mz, 'mouth', pm_x, pm_y, self.mood, m_open, 4.0 * self.scale))

        # 4. 3D Apple (if visible and not eaten)
        if self.show_apple and not self.apple_eaten:
            # Render apple facets at (apple_x, apple_y)
            apple_depth = 10.0
            for f in self._apple_faces:
                poly_pts = []
                avg_az = 0.0
                for idx in f:
                    vx, vy, vz = self._apple_verts[idx]
                    vx *= self.apple_scale
                    vy *= self.apple_scale
                    vz *= self.apple_scale
                    vx, vy, vz = rotate_point_3d(vx, vy, vz, yaw=self.apple_yaw)
                    px = self.apple_x + vx
                    py = self.apple_y - vy
                    poly_pts.extend([px, py])
                    avg_az += vz
                avg_az /= len(f)
                elements.append((avg_az + 50.0, 'poly', poly_pts, "#ef4444"))
                
            # Apple stem & leaf
            stem_top_x = self.apple_x
            stem_top_y = self.apple_y - int(15 * self.scale * self.apple_scale)
            elements.append((60.0, 'line', self.apple_x, self.apple_y - int(10*self.scale), stem_top_x, stem_top_y, "#78350f", 2))
            # Green leaf
            leaf_pts = [
                stem_top_x, stem_top_y,
                stem_top_x + int(8*self.scale), stem_top_y - int(4*self.scale),
                stem_top_x + int(4*self.scale), stem_top_y + int(1*self.scale)
            ]
            elements.append((61.0, 'poly', leaf_pts, "#22c55e"))

        # Sort all 3D scene elements by Z-depth (back to front)
        elements.sort(key=lambda item: item[0])
        
        # Draw sorted elements
        for el in elements:
            kind = el[1]
            if kind == 'poly':
                _, _, pts, col = el
                if len(pts) >= 6:
                    self.canvas.create_polygon(pts, fill=col, outline="", tags="tamagotchi_3d")
            elif kind == 'line':
                _, _, x1, y1, x2, y2, col, w = el
                self.canvas.create_line(x1, y1, x2, y2, fill=col, width=w, tags="tamagotchi_3d")
            elif kind == 'oval_eyes':
                _, _, lx, ly, rx, ry, r = el
                # Left eye
                self.canvas.create_oval(lx - r, ly - r*1.3, lx + r, ly + r*1.3, fill="#0f172a", outline="", tags="tamagotchi_3d")
                self.canvas.create_oval(lx - r*0.4, ly - r*0.8, lx + r*0.3, ly - r*0.1, fill="#ffffff", outline="", tags="tamagotchi_3d")
                # Right eye
                self.canvas.create_oval(rx - r, ry - r*1.3, rx + r, ry + r*1.3, fill="#0f172a", outline="", tags="tamagotchi_3d")
                self.canvas.create_oval(rx - r*0.4, ry - r*0.8, rx + r*0.3, ry - r*0.1, fill="#ffffff", outline="", tags="tamagotchi_3d")
            elif kind == 'happy_eyes':
                _, _, lx, ly, rx, ry, r = el
                # Smiling arcs ^ ^
                self.canvas.create_arc(lx - r*1.2, ly - r*1.2, lx + r*1.2, ly + r*1.2, start=0, extent=180, style=tk.ARC, outline="#0f172a", width=max(2, int(2.5*self.scale)), tags="tamagotchi_3d")
                self.canvas.create_arc(rx - r*1.2, ry - r*1.2, rx + r*1.2, ry + r*1.2, start=0, extent=180, style=tk.ARC, outline="#0f172a", width=max(2, int(2.5*self.scale)), tags="tamagotchi_3d")
            elif kind == 'cheeks':
                _, _, lx, ly, rx, ry, r = el
                self.canvas.create_oval(lx - r, ly - r*0.6, lx + r, ly + r*0.6, fill="#fb7185", outline="", tags="tamagotchi_3d")
                self.canvas.create_oval(rx - r, ry - r*0.6, rx + r, ry + r*0.6, fill="#fb7185", outline="", tags="tamagotchi_3d")
            elif kind == 'mouth':
                _, _, mx, my, m_mood, m_open, mr = el
                if m_open:
                    # Open mouth (eating or hungry)
                    self.canvas.create_oval(mx - mr, my - mr*1.2, mx + mr, my + mr*1.2, fill="#881337", outline="#0f172a", width=1, tags="tamagotchi_3d")
                    # Cute little pink tongue
                    self.canvas.create_oval(mx - mr*0.6, my + mr*0.2, mx + mr*0.6, my + mr*1.1, fill="#fb7185", outline="", tags="tamagotchi_3d")
                elif m_mood == 'sad':
                    # Downturned mouth
                    self.canvas.create_arc(mx - mr, my - mr*0.2, mx + mr, my + mr*1.8, start=0, extent=180, style=tk.ARC, outline="#0f172a", width=2, tags="tamagotchi_3d")
                else:
                    # Happy open smile
                    self.canvas.create_arc(mx - mr*1.2, my - mr*1.5, mx + mr*1.2, my + mr*0.8, start=180, extent=180, style=tk.CHORD, fill="#991b1b", outline="#0f172a", width=1, tags="tamagotchi_3d")
                    self.canvas.create_oval(mx - mr*0.6, my - mr*0.2, mx + mr*0.6, my + mr*0.7, fill="#fb7185", outline="", tags="tamagotchi_3d")

        # 5. Draw active particle effects
        for p in self.particles:
            self.canvas.create_text(
                p["x"], p["y"], text=p.get("text", "★"),
                font=("Helvetica", int(12 * self.scale * max(0.4, p["life"]))),
                fill=p.get("color", "#fbbf24"), tags="tamagotchi_3d"
            )
