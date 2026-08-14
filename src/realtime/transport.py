"""
Transport layer: gets audio/video in and out of a real live video call.

Fallback stack per the spec: "Plain WebRTC, or Daily.co free tier" — this
implements Daily.co, since its REST + Python client gives a room URL a
candidate can join from a browser with zero client-side install, which
matters more under a 24h clock than a hand-rolled WebRTC signalling server.

CallTransport is the interface turn_manager.py codes against, so swapping
in LiveKit (the "recommended" column) later means writing one new class,
not touching any node/graph code.
"""
from abc import ABC, abstractmethod
from src.config import SETTINGS


class CallTransport(ABC):
    @abstractmethod
    def create_room(self, room_name: str) -> str:
        """Creates (or reuses) a call room, returns the joinable URL to send the candidate."""

    @abstractmethod
    def send_audio(self, pcm16_bytes: bytes, sample_rate: int = 16000):
        """Pushes one chunk of synthesized speech audio to the outgoing track."""

    @abstractmethod
    def send_video_frame(self, rgb_frame):
        """Pushes one avatar video frame (PIL Image or ndarray) to the outgoing track."""

    @abstractmethod
    def read_incoming_audio_frame(self, timeout_s: float = 0.5) -> bytes | None:
        """Blocks up to timeout_s for the next 30ms PCM16 frame from the
        candidate's mic. Returns None on timeout (used by both barge-in
        polling and end-of-speech silence detection)."""

    @abstractmethod
    def stop_outgoing_audio(self):
        """Hard-stops audio playback immediately — the actual mechanism
        behind 'agent stops instantly' on barge-in."""

    def close(self) -> None:
        """Release transport resources. Stateless transports may do nothing."""


class DailyTransport(CallTransport):
    """
    Uses daily-python (pip install daily-python) for the media I/O and the
    Daily REST API for room creation. Requires DAILY_API_KEY (free tier).

    NOTE: this class exercises real network + native audio APIs and was
    written against daily-python's documented interface but could not be
    exercised end-to-end in the build sandbox (no network/mic access there)
    — see ARCHITECTURE.md "Known limitations". Treat first real run as a
    debugging session, budgeted for in the 24h plan's hours 1-3.
    """

    def __init__(self):
        import requests
        self._requests = requests
        self._client = None  # lazily constructed in create_room, needs the event loop

    def create_room(self, room_name: str) -> str:
        resp = self._requests.post(
            "https://api.daily.co/v1/rooms",
            headers={"Authorization": f"Bearer {SETTINGS.daily_api_key}"},
            json={"name": room_name, "properties": {"enable_screenshare": False,
                                                      "start_video_off": False,
                                                      "start_audio_off": False,
                                                      "exp": None}},
            timeout=15,
        )
        resp.raise_for_status()
        room_url = resp.json()["url"]

        from daily import CallClient, Daily  # pip install daily-python

        Daily.init()
        self._client = CallClient()
        self._client.join(room_url)
        return room_url

    def send_audio(self, pcm16_bytes: bytes, sample_rate: int = 16000):
        self._client.send_audio_frame(pcm16_bytes, sample_rate=sample_rate, channels=1)

    def send_video_frame(self, rgb_frame):
        import numpy as np
        arr = np.asarray(rgb_frame)
        self._client.send_video_frame(arr)

    def read_incoming_audio_frame(self, timeout_s: float = 0.5) -> bytes | None:
        return self._client.receive_audio_frame(timeout=timeout_s)

    def stop_outgoing_audio(self):
        self._client.clear_audio_buffer()


_transport_singleton: CallTransport | None = None


def get_transport() -> CallTransport:
    """Single seam the rest of the codebase uses to get a transport, so
    REALTIME_MODE=console (dev/testing, see console_transport.py) vs.
    livekit (recommended) vs. daily (legacy) is one env var, not a code
    change — this was the whole point of CallTransport being an ABC.

    Cached as a module-level singleton: turn_manager.py calls this once
    per speak_and_listen() turn (many times per interview), and it must
    keep returning the SAME connected instance — a fresh DailyTransport/
    LiveKitTransport has an unconnected room and None media sources until
    create_room() runs. main.py calls create_room() exactly once, early,
    before any turn happens; every later get_transport() call here just
    returns that same already-connected object."""
    global _transport_singleton
    if _transport_singleton is not None:
        return _transport_singleton

    if SETTINGS.realtime_mode == "console":
        from src.realtime.console_transport import ConsoleTransport
        _transport_singleton = ConsoleTransport()
    elif SETTINGS.realtime_mode == "livekit":
        from src.realtime.livekit_transport import LiveKitTransport
        _transport_singleton = LiveKitTransport()
    else:
        _transport_singleton = DailyTransport()
    return _transport_singleton


def close_transport() -> None:
    """Close and clear the process-wide transport singleton."""
    global _transport_singleton
    transport = _transport_singleton
    _transport_singleton = None
    if transport is not None:
        transport.close()