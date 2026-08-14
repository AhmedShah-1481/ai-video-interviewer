"""Network-free regression tests for the LiveKit transport state machine."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from livekit import rtc

from src.config import Settings
from src.realtime.livekit_transport import (
    LiveKitDisconnectedError,
    LiveKitTransport,
    LiveKitTransportError,
    _resample_pcm16,
)
from src.realtime import transport as transport_module


def _settings(**overrides) -> Settings:
    values = {
        "livekit_url": "wss://example.livekit.cloud",
        "livekit_api_key": "key",
        "livekit_api_secret": "secret",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def transport():
    value = LiveKitTransport(settings=_settings())
    yield value
    value._room = None
    value.close()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("all", rtc.IceTransportType.TRANSPORT_ALL),
        ("relay", rtc.IceTransportType.TRANSPORT_RELAY),
        ("nohost", rtc.IceTransportType.TRANSPORT_NOHOST),
    ],
)
def test_room_options_apply_rtc_controls(mode, expected):
    value = LiveKitTransport(
        settings=_settings(
            livekit_ice_transport=mode,
            livekit_auto_subscribe=False,
            livekit_single_peer_connection=True,
        )
    )
    try:
        options = value._room_options(rtc)
        assert options.auto_subscribe is False
        assert options.single_peer_connection is True
        assert options.rtc_config.ice_transport_type == expected
    finally:
        value.close()


def test_invalid_ice_mode_is_rejected(transport):
    transport.settings = _settings(livekit_ice_transport="invalid")
    with pytest.raises(LiveKitTransportError, match="ICE_TRANSPORT"):
        transport._validate_settings()


def test_existing_candidate_is_checked_against_connection_state(transport):
    transport._room = SimpleNamespace(remote_participants={"candidate": object()})
    with pytest.raises(LiveKitDisconnectedError, match="disconnected"):
        transport.wait_for_candidate(timeout_s=0.01)


def test_candidate_disconnect_interrupts_audio_read(transport):
    participant = SimpleNamespace(identity="candidate")
    transport._connected.set()
    transport._on_participant_connected(participant)
    transport._room = SimpleNamespace(remote_participants={})
    transport._on_participant_disconnected(participant)

    with pytest.raises(LiveKitDisconnectedError, match="candidate disconnected"):
        transport.read_incoming_audio_frame(timeout_s=0.01)


def test_audio_subscription_failure_is_not_treated_as_silence(transport):
    publication = SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO)
    participant = SimpleNamespace(
        identity="candidate", track_publications={"TR_audio": publication}
    )
    transport._connected.set()
    transport._on_track_subscription_failed(participant, "TR_audio", "ICE failed")

    with pytest.raises(LiveKitTransportError, match="audio subscription failed"):
        transport.read_incoming_audio_frame(timeout_s=0.01)


def test_video_subscription_failure_does_not_abort_audio(transport):
    publication = SimpleNamespace(kind=rtc.TrackKind.KIND_VIDEO)
    participant = SimpleNamespace(
        identity="candidate", track_publications={"TR_video": publication}
    )
    transport._connected.set()
    transport._on_track_subscription_failed(participant, "TR_video", "codec error")

    assert transport.read_incoming_audio_frame(timeout_s=0.01) is None


def test_pcm_resampling_preserves_duration():
    source = (np.sin(np.linspace(0, 4 * np.pi, 800)) * 10_000).astype(np.int16)
    result = np.frombuffer(_resample_pcm16(source.tobytes(), 8_000, 16_000), np.int16)
    assert len(result) == 1_600
    assert np.max(np.abs(result)) > 9_000


def test_close_transport_clears_singleton(monkeypatch):
    closed = []
    dummy = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(transport_module, "_transport_singleton", dummy)

    transport_module.close_transport()

    assert closed == [True]
    assert transport_module._transport_singleton is None