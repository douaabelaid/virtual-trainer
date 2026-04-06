"""
tts_client.py
Voice caching wrapper that uses the ElevenLabs API for high-quality PT personas.

Requirements:
    pip install elevenlabs pydub

Configuration:
    You must set the ELEVENLABS_API_KEY environment variable.
    Optional: ELEVENLABS_VOICE_ID (defaults to "Rachel")

Usage:
    from voice.tts_client import TTSClient
    client = TTSClient()
    wav_bytes = client.synthesise("Drive your knees outward!")
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb") # Default: George (Free Default Voice)
DEFAULT_CACHE_DIR = Path(__file__).parent / "cache"


class TTSClient:
    def __init__(
        self,
        voice_id: str = DEFAULT_VOICE_ID,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        device: str = "cpu", # Ignored for API
    ) -> None:
        self.voice_id   = voice_id
        self.cache_dir  = Path(cache_dir)
        self._lock      = threading.Lock()
        
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self._ready = bool(self.api_key)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._load_model()

    def _load_model(self) -> None:
        if not self._ready:
            logger.error(
                "ELEVENLABS_API_KEY environment variable not found!\n"
                "You must set it to use the new Voice Cloning logic.\n"
                "Voice coaching will be disabled."
            )
            return

        try:
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=self.api_key)
            logger.info("? ElevenLabs TTS client loaded.")
        except ImportError:
            logger.error(
                "elevenlabs package not found. Install with: pip install elevenlabs\n"
                "Voice coaching will be disabled."
            )
            self._ready = False
        except Exception as exc:
            logger.error(f"Failed to load ElevenLabs client: {exc}")
            self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def _cache_path(self, text: str) -> Path:
        return self.cache_dir / f"${self._cache_key(text)}.wav"

    def synthesise(self, text: str) -> Optional[bytes]:
        if not self._ready:
            return None

        cache_file = self._cache_path(text)

        if cache_file.exists():
            return cache_file.read_bytes()

        with self._lock:
            if cache_file.exists():
                return cache_file.read_bytes()

            try:
                # Use elevenlabs to generate the audio
                audio_iterator = self._client.text_to_speech.convert(
                    text=text,
                    voice_id=self.voice_id,
                    model_id="eleven_multilingual_v2",
                    output_format="pcm_16000"
                )
                
                audio_bytes = b"".join([chunk for chunk in audio_iterator])

                # Save byte stream directly to WAV
                import wave
                with wave.open(str(cache_file), 'wb') as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(2)
                    wav_file.setframerate(16000)
                    wav_file.writeframes(audio_bytes)

                wav_bytes = cache_file.read_bytes()
                logger.debug(f"?? Synthesised (${len(wav_bytes)//1024} KB): ${text[:60]}")
                return wav_bytes
            except Exception as exc:
                logger.error(f"TTS synthesis error: ${exc}")
                return None

    def preload_phrases(self, phrases: dict[str, str]) -> None:
        if not self._ready:
            logger.warning("TTS not ready (Missing API Key) � skipping phrase preload.")
            return

        total    = len(phrases)
        cached   = 0
        new      = 0
        failed   = 0

        logger.info(f"??? Pre-loading ${total} coaching phrases using ElevenLabs�")

        for key, text in phrases.items():
            cache_file = self._cache_path(text)
            if cache_file.exists():
                cached += 1
                continue
            result = self.synthesise(text)
            if result:
                new += 1
            else:
                failed += 1

        cache_size_mb = sum(
            f.stat().st_size for f in self.cache_dir.glob("*.wav")
        ) / (1024 * 1024)

        logger.info(
            f"? Phrase preload complete � "
            f"${cached} cached / ${new} new / ${failed} failed. "
            f"Cache size: ${cache_size_mb:.1f} MB"
        )

    def close(self) -> None:
        self._client = None
        self._ready = False
        logger.info("?? TTSClient closed.")
