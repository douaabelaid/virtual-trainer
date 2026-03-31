"""
ws_server.py
WebSocket server — accepts base64 JPEG frames from a mobile app,
runs MediaPipe Pose via PoseDetector, streams back landmark JSON.

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
  "landmarks": [
      { "name":"left_knee",
        "x":0.45, "y":0.71, "z":-0.10,
        "visibility":0.998,
        "px":288,  "py":341,
        "visible":true }, ... ],
  "angles":    { "left_knee":92.3, "avg_knee":91.7, ... },
  "fps":       14.9,
  "latency_ms":17.4,
  "frame_idx":  38,
  "exercise":  "squat"  }

{ "type": "pong"                            }
{ "type": "exercise_set", "exercise":"..." }
{ "type": "reset_ok",     "rep_count": 0   }
{ "type": "error",        "message":  "..." }
──────────────────────────────────────────────────────────────
"""

import asyncio
import base64
import json
import logging
import os
import time
from http import HTTPStatus

import websockets
from websockets.asyncio.server import ServerConnection, serve

from pose_detector import PoseDetector

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ws_server")

# Silence noisy Codespaces health-check rejection logs
logging.getLogger("websockets.server").setLevel(logging.CRITICAL)

# ── Config (all overridable via env vars) ─────────────────────────────────────
WS_HOST        = os.getenv("WS_HOST",              "0.0.0.0")
WS_PORT        = int(os.getenv("WS_PORT",          "8765"))
MP_COMPLEXITY  = int(os.getenv("MP_COMPLEXITY",    "0"))
MP_DETECT_CONF = float(os.getenv("MP_DETECT_CONF", "0.5"))
MP_TRACK_CONF  = float(os.getenv("MP_TRACK_CONF",  "0.5"))
TARGET_FPS     = int(os.getenv("TARGET_FPS",       "15"))

# ── Server state ──────────────────────────────────────────────────────────────
_clients: set[ServerConnection] = set()
_start_time = time.time()


async def _broadcast(payload: dict) -> None:
    """Send a message to every connected client."""
    if not _clients:
        return
    message = json.dumps(payload, separators=(",", ":"))
    await asyncio.gather(
        *[client.send(message) for client in _clients],
        return_exceptions=True,
    )


# ── HTTP handler: answers Codespaces health-check probes ─────────────────────

async def _process_request(connection: ServerConnection, request) -> None:
    """Return HTTP 200 for plain HTTP probes; None for real WS upgrades."""
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return None

    body = json.dumps({
        "status":     "ok",
        "service":    "virtual-trainer-pose-backend",
        "clients":    len(_clients),
        "uptime_s":   int(time.time() - _start_time),
        "target_fps": TARGET_FPS,
    }).encode()

    headers = {  # type: ignore[call-arg]
        "Content-Type":                "application/json",
        "Content-Length":              str(len(body)),
        "Access-Control-Allow-Origin": "*",
    }
    return connection.respond(HTTPStatus.OK, body.decode(), headers=headers)  # type: ignore[call-arg]


# ── Per-client session ────────────────────────────────────────────────────────

async def handle_client(ws: ServerConnection) -> None:
    client_ip        = ws.remote_address[0]
    current_exercise = "squat"
    last_latency_ms  = 0.0   # tracks last inference time; used for frame-skip

    logger.info(f"📱 Connected    : {client_ip}  "
                f"(active clients: {len(_clients) + 1})")
    _clients.add(ws)

    # One PoseDetector per client — fully isolated
    detector = PoseDetector(
        model_complexity=MP_COMPLEXITY,
        min_detection_conf=MP_DETECT_CONF,
        min_tracking_conf=MP_TRACK_CONF,
        target_fps=TARGET_FPS,
        min_visibility=0.3,
    )
    loop = asyncio.get_event_loop()

    async def send(payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload, separators=(",", ":")))
        except Exception:
            pass

    try:
        async for raw in ws:

            # ── Parse JSON ────────────────────────────────────────────────────
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
                logger.info(f"🏋️  {client_ip} → exercise: {current_exercise}")
                await send({"type": "exercise_set",
                            "exercise": current_exercise})

            # ── reset ─────────────────────────────────────────────────────────
            elif msg_type == "reset":
                current_exercise = msg.get("exercise", current_exercise)
                await send({"type": "reset_ok", "rep_count": 0})

            # ── frame  ← main path ────────────────────────────────────────────
            elif msg_type == "frame":
                # Allow exercise to be set inline with the frame
                if "exercise" in msg:
                    current_exercise = msg["exercise"]

                b64 = msg.get("data", "")
                if not b64:
                    await send({"type": "error",
                                "message": "Missing 'data' field"})
                    continue

                # Decode base64 → raw JPEG bytes
                try:
                    jpeg_bytes = base64.b64decode(b64)
                except Exception as exc:
                    await send({"type": "error",
                                "message": f"base64 error: {exc}"})
                    continue

                # Skip frame when the previous inference was too slow.
                # This prevents backlog buildup and keeps throughput ≥ 15 FPS.
                if last_latency_ms > 100:
                    logger.debug(
                        f"⏭  {client_ip} — frame skipped "
                        f"(last latency {last_latency_ms:.1f} ms > 100 ms)"
                    )
                    continue

                # Run MediaPipe in a thread so asyncio loop stays responsive
                result = await loop.run_in_executor(
                    None, detector.detect, jpeg_bytes
                )

                # Silently drop throttled frames (mobile sent too fast)
                if result.error == "throttled":
                    continue

                last_latency_ms = result.latency_ms

                # Build pose response and broadcast to ALL connected clients
                response: dict = {
                    "type":         "pose",
                    "detected":     result.detected,
                    "landmarks":    result.landmarks,
                    "angles":       result.angles,
                    "fps":          result.fps,
                    "latency_ms":   result.latency_ms,
                    "frame_idx":    result.frame_idx,
                    "timestamp_ms": int(time.time() * 1000),   # ← ADD THIS
                    "exercise":     current_exercise,
                }
                if result.error:
                    response["error"] = result.error

                await _broadcast(response)

            # ── unknown ───────────────────────────────────────────────────────
            else:
                await send({"type": "error",
                            "message": f"Unknown type: {msg_type!r}"})

    except websockets.exceptions.ConnectionClosedOK:
        logger.info(f"📴 Disconnected : {client_ip}")
    except websockets.exceptions.ConnectionClosedError as exc:
        logger.warning(f"⚠️  Connection error {client_ip}: {exc}")
    except Exception as exc:
        logger.error(f"❌ Unexpected error {client_ip}: {exc}", exc_info=True)
    finally:
        _clients.discard(ws)
        detector.close()
        logger.info(f"🧹 Cleaned up   : {client_ip}  "
                    f"(active clients: {len(_clients)})")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    cs = os.getenv("CODESPACE_NAME", "<codespace>")
    logger.info(f"🚀 Starting pose backend  ws://{WS_HOST}:{WS_PORT}")
    logger.info(f"   MP complexity : {MP_COMPLEXITY}")
    logger.info(f"   Target FPS    : {TARGET_FPS}")

    # Pre-load model BEFORE accepting connections
    logger.info("⏳ Pre-loading MediaPipe model...")
    _warmup_detector = PoseDetector(model_complexity=MP_COMPLEXITY)
    cold_ms = _warmup_detector.warmup()
    _warmup_detector.close()
    logger.info(f"✅ Model warm — cold-start: {cold_ms:.1f} ms")

    async with serve(
        handle_client,
        WS_HOST,
        WS_PORT,
        process_request=_process_request,
    ):
        logger.info("✅ Server ready — waiting for mobile frames …")
        logger.info(f"🔌 WSS URL      : wss://{cs}-{WS_PORT}.app.github.dev")
        logger.info(f"📡 Health-check : https://{cs}-{WS_PORT}.app.github.dev")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())