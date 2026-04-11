"""
tts_client.py
Coqui TTS wrapper — synthesises text to WAV bytes, caches on disk.

Model (default): tts_models/en/ljspeech/tacotron2-DDC
Override via env var: TTS_MODEL=tts_models/en/ljspeech/glow-tts

Usage:
    from voice.tts_client import TTSClient
    client = TTSClient()
    wav_bytes = client.synthesise("Drive your knees outward.")
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import threading
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default fast CPU model — downloads ~100 MB on first run
DEFAULT_MODEL = os.getenv("TTS_MODEL", "tts_models/en/ljspeech/tacotron2-DDC")
DEFAULT_CACHE_DIR = Path(__file__).parent / "cache"


class TTSClient:
    """
    Thread-safe Coqui TTS client with disk-backed WAV cache.

    Parameters
    ----------
    model_name : str
        Coqui TTS model identifier.
    cache_dir  : Path | str
        Directory where synthesised WAV files are stored.
    device     : str
        "cpu" or "cuda" — passed to TTS model loader.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.cache_dir  = Path(cache_dir)
        self.device     = device
        self._lock      = threading.Lock()
        self._tts       = None          # lazy-loaded below
        self._ready     = False

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._load_model()

    # ── Model loading ────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        try:
            from TTS.api import TTS  # type: ignore
            logger.info(f"🔊 Loading TTS model: {self.model_name}  (device={self.device})")
            self._tts   = TTS(model_name=self.model_name, progress_bar=False)
            self._ready = True
            logger.info("✅ TTS model loaded.")
        except ImportError:
            logger.error(
                "TTS package not found. Install with: pip install TTS\n"
                "Voice coaching will be disabled."
            )
        except Exception as exc:
            logger.error(f"Failed to load TTS model: {exc}\nVoice coaching will be disabled.")

    @property
    def ready(self) -> bool:
        return self._ready

    # ── Synthesis ────────────────────────────────────────────────────────────

    @staticmethod
    def _cache_key(text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def _cache_path(self, text: str) -> Path:
        return self.cache_dir / f"{self._cache_key(text)}.wav"

    def synthesise(self, text: str) -> Optional[bytes]:
        """
        Synthesise *text* → raw WAV bytes.
        Returns None if TTS is not ready.
        Hits disk cache before invoking the model.
        """
        if not self._ready:
            return None

        cache_file = self._cache_path(text)

        # ── Cache hit ──────────────────────────────────────────────────────
        if cache_file.exists():
            return cache_file.read_bytes()

        # ── Cache miss — run model ─────────────────────────────────────────
        with self._lock:
            # Double-check after acquiring lock
            if cache_file.exists():
                return cache_file.read_bytes()

            try:
                # Coqui TTS writes to a file path; use a temp path then rename.
                tmp_path = cache_file.with_suffix(".tmp.wav")
                self._tts.tts_to_file(text=text, file_path=str(tmp_path))
                tmp_path.rename(cache_file)
                wav_bytes = cache_file.read_bytes()
                logger.debug(f"🔊 Synthesised ({len(wav_bytes)//1024} KB): {text[:60]}")
                return wav_bytes
            except Exception as exc:
                logger.error(f"TTS synthesis error: {exc}")
                return None

    # ── Pre-loading ──────────────────────────────────────────────────────────

    def preload_phrases(self, phrases: dict[str, str]) -> None:
        """
        Pre-synthesise all phrases in *phrases* dict at startup.
        Skips any that are already cached.
        phrases: {key: text_to_speak}
        """
        if not self._ready:
            logger.warning("TTS not ready — skipping phrase preload.")
            return

        total    = len(phrases)
        cached   = 0
        new      = 0
        failed   = 0

        logger.info(f"🎙️  Pre-loading {total} coaching phrases …")

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
            f"✅ Phrase preload complete — "
            f"{cached} cached / {new} new / {failed} failed. "
            f"Cache size: {cache_size_mb:.1f} MB"
        )

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._tts   = None
        self._ready = False
        logger.info("🔇 TTSClient closed.")


# ── Standalone test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    from voice.phrase_library import ALL_PHRASES

    client = TTSClient()
    if not client.ready:
        print("TTS not ready. Is the TTS package installed?")
        sys.exit(1)

    client.preload_phrases(ALL_PHRASES)
    print("\n--- Smoke test ---")
    wav = client.synthesise("Drive your knees outward.")
    print(f"Synthesised {len(wav)} bytes" if wav else "Synthesis failed")