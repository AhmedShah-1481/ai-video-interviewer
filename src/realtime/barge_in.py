"""
barge-in: candidate cuts in -> agent stops instantly

Requirement #2. This module is deliberately separate from turn_manager so
it can be unit-tested with a synthetic PCM stream (silence vs. speech
frames) without spinning up a real call — the viva may ask to "show the
code that stops the agent when interrupted", and the answer is this file
plus the check in turn_manager.speak_and_listen's playback loop.

Uses WebRTC VAD (Voice Activity Detection) — the same technique real-time
voice agents use, not amplitude-thresholding, because raw amplitude alone
false-triggers on background noise/breath. webrtcvad is a small C-extension
wrapper (pip install webrtcvad) with no network dependency.
"""
import collections
from src.config import SETTINGS


class BargeInMonitor:
    """
    Feed it 20/30ms PCM16 mono frames from the candidate's live mic track
    while the agent is speaking. `triggered` flips True as soon as enough
    consecutive frames look like real speech (not a cough, not noise) —
    that's the signal turn_manager polls every playback chunk to decide
    "stop talking right now".
    """

    def __init__(self, sample_rate: int = 16000, aggressiveness: int = 2,
                 frame_ms: int = 30, trigger_frames: int = 3):
        import webrtcvad
        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = int(sample_rate * frame_ms / 1000) * 2  # 16-bit mono
        self._recent = collections.deque(maxlen=trigger_frames)
        self.trigger_frames = trigger_frames
        self.triggered = False
        self.enabled = SETTINGS.barge_in_enabled

    def reset(self):
        self.triggered = False
        self._recent.clear()

    def feed(self, pcm_frame: bytes) -> bool:
        """Call once per incoming audio frame while the agent's TTS is
        playing. Returns True the instant barge-in should fire."""
        if not self.enabled or self.triggered:
            return self.triggered
        if len(pcm_frame) != self.frame_bytes:
            return self.triggered  # malformed frame, ignore rather than crash mid-call
        is_speech = self.vad.is_speech(pcm_frame, self.sample_rate)
        self._recent.append(is_speech)
        if len(self._recent) == self.trigger_frames and all(self._recent):
            self.triggered = True
        return self.triggered
