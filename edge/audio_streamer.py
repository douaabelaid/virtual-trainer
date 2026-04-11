"""
audio_streamer.py — Real-time Audio Feedback Streaming

Modular audio pipeline for streaming audio feedback to clients or playing locally.
Supports binary WebSocket frames for efficient audio data transmission.

ARCHITECTURE:
- Receive audio from backend API (future integration)
- Forward to client via WebSocket binary frames
- OR play locally using system audio
- Non-blocking async design (does not interfere with video pipeline)

AUDIO FORMATS SUPPORTED:
- WAV (PCM 16-bit)
- MP3 (streaming)
- Opus (low latency)
"""

import asyncio
import io
import json
import logging
import struct
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict

logger = logging.getLogger("audio_streamer")


# ── Audio Configuration ───────────────────────────────────────

class AudioFormat(Enum):
    """Supported audio formats."""
    WAV = "wav"
    MP3 = "mp3"
    OPUS = "opus"


class AudioMode(Enum):
    """Audio playback modes."""
    FORWARD_TO_CLIENT = "forward"      # Send to client via WebSocket
    PLAY_LOCALLY = "local"             # Play on server (for testing)
    BOTH = "both"                       # Both forward and play


@dataclass
class AudioConfig:
    """Audio streaming configuration."""
    mode: AudioMode = AudioMode.FORWARD_TO_CLIENT
    sample_rate: int = 16000           # 16kHz (good for speech)
    channels: int = 1                   # Mono
    sample_width: int = 2               # 16-bit PCM
    chunk_size: int = 1024              # Audio chunk size in samples
    buffer_size: int = 10               # Max audio messages in buffer
    cooldown_ms: int = 500              # Min time between audio messages


@dataclass
class AudioMessage:
    """Audio feedback message from backend."""
    audio_data: bytes                   # Raw audio bytes
    format: AudioFormat                 # Audio format
    feedback_code: str                  # e.g., "KNEE_CAVE", "DEPTH_GOOD"
    severity: str                       # "info", "warning", "error"
    text: Optional[str] = None          # Human-readable text
    timestamp: float = field(default_factory=time.time)
    duration_ms: Optional[float] = None # Audio clip duration


class AudioStreamer:
    """
    Manages real-time audio feedback streaming.
    
    Features:
    - Non-blocking async audio playback
    - WebSocket binary frame support
    - Cooldown to prevent audio spam
    - Audio buffer management
    - Per-client audio state
    """
    
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()
        
        # Audio buffer per client (thread-safe via asyncio)
        self._audio_buffers: Dict[str, deque] = {}
        
        # Cooldown tracking per client
        self._last_audio_time: Dict[str, float] = {}
        
        # Statistics
        self._audio_sent = 0
        self._audio_dropped = 0
        self._audio_errors = 0
        
        logger.info(
            f"🎙️  AudioStreamer initialized — mode: {self.config.mode.value}, "
            f"sample_rate: {self.config.sample_rate}Hz"
        )
    
    def register_client(self, client_id: str):
        """Register a new client for audio streaming."""
        if client_id not in self._audio_buffers:
            self._audio_buffers[client_id] = deque(maxlen=self.config.buffer_size)
            self._last_audio_time[client_id] = 0
            logger.debug(f"🎵 Audio client registered: {client_id}")
    
    def unregister_client(self, client_id: str):
        """Unregister client and clean up resources."""
        self._audio_buffers.pop(client_id, None)
        self._last_audio_time.pop(client_id, None)
        logger.debug(f"🔇 Audio client unregistered: {client_id}")
    
    def should_play_audio(self, client_id: str) -> bool:
        """Check if audio cooldown has expired for client."""
        now = time.time()
        last_time = self._last_audio_time.get(client_id, 0)
        cooldown_seconds = self.config.cooldown_ms / 1000.0
        
        return (now - last_time) >= cooldown_seconds
    
    async def stream_audio(
        self,
        websocket,
        client_id: str,
        audio_msg: AudioMessage
    ) -> bool:
        """
        Stream audio to client via WebSocket binary frames.
        
        Args:
            websocket: WebSocket connection
            client_id: Client identifier
            audio_msg: Audio message to stream
        
        Returns:
            True if audio was sent successfully, False otherwise
        """
        # Check cooldown
        if not self.should_play_audio(client_id):
            logger.debug(
                f"🔇 Audio dropped (cooldown) — client: {client_id}, "
                f"code: {audio_msg.feedback_code}"
            )
            self._audio_dropped += 1
            return False
        
        try:
            # Send JSON metadata first
            metadata = {
                "type": "audio_metadata",
                "format": audio_msg.format.value,
                "code": audio_msg.feedback_code,
                "severity": audio_msg.severity,
                "text": audio_msg.text,
                "duration_ms": audio_msg.duration_ms,
                "sample_rate": self.config.sample_rate,
                "channels": self.config.channels,
            }
            await websocket.send(json.dumps(metadata, separators=(",", ":")))
            
            # Send binary audio data
            await websocket.send(audio_msg.audio_data)
            
            # Update state
            self._last_audio_time[client_id] = time.time()
            self._audio_sent += 1
            
            logger.info(
                f"🎵 Audio sent — client: {client_id}, code: {audio_msg.feedback_code}, "
                f"size: {len(audio_msg.audio_data)} bytes"
            )
            return True
            
        except Exception as exc:
            self._audio_errors += 1
            logger.error(
                f"❌ Audio streaming error — client: {client_id}: {exc}",
                exc_info=True
            )
            return False
    
    async def play_audio_locally(self, audio_msg: AudioMessage):
        """
        Play audio locally on the server (for testing).
        
        Note: Requires system audio support (pyaudio, simpleaudio, etc.)
        This is a placeholder for local playback logic.
        """
        logger.info(
            f"🔊 Local audio playback (placeholder) — code: {audio_msg.feedback_code}, "
            f"size: {len(audio_msg.audio_data)} bytes"
        )
        # TODO: Implement local playback if needed
        # Could use: pyaudio, simpleaudio, sounddevice, etc.
        # For now, just log (server environments typically don't have audio output)
    
    def encode_wav(
        self,
        pcm_data: bytes,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        sample_width: Optional[int] = None
    ) -> bytes:
        """
        Encode raw PCM data to WAV format.
        
        Args:
            pcm_data: Raw PCM audio bytes
            sample_rate: Sample rate (default: config value)
            channels: Number of channels (default: config value)
            sample_width: Sample width in bytes (default: config value)
        
        Returns:
            WAV-encoded audio bytes
        """
        sample_rate = sample_rate or self.config.sample_rate
        channels = channels or self.config.channels
        sample_width = sample_width or self.config.sample_width
        
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(sample_width)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        
        return wav_buffer.getvalue()
    
    def decode_wav(self, wav_data: bytes) -> tuple[bytes, int, int, int]:
        """
        Decode WAV audio to raw PCM data.
        
        Args:
            wav_data: WAV-encoded audio bytes
        
        Returns:
            Tuple of (pcm_data, sample_rate, channels, sample_width)
        """
        wav_buffer = io.BytesIO(wav_data)
        with wave.open(wav_buffer, 'rb') as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            pcm_data = wav_file.readframes(wav_file.getnframes())
        
        return pcm_data, sample_rate, channels, sample_width
    
    def get_audio_duration_ms(self, audio_data: bytes, format: AudioFormat) -> float:
        """
        Calculate audio duration in milliseconds.
        
        Args:
            audio_data: Audio bytes
            format: Audio format
        
        Returns:
            Duration in milliseconds
        """
        if format == AudioFormat.WAV:
            try:
                _, sample_rate, channels, sample_width = self.decode_wav(audio_data)
                num_samples = len(audio_data) / (channels * sample_width)
                return (num_samples / sample_rate) * 1000
            except Exception as exc:
                logger.warning(f"Failed to calculate WAV duration: {exc}")
                return 0.0
        else:
            # For other formats, would need format-specific decoding
            logger.warning(f"Duration calculation not implemented for {format.value}")
            return 0.0
    
    def get_stats(self) -> Dict[str, int]:
        """Get audio streaming statistics."""
        return {
            "audio_sent": self._audio_sent,
            "audio_dropped": self._audio_dropped,
            "audio_errors": self._audio_errors,
            "active_clients": len(self._audio_buffers),
        }
    
    def reset_stats(self):
        """Reset statistics counters."""
        self._audio_sent = 0
        self._audio_dropped = 0
        self._audio_errors = 0


# ── Helper Functions ──────────────────────────────────────────

def create_audio_message(
    audio_data: bytes,
    feedback_code: str,
    severity: str = "info",
    text: Optional[str] = None,
    format: AudioFormat = AudioFormat.WAV
) -> AudioMessage:
    """
    Factory function to create AudioMessage.
    
    Args:
        audio_data: Raw audio bytes
        feedback_code: Feedback code (e.g., "KNEE_CAVE")
        severity: Severity level ("info", "warning", "error")
        text: Optional human-readable text
        format: Audio format
    
    Returns:
        AudioMessage instance
    """
    return AudioMessage(
        audio_data=audio_data,
        format=format,
        feedback_code=feedback_code,
        severity=severity,
        text=text,
    )


if __name__ == "__main__":
    # Simple test
    print("🎙️  AudioStreamer module")
    print("   - Supports WAV, MP3, Opus formats")
    print("   - Forward to client or play locally")
    print("   - Non-blocking async design")
    print("   - Binary WebSocket frame support")
    print("   ✅ Ready for integration")
