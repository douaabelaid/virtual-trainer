"""
audio_streamer.py
Picks the highest-priority feedback flag, synthesises audio via Coqui TTS,
and streams it to the mobile client as two consecutive WebSocket frames:

  Frame 1 (text / JSON):
    {"type":"audio","format":"wav","code":"KNEE_CAVE","severity":"warning","text":"..."}

  Frame 2 (binary):
    <raw WAV bytes>

Usage:
    streamer = AudioStreamer(tts_client)
    await streamer.stream_coaching(ws, feedback_flags, exercise="squat")
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Priority order: errors first, then warnings, then positive info
_SEVERITY_PRIORITY = {"error": 0, "warning": 1, "info": 2}

# Info codes that are worth speaking (positive reinforcement)
_SPEAKABLE_INFO = {"DEPTH_OK", "GOOD_FORM"}


class AudioStreamer:
    """
    Picks the top-priority feedback flag per frame and streams coaching audio.

    Parameters
    ----------
    tts_client : TTSClient
        Initialised TTSClient instance.
    cooldown_s : float
        Minimum seconds between repeating the same feedback code.
    """

    def __init__(self, tts_client, cooldown_s: float = 2.0) -> None:
        self._tts          = tts_client
        self._cooldown_s   = cooldown_s
        self._last_sent: dict[str, float] = {}   # code → last-sent timestamp

    # ── Public API ───────────────────────────────────────────────────────────

    async def stream_coaching(
        self,
        ws,
        feedback_flags: list,
        exercise: str = "squat",
    ) -> None:
        """
        Select the highest-priority actionable flag and stream its audio.
        No-op if TTS is not ready, no flags, or cooldown not elapsed.
        """
        if not self._tts or not self._tts.ready:
            return
        if not feedback_flags:
            return

        flag = self._pick_flag(feedback_flags)
        if flag is None:
            return

        code     = flag.code
        severity = flag.severity.value

        # ── Cooldown check ────────────────────────────────────────────────
        now  = time.monotonic()
        last = self._last_sent.get(code, 0.0)
        if now - last < self._cooldown_s:
            return

        # ── Get coaching text ─────────────────────────────────────────────
        try:
            from logic.feedback_mapper import get_coaching_message
            text = get_coaching_message(code)
        except Exception as exc:
            logger.warning(f"feedback_mapper error: {exc}")
            text = flag.message  # fallback to raw message

        # ── Synthesise in thread (non-blocking) ───────────────────────────
        loop      = asyncio.get_event_loop()
        wav_bytes = await loop.run_in_executor(None, self._tts.synthesise, text)

        if not wav_bytes:
            logger.warning(f"No audio for code={code}")
            return

        # ── Send to client ────────────────────────────────────────────────
        await stream_audio_bytes(
            ws,
            wav_bytes,
            metadata={
                "type":     "audio",
                "format":   "wav",
                "code":     code,
                "severity": severity,
                "text":     text,
                "exercise": exercise,
            },
        )

        self._last_sent[code] = time.monotonic()
        logger.debug(f"🔊 Audio sent: [{severity.upper()}] {code}")

    # ── Flag selection ───────────────────────────────────────────────────────

    def _pick_flag(self, flags: list) -> Optional[object]:
        """
        Returns the single highest-priority speakable flag, or None.
        Priority: error < warning < info (lower number = higher priority).
        Info flags are only included if their code is in _SPEAKABLE_INFO.
        """
        candidates = []
        for f in flags:
            sev = f.severity.value
            if sev in ("error", "warning"):
                candidates.append(f)
            elif sev == "info" and f.code in _SPEAKABLE_INFO:
                candidates.append(f)

        if not candidates:
            return None

        candidates.sort(key=lambda f: _SEVERITY_PRIORITY.get(f.severity.value, 99))
        return candidates[0]

    def reset_cooldowns(self) -> None:
        """Call when the exercise is reset / a new set starts."""
        self._last_sent.clear()


# ── Standalone helper ────────────────────────────────────────────────────────

async def stream_audio_bytes(ws, wav_bytes: bytes, metadata: dict) -> None:
    """
    Send metadata JSON frame then binary WAV frame.
    Safe to call; catches send errors silently.
    """
    try:
        await ws.send(json.dumps(metadata, separators=(",", ":")))
        await ws.send(wav_bytes)
    except Exception as exc:
        logger.debug(f"Audio send error (client may have disconnected): {exc}")