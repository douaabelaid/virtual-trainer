"""
ws_server.py
WebSocket server — accepts base64 JPEG frames from a mobile app,
runs MediaPipe Pose via PoseDetector, streams back landmark JSON + audio coaching.

──────────────────────────────────────────────────────────────
Mobile → Server (JSON)
──────────────────────────────────────────────────────────────
{ "type": "frame",
  "data": "<base64-encoded JPEG>",
  "exercise": "squat"            }   ← exercise is optional

{ "type": "ping"                 }
{ "type": "set_exercise", "exercise": "squat" }
{ "type": "reset"                }

──────────────────────────────────────────────────────────────
Server → Mobile (JSON)
──────────────────────────────────────────────────────────────
{ "type":      "pose",
  "detected":  true,
  "landmarks": [...],
  "angles":    { "left_knee":92.3, ... },
  "fps":       14.9,
  "latency_ms":17.4,
  "frame_idx":  38,
  "exercise":  "squat",
  "rep_count":  4,
  "stage":     "down"  }

{ "type": "audio", "format": "wav",
  "code": "KNEE_CAVE", "severity": "warning",
  "text": "...", "exercise": "squat" }
<binary WAV frame>

{ "type": "pong"                            }
{ "type": "exercise_set", "exercise":"..." }
{ "type": "reset_ok",     "rep_count": 0   }
{ "type": "error",        "message":  "..." }
────────────���─────────────────────────────────────────────────
"""

import asyncio
import base64
from datetime import datetime
import json
import logging
import os
import sys
import time
from http import HTTPStatus
from pathlib import Path

import numpy as np
import websockets
from websockets.asyncio.server import ServerConnection, serve

# ── Path setup (so edge/ can import logic/ and voice/) ───────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pose_detector import PoseDetector  # noqa: E402  (local import)

# ── Exercise logic ────────────────────────────────────────────────────────────
try:
    from logic.exercise_detector import ExerciseDetector
    from logic.feedback_mapper import map_flags_to_coaching
    _LOGIC_AVAILABLE = True
except ImportError as _e:
    _LOGIC_AVAILABLE = False
    logging.getLogger("ws_server").warning(f"logic layer not available: {_e}")

# ── Voice layer (optional) ────────────────────────────────────────────────────
_VOICE_ENABLED = os.getenv("VOICE_ENABLED", "1") not in ("0", "false", "False")
_audio_streamer = None   # initialised in main() if voice is enabled

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ws_server")
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)

# ── Config (all overridable via env vars) ─────────────────────────────────────
# Force this in your Python code:
WS_HOST = "0.0.0.0" 
WS_PORT = 8765
# WS_HOST        = os.getenv("WS_HOST",              "0.0.0.0")
# WS_PORT        = int(os.getenv("WS_PORT",          "8765"))
MP_COMPLEXITY  = int(os.getenv("MP_COMPLEXITY",    "1"))
MP_DETECT_CONF = float(os.getenv("MP_DETECT_CONF", "0.5"))
MP_TRACK_CONF  = float(os.getenv("MP_TRACK_CONF",  "0.5"))
TARGET_FPS     = int(os.getenv("TARGET_FPS",       "15"))

# ── Server state ──────────────────────────────────────────────────────────────
_clients: set[ServerConnection] = set()
_start_time = time.time()


# ── Session Logger ────────────────────────────────────────────────────────────

class SessionLogger:
    """Logs per-frame latency metrics to a session-specific JSON file."""

    def __init__(self, logs_dir: Path = Path("logs")):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = self.logs_dir / f"session_{timestamp}.json"
        
        self.file_handle = open(self.log_file_path, "w")
        self.session_start = time.time()
        
        self.latencies: list[float] = []
        self.frame_count = 0
        self.high_latency_count = 0
        
        logger.info(f"📊 Session log: {self.log_file_path}")
    
    def log_frame(self, frame_idx: int, latency_ms: float, fps: float, timestamp_ms: int) -> None:
        """Write one JSON line per frame."""
        self.frame_count += 1
        self.latencies.append(latency_ms)
        
        if latency_ms > 120:
            self.high_latency_count += 1
        
        frame_data = {
            "frame_idx": frame_idx,
            "latency_ms": round(latency_ms, 2),
            "e2e_latency_ms": round(latency_ms, 2),  # Same for now (can be extended)
            "fps": round(fps, 2),
            "timestamp_ms": timestamp_ms,
        }
        self.file_handle.write(json.dumps(frame_data, separators=(",", ":")) + "\n")
    
    def close(self) -> None:
        """Write summary block and close file."""
        if not self.file_handle or self.file_handle.closed:
            return
        
        session_duration = time.time() - self.session_start
        
        summary = {
            "type": "summary",
            "total_frames": self.frame_count,
            "avg_latency_ms": round(float(np.mean(self.latencies)), 2) if self.latencies else 0.0,
            "p95_latency_ms": round(float(np.percentile(self.latencies, 95)), 2) if self.latencies else 0.0,
            "p99_latency_ms": round(float(np.percentile(self.latencies, 99)), 2) if self.latencies else 0.0,
            "high_latency_count": self.high_latency_count,
            "session_duration_s": round(session_duration, 2),
        }
        
        self.file_handle.write(json.dumps(summary, separators=(",", ":"), indent=2) + "\n")
        self.file_handle.flush()
        self.file_handle.close()
        
        logger.info(f"📊 Session summary: {self.frame_count} frames, "
                   f"P95={summary['p95_latency_ms']}ms, P99={summary['p99_latency_ms']}ms")


# ── HTTP handler: answers Codespaces health-check probes ─────────────────────

async def _process_request(connection: ServerConnection, request) -> None:
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None

    body = json.dumps({
        "status":        "ok",
        "service":       "virtual-trainer-pose-backend",
        "clients":       len(_clients),
        "uptime_s":      int(time.time() - _start_time),
        "target_fps":    TARGET_FPS,
        "voice_enabled": _audio_streamer is not None,
    }).encode()

    return connection.respond(
        HTTPStatus.OK,
        body.decode(),
        headers=[
            ("Content-Type",                "application/json"),
            ("Content-Length",              str(len(body))),
            ("Access-Control-Allow-Origin", "*"),
        ],
    )


# ── Per-client session ────────────────────────────────────────────────────────

async def handle_client(ws: ServerConnection) -> None:
    client_ip        = ws.remote_address[0]
    current_exercise = "squat"

    logger.info(f"📱 Connected    : {client_ip}  (active clients: {len(_clients) + 1})")
    _clients.add(ws)

    # One PoseDetector per client
    detector = PoseDetector(
        model_complexity=MP_COMPLEXITY,
        min_detection_conf=MP_DETECT_CONF,
        min_tracking_conf=MP_TRACK_CONF,
        target_fps=TARGET_FPS,
    )

    # One ExerciseDetector per client (if logic layer available)
    logic_detector = ExerciseDetector(exercise=current_exercise) if _LOGIC_AVAILABLE else None

    # One SessionLogger per client
    session_logger = SessionLogger(logs_dir=_ROOT / "logs")

    loop = asyncio.get_event_loop()

    async def send(payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload, separators=(",", ":")))
        except Exception:
            pass

    try:
        async for raw in ws:

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError as exc:
                await send({"type": "error", "message": f"JSON error: {exc}"})
                continue

            msg_type = msg.get("type", "")

            # ── ping ──────────────────────────────────────────────────────────
            if msg_type == "ping":
                await send({"type": "pong"})

            # ── set_exercise ──────────────────────────────────────────────────
            elif msg_type == "set_exercise":
                current_exercise = msg.get("exercise", current_exercise)
                if logic_detector and _LOGIC_AVAILABLE:
                    logic_detector = ExerciseDetector(exercise=current_exercise)
                logger.info(f"🏋️  {client_ip} → exercise: {current_exercise}")
                await send({"type": "exercise_set", "exercise": current_exercise})

            # ── reset ─────────────────────────────────────────────────────────
            elif msg_type == "reset":
                current_exercise = msg.get("exercise", current_exercise)
                if logic_detector:
                    logic_detector.reset()
                if _audio_streamer:
                    _audio_streamer.reset_cooldowns()
                await send({"type": "reset_ok", "rep_count": 0})

            # ── frame  ← main path ────────────────────────────────────────────
            elif msg_type == "frame":
                if "exercise" in msg:
                    new_ex = msg["exercise"]
                    if new_ex != current_exercise:
                        current_exercise = new_ex
                        if _LOGIC_AVAILABLE:
                            logic_detector = ExerciseDetector(exercise=current_exercise)

                b64 = msg.get("data", "")
                if not b64:
                    await send({"type": "error", "message": "Missing 'data' field"})
                    continue

                try:
                    jpeg_bytes = base64.b64decode(b64)
                except Exception as exc:
                    await send({"type": "error", "message": f"base64 error: {exc}"})
                    continue

                # Run MediaPipe in thread
                result = await loop.run_in_executor(None, detector.detect, jpeg_bytes)

                if result.error == "throttled":
                    continue

                # ── Build pose response ───────────────────────────────────────
                # Build landmarks_raw dict for backward compatibility with ws_client.py
                landmarks_dict = {}
                if result.landmarks:
                    landmarks_dict = {
                        lm["name"]: {"x": lm["x"], "y": lm["y"]}
                        for lm in result.landmarks
                        if lm.get("visible", True)
                    }
                
                response: dict = {
                    "type":       "pose",
                    "detected":   result.detected,
                    "landmarks":  result.landmarks,      # List format (Phase 2, new)
                    "landmarks_raw": landmarks_dict,     # Dict format (backward compat)
                    "angles":     result.angles,
                    "fps":        result.fps,
                    "latency_ms": result.latency_ms,
                    "frame_idx":  result.frame_idx,
                    "exercise":   current_exercise,
                    "timestamp_ms": int(time.time() * 1000),  # Added for compatibility
                }
                if result.error:
                    response["error"] = result.error

                # ── Run exercise logic ────────────────────────────────────────
                feedback_flags = []
                if logic_detector and result.detected and result.landmarks:
                    try:
                        # Use pre-built landmarks_dict
                        state = logic_detector.update(landmarks_dict)
                        feedback_flags = state.feedback_flags
                        response["rep_count"] = state.rep_count
                        response["stage"]     = state.stage.value
                    except Exception as exc:
                        logger.warning(f"Exercise logic error: {exc}")

                await send(response)

                # ── Log frame metrics ─────────────────────────────────────────
                session_logger.log_frame(
                    frame_idx=result.frame_idx,
                    latency_ms=result.latency_ms,
                    fps=result.fps,
                    timestamp_ms=response["timestamp_ms"],
                )

                # ── Stream voice coaching (fire-and-forget) ───────────────────
                if _audio_streamer and feedback_flags:
                    asyncio.create_task(
                        _audio_streamer.stream_coaching(ws, feedback_flags, current_exercise)
                    )

            # ── unknown ───────────────────────────────────────────────────────
            else:
                await send({"type": "error", "message": f"Unknown type: {msg_type!r}"})

    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"📴 Disconnected : {client_ip}")
    except websockets.exceptions.ConnectionClosedError as exc:
        logger.warning(f"⚠️  Connection error {client_ip}: {exc}")
    except Exception as exc:
        logger.error(f"❌ Unexpected error {client_ip}: {exc}", exc_info=True)
    finally:
        _clients.discard(ws)
        detector.close()
        session_logger.close()
        logger.info(f"🧹 Cleaned up   : {client_ip}  (active clients: {len(_clients)})")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    global _audio_streamer

    # cs = os.getenv("CODESPACE_NAME", "<codespace>")
    logger.info(f"🚀 Starting pose backend  ws://{WS_HOST}:{WS_PORT}")
    logger.info(f"   MP complexity : {MP_COMPLEXITY}")
    logger.info(f"   Target FPS    : {TARGET_FPS}")

    # ── Initialise voice layer ────────────────────────────────────────────────
    if _VOICE_ENABLED:
        try:
            from voice.tts_client    import TTSClient
            from voice.audio_streamer import AudioStreamer
            from voice.phrase_library import ALL_PHRASES

            tts_client = TTSClient()
            if tts_client.ready:
                # Pre-load phrases in a thread so server starts immediately
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, tts_client.preload_phrases, ALL_PHRASES)
                _audio_streamer = AudioStreamer(tts_client, cooldown_s=2.0)
                logger.info("🎙️  Voice coaching: ENABLED (Coqui TTS)")
            else:
                logger.warning("🔇 TTS model not ready — voice coaching disabled.")
        except ImportError as exc:
            logger.warning(f"🔇 Voice layer import failed ({exc}) — voice coaching disabled.")
        except Exception as exc:
            logger.error(f"🔇 Voice init error: {exc} — voice coaching disabled.")
    else:
        logger.info("🔇 Voice coaching: DISABLED (VOICE_ENABLED=0)")

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
        # logger.info(f"🔌 WSS URL      : wss://{cs}-{WS_PORT}.app.github.dev")
        # logger.info(f"📡 Health-check : https://{cs}-{WS_PORT}.app.github.dev")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())