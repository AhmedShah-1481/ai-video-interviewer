"""
speak_and_listen() — the single function every interview node calls
(see src/nodes/interview_common.py). This is where requirements #1
(live call), #2 (barge-in), and the avatar face actually meet: synthesize
speech, stream it + lip-synced video frames to the transport, watch the
candidate's incoming audio for barge-in on every chunk, stop instantly if
it fires, then listen for their answer until real silence.

Three code paths, chosen by SETTINGS.realtime_mode:
  - "livekit": the recommended stack — LiveKit transport, Simli lip-synced
    avatar (auto-degrades to the local 2D avatar on any Simli error),
    VAD-based barge-in against the live mic frame stream, Groq STT on the
    captured answer. This is what requirement #1's raw recording proves
    happened if you're running the recommended stack.
  - "daily": legacy path, kept for reference — TTS -> Daily audio/video
    tracks with the local 2D viseme avatar only.
  - "console": text-mode dev double (src/realtime/console_transport.py),
    used by evals/ and local development so node/graph logic can be
    exercised without a live call.
"""
import asyncio
import time
import wave
import io

from src.config import SETTINGS
from src.realtime.transport import get_transport
from src.realtime.barge_in import BargeInMonitor
from src.realtime.avatar import render_frame, frames_for_viseme_track
from src.realtime import tts as tts_module
from src.realtime import stt as stt_module

AUDIO_CHUNK_MS = 200  # how often we poll for barge-in while "speaking"


def speak_and_listen(text: str, node_name: str = "", expect_answer: bool = True) -> dict:
    if SETTINGS.realtime_mode == "console":
        return _speak_and_listen_console(text, expect_answer)
    if SETTINGS.realtime_mode == "livekit":
        return asyncio.run(_speak_and_listen_livekit(text, expect_answer))
    return _speak_and_listen_daily(text, expect_answer)


# --------------------------------------------------------------------------- #
# console mode — dev/test double, see console_transport.py
# --------------------------------------------------------------------------- #
def _speak_and_listen_console(text: str, expect_answer: bool) -> dict:
    from src.realtime.console_transport import speak_console, listen_console

    try:
        synth = tts_module.synthesize(text)
        viseme_track = synth.get("viseme_track", [])
    except Exception:
        # console mode is meant to run without any TTS deps installed too —
        # fall back to text-only if edge-tts/pydub/ffmpeg aren't present.
        viseme_track = []
    speak_console(text, viseme_track=viseme_track, save_frames=False)

    if not expect_answer:
        return {"answer_text": "", "was_interrupted": False, "agent_text_spoken": text}

    answer = listen_console()
    agent_text_spoken = text
    if answer["was_interrupted"]:
        # simulate truncation: agent only "got out" the first clause
        agent_text_spoken = text.split(".")[0] + "..." if "." in text else text[: max(1, len(text) // 2)]
    return {
        "answer_text": answer["answer_text"],
        "was_interrupted": answer["was_interrupted"],
        "agent_text_spoken": agent_text_spoken,
    }


# --------------------------------------------------------------------------- #
# daily mode — the real live call
# --------------------------------------------------------------------------- #
def _speak_and_listen_daily(text: str, expect_answer: bool) -> dict:
    transport = get_transport()
    synth = tts_module.synthesize(text)
    pcm_bytes, sample_rate = _load_pcm(synth["audio_path"])

    monitor = BargeInMonitor(sample_rate=16000)
    was_interrupted = False
    spoken_ms = 0
    frame_bytes = monitor.frame_bytes
    total_ms = synth["duration_ms"]

    # stream audio + lip-synced video in lockstep, polling for barge-in
    # every AUDIO_CHUNK_MS — this loop IS "the code that stops the agent
    # when interrupted" the viva asks to see.
    bytes_per_ms = int(sample_rate * 2 / 1000)
    chunk_bytes = bytes_per_ms * AUDIO_CHUNK_MS
    pos = 0
    while pos < len(pcm_bytes):
        chunk = pcm_bytes[pos: pos + chunk_bytes]
        transport.send_audio(chunk, sample_rate=sample_rate)

        shape = _shape_at(synth["viseme_track"], spoken_ms)
        transport.send_video_frame(render_frame(shape))

        incoming = transport.read_incoming_audio_frame(timeout_s=AUDIO_CHUNK_MS / 1000)
        if incoming and len(incoming) == frame_bytes and monitor.feed(incoming):
            was_interrupted = True
            transport.stop_outgoing_audio()
            break

        pos += chunk_bytes
        spoken_ms += AUDIO_CHUNK_MS

    agent_text_spoken = text if not was_interrupted else _truncate_to_fraction(text, spoken_ms / max(total_ms, 1))

    if not expect_answer:
        return {"answer_text": "", "was_interrupted": was_interrupted, "agent_text_spoken": agent_text_spoken}

    answer_text = _listen_until_silence(transport)
    return {"answer_text": answer_text, "was_interrupted": was_interrupted, "agent_text_spoken": agent_text_spoken}


# --------------------------------------------------------------------------- #
# livekit mode — the recommended stack: LiveKit transport + Simli avatar
# --------------------------------------------------------------------------- #
async def _speak_and_listen_livekit(text: str, expect_answer: bool) -> dict:
    """Same barge-in-aware playback loop as _speak_and_listen_daily, but
    async: audio goes out through LiveKitTransport (transport.py's sync
    methods are pushed onto a thread with asyncio.to_thread so they don't
    block this event loop), and video frames come from get_avatar_session()
    — Simli if configured, the local 2D renderer otherwise or on Simli
    failure. The barge-in monitor, silence-based listening, and STT call
    are untouched from the Daily path; only where audio/video actually go
    is different."""
    from src.realtime.simli_avatar import get_avatar_session

    transport = get_transport()
    synth = await tts_module.synthesize_async(text)
    pcm_bytes, sample_rate = _load_pcm(synth["audio_path"])
    total_ms = synth["duration_ms"]

    monitor = BargeInMonitor(sample_rate=16000)
    was_interrupted = False
    spoken_ms = 0
    bytes_per_ms = int(sample_rate * 2 / 1000)
    chunk_bytes = bytes_per_ms * AUDIO_CHUNK_MS

    async with get_avatar_session() as avatar:
        pos = 0
        while pos < len(pcm_bytes):
            chunk = pcm_bytes[pos: pos + chunk_bytes]
            shape = _shape_at(synth["viseme_track"], spoken_ms)

            frame, _sent = await asyncio.gather(
                avatar.push_audio_get_frame(chunk, viseme_shape=shape),
                asyncio.to_thread(transport.send_audio, chunk, sample_rate),
            )
            await asyncio.to_thread(transport.send_video_frame, frame)

            incoming = await asyncio.to_thread(
                transport.read_incoming_audio_frame, AUDIO_CHUNK_MS / 1000
            )
            if incoming and len(incoming) == monitor.frame_bytes and monitor.feed(incoming):
                was_interrupted = True
                await asyncio.to_thread(transport.stop_outgoing_audio)
                break

            pos += chunk_bytes
            spoken_ms += AUDIO_CHUNK_MS

    agent_text_spoken = text if not was_interrupted else _truncate_to_fraction(text, spoken_ms / max(total_ms, 1))

    if not expect_answer:
        return {"answer_text": "", "was_interrupted": was_interrupted, "agent_text_spoken": agent_text_spoken}

    answer_text = await asyncio.to_thread(_listen_until_silence, transport)
    return {"answer_text": answer_text, "was_interrupted": was_interrupted, "agent_text_spoken": agent_text_spoken}


def _listen_until_silence(transport) -> str:
    """Accumulates candidate mic frames until SETTINGS.candidate_silence_timeout_s
    of continuous silence (via the same VAD used for barge-in) or the hard
    max_answer_duration_s cap, then runs STT on the whole buffer."""
    from src.realtime.barge_in import BargeInMonitor

    vad_check = BargeInMonitor(sample_rate=16000, trigger_frames=1)
    frames = []
    silence_ms = 0.0
    elapsed_s = 0.0
    frame_s = vad_check.frame_ms / 1000

    while silence_ms / 1000 < SETTINGS.candidate_silence_timeout_s and elapsed_s < SETTINGS.max_answer_duration_s:
        frame = transport.read_incoming_audio_frame(timeout_s=frame_s)
        elapsed_s += frame_s
        if frame is None:
            silence_ms += vad_check.frame_ms
            continue
        frames.append(frame)
        if len(frame) == vad_check.frame_bytes and vad_check.vad.is_speech(frame, 16000):
            silence_ms = 0.0
        else:
            silence_ms += vad_check.frame_ms

    if not frames:
        return ""
    wav_bytes = _frames_to_wav(frames, sample_rate=16000)
    return stt_module.transcribe(wav_bytes).strip()


def _frames_to_wav(frames: list[bytes], sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"".join(frames))
    return buf.getvalue()


def _load_pcm(audio_path: str) -> tuple[bytes, int]:
    from pydub import AudioSegment

    audio = AudioSegment.from_file(audio_path).set_channels(1).set_frame_rate(16000)
    return audio.raw_data, audio.frame_rate


def _shape_at(viseme_track: list[dict], t_ms: int) -> str:
    if not viseme_track:
        return "closed"
    shape = viseme_track[0]["shape"]
    for v in viseme_track:
        if v["t_ms"] > t_ms:
            break
        shape = v["shape"]
    return shape


def _truncate_to_fraction(text: str, fraction: float) -> str:
    words = text.split()
    cut = max(1, int(len(words) * max(0.0, min(1.0, fraction))))
    return " ".join(words[:cut]) + ("..." if cut < len(words) else "")