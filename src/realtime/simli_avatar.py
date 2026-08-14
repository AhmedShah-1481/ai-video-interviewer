"""
AI face, real-avatar version — swaps the hand-drawn 2D viseme avatar
(avatar.py) for Simli's real-time lip-synced avatar API, per the LiveKit +
Simli stack. Mirrors the same seam pattern transport.py already uses for
CallTransport: one small interface (AvatarSession), two implementations,
one factory function — so turn_manager.py never branches on "which avatar
provider" itself.

How Simli's session model works: open a WebSocket session against a chosen
face_id, stream raw PCM16 audio chunks in, get back video frames already
lip-synced to that audio.

Requires: pip install websockets
Free tier: Simli issues trial credits (minutes of avatar session time) on
signup. Check your dashboard's remaining balance before the graded
8-minute recording — CLAUDE.md's stack table flags exactly this risk.
SimliAvatarSession falls back to the local 2D avatar automatically on any
error (dead trial, network issue, bad key), so a depleted trial degrades
the face for that turn rather than crashing the interview.

NOTE, same honest flag the rest of realtime/ carries: written against
Simli's documented WebSocket session API but not exercised against a live
Simli account in this build environment (no network access here). Verify
in Phase 4 of PHASE_PLAN.md — and re-verify right before the real
recording, since trial credits can run out between your last test and the
actual take.
"""
import io
import json
from abc import ABC, abstractmethod

from src.config import SETTINGS


class AvatarSession(ABC):
    """Opened for the lifetime of one speak_and_listen() call. Each
    push_audio_get_frame() call feeds one outgoing audio chunk and returns
    the video frame to display for it — always returns a real PIL Image,
    never None, so turn_manager's loop doesn't need provider-specific
    branching."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    @abstractmethod
    async def push_audio_get_frame(self, pcm16_bytes: bytes, viseme_shape: str = "closed"):
        ...


class Local2DAvatarSession(AvatarSession):
    """The spec's fallback column — zero external dependency, full marks
    on its own. Also what SimliAvatarSession degrades to mid-turn on error."""

    async def push_audio_get_frame(self, pcm16_bytes: bytes, viseme_shape: str = "closed"):
        from src.realtime.avatar import render_frame

        return render_frame(viseme_shape)


class SimliAvatarSession(AvatarSession):
    def __init__(self):
        self._ws = None
        self._degraded = False  # flips True on first failure, sticks for the rest of the turn
        self._local = Local2DAvatarSession()

    async def __aenter__(self):
        import websockets

        try:
            self._ws = await websockets.connect(
                "wss://api.simli.ai/startAudioToVideoSession", max_size=None, open_timeout=10
            )
            await self._ws.send(json.dumps({
                "apiKey": SETTINGS.simli_api_key,
                "faceId": SETTINGS.simli_face_id,
                "syncAudio": True,
            }))
        except Exception as exc:  # noqa: BLE001 — any connect failure degrades, doesn't crash the call
            print(f"[SimliAvatarSession] could not open session, using 2D avatar for this turn: {exc!r}")
            self._degraded = True
        return self

    async def __aexit__(self, *exc):
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 — closing a dead socket shouldn't raise into the caller
                pass

    async def push_audio_get_frame(self, pcm16_bytes: bytes, viseme_shape: str = "closed"):
        from PIL import Image

        if self._degraded:
            return await self._local.push_audio_get_frame(pcm16_bytes, viseme_shape)

        try:
            await self._ws.send(pcm16_bytes)
            message = await self._ws.recv()
            if isinstance(message, (bytes, bytearray)):
                return Image.open(io.BytesIO(message)).convert("RGB")
            # a text/control message with no frame attached this tick —
            # repeat the last known shape via the local renderer rather
            # than send nothing
            return await self._local.push_audio_get_frame(pcm16_bytes, viseme_shape)
        except Exception as exc:  # noqa: BLE001 — mid-call drop degrades, doesn't crash the turn
            print(f"[SimliAvatarSession] dropped mid-turn, using 2D avatar for the rest: {exc!r}")
            self._degraded = True
            return await self._local.push_audio_get_frame(pcm16_bytes, viseme_shape)


def get_avatar_session() -> AvatarSession:
    """Single seam the rest of the codebase uses to get an avatar session
    — SETTINGS.avatar_provider is one env var, not a code change, exactly
    like transport.get_transport()."""
    if SETTINGS.avatar_provider == "simli" and SETTINGS.simli_api_key:
        return SimliAvatarSession()
    return Local2DAvatarSession()
