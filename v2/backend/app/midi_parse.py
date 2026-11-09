"""Standard MIDI File parser + chord extractor (ported from v1 web_server.py, stdlib only)."""
from __future__ import annotations

import struct

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CHORDS_MAP = {
    frozenset([0, 4, 7]): "", frozenset([0, 3, 7]): "m", frozenset([0, 3, 6]): "dim", frozenset([0, 4, 8]): "aug",
    frozenset([0, 4, 7, 10]): "7", frozenset([0, 4, 7, 11]): "maj7", frozenset([0, 3, 7, 10]): "m7",
    frozenset([0, 5, 7]): "sus4", frozenset([0, 2, 7]): "sus2",
}


def _vlq(data: bytes, pos: int) -> tuple[int, int]:
    val = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        val = (val << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return val, pos


def parse_smf(data: bytes) -> tuple[list[dict], int]:
    if len(data) < 14 or data[:4] != b"MThd":
        raise ValueError("Invalid MIDI header (missing MThd)")
    header_len = struct.unpack(">I", data[4:8])[0]
    _fmt, num_tracks, division = struct.unpack(">HHH", data[8:14])
    pos = 8 + header_len
    raw: list[tuple] = []

    for _ in range(num_tracks):
        if pos >= len(data) or data[pos:pos + 4] != b"MTrk":
            break
        track_len = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        track_end = pos + 8 + track_len
        t = pos + 8
        pos = track_end
        ticks = 0
        running = None
        while t < track_end and t < len(data):
            delta, t = _vlq(data, t)
            ticks += delta
            if t >= track_end:
                break
            b = data[t]
            if b >= 0x80:
                status = b
                t += 1
                if status < 0xF0:
                    running = status
            else:
                status = running
                if status is None:
                    t += 1
                    continue
            if status == 0xFF:
                if t >= track_end:
                    break
                meta_type = data[t]
                t += 1
                mlen, t = _vlq(data, t)
                meta = data[t:t + mlen]
                t += mlen
                if meta_type == 0x51 and len(meta) == 3:
                    raw.append((ticks, "tempo", (meta[0] << 16) | (meta[1] << 8) | meta[2]))
            elif status in (0xF0, 0xF7):
                slen, t = _vlq(data, t)
                t += slen
            else:
                et, ch = status & 0xF0, status & 0x0F
                if et in (0x80, 0x90):
                    note, vel = data[t], data[t + 1]
                    t += 2
                    on = et == 0x90 and vel > 0
                    raw.append((ticks, "on" if on else "off", note, vel, ch))
                elif et in (0xA0, 0xB0, 0xE0):
                    t += 2
                elif et in (0xC0, 0xD0):
                    t += 1

    raw.sort(key=lambda x: x[0])
    tpb = division if (division & 0x8000) == 0 else 480
    now, cur_tick, us_per_beat = 0.0, 0, 500000
    events: list[dict] = []
    for ev in raw:
        d = ev[0] - cur_tick
        if d > 0:
            now += (d / tpb) * (us_per_beat / 1e6)
            cur_tick = ev[0]
        if ev[1] == "tempo":
            us_per_beat = ev[2]
        else:
            events.append({"time": round(now, 3), "type": ev[1], "note": ev[2], "vel": ev[3] if ev[1] == "on" else 0,
                           "channel": ev[4], "is_drum": ev[4] == 9})
    return events, num_tracks


def extract_chords(events: list[dict], top: int = 6) -> list[str]:
    active: set[int] = set()
    counts: dict[str, int] = {}
    last = None
    for ev in events:
        if ev.get("is_drum") or ev.get("channel") == 9:
            continue
        if ev.get("type") == "on":
            active.add(ev["note"])
            if len(active) >= 3:
                pcs = {n % 12 for n in active}
                matched = None
                for root in pcs:
                    rel = frozenset((p - root) % 12 for p in pcs)
                    if rel in CHORDS_MAP:
                        matched = NOTES[root] + CHORDS_MAP[rel]
                        break
                if matched and matched != last:
                    counts[matched] = counts.get(matched, 0) + 1
                    last = matched
        else:
            active.discard(ev.get("note"))
            if len(active) < 3:
                last = None
    return [c for c, _ in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top]]


def parse_midi_bytes(data: bytes) -> dict:
    events, tracks = parse_smf(data)
    if not events:
        raise ValueError("MIDI file contains no notes")
    return {
        "midi_events": events,
        "track_count": tracks,
        "duration_seconds": round(events[-1]["time"], 2),
        "notes_count": sum(1 for e in events if e["type"] == "on"),
        "chords": extract_chords(events),
    }
