"""
Piano Timer v2 backend — FastAPI.

    uvicorn app.main:app --host 0.0.0.0 --port 8080

Routes (all JSON unless noted):
  GET  /api/v1/health
  GET  /api/v1/settings                PUT /api/v1/settings
  GET  /api/v1/students                POST /api/v1/students   PATCH/DELETE /api/v1/students/{id}
  GET  /api/v1/students/{id}/buddy     GET /api/v1/students/{id}/stats
  POST /api/v1/students/{id}/progress  {seconds}            -> buddy status
  POST /api/v1/students/{id}/celebrate
  POST/DELETE /api/v1/students/{id}/road  {level, steps_in_level} | {steps}   (place on the road; rules continue)
  POST /api/v1/students/{id}/reset {practice, sessions, runs, road}
  GET  /api/v1/buddies                 (all active students' buddy status — kiosk select screen)
  GET  /api/v1/students/{id}/game/credits   POST /api/v1/students/{id}/game/runs {score,distance,duration_s}
  GET  /api/v1/students/{id}/game/runs      POST /api/v1/students/{id}/game/reset (admin)
  GET  /api/v1/game/leaderboard?period=all|week|today   DELETE /api/v1/game/runs/{id} (admin)
  GET  /api/v1/sessions?student_id&limit&offset   POST /api/v1/sessions   GET/DELETE /api/v1/sessions/{id}
  GET  /api/v1/lessons  POST /api/v1/lessons  GET/PUT/DELETE /api/v1/lessons/{id}
  GET  /api/v1/songs    POST /api/v1/songs/upload (multipart .mid)  GET/DELETE /api/v1/songs/{id}
  POST /api/v1/songs/{id}/to-lesson
  GET/POST /api/v1/sprites/sets   PATCH/DELETE /api/v1/sprites/sets/{id}   POST .../{id}/default
  GET/POST /api/v1/sprites/sets/{id}/levels        (list / add a level, any number of levels)
  PATCH/DELETE /api/v1/sprites/levels/{level_id}   POST .../move {to}
  POST/DELETE /api/v1/sprites/levels/{level_id}/animations/{name}  (multipart atlas + frames, one animation per upload)
  GET  /api/v1/sprites/animations     (names, required, fallback chain)
  POST /api/v1/sprites/sets/{id}/placeholders      {only_missing}
  GET  /api/v1/sprites/manifest?set_id
  GET  /api/v1/releases  POST /api/v1/releases (multipart .pck)  POST /api/v1/releases/{version}/current
  GET  /api/v1/releases/current
  POST /api/v1/player/{load|play|pause|stop|seek|speed|mute-drums}   GET /api/v1/player/status
  POST /api/v1/metronome/{start|stop|bpm|count-in}                   GET /api/v1/metronome/status
  GET  /api/v1/midi/ports              WS /ws/midi (piano input stream: status, note on/off)
  GET/POST /api/v1/live                (kiosk mirrors its state here for the admin)
  POST /api/v1/system/update           (runs deploy/update.sh — admin token required if set)
  /files/**  static DATA_DIR            /admin/**  static SPA
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import asyncio

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, db, game, midi_service, repo, sprites
from .midi_parse import parse_midi_bytes

app = FastAPI(title="Piano Timer v2", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def _startup() -> None:
    config.ensure_dirs()
    db.connect()
    if repo.default_sprite_set_id() is None:
        repo.create_sprite_set("Default", make_default=True)
    midi_service.midi_in.start()


@app.on_event("shutdown")
def _shutdown() -> None:
    midi_service.midi_in.stop()


# --------------------------------------------------------------------------- helpers
def admin_guard(x_admin_token: str | None = Header(default=None)) -> None:
    if config.ADMIN_TOKEN and x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(401, "admin token required")


def _404(obj: Any, what: str = "not found"):
    if obj is None:
        raise HTTPException(404, what)
    return obj


# --------------------------------------------------------------------------- health / settings
@app.get("/api/v1/health")
def health():
    midi = midi_service.available_ports()
    midi["input"] = midi_service.midi_in.status()
    return {"ok": True, "version": app.version, "data_dir": str(config.DATA_DIR), "midi": midi}


@app.get("/api/v1/settings")
def get_settings():
    return repo.get_settings()


@app.put("/api/v1/settings", dependencies=[Depends(admin_guard)])
def put_settings(patch: dict):
    return repo.set_settings(patch)


# --------------------------------------------------------------------------- students & buddies
@app.get("/api/v1/students")
def students(include_inactive: bool = False):
    return repo.list_students(include_inactive)


@app.post("/api/v1/students", dependencies=[Depends(admin_guard)])
def create_student(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name required")
    if repo.get_student_by_name(name):
        raise HTTPException(409, "student exists")
    return repo.create_student(name, body.get("color"), body.get("sprite_set"))


@app.patch("/api/v1/students/{sid}", dependencies=[Depends(admin_guard)])
def patch_student(sid: int, body: dict):
    return _404(repo.update_student(sid, body))


@app.delete("/api/v1/students/{sid}", dependencies=[Depends(admin_guard)])
def delete_student(sid: int):
    repo.delete_student(sid)
    return {"ok": True}


@app.get("/api/v1/students/{sid}/buddy")
def student_buddy(sid: int):
    return repo.buddy_status(_404(repo.get_student(sid)))


@app.get("/api/v1/students/{sid}/stats")
def student_stats(sid: int):
    _404(repo.get_student(sid))
    return repo.student_stats(sid)


@app.post("/api/v1/students/{sid}/progress")
def student_progress(sid: int, body: dict):
    st = _404(repo.get_student(sid))
    repo.record_progress(sid, float(body.get("seconds", 0)), body.get("day"))
    return repo.buddy_status(st)


@app.post("/api/v1/students/{sid}/road", dependencies=[Depends(admin_guard)])
def student_set_road(sid: int, body: dict):
    """{"level": 4, "steps_in_level": 1}  or  {"steps": 10}  — optional "day": "YYYY-MM-DD" (default today)."""
    _404(repo.get_student(sid))
    return repo.set_road_position(sid, body.get("level"), int(body.get("steps_in_level", 0)), body.get("steps"), body.get("day"))


@app.delete("/api/v1/students/{sid}/road", dependencies=[Depends(admin_guard)])
def student_clear_road(sid: int):
    _404(repo.get_student(sid))
    repo.clear_road_position(sid)
    return repo.buddy_status(repo.get_student(sid))


@app.post("/api/v1/students/{sid}/reset", dependencies=[Depends(admin_guard)])
def student_reset(sid: int, body: dict):
    """Opt-in flags: practice, sessions, runs, road."""
    _404(repo.get_student(sid))
    return repo.reset_student(sid, bool(body.get("practice")), bool(body.get("sessions")), bool(body.get("runs")), bool(body.get("road")))


@app.post("/api/v1/students/{sid}/celebrate")
def student_celebrate(sid: int):
    return _404(repo.celebrate_buddy(sid))


@app.get("/api/v1/buddies")
def buddies():
    return [repo.buddy_status(s) for s in repo.list_students()]


# --------------------------------------------------------------------------- runner mini-game
@app.get("/api/v1/students/{sid}/game/credits")
def game_credits(sid: int):
    return game.credits(_404(repo.get_student(sid)))


@app.post("/api/v1/students/{sid}/game/runs")
def game_run(sid: int, body: dict):
    st = _404(repo.get_student(sid))
    try:
        return game.record_run(st, int(body.get("score", 0)), body.get("distance"), body.get("duration_s"))
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


@app.get("/api/v1/students/{sid}/game/runs")
def game_student_runs(sid: int, limit: int = 50):
    _404(repo.get_student(sid))
    return game.student_runs(sid, limit)


@app.post("/api/v1/students/{sid}/game/reset", dependencies=[Depends(admin_guard)])
def game_reset(sid: int, body: dict | None = None):
    game.reset_credits(sid, (body or {}).get("day"))
    return {"ok": True}


@app.get("/api/v1/game/leaderboard")
def game_leaderboard(period: str = "all", limit: int = Query(10, le=100)):
    if period not in ("all", "week", "today"):
        raise HTTPException(400, "period must be all|week|today")
    return game.leaderboard(period, limit)


@app.delete("/api/v1/game/runs/{run_id}", dependencies=[Depends(admin_guard)])
def game_delete_run(run_id: int):
    game.delete_run(run_id)
    return {"ok": True}


# --------------------------------------------------------------------------- sessions
@app.get("/api/v1/sessions")
def sessions(student_id: int | None = None, limit: int = Query(50, le=500), offset: int = 0):
    return repo.list_sessions(student_id, limit, offset)


@app.post("/api/v1/sessions")
def post_session(body: dict):
    return repo.save_session(body)


@app.get("/api/v1/sessions/{sid}")
def session(sid: str, events: bool = True):
    return _404(repo.get_session(sid, with_events=events))


@app.delete("/api/v1/sessions/{sid}", dependencies=[Depends(admin_guard)])
def delete_session(sid: str):
    repo.delete_session(sid)
    return {"ok": True}


# --------------------------------------------------------------------------- lessons
@app.get("/api/v1/lessons")
def lessons():
    return repo.list_lessons()


@app.post("/api/v1/lessons")
def post_lesson(body: dict):
    if not body.get("name"):
        raise HTTPException(400, "name required")
    return repo.upsert_lesson(body)


@app.get("/api/v1/lessons/{lid}")
def lesson(lid: str):
    return _404(repo.get_lesson(lid))


@app.put("/api/v1/lessons/{lid}")
def put_lesson(lid: str, body: dict):
    _404(repo.get_lesson(lid))
    body["id"] = lid
    return repo.upsert_lesson(body)


@app.delete("/api/v1/lessons/{lid}", dependencies=[Depends(admin_guard)])
def delete_lesson(lid: str):
    repo.delete_lesson(lid)
    return {"ok": True}


# --------------------------------------------------------------------------- songs
@app.get("/api/v1/songs")
def songs():
    return repo.list_songs()


@app.get("/api/v1/songs/{sid}")
def song(sid: str):
    return _404(repo.get_song(sid))


@app.post("/api/v1/songs/upload", dependencies=[Depends(admin_guard)])
async def upload_song(file: UploadFile = File(...), title: str = Form(""), composer: str = Form("")):
    data = await file.read()
    try:
        parsed = parse_midi_bytes(data)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    safe = "".join(ch for ch in (file.filename or "song.mid") if ch.isalnum() or ch in "._-") or "song.mid"
    (config.SONGS_DIR / safe).write_bytes(data)
    return repo.upsert_song({
        "title": title or Path(safe).stem.replace("_", " ").title(), "composer": composer, "filename": safe,
        "file_size": len(data), **parsed,
    })


@app.delete("/api/v1/songs/{sid}", dependencies=[Depends(admin_guard)])
def delete_song(sid: str):
    s = repo.get_song(sid)
    if s and s.get("filename"):
        (config.SONGS_DIR / s["filename"]).unlink(missing_ok=True)
    repo.delete_song(sid)
    return {"ok": True}


@app.post("/api/v1/songs/{sid}/to-lesson", dependencies=[Depends(admin_guard)])
def song_to_lesson(sid: str, body: dict | None = None):
    s = _404(repo.get_song(sid))
    name = (body or {}).get("name") or s["title"]
    return repo.upsert_lesson({"name": name, "chords": s["chords"], "midi_events": s["midi_events"], "source_song_id": sid})


# --------------------------------------------------------------------------- sprites
@app.get("/api/v1/sprites/sets")
def sprite_sets():
    return repo.list_sprite_sets()


@app.post("/api/v1/sprites/sets", dependencies=[Depends(admin_guard)])
def create_sprite_set(body: dict):
    return repo.create_sprite_set(body.get("name", "New set"), bool(body.get("default")), bool(body.get("seed_defaults", True)))


@app.patch("/api/v1/sprites/sets/{set_id}", dependencies=[Depends(admin_guard)])
def rename_sprite_set(set_id: int, body: dict):
    repo.rename_sprite_set(set_id, body.get("name", "").strip() or "Set")
    return {"ok": True}


@app.delete("/api/v1/sprites/sets/{set_id}", dependencies=[Depends(admin_guard)])
def delete_sprite_set(set_id: int):
    if not repo.delete_sprite_set(set_id):
        raise HTTPException(400, "cannot delete the default or the only sprite set")
    return {"ok": True}


@app.post("/api/v1/sprites/sets/{set_id}/default", dependencies=[Depends(admin_guard)])
def default_sprite_set(set_id: int):
    repo.set_default_sprite_set(set_id)
    return {"ok": True}


@app.get("/api/v1/sprites/sets/{set_id}/levels")
def sprite_levels(set_id: int):
    return repo.list_sprite_levels(set_id)


@app.post("/api/v1/sprites/sets/{set_id}/levels", dependencies=[Depends(admin_guard)])
def add_sprite_level(set_id: int, body: dict | None = None):
    b = body or {}
    return repo.add_sprite_level(set_id, b.get("display_name"), b.get("color"), b.get("position"))


@app.patch("/api/v1/sprites/levels/{level_id}", dependencies=[Depends(admin_guard)])
def patch_sprite_level(level_id: int, body: dict):
    return _404(repo.update_sprite_level(level_id, body))


@app.post("/api/v1/sprites/levels/{level_id}/move", dependencies=[Depends(admin_guard)])
def move_sprite_level(level_id: int, body: dict):
    return repo.move_sprite_level(level_id, int(body.get("to", 1)))


@app.delete("/api/v1/sprites/levels/{level_id}", dependencies=[Depends(admin_guard)])
def delete_sprite_level(level_id: int):
    if not repo.delete_sprite_level(level_id):
        raise HTTPException(400, "level not found or it is the last level of its set")
    return {"ok": True}


@app.post("/api/v1/sprites/levels/{level_id}/animations/{name}", dependencies=[Depends(admin_guard)])
async def upload_sprite_animation(level_id: int, name: str, atlas: UploadFile = File(...), frames: UploadFile = File(...)):
    """One animation per upload (name = idle_happy | idle_hungry | idle_sad | dance | evolve | poke | eat, or 'auto'
    for a tagged Aseprite sheet, which is split into its tags)."""
    try:
        return sprites.store_animation(level_id, name, await atlas.read(), await frames.read())
    except sprites.SpriteError as e:
        raise HTTPException(400, str(e)) from e


@app.delete("/api/v1/sprites/levels/{level_id}/animations/{name}", dependencies=[Depends(admin_guard)])
def delete_sprite_animation(level_id: int, name: str):
    if not repo.delete_sprite_animation(level_id, name):
        raise HTTPException(404, "animation not found")
    return {"ok": True}


@app.get("/api/v1/sprites/animations")
def sprite_animation_names():
    return {"names": list(sprites.ANIMATIONS), "required": list(sprites.REQUIRED), "fallbacks": sprites.FALLBACKS}


@app.post("/api/v1/sprites/sets/{set_id}/placeholders", dependencies=[Depends(admin_guard)])
def generate_placeholders(set_id: int, body: dict | None = None):
    only_missing = bool((body or {}).get("only_missing", False))
    done = []
    for lvl in repo.list_sprite_levels(set_id):
        if only_missing and lvl["ready"]:
            continue
        for name in sprites.ANIMATIONS:
            try:
                png, frames_json = sprites.make_placeholder(lvl["level"], lvl["color"] or "#38bdf8", name)
            except sprites.SpriteError as e:
                raise HTTPException(500, str(e)) from e
            sprites.store_animation(lvl["id"], name, png, frames_json)
        done.append(lvl["level"])
    return {"generated": done}


@app.get("/api/v1/sprites/manifest")
def sprite_manifest(set_id: int | None = None):
    return repo.sprite_manifest(set_id)


# --------------------------------------------------------------------------- releases (Godot .pck hot updates)
@app.get("/api/v1/releases")
def releases():
    return repo.list_releases()


@app.get("/api/v1/releases/current")
def release_current():
    r = repo.current_release()
    return r or JSONResponse({"version": None}, status_code=204)


@app.post("/api/v1/releases", dependencies=[Depends(admin_guard)])
async def upload_release(file: UploadFile = File(...), version: str = Form(...), notes: str = Form(""),
                         make_current: bool = Form(True)):
    data = await file.read()
    if not data.startswith(b"GDPC"):
        raise HTTPException(400, "not a Godot .pck file")
    safe_v = "".join(ch for ch in version if ch.isalnum() or ch in "._-")
    rel = Path("releases") / safe_v / "main.pck"
    (config.DATA_DIR / rel).parent.mkdir(parents=True, exist_ok=True)
    (config.DATA_DIR / rel).write_bytes(data)
    return repo.add_release(safe_v, str(rel).replace("\\", "/"), hashlib.sha256(data).hexdigest(), len(data), notes, make_current)


@app.post("/api/v1/releases/{version}/current", dependencies=[Depends(admin_guard)])
def set_current_release(version: str):
    repo.set_current_release(version)
    return {"ok": True}


# --------------------------------------------------------------------------- MIDI out: player & metronome
def _load_events_for(body: dict) -> tuple[list[dict], str | None, str | None]:
    if body.get("song_id"):
        s = _404(repo.get_song(body["song_id"]), "song not found")
        return s["midi_events"], s["id"], s["title"]
    if body.get("lesson_id"):
        l = _404(repo.get_lesson(body["lesson_id"]), "lesson not found")
        return l["midi_events"], l["id"], l["name"]
    if body.get("events"):
        return body["events"], None, body.get("label")
    raise HTTPException(400, "song_id, lesson_id or events required")


@app.post("/api/v1/player/load")
def player_load(body: dict):
    events, sid, label = _load_events_for(body)
    midi_service.player.load(events, sid, label, float(body.get("speed", 1.0)), bool(body.get("mute_drums", True)))
    if body.get("autoplay", True):
        midi_service.player.play()
    return midi_service.player.status()


@app.post("/api/v1/player/play")
def player_play():
    midi_service.player.play()
    return midi_service.player.status()


@app.post("/api/v1/player/pause")
def player_pause():
    midi_service.player.pause()
    return midi_service.player.status()


@app.post("/api/v1/player/stop")
def player_stop():
    midi_service.player.stop()
    return midi_service.player.status()


@app.post("/api/v1/player/seek")
def player_seek(body: dict):
    midi_service.player.seek(float(body.get("pct", 0)))
    return midi_service.player.status()


@app.post("/api/v1/player/speed")
def player_speed(body: dict):
    midi_service.player.set_speed(float(body.get("speed", 1.0)))
    return midi_service.player.status()


@app.post("/api/v1/player/mute-drums")
def player_mute(body: dict):
    midi_service.player.mute_drums = bool(body.get("mute", True))
    return midi_service.player.status()


@app.get("/api/v1/player/status")
def player_status():
    return midi_service.player.status()


@app.post("/api/v1/metronome/start")
def metro_start(body: dict | None = None):
    midi_service.metronome.start((body or {}).get("bpm"))
    return midi_service.metronome.status()


@app.post("/api/v1/metronome/stop")
def metro_stop():
    midi_service.metronome.stop()
    return midi_service.metronome.status()


@app.post("/api/v1/metronome/bpm")
def metro_bpm(body: dict):
    midi_service.metronome.set_bpm(int(body.get("bpm", 80)))
    return midi_service.metronome.status()


@app.post("/api/v1/metronome/count-in")
def metro_count_in(body: dict | None = None):
    b = body or {}
    if b.get("bpm"):
        midi_service.metronome.set_bpm(int(b["bpm"]))
    midi_service.metronome.count_in(int(b.get("beats", 4)), then=midi_service.player.play if b.get("then_play") else None)
    return {"ok": True}


@app.get("/api/v1/metronome/status")
def metro_status():
    return midi_service.metronome.status()


@app.get("/api/v1/midi/ports")
def midi_ports():
    out = midi_service.available_ports()
    out["input_status"] = midi_service.midi_in.status()
    return out


@app.websocket("/ws/midi")
async def ws_midi(ws: WebSocket):
    """Streams piano input to the kiosk/admin: status first, then {"t":"on"/"off","n","v","ts"}."""
    await ws.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)

    def push(msg: dict) -> None:          # called from the MIDI thread
        try:
            loop.call_soon_threadsafe(queue.put_nowait, msg)
        except RuntimeError:
            pass

    unsub = midi_service.midi_in.subscribe(push)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=15.0)
            except asyncio.TimeoutError:
                msg = {"t": "ping"}
            await ws.send_json(msg)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        unsub()


# --------------------------------------------------------------------------- live state & system
@app.get("/api/v1/live")
def live():
    return repo.get_live()


@app.post("/api/v1/live")
def post_live(body: dict):
    return repo.set_live(body)


@app.post("/api/v1/system/update", dependencies=[Depends(admin_guard)])
def system_update():
    script = config.CODE_DIR.parent / "deploy" / "update.sh"
    if not script.exists():
        raise HTTPException(500, "deploy/update.sh missing")
    # fire and forget; the script restarts this service when done
    subprocess.Popen(["/bin/bash", str(script)], cwd=str(script.parent), start_new_session=True)
    return {"started": True}


# --------------------------------------------------------------------------- static
app.mount("/files", StaticFiles(directory=str(config.DATA_DIR)), name="files")
if config.ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(config.ADMIN_DIR), html=True), name="admin")


@app.get("/")
def root():
    return RedirectResponse("/admin/")
