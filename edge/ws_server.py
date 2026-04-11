"""
<<<<<<< HEAD
ws_server.py — Virtual Trainer Pose Backend

Data flow (per connected client):
  [Webcam]
      │  raw BGR frame (640×480)
      ▼
  PoseDetector.detect()
      │  MediaPipe Pose → 33 landmarks + joint angles
      ▼
  _filter_landmarks()
      │  keep only 12 key joints that are visible
      ▼
  ExerciseDetector.update()
      │  compute stage (STANDING/DOWN/TRANSITION) + rep count
      ▼
  map_flags_to_coaching()
      │  convert feedback flags → human-readable coaching messages
      ▼
  websocket.send_text()
      │  JSON payload → client (Douaa's ws_client.py or mobile app)

Run:
    python edge/ws_server.py
    python edge/ws_server.py  (WS_PORT=8000 WS_HOST=0.0.0.0 by default)
=======
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
>>>>>>> 65b85d6d4ea6a0834f3b8ff4209358b5a4340ebf
"""

import asyncio
import base64
from datetime import datetime
import json
import logging
import os
<<<<<<< HEAD
import threading
=======
import sys
>>>>>>> 65b85d6d4ea6a0834f3b8ff4209358b5a4340ebf
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

<<<<<<< HEAD
HOST       = os.getenv('WS_HOST', '0.0.0.0')
PORT       = int(os.getenv('WS_PORT', '8000'))
SHOW_CAMERA = os.getenv('SHOW_CAMERA', '1') == '1'  # Display camera window

# FRAME_SKIP: process only every Nth captured frame.
# Why: MediaPipe inference takes ~30-50 ms on CPU. Capturing at 30 FPS but
# running inference on every frame would create a growing backlog, increasing
# latency with each frame. Skipping alternate frames keeps the pipeline
# real-time without dropping WebSocket throughput noticeably.
FRAME_SKIP = int(os.getenv('FRAME_SKIP', '2'))

# TARGET_FPS: controls the sleep at the end of each loop iteration.
# Without it, the loop would spin at maximum CPU speed, burning 100% CPU
# even when there is nothing useful to compute.
TARGET_FPS = 30

# Only the 12 joints required by ExerciseDetector are kept.
# Why filter: MediaPipe returns 33 full-body landmarks (~3 KB per frame).
# Sending all 33 over WebSocket doubles payload size with no benefit for
# squat/lunge/pushup detection, which only uses hips, knees, ankles,
# shoulders, elbows, and wrists.
_KEY_LANDMARKS = (
    'left_hip', 'right_hip',
    'left_knee', 'right_knee',
    'left_ankle', 'right_ankle',
    'left_shoulder', 'right_shoulder',
    'left_elbow', 'right_elbow',
    'left_wrist', 'right_wrist',
=======
# ── Voice layer (optional) ────────────────────────────────────────────────────
_VOICE_ENABLED = os.getenv("VOICE_ENABLED", "1") not in ("0", "false", "False")
_audio_streamer = None   # initialised in main() if voice is enabled

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
>>>>>>> 65b85d6d4ea6a0834f3b8ff4209358b5a4340ebf
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

# Tracks all active WebSocket connections for monitoring
_active_clients: set = set()

# Server start time for uptime reporting
_start_time = time.time()

# Latest-frame queue: maxsize=1 means the camera thread always overwrites
# the old frame with the newest one. The WebSocket loop never processes a
# stale frame, keeping end-to-end latency minimal.
_frame_queue: asyncio.Queue = None  # type: ignore[assignment]

# Stop flag: set to True on shutdown to exit the camera thread cleanly
_camera_running = False

# Display state: latest frame and pose data for visualization
_display_lock = threading.Lock()
_latest_display_frame = None
_latest_landmarks = []
_latest_state = None


def _camera_thread(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> None:
    """
    Dedicated background thread for webcam capture.
    Reads frames continuously and keeps only the latest one in the queue.
    Exits cleanly when _camera_running is set to False on shutdown.
    """
    global _camera_running
    logger.info('Camera thread running.')
    while _camera_running:
        ret, frame = cap.read()
        if not ret or frame is None:
            time.sleep(0.005)
            continue
        # Discard the old frame if the handler hasn't consumed it yet
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
        asyncio.run_coroutine_threadsafe(queue.put(frame), loop)
    logger.info('Camera thread stopped.')


def _display_thread() -> None:
    """Display camera feed with pose visualization in a separate thread."""
    global _camera_running
    
    # Start window thread for Windows compatibility
    cv2.startWindowThread()
    cv2.namedWindow('Virtual Trainer - Camera Feed', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Virtual Trainer - Camera Feed', 800, 600)
    
    logger.info('Display window opened - Press Q to close')
    
    while _camera_running:
        with _display_lock:
            if _latest_display_frame is None:
                time.sleep(0.033)  # ~30 FPS
                continue
            
            frame = _latest_display_frame.copy()
            landmarks = _latest_landmarks.copy() if _latest_landmarks else []
            state = _latest_state
        
        h, w = frame.shape[:2]
        
        # Draw landmarks (green circles)
        for lm in landmarks:
            if lm.get('visible', False):
                x = int(lm['x'] * w)
                y = int(lm['y'] * h)
                cv2.circle(frame, (x, y), 5, (0, 255, 0), -1)
        
        # Draw exercise state
        if state:
            y_pos = 30
            # Exercise name (green)
            cv2.putText(frame, f"Exercise: {state.exercise.value.upper()}", 
                       (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            y_pos += 35
            
            # Stage (color coded)
            stage_colors = {
                'standing': (0, 255, 0),
                'down': (255, 200, 0),
                'transition': (0, 255, 255)
            }
            stage_color = stage_colors.get(state.stage.value, (255, 255, 255))
            cv2.putText(frame, f"Stage: {state.stage.value.upper()}", 
                       (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.8, stage_color, 2)
            y_pos += 35
            
            # Rep count (large, green)
            cv2.putText(frame, f"REPS: {state.rep_count}", 
                       (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
            y_pos += 50
            
            # Feedback (red warnings)
            if state.feedback_flags:
                cv2.putText(frame, "FEEDBACK:", 
                           (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 100, 255), 2)
                y_pos += 25
                for msg in state.feedback_flags[:3]:
                    cv2.putText(frame, f"• {msg}", 
                               (10, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    y_pos += 22
        else:
            cv2.putText(frame, "Waiting for pose...", 
                       (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Show frame
        cv2.imshow('Virtual Trainer - Camera Feed', frame)
        
        # Handle key press (must be in the same thread as imshow)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == ord('Q'):
            logger.info('Display closed by user')
            break
        
        time.sleep(0.001)  # Small sleep to prevent CPU spinning
    
    cv2.destroyAllWindows()
    logger.info('Display thread stopped')


@app.on_event('startup')
def startup():
    global pose_detector, exercise_detector, cap, _frame_queue, _camera_running
    logger.info('Initialising PoseDetector ...')
    # Improved parameters for better stability and detection
    pose_detector = PoseDetector(
        model_complexity=1,           # Better quality (was 0)
        min_detection_conf=0.3,       # Lower = easier to detect (default 0.5)
        min_tracking_conf=0.3,        # Lower = better tracking (default 0.5)
        target_fps=TARGET_FPS,
        min_visibility=0.2            # Lower = accept more landmarks (default 0.3)
    )
    logger.info('Pre-loading MediaPipe model...')
    cold_ms = pose_detector.warmup()
    logger.info(f'Model warm - cold-start: {cold_ms:.1f} ms')
    logger.info('Initialising ExerciseDetector ...')
    exercise_detector = ExerciseDetector(exercise='squat')
    logger.info('Opening camera ...')
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        logger.error('Camera index 0 could not be opened.')
    else:
        logger.info('Camera ready (640x480).')

    # Start camera capture thread
    loop = asyncio.get_event_loop()
    _frame_queue = asyncio.Queue(maxsize=1)
    _camera_running = True
    t = threading.Thread(target=_camera_thread, args=(_frame_queue, loop), daemon=True)
    t.start()
    
    # Start display thread if enabled
    if SHOW_CAMERA:
        display_thread = threading.Thread(target=_display_thread, daemon=True)
        display_thread.start()
        logger.info('Camera display enabled')
    
    logger.info(f'Server ready - ws://{HOST}:{PORT}/ws')


@app.on_event('shutdown')
def shutdown():
    global _camera_running
    # Signal camera thread to stop before releasing hardware
    _camera_running = False
    time.sleep(0.1)  # give thread time to exit its loop
    if cap and cap.isOpened():
        cap.release()
        logger.info('Camera released.')
    if pose_detector:
        pose_detector.close()
        logger.info('PoseDetector closed.')
    logger.info(f'Server shut down. Total uptime: {int(time.time() - _start_time)}s')


def _filter_landmarks(landmarks):
    """
    Convert the full 33-landmark list from PoseDetector into a compact dict
    containing only the 12 joints needed for exercise detection.

    Joints with visibility < 0.3 (set in PoseDetector) are excluded.
    This prevents passing unreliable coordinates (e.g. occluded ankle when
    the user is partially out of frame) into the angle calculations, which
    would produce nonsense angles and trigger false feedback.
    """
    lm_map = {lm['name']: lm for lm in landmarks if 'name' in lm}
    return {name: lm_map[name] for name in _KEY_LANDMARKS
            if name in lm_map and lm_map[name].get('visible', False)}


def _build_output(state, result, coaching, filtered):
    """
    Assemble the final JSON payload sent to the client after every processed frame.

    Fields:
      timestamp_ms  — Unix time in ms (lets client measure end-to-end latency)
      exercise      — current exercise name ('squat', 'lunge', 'pushup')
      stage         — movement phase ('standing', 'down', 'transition')
      rep_count     — cumulative reps completed this session
      feedback      — list of coaching messages (may be empty)
      angles        — computed joint angles in degrees (for UI visualisation)
      fps           — server-side inference FPS (EMA smoothed)
      latency_ms    — time MediaPipe took to process this frame
      landmarks     — filtered visible joints sent to client for rendering
    """
    return {
        'timestamp_ms': int(time.time() * 1000),
        'exercise':     state.exercise.value,
        'stage':        state.stage.value,
        'rep_count':    state.rep_count,
        'feedback':     coaching,
        'angles':       result.angles,
        'fps':          result.fps,
        'latency_ms':   result.latency_ms,
        'landmarks':    filtered,
    }

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

<<<<<<< HEAD
@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client = websocket.client.host if websocket.client else 'unknown'
    _active_clients.add(client)
    logger.info(f'Client connected: {client} | active: {len(_active_clients)}')
=======
>>>>>>> 65b85d6d4ea6a0834f3b8ff4209358b5a4340ebf
    loop = asyncio.get_event_loop()
    last_latency_ms = 0.0   # tracks previous inference time for adaptive skip
    frame_counter = 0       # track frames for heartbeat messages
    last_heartbeat_frame = 0

    async def send(payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload, separators=(",", ":")))
        except Exception:
            pass

    try:
<<<<<<< HEAD
        while True:
            t0 = time.perf_counter()
            frame_counter += 1

            # ── Step 1: Get latest frame from camera thread ────────────────
            # The camera thread continuously captures and overwrites the queue
            # with the newest frame. await queue.get() returns immediately if
            # a frame is ready, otherwise waits up to 1 s before retrying.
            try:
                frame = await asyncio.wait_for(_frame_queue.get(), timeout=1.0)
                if frame_counter == 1:
                    logger.info(f'First frame received from camera - processing started')
            except asyncio.TimeoutError:
                logger.warning('No frame received in 1s - camera stalled?')
                continue

            # ── Step 2: Adaptive frame skip - DISABLED ─────────────────────
            # NOTE: Frame skipping is already handled by FRAME_SKIP setting.
            # The adaptive skip was too aggressive (threshold 33ms but MediaPipe
            # takes 40-50ms), causing all frames to be skipped after the first one.
            # Uncomment below if needed, but increase threshold significantly:
            # if last_latency_ms > (2000.0 / TARGET_FPS):  # 2x budget = 66ms
            #     continue

            try:
                # ── Step 3: Pose detection (direct BGR, no JPEG round-trip) ─
                # detect_bgr() skips the cv2.imencode + imdecode step that
                # detect(jpeg_bytes) requires, saving ~5-10 ms per frame.
                result = await loop.run_in_executor(
                    None, pose_detector.detect_bgr, frame
                )

                if not result.detected or not result.landmarks:
                    # Update display (no pose)
                    if SHOW_CAMERA:
                        with _display_lock:
                            _latest_display_frame = frame
                            _latest_landmarks = []
                            _latest_state = None
                    
                    # Send heartbeat every 15 frames (~0.5s) to show camera is working
                    if frame_counter - last_heartbeat_frame >= 15:
                        heartbeat = {
                            'type': 'heartbeat',
                            'message': 'Camera active - no pose detected. Stand in front of camera.',
                            'timestamp_ms': int(time.time() * 1000),
                            'frame_count': frame_counter
                        }
                        await websocket.send_text(json.dumps(heartbeat, separators=(',', ':')))
                        last_heartbeat_frame = frame_counter
                        logger.info(f'Sent heartbeat - frame {frame_counter}, no pose detected')
                    continue

                last_latency_ms = result.latency_ms

                # ── Step 4: Filter landmarks ──────────────────────────────
                filtered = _filter_landmarks(result.landmarks)
                if not filtered.get('left_knee') and not filtered.get('right_knee'):
                    logger.debug('No knee landmarks visible - skipping frame.')
                
                # ── Update display (pose detected) ────────────────────────
                if SHOW_CAMERA:
                    with _display_lock:
                        _latest_display_frame = frame
                        _latest_landmarks = result.landmarks
                        _latest_state = state
                    continue

                # ── Step 5: Exercise detection ─────────────────────────────
                state = exercise_detector.update(filtered)

                # ── Step 6: Feedback ───────────────────────────────────────
                coaching = map_flags_to_coaching(state.feedback_flags)

                # ── Step 7: Send JSON ──────────────────────────────────────
                output = _build_output(state, result, coaching, filtered)
                output['type'] = 'pose'  # Mark as pose data
                await websocket.send_text(json.dumps(output, separators=(',', ':')))

            except Exception as frame_exc:
                logger.error(f'Frame error: {frame_exc}', exc_info=True)
                continue

            # ── Step 8: FPS throttle ───────────────────────────────────────
            elapsed = time.perf_counter() - t0
            sleep_for = (1.0 / TARGET_FPS) - elapsed
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

    except WebSocketDisconnect:
        logger.info(f'Client disconnected: {client} | active: {len(_active_clients) - 1}')
=======
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
>>>>>>> 65b85d6d4ea6a0834f3b8ff4209358b5a4340ebf
    except Exception as exc:
        logger.error(f"❌ Unexpected error {client_ip}: {exc}", exc_info=True)
    finally:
<<<<<<< HEAD
        _active_clients.discard(client)
        await websocket.close()


@app.get('/')
def index():
    return HTMLResponse(f'<html><body><h1>Virtual Trainer - Pose Backend</h1><p>ws://{{host}}:{PORT}/ws</p></body></html>')


@app.get('/health')
def health():
    return {
        'status':          'ok',
        'camera':          cap.isOpened() if cap else False,
        'active_clients':  len(_active_clients),
        'uptime_s':        int(time.time() - _start_time),
        'fps_target':      TARGET_FPS,
    }


if __name__ == '__main__':
    uvicorn.run(
        'edge.ws_server:app',
        host=HOST,
        port=PORT,
        reload=False,
        log_level='info',
        access_log=False,   # disable per-request access logs to reduce noise
    )
=======
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
>>>>>>> 65b85d6d4ea6a0834f3b8ff4209358b5a4340ebf
