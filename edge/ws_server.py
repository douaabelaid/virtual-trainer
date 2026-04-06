"""
ws_server.py — Phase 2 Architecture
WebSocket server for real-time pose landmark extraction + audio feedback streaming.

Accepts base64 JPEG frames from mobile clients, runs MediaPipe Pose detection,
and streams back clean landmark JSON data.

ARCHITECTURE:
- Video Pipeline: capture → detect → validate → send (unchanged)
- Audio Pipeline: receive → buffer → stream (non-blocking)
- Multi-user support with per-client isolation

──────────────────────────────────────────────────────────────
Mobile → Server (JSON)
──────────────────────────────────────────────────────────────
{ "type": "frame",
  "data": "<base64-encoded JPEG>",
  "client_id": "user123"         }   ← optional client identifier

{ "type": "ping" }

──────────────────────────────────────────────────────────────
Server → Mobile (JSON + Binary)
──────────────────────────────────────────────────────────────
// Video response (JSON)
{ "type":        "pose",
  "detected":    true,
  "landmarks":   [...],          ← 33 MediaPipe landmarks
  "fps":         14.9,
  "latency_ms":  17.4,
  "frame_idx":   38,
  "timestamp":   1649251234.567  }

// Audio metadata (JSON) followed by audio data (binary)
{ "type": "audio_metadata",
  "format": "wav",
  "code": "KNEE_CAVE",
  "severity": "warning",
  "text": "Keep knees aligned",
  "duration_ms": 1200 }
<binary WAV data>

{ "type": "pong" }
{ "type": "error", "message": "..." }
────────────────────────────────────────────────────────────────
"""

import asyncio
import base64
import json
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Dict, Optional

import numpy as np

import websockets
from websockets.asyncio.server import ServerConnection, serve
from websockets.http11 import Response
from websockets.datastructures import Headers

# ── Path setup ────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pose_detector import PoseDetector  # noqa: E402
from audio_streamer import AudioStreamer, AudioConfig, AudioMode, AudioMessage, AudioFormat, create_audio_message  # noqa: E402

# ── Structured logging ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ws_server")
logging.getLogger("websockets.server").setLevel(logging.WARNING)

# ── Config (all overridable via env vars) ─────────────────────────────────────
WS_HOST        = os.getenv("WS_HOST",              "0.0.0.0")
WS_PORT        = int(os.getenv("WS_PORT",          "8765"))
MP_COMPLEXITY  = int(os.getenv("MP_COMPLEXITY",    "1"))
MP_DETECT_CONF = float(os.getenv("MP_DETECT_CONF", "0.5"))
MP_TRACK_CONF  = float(os.getenv("MP_TRACK_CONF",  "0.5"))
TARGET_FPS     = int(os.getenv("TARGET_FPS",       "15"))
MAX_LATENCY_MS = int(os.getenv("MAX_LATENCY_MS",   "100"))

# Audio configuration
AUDIO_ENABLED  = os.getenv("AUDIO_ENABLED", "1") not in ("0", "false", "False")
_VOICE_ENABLED = AUDIO_ENABLED
AUDIO_MODE     = os.getenv("AUDIO_MODE", "forward")  # "forward", "local", "both"
TARGET_FPS     = int(os.getenv("TARGET_FPS",       "15"))
MAX_LATENCY_MS = int(os.getenv("MAX_LATENCY_MS",   "100"))

# ── Server state ──────────────────────────────────────────────
_clients: Dict[str, "ClientSession"] = {}
_start_time = time.time()
_audio_streamer: Optional[AudioStreamer] = None


# ── Client session tracking ───────────────────────────────────

@dataclass
class ClientSession:
    """Per-client session with isolated state and metrics."""
    
    client_id: str
    websocket: ServerConnection
    detector: PoseDetector
    connected_at: float = field(default_factory=time.time)
    
    # Performance metrics
    frames_received: int = 0
    frames_processed: int = 0
    frames_dropped: int = 0
    
    # Audio metrics
    audio_messages_sent: int = 0
    audio_messages_dropped: int = 0
    
    # Latency tracking for P95 calculation
    # MediaPipe inference latency (detection only)
    inference_latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    # End-to-end latency (capture → send)
    e2e_latency_samples: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # Warnings tracking
    high_latency_warnings: int = 0
    p95_warnings: int = 0
    
    def record_frame_received(self):
        """Record incoming frame."""
        self.frames_received += 1
    
    def record_frame_processed(self, inference_latency_ms: float, e2e_latency_ms: float):
        """Record successfully processed frame with latency metrics.
        
        Args:
            inference_latency_ms: MediaPipe detection time only
            e2e_latency_ms: End-to-end time (capture → send)
        """
        self.frames_processed += 1
        self.inference_latency_samples.append(inference_latency_ms)
        self.e2e_latency_samples.append(e2e_latency_ms)
        
        # Check thresholds and log warnings
        self._check_latency_thresholds(e2e_latency_ms)
    
    def record_frame_dropped(self):
        """Record dropped frame."""
        self.frames_dropped += 1
    
    def get_latency_stats(self) -> Dict[str, Dict[str, float]]:
        """Calculate latency statistics using numpy for accurate P95.
        
        Returns:
            Dictionary with 'inference' and 'e2e' latency stats
        """
        def compute_stats(samples_deque) -> Dict[str, float]:
            if not samples_deque:
                return {"avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0, "p99": 0.0}
            
            samples = np.array(list(samples_deque))
            return {
                "avg": float(np.mean(samples)),
                "min": float(np.min(samples)),
                "max": float(np.max(samples)),
                "p95": float(np.percentile(samples, 95)),
                "p99": float(np.percentile(samples, 99)),
            }
        
        return {
            "inference": compute_stats(self.inference_latency_samples),
            "e2e": compute_stats(self.e2e_latency_samples),
        }
    
    def _check_latency_thresholds(self, e2e_latency_ms: float):
        """Check latency thresholds and log warnings.
        
        Logs warnings if:
        - Any frame latency > 120ms
        - P95 latency > 80ms (checked every 20 frames)
        """
        # Check per-frame threshold
        if e2e_latency_ms > 120.0:
            self.high_latency_warnings += 1
            logger.warning(
                f"⚠️  HIGH LATENCY: {e2e_latency_ms:.1f}ms > 120ms",
                extra={
                    "event": "high_latency",
                    "client_id": self.client_id,
                    "e2e_latency_ms": round(e2e_latency_ms, 2),
                    "threshold_ms": 120,
                    "frames_processed": self.frames_processed,
                }
            )
        
        # Check P95 threshold every 20 frames (to avoid overhead)
        if self.frames_processed % 20 == 0 and len(self.e2e_latency_samples) >= 20:
            stats = self.get_latency_stats()
            p95 = stats["e2e"]["p95"]
            
            if p95 > 80.0:
                self.p95_warnings += 1
                logger.warning(
                    f"⚠️  P95 LATENCY ELEVATED: {p95:.1f}ms > 80ms",
                    extra={
                        "event": "p95_latency_high",
                        "client_id": self.client_id,
                        "p95_latency_ms": round(p95, 2),
                        "threshold_ms": 80,
                        "avg_latency_ms": round(stats["e2e"]["avg"], 2),
                        "frames_processed": self.frames_processed,
                    }
                )
    
    def log_stats(self):
        """Log session statistics (structured logging)."""
        uptime = time.time() - self.connected_at
        latency_stats = self.get_latency_stats()
        
        inference = latency_stats["inference"]
        e2e = latency_stats["e2e"]
        
        logger.info(
            f"📊 Session summary — {self.client_id}",
            extra={
                "event": "session_stats",
                "client_id": self.client_id,
                "uptime_s": int(uptime),
                "frames_received": self.frames_received,
                "frames_processed": self.frames_processed,
                "frames_dropped": self.frames_dropped,
                "drop_rate_pct": round(
                    100 * self.frames_dropped / self.frames_received
                    if self.frames_received > 0 else 0.0,
                    1
                ),
                # Inference latency (MediaPipe only)
                "inference_avg_ms": round(inference["avg"], 2),
                "inference_p95_ms": round(inference["p95"], 2),
                "inference_max_ms": round(inference["max"], 2),
                # End-to-end latency (full pipeline)
                "e2e_avg_ms": round(e2e["avg"], 2),
                "e2e_p95_ms": round(e2e["p95"], 2),
                "e2e_p99_ms": round(e2e["p99"], 2),
                "e2e_max_ms": round(e2e["max"], 2),
                # Warning counts
                "high_latency_warnings": self.high_latency_warnings,
                "p95_warnings": self.p95_warnings,
                # Audio stats
                "audio_sent": self.audio_messages_sent,
                "audio_dropped": self.audio_messages_dropped,
            }
        )


# ── HTTP health check handler ─────────────────────────────────

async def _process_request(connection: ServerConnection, request):
    """Handle HTTP health check requests (Codespaces probes)."""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None

    # Aggregate stats across all clients
    total_frames = sum(s.frames_processed for s in _clients.values())
    total_dropped = sum(s.frames_dropped for s in _clients.values())
    
    # Calculate average e2e latency across all clients
    avg_latencies = [
        s.get_latency_stats()["e2e"]["avg"]
        for s in _clients.values()
        if s.e2e_latency_samples
    ]
    avg_latency = sum(avg_latencies) / len(avg_latencies) if avg_latencies else 0.0

    body = json.dumps({
        "status":          "ok",
        "service":         "virtual-trainer-pose-edge-phase2",
        "uptime_s":        int(time.time() - _start_time),
        "active_clients":  len(_clients),
        "target_fps":      TARGET_FPS,
        "max_latency_ms":  MAX_LATENCY_MS,
        "total_frames":    total_frames,
        "total_dropped":   total_dropped,
        "avg_latency_ms":  round(avg_latency, 2),
    }).encode()

    headers = Headers([
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ])
    
    return Response(
        status_code=HTTPStatus.OK,
        reason_phrase="OK",
        headers=headers,
        body=body,
    )


# ── Frame processing pipeline ─────────────────────────────────

async def process_frame(
    session: ClientSession,
    jpeg_bytes: bytes,
    loop: asyncio.AbstractEventLoop,
    frame_start_time: float
) -> Optional[dict]:
    """
    Process frame through detection pipeline with end-to-end latency tracking.
    
    Pipeline stages:
    1. Decode base64 → JPEG bytes
    2. Run MediaPipe detection (in executor to avoid blocking)
    3. Validate result
    4. Return clean landmark data
    
    Args:
        frame_start_time: Time when frame message was received (for e2e latency)
    
    Returns None if frame should be skipped (throttled, latency exceeded, etc.)
    """
    session.record_frame_received()
    
    # Run MediaPipe detection in thread pool (non-blocking)
    result = await loop.run_in_executor(None, session.detector.detect, jpeg_bytes)
    
    # Calculate end-to-end latency (capture → send)
    e2e_latency_ms = (time.perf_counter() - frame_start_time) * 1000
    
    # Handle throttled or dropped frames
    if result.error in ("throttled", "latency_exceeded"):
        if result.error == "latency_exceeded":
            session.record_frame_dropped()
            logger.debug(
                f"🚫 Frame dropped (inference {result.latency_ms:.1f}ms > {MAX_LATENCY_MS}ms)",
                extra={
                    "event": "frame_dropped",
                    "client_id": session.client_id,
                    "inference_latency_ms": round(result.latency_ms, 2),
                    "threshold_ms": MAX_LATENCY_MS,
                }
            )
        return None
    
    # Handle decode errors
    if result.error == "frame_decode_error":
        session.record_frame_dropped()
        return {"type": "error", "message": "Failed to decode frame"}
    
    # Record successful processing with both inference and e2e latency
    session.record_frame_processed(result.latency_ms, e2e_latency_ms)
    
    # Build response with clean landmark data
    response = {
        "type":              "pose",
        "detected":          result.detected,
        "landmarks":         result.landmarks,
        "fps":               round(result.fps, 2),
        "latency_ms":        round(result.latency_ms, 2),      # Inference only
        "e2e_latency_ms":    round(e2e_latency_ms, 2),        # Full pipeline
        "frame_idx":         result.frame_idx,
        "timestamp":         time.time(),
    }
    
    return response


# ── WebSocket message handler ────────────────────────────────

async def handle_message(session: ClientSession, msg: dict) -> Optional[dict]:
    """Handle incoming WebSocket message and return response."""
    
    msg_type = msg.get("type", "")
    
    # ── ping ──────────────────────────────────────────────────
    if msg_type == "ping":
        return {"type": "pong"}
    
    # ── frame ← main video processing path ────────────────────
    elif msg_type == "frame":
        # Start timing for end-to-end latency measurement
        frame_start_time = time.perf_counter()
        
        b64_data = msg.get("data", "")
        if not b64_data:
            return {"type": "error", "message": "Missing 'data' field in frame"}
        
        try:
            jpeg_bytes = base64.b64decode(b64_data)
        except Exception as exc:
            session.record_frame_dropped()
            return {"type": "error", "message": f"Base64 decode error: {exc}"}
        
        loop = asyncio.get_event_loop()
        response = await process_frame(session, jpeg_bytes, loop, frame_start_time)
        return response  # May be None if frame was skipped
    
    # ── audio feedback (from backend) ─────────────────────────
    elif msg_type == "audio_feedback":
        # This message type allows backend to send audio through edge server
        if not _audio_streamer:
            return {"type": "error", "message": "Audio streaming not enabled"}
        
        try:
            # Extract audio message fields
            audio_data_b64 = msg.get("audio_data")
            if not audio_data_b64:
                return {"type": "error", "message": "Missing audio_data"}
            
            audio_data = base64.b64decode(audio_data_b64)
            feedback_code = msg.get("code", "UNKNOWN")
            severity = msg.get("severity", "info")
            text = msg.get("text")
            format_str = msg.get("format", "wav")
            
            # Create audio message
            audio_format = AudioFormat(format_str)
            audio_msg = create_audio_message(
                audio_data=audio_data,
                feedback_code=feedback_code,
                severity=severity,
                text=text,
                format=audio_format
            )
            
            # Stream audio to client (non-blocking)
            asyncio.create_task(
                _stream_audio_to_client(session, audio_msg)
            )
            
            return {"type": "audio_queued", "code": feedback_code}
            
        except Exception as exc:
            logger.error(f"Audio feedback processing error: {exc}", exc_info=True)
            return {"type": "error", "message": f"Audio processing error: {exc}"}
    
    # ── unknown ───────────────────────────────────────────────
    else:
        return {"type": "error", "message": f"Unknown message type: {msg_type!r}"}


# ── Audio Pipeline (separate from video) ──────────────────────

async def _stream_audio_to_client(session: ClientSession, audio_msg: AudioMessage):
    """
    Stream audio to client via WebSocket (non-blocking).
    
    This runs as a separate async task and does not block video processing.
    """
    if not _audio_streamer:
        return
    
    try:
        success = await _audio_streamer.stream_audio(
            session.websocket,
            session.client_id,
            audio_msg
        )
        
        if success:
            session.audio_messages_sent += 1
        else:
            session.audio_messages_dropped += 1
            
    except Exception as exc:
        logger.error(
            f"Audio streaming task error — client: {session.client_id}: {exc}",
            exc_info=True
        )
        session.audio_messages_dropped += 1


# ── Per-client WebSocket handler ──────────────────────────────

async def handle_client(ws: ServerConnection) -> None:
    """Handle WebSocket connection for a single client."""
    
    client_ip = ws.remote_address[0]
    client_id = f"{client_ip}:{ws.remote_address[1]}"
    
    logger.info(f"📱 Client connected: {client_id}")
    
    # Create isolated session
    detector = PoseDetector(
        model_complexity=MP_COMPLEXITY,
        min_detection_conf=MP_DETECT_CONF,
        min_tracking_conf=MP_TRACK_CONF,
        target_fps=TARGET_FPS,
        max_latency_ms=MAX_LATENCY_MS,
    )
    
    session = ClientSession(
        client_id=client_id,
        websocket=ws,
        detector=detector,
    )
    _clients[client_id] = session
    
    # Register client for audio streaming
    if _audio_streamer:
        _audio_streamer.register_client(client_id)
    
    logger.info(f"✅ Session initialized: {client_id} (active: {len(_clients)})")
    
    async def send(payload: dict) -> None:
        """Send JSON message to client with error handling."""
        try:
            await ws.send(json.dumps(payload, separators=(",", ":")))
        except Exception as exc:
            logger.warning(f"Failed to send to {client_id}: {exc}")
    
    try:
        async for raw in ws:
            # Parse incoming message
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError as exc:
                await send({"type": "error", "message": f"JSON decode error: {exc}"})
                continue
            
            # Process message and send response
            response = await handle_message(session, msg)
            if response:
                await send(response)
        
    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"📴 Client disconnected (normal): {client_id}")
    
    except websockets.exceptions.ConnectionClosedError as exc:
        logger.warning(f"⚠️  Client disconnected (error): {client_id} — {exc}")
    
    except Exception as exc:
        logger.error(f"❌ Unexpected error: {client_id} — {exc}", exc_info=True)
    
    finally:
        # Cleanup: log stats, close detector, remove from active clients
        session.log_stats()
        detector.close()
        
        # Unregister from audio streaming
        if _audio_streamer:
            _audio_streamer.unregister_client(client_id)
        
        _clients.pop(client_id, None)
        logger.info(f"🧹 Session cleaned up: {client_id} (active: {len(_clients)})")


# ── Entry point ───────────────────────────────────────────────

async def main() -> None:
    """Start WebSocket server."""
    
    global _audio_streamer

    cs = os.getenv("CODESPACE_NAME", "<codespace>")
    logger.info(f"🚀 Starting pose backend  ws://{WS_HOST}:{WS_PORT}")
    logger.info(f"   MP complexity : {MP_COMPLEXITY}")
    logger.info(f"   Target FPS    : {TARGET_FPS}")

    # ── Initialise voice layer ────────────────────────────────────────────────
    if _VOICE_ENABLED:
        try:
            audio_mode_map = {
                "forward": AudioMode.FORWARD_TO_CLIENT,
                "local": AudioMode.PLAY_LOCALLY,
                "both": AudioMode.BOTH,
            }
            audio_mode = audio_mode_map.get(AUDIO_MODE, AudioMode.FORWARD_TO_CLIENT)
            
            audio_config = AudioConfig(
                mode=audio_mode,
                sample_rate=16000,
                channels=1,
                cooldown_ms=500,
            )
            _audio_streamer = AudioStreamer(audio_config)
            logger.info(f"   Audio enabled   : YES (mode: {audio_mode.value})")
        except Exception as exc:
            logger.error(f"Failed to initialize audio streamer: {exc}")
            logger.info("   Audio enabled   : NO (initialization failed)")
    else:
        logger.info("   Audio enabled   : NO (AUDIO_ENABLED=0)")
    
    logger.info("─" * 70)
    logger.info(f"   WSS URL         : wss://{cs}-{WS_PORT}.app.github.dev")
    logger.info(f"   Health check    : https://{cs}-{WS_PORT}.app.github.dev")
    logger.info("=" * 70)
    
    async with serve(
        handle_client,
        WS_HOST,
        WS_PORT,
        process_request=_process_request,
        ping_interval=None,
        ping_timeout=None,
        close_timeout=10,
    ):
        logger.info("✅ Server ready — waiting for mobile frames …")
        logger.info(f"🔌 WSS URL      : wss://{cs}-{WS_PORT}.app.github.dev")
        logger.info(f"📡 Health-check : https://{cs}-{WS_PORT}.app.github.dev")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n👋 Server shutdown (KeyboardInterrupt)")
    except Exception as exc:
        logger.error(f"❌ Server crashed: {exc}", exc_info=True)
        sys.exit(1)
