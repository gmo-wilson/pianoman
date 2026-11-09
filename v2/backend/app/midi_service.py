"""
MIDI OUT service — the one thing Godot cannot do itself.

Ports v1's `MetronomeRunner` and `Player` (piano_timer.py) into a self-contained engine
driven by high-level commands. Runs inside the backend process; Godot calls
/api/v1/player/* and /api/v1/metronome/* and polls /api/v1/player/status.

Degrades gracefully when `mido`/`python-rtmidi` or a MIDI port is missing (status reports it).
"""
from __future__ import annotations

import threading
import time
from typing import Callable

try:
    import mido  # type: ignore
except ImportError:  # pragma: no cover
    mido = None

from . import config

_lock = threading.RLock()
_outport = None
_outport_name: str | None = None


def _open_outport():
    global _outport, _outport_name
    if mido is None:
        return None
    with _lock:
        if _outport is not None:
            return _outport
        names = mido.get_output_names()
        hint = config.MIDI_OUT_PORT_HINT.lower()
        chosen = None
        for n in names:
            low = n.lower()
            if "through" in low or "midi through" in low:
                continue
            if hint and hint in low:
                chosen = n
                break
            if chosen is None:
                chosen = n
        if chosen is None:
            return None
        try:
            _outport = mido.open_output(chosen)
            _outport_name = chosen
        except Exception:  # noqa: BLE001
            _outport = None
        return _outport


def _close_outport() -> None:
    global _outport, _outport_name
    with _lock:
        if _outport is not None:
            try:
                _outport.close()
            except Exception:  # noqa: BLE001
                pass
        _outport, _outport_name = None, None


def reconcile_outport(output_names: list[str]) -> None:
    """Called by the input watcher every second: drop a vanished output port, so the next send reopens a fresh one."""
    if _outport is not None and _outport_name not in output_names:
        _close_outport()


def _send(msg) -> None:
    port = _open_outport()
    if port is not None:
        try:
            port.send(msg)
        except Exception:  # noqa: BLE001
            _close_outport()          # stale handle (piano switched off mid-note); reopen on the next send


def available_ports() -> dict:
    if mido is None:
        return {"inputs": [], "outputs": [], "error": "mido not installed"}
    return {"inputs": mido.get_input_names(), "outputs": mido.get_output_names(), "selected_output": _outport_name}


# --------------------------------------------------------------------------- metronome
class Metronome:
    """Clicks on MIDI channel 10 (drums): high woodblock on beat 1, low woodblock otherwise."""

    def __init__(self) -> None:
        self.bpm = 80
        self.beats_per_bar = 4
        self.active = False
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.beat = 0
        self.on_beat: Callable[[int], None] | None = None

    def start(self, bpm: int | None = None) -> None:
        if bpm:
            self.bpm = int(bpm)
        if self.active:
            return
        self.active = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.active = False
        self._stop.set()

    def set_bpm(self, bpm: int) -> None:
        self.bpm = max(20, min(300, int(bpm)))

    def count_in(self, beats: int = 4, then: Callable[[], None] | None = None) -> None:
        def _go():
            interval = 60.0 / self.bpm
            for i in range(beats):
                self._click(i)
                time.sleep(interval)
            if then:
                then()
        threading.Thread(target=_go, daemon=True).start()

    def _click(self, beat_in_bar: int) -> None:
        if mido is None:
            return
        note = 76 if beat_in_bar == 0 else 77
        _send(mido.Message("note_on", channel=9, note=note, velocity=110 if beat_in_bar == 0 else 80))
        _send(mido.Message("note_off", channel=9, note=note, velocity=0))
        if self.on_beat:
            self.on_beat(beat_in_bar)

    def _run(self) -> None:
        next_t = time.monotonic()
        self.beat = 0
        while not self._stop.is_set():
            self._click(self.beat % self.beats_per_bar)
            self.beat += 1
            next_t += 60.0 / self.bpm
            delay = next_t - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = time.monotonic()

    def status(self) -> dict:
        return {"active": self.active, "bpm": self.bpm, "beat": self.beat % self.beats_per_bar}


# --------------------------------------------------------------------------- song / lesson player
class Player:
    """Plays a list of {time, type:'on'|'off', note, vel} events with speed, seek, pause."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.speed = 1.0
        self.mute_drums = True
        self.playing = False
        self.position = 0.0            # song seconds
        self.duration = 0.0
        self.song_id: str | None = None
        self.label: str | None = None
        self._idx = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._active_notes: set[tuple[int, int]] = set()
        self.on_note: Callable[[dict], None] | None = None   # mirrored to Godot via live state

    def load(self, events: list[dict], song_id: str | None = None, label: str | None = None,
             speed: float = 1.0, mute_drums: bool = True) -> None:
        self.stop()
        self.events = sorted(events, key=lambda e: e["time"])
        self.duration = self.events[-1]["time"] if self.events else 0.0
        self.song_id, self.label = song_id, label
        self.speed, self.mute_drums = speed, mute_drums
        self.position, self._idx = 0.0, 0

    def play(self) -> None:
        if self.playing or not self.events:
            return
        self.playing = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self.playing = False
        self._stop.set()
        self.silence()

    def stop(self) -> None:
        self.pause()
        self.position, self._idx = 0.0, 0

    def seek(self, pct: float) -> None:
        was = self.playing
        self.pause()
        self.position = max(0.0, min(1.0, pct)) * self.duration
        self._idx = next((i for i, e in enumerate(self.events) if e["time"] >= self.position), len(self.events))
        if was:
            self.play()

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.25, min(2.0, float(speed)))

    def silence(self) -> None:
        if mido is None:
            return
        for ch, note in list(self._active_notes):
            _send(mido.Message("note_off", channel=ch, note=note, velocity=0))
        self._active_notes.clear()
        for ch in range(16):
            _send(mido.Message("control_change", channel=ch, control=123, value=0))

    def _loop(self) -> None:
        start_wall = time.monotonic()
        start_pos = self.position
        while not self._stop.is_set() and self._idx < len(self.events):
            e = self.events[self._idx]
            target = start_wall + (e["time"] - start_pos) / self.speed
            delay = target - time.monotonic()
            if delay > 0:
                if self._stop.wait(min(delay, 0.05)):
                    break
                continue
            ch = int(e.get("channel", 0))
            if not (self.mute_drums and ch == 9) and mido is not None:
                if e["type"] == "on" and e.get("vel", 0) > 0:
                    _send(mido.Message("note_on", channel=ch, note=e["note"], velocity=min(127, e["vel"])))
                    self._active_notes.add((ch, e["note"]))
                else:
                    _send(mido.Message("note_off", channel=ch, note=e["note"], velocity=0))
                    self._active_notes.discard((ch, e["note"]))
            if self.on_note:
                self.on_note(e)
            self.position = e["time"]
            self._idx += 1
        if self._idx >= len(self.events):
            self.playing = False
            self.position = self.duration
            self.silence()

    def status(self) -> dict:
        return {
            "playing": self.playing, "position": round(self.position, 2), "duration": round(self.duration, 2),
            "progress": (self.position / self.duration) if self.duration else 0.0,
            "speed": self.speed, "mute_drums": self.mute_drums, "song_id": self.song_id, "label": self.label,
            "events_loaded": len(self.events), "midi_out": _outport_name, "midi_available": mido is not None,
        }


# --------------------------------------------------------------------------- MIDI IN bridge
class MidiInput:
    """
    Owns the piano's input port and fans note events out to subscribers (the kiosk over WebSocket,
    the admin live view). Re-enumerates every second so hot-plug works on every OS.
    Messages: {"t": "on"|"off", "n": note, "v": velocity, "ts": unix}  and
              {"t": "status", "connected": bool, "name": str, "inputs": [...]}
    """

    def __init__(self) -> None:
        self.port = None
        self.port_name: str | None = None
        self.inputs: list[str] = []
        self.active_notes: dict[int, int] = {}
        self._subs: list[Callable[[dict], None]] = []
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.last_event_ts = 0.0

    def subscribe(self, cb: Callable[[dict], None]) -> Callable[[], None]:
        with _lock:
            self._subs.append(cb)
        cb(self.status())
        def unsub():
            with _lock:
                if cb in self._subs:
                    self._subs.remove(cb)
        return unsub

    def status(self) -> dict:
        return {"t": "status", "connected": self.port is not None, "name": self.port_name, "inputs": self.inputs,
                "active_notes": sorted(self.active_notes)}

    def start(self) -> None:
        if mido is None or self._thread:
            return
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._close()

    def _publish(self, msg: dict) -> None:
        with _lock:
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(msg)
            except Exception:  # noqa: BLE001
                pass

    def _on_message(self, m) -> None:
        ts = time.time()
        if m.type == "note_on" and m.velocity > 0:
            self.active_notes[m.note] = m.velocity
            self.last_event_ts = ts
            self._publish({"t": "on", "n": m.note, "v": m.velocity, "ts": ts})
        elif m.type in ("note_off", "note_on"):
            self.active_notes.pop(m.note, None)
            self._publish({"t": "off", "n": m.note, "v": 0, "ts": ts})

    def _pick(self, names: list[str]) -> str | None:
        hint = config.MIDI_IN_PORT_HINT.lower()
        for n in names:
            if hint and hint in n.lower():
                return n
        for n in names:
            if "through" not in n.lower():
                return n
        return None

    def _close(self) -> None:
        if self.port is not None:
            try:
                self.port.close()
            except Exception:  # noqa: BLE001
                pass
        self.port, self.port_name = None, None
        if self.active_notes:
            for n in list(self.active_notes):      # release held notes on the kiosk side
                self._publish({"t": "off", "n": n, "v": 0, "ts": time.time()})
            self.active_notes.clear()
        player._active_notes.clear()
        _close_outport()
        self._publish(self.status())

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                names = [n for n in mido.get_input_names()]
                reconcile_outport(list(mido.get_output_names()))
            except Exception:  # noqa: BLE001
                names = []
            if names != self.inputs:
                self.inputs = names
                self._publish(self.status())
            if self.port is not None and self.port_name not in names:
                self._close()
            if self.port is None:
                target = self._pick(names)
                if target:
                    try:
                        self.port = mido.open_input(target, callback=self._on_message)
                        self.port_name = target
                        self._publish(self.status())
                    except Exception:  # noqa: BLE001
                        self.port = None
            self._stop.wait(1.0)


metronome = Metronome()
player = Player()
midi_in = MidiInput()
