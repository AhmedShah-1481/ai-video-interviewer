"""LiveKit Cloud transport with explicit RTC negotiation and cleanup."""
from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading
from concurrent.futures import Future
from typing import Any, Callable, Coroutine

import numpy as np

from src.config import SETTINGS, Settings
from src.realtime.transport import CallTransport

logger = logging.getLogger(__name__)
_AUDIO_STOP = object()


class LiveKitTransportError(RuntimeError):
    """A user-actionable LiveKit setup or media error."""


class LiveKitDisconnectedError(LiveKitTransportError):
    """The room or candidate disconnected during an active operation."""


class LiveKitTransport(CallTransport):
    """Synchronous facade over LiveKit's asyncio-native Python RTC SDK."""

    AUDIO_RATE = 16_000
    VIDEO_WIDTH = 512
    VIDEO_HEIGHT = 512

    def __init__(
        self,
        settings: Settings = SETTINGS,
        room_factory: Callable[[], Any] | None = None,
        api_factory: Callable[..., Any] | None = None,
    ):
        self.settings = settings
        self._room_factory = room_factory
        self._api_factory = api_factory

        self._room = None
        self._api = None
        self._room_name = ""
        self.candidate_join_token = ""
        self._audio_source = None
        self._video_source = None
        self._audio_track = None
        self._video_track = None
        self._streams: set[Any] = set()
        self._stream_tasks: set[asyncio.Task] = set()
        self._handlers: list[tuple[str, Callable]] = []

        self._incoming_audio: queue.Queue[bytes | object] = queue.Queue(maxsize=300)
        self._participant_signal = threading.Event()
        self._candidate_present = threading.Event()
        self._candidate_ever_joined = False
        self._connected = threading.Event()
        self._closed = threading.Event()
        self._closing = False
        self._disconnect_reason = ""
        self._media_error = ""
        self._close_lock = threading.Lock()

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, name="livekit-rtc", daemon=True
        )
        self._thread.start()

    @property
    def is_connected(self) -> bool:
        return self._connected.is_set() and not self._closed.is_set()

    @property
    def room_name(self) -> str:
        return self._room_name

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        self._loop.close()

    def _call(self, coro: Coroutine, timeout: float = 30):
        if self._closed.is_set() or not self._thread.is_alive():
            coro.close()
            raise LiveKitTransportError("LiveKit transport is closed")
        future: Future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except BaseException:
            future.cancel()
            raise

    def create_room(self, room_name: str) -> str:
        """Create and join a room, then publish the agent media tracks."""
        if self.is_connected:
            if room_name == self._room_name:
                return f"{self.settings.livekit_url} (room={self._room_name})"
            raise LiveKitTransportError("Transport is already connected to another room")
        self._validate_settings()
        self._room_name = re.sub(r"[^a-zA-Z0-9_-]", "-", room_name)[:100]
        try:
            self._call(
                self._create_and_connect(),
                timeout=self.settings.livekit_connect_timeout_s + 20,
            )
        except Exception as exc:
            self.close()
            if isinstance(exc, LiveKitTransportError):
                raise
            raise LiveKitTransportError(
                f"Could not connect to LiveKit room '{self._room_name}': {exc}"
            ) from exc
        return f"{self.settings.livekit_url} (room={self._room_name})"

    def _validate_settings(self) -> None:
        missing = [
            key
            for key, value in (
                ("LIVEKIT_URL", self.settings.livekit_url),
                ("LIVEKIT_API_KEY", self.settings.livekit_api_key),
                ("LIVEKIT_API_SECRET", self.settings.livekit_api_secret),
            )
            if not value
        ]
        if missing:
            raise LiveKitTransportError(
                "Missing LiveKit configuration: " + ", ".join(missing)
            )
        if self.settings.livekit_ice_transport not in {"all", "relay", "nohost"}:
            raise LiveKitTransportError(
                "LIVEKIT_ICE_TRANSPORT must be one of: all, relay, nohost"
            )

    async def _create_and_connect(self) -> None:
        from livekit import api, rtc

        api_factory = self._api_factory or api.LiveKitAPI
        self._api = api_factory(
            self.settings.livekit_url,
            self.settings.livekit_api_key,
            self.settings.livekit_api_secret,
        )
        await self._api.room.create_room(api.CreateRoomRequest(name=self._room_name))
        agent_token = self._make_token(api, "firstround-agent", "FirstRound AI Interviewer")
        self.candidate_join_token = self._make_token(api, "candidate", "Candidate")

        self._room = (self._room_factory or rtc.Room)()
        self._register_room_handlers(rtc)
        options = self._room_options(rtc)
        if self.settings.livekit_rtc_debug:
            logging.getLogger("livekit").setLevel(logging.DEBUG)
            logging.getLogger("livekit.rtc").setLevel(logging.DEBUG)
        logger.info(
            "LiveKit SDK=%s protocol=%s",
            getattr(rtc, "__version__", "unknown"),
            self.settings.livekit_url.split(":", 1)[0],
        )
        logger.info(
            "Connecting to LiveKit room=%s single_pc=%s auto_subscribe=%s ice=%s",
            self._room_name,
            self.settings.livekit_single_peer_connection,
            self.settings.livekit_auto_subscribe,
            self.settings.livekit_ice_transport,
        )
        await asyncio.wait_for(
            self._room.connect(self.settings.livekit_url, agent_token, options=options),
            timeout=self.settings.livekit_connect_timeout_s + 2,
        )
        self._connected.set()

        self._audio_source = rtc.AudioSource(self.AUDIO_RATE, 1, queue_size_ms=300)
        self._video_source = rtc.VideoSource(self.VIDEO_WIDTH, self.VIDEO_HEIGHT)
        self._audio_track = rtc.LocalAudioTrack.create_audio_track(
            "agent-microphone", self._audio_source
        )
        self._video_track = rtc.LocalVideoTrack.create_video_track(
            "agent-camera", self._video_source
        )
        await self._room.local_participant.publish_track(
            self._audio_track,
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
        )
        await self._room.local_participant.publish_track(
            self._video_track,
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA),
        )
        for participant in self._room.remote_participants.values():
            self._on_participant_connected(participant)
        logger.info("LiveKit room connected and local media published")

    def _room_options(self, rtc):
        ice_types = {
            "relay": rtc.IceTransportType.TRANSPORT_RELAY,
            "nohost": rtc.IceTransportType.TRANSPORT_NOHOST,
            "all": rtc.IceTransportType.TRANSPORT_ALL,
        }
        return rtc.RoomOptions(
            auto_subscribe=self.settings.livekit_auto_subscribe,
            single_peer_connection=self.settings.livekit_single_peer_connection,
            connect_timeout=self.settings.livekit_connect_timeout_s,
            rtc_config=rtc.RtcConfiguration(
                ice_transport_type=ice_types[self.settings.livekit_ice_transport]
            ),
        )

    def _make_token(self, api, identity: str, name: str) -> str:
        return (
            api.AccessToken(
                self.settings.livekit_api_key, self.settings.livekit_api_secret
            )
            .with_identity(identity)
            .with_name(name)
            .with_grants(api.VideoGrants(room_join=True, room=self._room_name))
            .to_jwt()
        )

    def _on(self, event: str, callback: Callable) -> None:
        self._room.on(event, callback)
        self._handlers.append((event, callback))

    def _register_room_handlers(self, rtc) -> None:
        self._on("connected", lambda: logger.info("LiveKit state: connected"))
        self._on(
            "connection_state_changed",
            lambda state: logger.info(
                "LiveKit connection state: %s", rtc.ConnectionState.Name(state)
            ),
        )
        self._on("reconnecting", lambda: logger.warning("LiveKit state: reconnecting"))
        self._on("reconnected", lambda: logger.info("LiveKit state: reconnected"))
        self._on("participant_connected", self._on_participant_connected)
        self._on("participant_disconnected", self._on_participant_disconnected)
        self._on("track_published", self._on_track_published)
        self._on("track_subscribed", self._on_track_subscribed)
        self._on(
            "track_subscription_failed",
            self._on_track_subscription_failed,
        )

        def disconnected(reason) -> None:
            self._disconnect_reason = rtc.DisconnectReason.Name(reason)
            self._connected.clear()
            self._participant_signal.set()
            self._put_audio(_AUDIO_STOP)
            level = logging.INFO if self._closing else logging.ERROR
            logger.log(level, "LiveKit state: disconnected (%s)", self._disconnect_reason)

        self._on("disconnected", disconnected)

    def _on_participant_connected(self, participant) -> None:
        logger.info("LiveKit participant joined: %s", participant.identity)
        self._candidate_ever_joined = True
        self._candidate_present.set()
        self._participant_signal.set()
        if not self.settings.livekit_auto_subscribe:
            for publication in participant.track_publications.values():
                self._subscribe_if_audio(publication)

    def _on_participant_disconnected(self, participant) -> None:
        logger.info("LiveKit participant left: %s", participant.identity)
        room = self._room
        if room is not None and not room.remote_participants:
            self._candidate_present.clear()
            self._put_audio(_AUDIO_STOP)

    def _on_track_published(self, publication, participant) -> None:
        logger.info(
            "Remote track published: %s from %s", publication.name, participant.identity
        )
        if not self.settings.livekit_auto_subscribe:
            self._subscribe_if_audio(publication)

    @staticmethod
    def _subscribe_if_audio(publication) -> None:
        from livekit import rtc

        if publication.kind == rtc.TrackKind.KIND_AUDIO and not publication.subscribed:
            publication.set_subscribed(True)

    def _on_track_subscribed(self, track, publication, participant) -> None:
        from livekit import rtc

        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        logger.info(
            "Remote audio subscribed: %s from %s", publication.name, participant.identity
        )
        stream = rtc.AudioStream(
            track,
            sample_rate=self.AUDIO_RATE,
            num_channels=1,
            frame_size_ms=30,
        )
        self._streams.add(stream)
        task = self._loop.create_task(self._consume_audio(stream))
        self._stream_tasks.add(task)
        task.add_done_callback(self._stream_tasks.discard)

    def _on_track_subscription_failed(self, participant, sid, error) -> None:
        publication = participant.track_publications.get(sid)
        if publication is not None:
            from livekit import rtc

            if publication.kind != rtc.TrackKind.KIND_AUDIO:
                logger.warning(
                    "Non-audio track subscription failed for %s (track %s): %s",
                    participant.identity,
                    sid,
                    error,
                )
                return
        self._media_error = (
            f"Remote audio subscription failed for {participant.identity} "
            f"(track {sid}): {error}"
        )
        logger.error(self._media_error)
        self._put_audio(_AUDIO_STOP)

    async def _consume_audio(self, stream) -> None:
        try:
            async for event in stream:
                self._put_audio(bytes(event.frame.data))
        except asyncio.CancelledError:
            raise
        except Exception:
            if not self._closing:
                self._media_error = "The candidate audio stream failed"
                logger.exception("Remote LiveKit audio stream failed")
                self._put_audio(_AUDIO_STOP)
        finally:
            self._streams.discard(stream)
            await stream.aclose()

    def _put_audio(self, item: bytes | object) -> None:
        try:
            self._incoming_audio.put_nowait(item)
        except queue.Full:
            try:
                self._incoming_audio.get_nowait()
            except queue.Empty:
                pass
            self._incoming_audio.put_nowait(item)

    def wait_for_candidate(self, timeout_s: float | None = None) -> None:
        """Wait for a remote participant; abort immediately if RTC disconnects."""
        timeout_s = timeout_s or self.settings.livekit_candidate_wait_timeout_s
        self._participant_signal.clear()
        if self._room is not None and self._room.remote_participants:
            self._raise_if_unavailable()
            return
        logger.info("Waiting up to %.1fs for a candidate", timeout_s)
        if not self._participant_signal.wait(timeout_s):
            raise LiveKitTransportError(
                f"No candidate joined LiveKit room '{self._room_name}' within {timeout_s:.0f}s"
            )
        self._raise_if_unavailable()
        if self._room is None or not self._room.remote_participants:
            raise LiveKitTransportError("Candidate wait ended without a remote participant")

    def _raise_if_unavailable(self) -> None:
        if self._media_error:
            raise LiveKitTransportError(self._media_error)
        if not self._connected.is_set():
            detail = f" ({self._disconnect_reason})" if self._disconnect_reason else ""
            raise LiveKitDisconnectedError(f"LiveKit room is disconnected{detail}")
        if self._candidate_ever_joined and not self._candidate_present.is_set():
            raise LiveKitDisconnectedError("The candidate disconnected from the LiveKit room")

    def send_audio(self, pcm16_bytes: bytes, sample_rate: int = AUDIO_RATE) -> None:
        self._raise_if_unavailable()
        if sample_rate != self.AUDIO_RATE:
            pcm16_bytes = _resample_pcm16(pcm16_bytes, sample_rate, self.AUDIO_RATE)
        self._call(self._capture_audio(pcm16_bytes), timeout=5)

    async def _capture_audio(self, pcm16_bytes: bytes) -> None:
        from livekit import rtc

        await self._audio_source.capture_frame(
            rtc.AudioFrame(
                data=pcm16_bytes,
                sample_rate=self.AUDIO_RATE,
                num_channels=1,
                samples_per_channel=len(pcm16_bytes) // 2,
            )
        )

    def send_video_frame(self, rgb_frame) -> None:
        self._raise_if_unavailable()
        self._loop.call_soon_threadsafe(self._capture_video, rgb_frame)

    def _capture_video(self, rgb_frame) -> None:
        from PIL import Image
        from livekit import rtc

        if hasattr(rgb_frame, "convert"):
            image = rgb_frame.convert("RGB")
        else:
            image = Image.fromarray(np.asarray(rgb_frame).astype(np.uint8)).convert("RGB")
        image = image.resize((self.VIDEO_WIDTH, self.VIDEO_HEIGHT))
        self._video_source.capture_frame(
            rtc.VideoFrame(
                self.VIDEO_WIDTH,
                self.VIDEO_HEIGHT,
                rtc.VideoBufferType.RGB24,
                np.ascontiguousarray(image).tobytes(),
            )
        )

    def read_incoming_audio_frame(self, timeout_s: float = 0.5) -> bytes | None:
        try:
            item = self._incoming_audio.get(timeout=timeout_s)
        except queue.Empty:
            self._raise_if_unavailable()
            return None
        if item is _AUDIO_STOP:
            self._raise_if_unavailable()
            return None
        return item  # type: ignore[return-value]

    def stop_outgoing_audio(self) -> None:
        """Flush already queued TTS audio so barge-in is immediately audible."""
        if self._audio_source is not None and self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._audio_source.clear_queue)

    async def _close_async(self) -> None:
        self._closing = True
        room = self._room
        if room is not None:
            for event, callback in self._handlers:
                room.off(event, callback)
            self._handlers.clear()
        for task in list(self._stream_tasks):
            task.cancel()
        if self._stream_tasks:
            await asyncio.gather(*self._stream_tasks, return_exceptions=True)
        if room is not None:
            await room.disconnect()
        if self._audio_source is not None:
            await self._audio_source.aclose()
        if self._video_source is not None:
            await self._video_source.aclose()
        if self._api is not None:
            try:
                if self._room_name:
                    from livekit import api

                    await self._api.room.delete_room(
                        api.DeleteRoomRequest(room=self._room_name)
                    )
            except Exception:
                logger.warning("Could not delete LiveKit room during cleanup", exc_info=True)
            await self._api.aclose()

    def close(self) -> None:
        """Disconnect and dispose native resources. Safe to call repeatedly."""
        with self._close_lock:
            if self._closed.is_set():
                return
            try:
                if self._thread.is_alive():
                    self._call(self._close_async(), timeout=15)
            except Exception:
                logger.warning("LiveKit cleanup did not complete cleanly", exc_info=True)
            finally:
                self._connected.clear()
                self._closed.set()
                if self._thread.is_alive():
                    self._loop.call_soon_threadsafe(self._loop.stop)
                    self._thread.join(timeout=5)


def _resample_pcm16(data: bytes, src_rate: int, dst_rate: int) -> bytes:
    samples = np.frombuffer(data, dtype=np.int16)
    if not len(samples) or src_rate == dst_rate:
        return data
    old = np.linspace(0, 1, len(samples), endpoint=False)
    new = np.linspace(0, 1, int(len(samples) * dst_rate / src_rate), endpoint=False)
    return np.interp(new, old, samples).astype(np.int16).tobytes()