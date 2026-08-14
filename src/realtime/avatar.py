"""
AI face — the mandatory part of requirement #1 ("the face is mandatory, the
vendor is not"). Implements the fallback column explicitly: "2D lip-synced
avatar — full marks", so the project's grade does NOT depend on a
Simli/Tavus/HeyGen trial credit being alive.

Approach: one portrait image + 4 mouth-shape overlays (closed/narrow/mid/
wide), swapped at video framerate according to the TTS viseme_track from
tts.py. This is the "portrait image + viseme lip-sync driven by the TTS
stream" the spec names as sufficient.

assets/avatar/ is expected to contain:
  base.png            - portrait, mouth region will be overlaid
  mouth_closed.png, mouth_narrow.png, mouth_mid.png, mouth_wide.png
  (transparent PNGs, same crop box, positioned via MOUTH_BOX below)
If assets are missing, generate_placeholder_assets() draws simple flat-shape
placeholders so the pipeline still runs end to end without hunting for art.
"""
from pathlib import Path

ASSET_DIR = Path("assets/avatar")
MOUTH_BOX = (180, 340, 340, 420)  # (left, top, right, bottom) — tune to your portrait


def generate_placeholder_assets():
    """Draws a simple placeholder head + 4 mouth shapes so `python -m
    src.realtime.avatar` produces a runnable demo even before you drop in a
    real portrait. Replace assets/avatar/*.png with a real photo/illustration
    for the actual submission — placeholders will look exactly like
    placeholders on camera."""
    from PIL import Image, ImageDraw

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    W, H = 512, 512

    base = Image.new("RGBA", (W, H), (235, 230, 220, 255))
    d = ImageDraw.Draw(base)
    d.ellipse((96, 60, 416, 420), fill=(222, 184, 152, 255))       # face
    d.ellipse((180, 180, 220, 210), fill=(60, 40, 30, 255))        # left eye
    d.ellipse((292, 180, 332, 210), fill=(60, 40, 30, 255))        # right eye
    base.save(ASSET_DIR / "base.png")

    shapes = {
        "mouth_closed.png": [(200, 360, 312, 372)],
        "mouth_narrow.png": [(210, 355, 302, 385)],
        "mouth_mid.png":    [(195, 350, 317, 400)],
        "mouth_wide.png":   [(180, 340, 332, 415)],
    }
    for filename, ellipses in shapes.items():
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for box in ellipses:
            ld.ellipse(box, fill=(120, 40, 40, 255))
        layer.save(ASSET_DIR / filename)


def _ensure_assets():
    required = ["base.png", "mouth_closed.png", "mouth_narrow.png", "mouth_mid.png", "mouth_wide.png"]
    if not all((ASSET_DIR / f).exists() for f in required):
        generate_placeholder_assets()


def render_frame(mouth_shape: str):
    """Composites the current mouth overlay onto the base portrait. Returns
    a PIL Image (RGB) ready to be pushed as one video frame to the
    transport's outgoing video track."""
    from PIL import Image

    _ensure_assets()
    base = Image.open(ASSET_DIR / "base.png").convert("RGBA")
    mouth = Image.open(ASSET_DIR / f"mouth_{mouth_shape}.png").convert("RGBA")
    composited = Image.alpha_composite(base, mouth)
    return composited.convert("RGB")


def frames_for_viseme_track(viseme_track: list[dict], fps: int = 15):
    """Expands the coarse viseme_track (one entry per ~60ms window, see
    tts.py) into a per-video-frame shape sequence at `fps`, so the
    transport can push a steady frame rate regardless of the TTS chunking
    granularity. Yields (t_ms, mouth_shape) pairs."""
    if not viseme_track:
        yield (0, "closed")
        return
    frame_interval_ms = 1000 / fps
    total_ms = viseme_track[-1]["t_ms"] + 60
    t = 0
    vi = 0
    while t < total_ms:
        while vi + 1 < len(viseme_track) and viseme_track[vi + 1]["t_ms"] <= t:
            vi += 1
        yield (t, viseme_track[vi]["shape"])
        t += frame_interval_ms


if __name__ == "__main__":
    _ensure_assets()
    print(f"Placeholder avatar assets written to {ASSET_DIR}/ — swap these for a real portrait.")
