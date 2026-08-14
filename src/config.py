"""
Central config. Everything reads keys from env vars — never hardcode a key.
Copy .env.example to .env and fill in real values before running anything.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # --- LLM brain (used for parsing, question planning, scoring) ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")  # "groq" | "anthropic"
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    # --- GitHub grounding ---
    github_token: str = os.getenv("GITHUB_TOKEN", "")  # optional, raises rate limit 60->5000/hr

    # --- Realtime call ---
    # "livekit" = LiveKit Cloud + LiveKit Agents transport (recommended
    #   stack). "daily" = legacy Daily.co transport, kept for reference/
    #   Windows-install-pain avoidance is exactly why this project moved off
    #   it. "console" = text-mode dev double, see
    #   src/realtime/console_transport.py — lets you exercise the whole
    #   graph (barge-in simulated, avatar frames written to disk) without a
    #   live call, for local development and for evals/. NOT a substitute
    #   for the real recording requirement #1.
    realtime_mode: str = os.getenv("REALTIME_MODE", "livekit")
    daily_api_key: str = os.getenv("DAILY_API_KEY", "")

    livekit_url: str = os.getenv("LIVEKIT_URL", "")
    livekit_api_key: str = os.getenv("LIVEKIT_API_KEY", "")
    livekit_api_secret: str = os.getenv("LIVEKIT_API_SECRET", "")
    livekit_rtc_debug: bool = os.getenv("LIVEKIT_RTC_DEBUG", "false").lower() == "true"
    livekit_connect_timeout_s: float = float(os.getenv("LIVEKIT_CONNECT_TIMEOUT_S", "15"))
    livekit_single_peer_connection: bool = os.getenv(
        "LIVEKIT_SINGLE_PEER_CONNECTION", "true"
    ).lower() == "true"
    livekit_auto_subscribe: bool = os.getenv("LIVEKIT_AUTO_SUBSCRIBE", "true").lower() == "true"
    livekit_ice_transport: str = os.getenv("LIVEKIT_ICE_TRANSPORT", "all").lower()
    livekit_candidate_wait_timeout_s: float = float(
        os.getenv("LIVEKIT_CANDIDATE_WAIT_TIMEOUT_S", "300")
    )

    tts_provider: str = os.getenv("TTS_PROVIDER", "edge-tts")  # "edge-tts" (free, no key) or "elevenlabs"
    elevenlabs_api_key: str = os.getenv("ELEVENLABS_API_KEY", "")

    # --- AI face ---
    # "simli" = real lip-synced avatar via Simli's session API (recommended
    #   stack, needs SIMLI_API_KEY + a trial that hasn't expired).
    # "2d"    = local viseme-swap portrait renderer (src/realtime/avatar.py)
    #   — zero external dependency, the spec's fallback column, earns full
    #   marks on its own. Falls back to this automatically if Simli errors.
    avatar_provider: str = os.getenv("AVATAR_PROVIDER", "simli")
    simli_api_key: str = os.getenv("SIMLI_API_KEY", "")
    simli_face_id: str = os.getenv("SIMLI_FACE_ID", "")

    # --- Checkpointer ---
    sqlite_path: str = os.getenv("SQLITE_PATH", "output/checkpoints.sqlite")

    # --- Behaviour knobs (touched during viva live-change requests) ---
    max_follow_up_probes: int = int(os.getenv("MAX_FOLLOW_UP_PROBES", "2"))
    barge_in_enabled: bool = os.getenv("BARGE_IN_ENABLED", "true").lower() == "true"

    # --- Turn-taking timing ---
    candidate_silence_timeout_s: float = float(os.getenv("CANDIDATE_SILENCE_TIMEOUT_S", "15"))  # "15 seconds of silence" per viva sample Q
    max_answer_duration_s: float = float(os.getenv("MAX_ANSWER_DURATION_S", "120"))


SETTINGS = Settings()
