"""
Sprite ingestion — one animation per upload.

Accepts the common sheet-export formats and normalises each into a per-animation `frames.json`
that Godot consumes:

{
  "image": "atlas.png", "size": {"w": 1280, "h": 1280},
  "loop": true, "fps": 10.7,
  "frames": [{"x": 89, "y": 95, "w": 84, "h": 68, "ms": 93}, ...]
}

Supported inputs
  * AI sprite generators / simple grids: {"frames": {"0": {x,y,w,h,duration,trim?}, ...},
    "meta": {"fps": 10.7, "frame_size": {...}}}  — `duration` is in frames at `meta.fps`;
    frames are cropped to the union of their `trim` boxes so a small character on a big canvas
    renders at a sensible size without jitter.
  * Aseprite / TexturePacker (array or hash) WITHOUT tags → the whole sheet is one animation
    (`duration` in ms).
  * Aseprite WITH frameTags → use `split_tagged()` to get {tag_name: canonical_json} and store each.
"""
from __future__ import annotations

import hashlib
import io
import json
import struct
from pathlib import Path

from . import config, repo

ANIMATIONS = ("idle", "dance", "run", "jump")
REQUIRED = ("idle",)
NON_LOOPING = {"jump"}
# When an animation is missing, Godot plays the first available one in this chain.
FALLBACKS = {"dance": ["idle"], "run": ["dance", "idle"], "jump": ["run", "idle"]}
# Older uploads / tags
ALIASES = {"idle_happy": "idle", "idle_hungry": "idle", "idle_sad": "idle", "walk": "run", "running": "run", "front": "idle"}


class SpriteError(ValueError):
    pass


def _png_size(data: bytes) -> tuple[int, int]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise SpriteError("atlas must be a PNG file")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _ordered_frames(raw: dict) -> list[dict]:
    frames = raw.get("frames")
    if isinstance(frames, dict):
        keys = list(frames.keys())
        if all(k.isdigit() for k in keys):
            keys.sort(key=int)
        items = []
        for k in keys:
            f = dict(frames[k])
            f.setdefault("filename", k)
            items.append(f)
        return items
    if isinstance(frames, list):
        return frames
    raise SpriteError("frames.json has no 'frames'")


def _rect(f: dict) -> tuple[int, int, int, int]:
    """Frame rect on the atlas — Aseprite nests it under 'frame', simple exporters put x/y/w/h at top level."""
    src = f.get("frame", f)
    try:
        return int(src["x"]), int(src["y"]), int(src["w"]), int(src["h"])
    except (KeyError, TypeError, ValueError) as e:
        raise SpriteError("every frame needs x, y, w, h") from e


def _frame_ms(f: dict, fps: float | None) -> int:
    d = f.get("duration", 1)
    if fps:                                 # duration counted in frames at meta.fps
        return max(16, int(round(float(d) * 1000.0 / fps)))
    return max(16, int(d)) if d else 100    # Aseprite: milliseconds


def normalise_animation(raw: dict, atlas_png: bytes, name: str, frames: list[dict] | None = None) -> dict:
    """Canonical JSON for ONE animation. `frames` overrides the raw list (used when splitting tagged sheets)."""
    aw, ah = _png_size(atlas_png)
    meta = raw.get("meta") or {}
    fps = meta.get("fps")
    try:
        fps = float(fps) if fps else None
    except (TypeError, ValueError):
        fps = None
    items = frames if frames is not None else _ordered_frames(raw)
    if not items:
        raise SpriteError("no frames in frames.json")

    # union of trim boxes (relative to the frame) → stable crop for every frame
    trims = [f["trim"] for f in items if isinstance(f.get("trim"), dict)]
    crop = None
    if trims and len(trims) == len(items):
        x0 = min(int(t["x"]) for t in trims)
        y0 = min(int(t["y"]) for t in trims)
        x1 = max(int(t["x"]) + int(t["w"]) for t in trims)
        y1 = max(int(t["y"]) + int(t["h"]) for t in trims)
        pad = 2
        crop = (max(0, x0 - pad), max(0, y0 - pad), x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)

    out = []
    for f in items:
        x, y, w, h = _rect(f)
        if crop:
            cx, cy, cw, ch = crop
            x, y, w, h = x + cx, y + cy, min(cw, w - cx), min(ch, h - cy)
        if w <= 0 or h <= 0 or x + w > aw or y + h > ah:
            raise SpriteError(f"a frame of '{name}' falls outside the atlas ({aw}x{ah})")
        out.append({"x": x, "y": y, "w": w, "h": h, "ms": _frame_ms(f, fps)})
    return {"image": "atlas.png", "size": {"w": aw, "h": ah}, "loop": name not in NON_LOOPING,
            "fps": fps or round(1000.0 / (sum(f["ms"] for f in out) / len(out)), 2), "frames": out}


def split_tagged(raw: dict, atlas_png: bytes) -> dict[str, dict]:
    """Aseprite export with meta.frameTags → {tag: canonical} (only tags we know)."""
    tags = (raw.get("meta") or {}).get("frameTags") or []
    items = _ordered_frames(raw)
    out: dict[str, dict] = {}
    for t in tags:
        name = str(t.get("name", "")).strip().lower()
        name = ALIASES.get(name, name)
        if name not in ANIMATIONS:
            continue
        a, b = int(t.get("from", 0)), int(t.get("to", -1))
        if b < a or b >= len(items):
            raise SpriteError(f"tag '{name}' has an invalid frame range")
        out[name] = normalise_animation(raw, atlas_png, name, items[a:b + 1])
    if not out:
        raise SpriteError("no known animation tags found (" + ", ".join(ANIMATIONS) + ")")
    return out


# --------------------------------------------------------------------------- storage
def store_animation(level_id: int, name: str, atlas_png: bytes, frames_raw: bytes) -> dict | list[dict]:
    """Store one animation. A tagged Aseprite sheet is split into several; returns the stored rows."""
    name = ALIASES.get(name, name)
    if name not in ANIMATIONS and name != "auto":
        raise SpriteError("unknown animation name; use one of " + ", ".join(ANIMATIONS))
    lvl = repo.get_sprite_level(level_id)
    if lvl is None:
        raise SpriteError("level not found")
    try:
        raw = json.loads(frames_raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise SpriteError(f"frames.json is not valid JSON: {e}") from e

    tagged = bool((raw.get("meta") or {}).get("frameTags"))
    if tagged:
        parts = split_tagged(raw, atlas_png)
        return [_write(lvl, n, atlas_png, c) for n, c in parts.items()]
    if name == "auto":
        name = "idle"
    return _write(lvl, name, atlas_png, normalise_animation(raw, atlas_png, name))


def _write(lvl: dict, name: str, atlas_png: bytes, canonical: dict) -> dict:
    rel_dir = Path("sprites") / str(lvl["set_id"]) / str(lvl["id"]) / name
    abs_dir = config.DATA_DIR / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    frames_bytes = json.dumps(canonical, separators=(",", ":")).encode()
    (abs_dir / "atlas.png").write_bytes(atlas_png)
    (abs_dir / "frames.json").write_bytes(frames_bytes)
    etag = hashlib.sha256(atlas_png + frames_bytes).hexdigest()[:16]
    f0 = canonical["frames"][0]
    return repo.set_sprite_animation(
        lvl["id"], name,
        atlas_rel=str(rel_dir / "atlas.png").replace("\\", "/"),
        frames_rel=str(rel_dir / "frames.json").replace("\\", "/"),
        frame_count=len(canonical["frames"]), frame_w=f0["w"], frame_h=f0["h"], etag=etag,
    )


# --------------------------------------------------------------------------- placeholder generator
def make_placeholder(level: int, color_hex: str, name: str, size: int = 96) -> tuple[bytes, bytes]:
    """Procedural single-animation sheet (Pillow) so the pipeline can run before real art exists."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:  # pragma: no cover
        raise SpriteError("Pillow is required for placeholder generation") from e

    def hex_to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    base = hex_to_rgb(color_hex)
    n = {"dance": 6, "run": 6, "jump": 5}.get(name, 4)
    img = Image.new("RGBA", (n * size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mouth = 1
    frames = {}
    for i in range(n):
        t = i / max(1, n - 1)
        cx, cy = i * size + size // 2, size // 2
        r = int(size * 0.34)
        if name == "dance":
            cy -= int(size * 0.12 * abs(2 * t - 1))
        if name == "run":
            cy += int(size * 0.05 * (1 if i % 2 else -1))
        if name == "jump":
            cy -= int(size * 0.22 * (1 - (2 * t - 1) ** 2))
        squash = 1.0 + 0.08 * (1 if i % 2 else -1)
        shade = tuple(min(255, int(c * (0.85 + 0.15 * t))) for c in base)
        d.ellipse((cx - r, cy - int(r * squash), cx + r, cy + int(r / squash)), fill=(*shade, 255), outline=(20, 20, 30, 255), width=3)
        for ex in (-r // 3, r // 3):
            d.ellipse((cx + ex - 4, cy - r // 4 - 4, cx + ex + 4, cy - r // 4 + 4), fill=(20, 20, 30, 255))
        my = cy + r // 4
        if mouth > 0:
            d.arc((cx - r // 3, my - 8, cx + r // 3, my + 8), 0, 180, fill=(20, 20, 30, 255), width=3)
        elif mouth < 0:
            d.arc((cx - r // 3, my - 2, cx + r // 3, my + 14), 180, 360, fill=(20, 20, 30, 255), width=3)
        else:
            d.line((cx - r // 3, my, cx + r // 3, my), fill=(20, 20, 30, 255), width=3)
        for s in range(min(level, 5)):
            sx = cx - r + 6 + s * 10
            d.ellipse((sx, cy - r - 10, sx + 6, cy - r - 4), fill=(250, 204, 21, 255))
        frames[str(i)] = {"x": i * size, "y": 0, "w": size, "h": size, "duration": 1}
    buf = io.BytesIO()
    img.save(buf, "PNG")
    meta = {"app": "piano-timer-placeholder", "size": {"w": img.width, "h": img.height}, "fps": 9 if name != "run" else 12}
    return buf.getvalue(), json.dumps({"frames": frames, "meta": meta}).encode()
