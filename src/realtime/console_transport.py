"""
Text-mode dev double for CallTransport. Exists so the graph, follow-up caps,
barge-in *logic*, and scoring pipeline can all be run and eval'd locally
without daily-python, a mic, or network access — this is how evals/run_evals.py
and CI-style checks exercise src/nodes/* without a live call.

This is explicitly NOT how requirement #1 (live video call) gets satisfied —
that needs REALTIME_MODE=daily and a real recording. SUBMISSION.md must not
claim console mode as the graded run.

Barge-in simulation: typing while the agent's text is "playing" isn't
possible in a blocking terminal read, so barge-in is simulated by a
scripted marker — prefixing a typed answer with "!" means "interrupt
immediately", which lets follow_up/verify/recovery routing and the
transcript's `interrupted` flag be tested deterministically.
"""
import sys
import time
from src.realtime.avatar import render_frame, frames_for_viseme_track
from src.config import SETTINGS


class ConsoleTransport:
    def __init__(self):
        self._frame_dir = None

    def create_room(self, room_name: str) -> str:
        return f"console://{room_name}"

    def send_audio(self, pcm16_bytes: bytes, sample_rate: int = 16000):
        pass  # no-op: console mode prints text instead of playing audio

    def send_video_frame(self, rgb_frame):
        pass  # avatar frames are rendered by turn_manager directly to output/.avatar_frames/ for inspection

    def read_incoming_audio_frame(self, timeout_s: float = 0.5):
        return None  # console mode has no real mic stream; turn_manager bypasses barge-in polling in this mode

    def stop_outgoing_audio(self):
        pass


def speak_console(text: str, viseme_track: list[dict] | None = None, save_frames: bool = False) -> None:
    print(f"\n🤖 AGENT: {text}")
    if save_frames and viseme_track:
        from pathlib import Path
        out_dir = Path("output/.avatar_frames")
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, (t_ms, shape) in enumerate(frames_for_viseme_track(viseme_track)):
            if i > 30:
                break  # sample only, not the full clip — this is a dev sanity check, not the recording
            render_frame(shape).save(out_dir / f"frame_{i:03d}_{shape}.png")


def listen_console() -> dict:
    """Blocks on stdin. A leading '!' simulates a barge-in (see module
    docstring); the rest of the line is the candidate's answer text."""
    raw = input("🎤 CANDIDATE (prefix ! to simulate barge-in): ").strip()
    interrupted = raw.startswith("!")
    text = raw[1:].strip() if interrupted else raw
    return {"answer_text": text, "was_interrupted": interrupted}
