"""
Speech-to-text for the candidate's mic track.

Groq Whisper is the fallback-column choice (free tier, fast, no local GPU
needed) — `groq_model` for STT is separate from the text-LLM model, both
just happen to share one API key/client library.
"""
import io
from src.config import SETTINGS


def transcribe(pcm_wav_bytes: bytes) -> str:
    """Takes a WAV byte blob (mono 16k PCM16, produced by the transport's
    audio buffer once VAD/barge_in decides the candidate has stopped
    talking) and returns the transcribed text."""
    if not pcm_wav_bytes:
        return ""
    from groq import Groq  # pip install groq

    client = Groq(api_key=SETTINGS.groq_api_key)
    resp = client.audio.transcriptions.create(
        file=("answer.wav", io.BytesIO(pcm_wav_bytes)),
        model="whisper-large-v3-turbo",
        response_format="text",
        language="en",
    )
    # SDK returns either a plain string or an object with .text depending on
    # response_format/version — normalize both.
    return resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
