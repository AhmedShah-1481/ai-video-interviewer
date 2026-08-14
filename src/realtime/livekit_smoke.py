"""Graph-independent LiveKit signaling and bidirectional media smoke test."""
from __future__ import annotations

import argparse
import logging
import time
import uuid
from dataclasses import replace

import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw

load_dotenv()

from src.config import SETTINGS
from src.realtime.livekit_transport import LiveKitTransport, LiveKitTransportError


def _send_test_media(transport: LiveKitTransport) -> None:
    image = Image.new("RGB", (512, 512), (20, 24, 31))
    draw = ImageDraw.Draw(image)
    draw.rectangle((48, 48, 464, 464), outline=(43, 196, 138), width=12)
    draw.text((135, 238), "FirstRound RTC", fill=(240, 244, 248))
    transport.send_video_frame(image)

    sample_rate = transport.AUDIO_RATE
    frame_samples = sample_rate // 50
    samples = np.arange(int(sample_rate * 0.6), dtype=np.float64)
    tone = (np.sin(2 * np.pi * 440 * samples / sample_rate) * 5_000).astype(np.int16)
    for offset in range(0, len(tone), frame_samples):
        transport.send_audio(tone[offset : offset + frame_samples].tobytes(), sample_rate)
        time.sleep(0.02)


def _listen_for_candidate(
    transport: LiveKitTransport, duration_s: float, minimum_rms: int
) -> tuple[int, int]:
    deadline = time.monotonic() + duration_s
    frame_count = 0
    peak_rms = 0
    while time.monotonic() < deadline:
        frame = transport.read_incoming_audio_frame(
            timeout_s=min(0.5, max(0.01, deadline - time.monotonic()))
        )
        if not frame:
            continue
        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float64)
        if not len(samples):
            continue
        frame_count += 1
        peak_rms = max(peak_rms, int(np.sqrt(np.mean(samples * samples))))
        if peak_rms >= minimum_rms:
            break
    return frame_count, peak_rms


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test LiveKit without LangGraph, LLM, STT, TTS, or avatar services."
    )
    parser.add_argument("--room", default=None, help="Room name; unique by default")
    parser.add_argument("--wait", type=float, default=120, help="Candidate join timeout")
    parser.add_argument("--listen", type=float, default=15, help="Inbound audio test duration")
    parser.add_argument("--minimum-rms", type=int, default=100, help="Speech energy threshold")
    parser.add_argument(
        "--ice", choices=["all", "relay", "nohost"], default=None,
        help="Override LIVEKIT_ICE_TRANSPORT",
    )
    parser.add_argument(
        "--auto-subscribe", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--single-peer-connection", action=argparse.BooleanOptionalAction, default=None
    )
    parser.add_argument(
        "--connect-only", action="store_true",
        help="Test agent connection/publication without waiting for a candidate",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose SDK logging")
    return parser


def run(args: argparse.Namespace) -> int:
    overrides = {}
    if args.ice is not None:
        overrides["livekit_ice_transport"] = args.ice
    if args.auto_subscribe is not None:
        overrides["livekit_auto_subscribe"] = args.auto_subscribe
    if args.single_peer_connection is not None:
        overrides["livekit_single_peer_connection"] = args.single_peer_connection
    if args.debug:
        overrides["livekit_rtc_debug"] = True
    settings = replace(SETTINGS, **overrides)

    logging.basicConfig(
        level=logging.DEBUG if settings.livekit_rtc_debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    room_name = args.room or f"firstround-smoke-{uuid.uuid4().hex[:8]}"
    transport = LiveKitTransport(settings=settings)
    try:
        print(
            "LiveKit smoke configuration: "
            f"room={room_name} ice={settings.livekit_ice_transport} "
            f"single_pc={settings.livekit_single_peer_connection} "
            f"auto_subscribe={settings.livekit_auto_subscribe}"
        )
        print(f"Connected: {transport.create_room(room_name)}")
        print(f"Candidate join token:\n{transport.candidate_join_token}\n")
        if args.connect_only:
            print("PASS: agent connected and published local audio/video tracks.")
            return 0

        print(
            "Join from a LiveKit-compatible client using LIVEKIT_URL and the token "
            "above. Enable the microphone and speak when prompted."
        )
        transport.wait_for_candidate(timeout_s=args.wait)
        print("Candidate joined. Sending a 440 Hz tone and a test video frame...")
        _send_test_media(transport)
        print(f"Speak now; listening for {args.listen:.1f}s...")
        frame_count, peak_rms = _listen_for_candidate(
            transport, args.listen, args.minimum_rms
        )
        if peak_rms < args.minimum_rms:
            print(
                "FAIL: candidate joined, but usable microphone audio was not received "
                f"(frames={frame_count}, peak_rms={peak_rms}, "
                f"required={args.minimum_rms})."
            )
            return 4
        print(
            "PASS: signaling, publication, candidate join, and inbound audio succeeded "
            f"(frames={frame_count}, peak_rms={peak_rms})."
        )
        return 0
    except LiveKitTransportError as exc:
        print(f"FAIL: {exc}")
        return 3
    except Exception as exc:
        logging.getLogger(__name__).exception("Unexpected smoke-test failure")
        print(f"FAIL: unexpected error: {exc}")
        return 5
    finally:
        transport.close()


def main() -> int:
    return run(_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())