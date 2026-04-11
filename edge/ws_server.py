"""
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
"""

import asyncio
import json
import logging
import os
import threading
import time

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from edge.pose_detector import PoseDetector
from logic.exercise_detector import ExerciseDetector
from logic.feedback_mapper import map_flags_to_coaching

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger('ws_server')

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
)

app = FastAPI(title='Virtual Trainer Pose Backend')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

pose_detector     = None
exercise_detector = None
cap               = None

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


@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client = websocket.client.host if websocket.client else 'unknown'
    _active_clients.add(client)
    logger.info(f'Client connected: {client} | active: {len(_active_clients)}')
    loop = asyncio.get_event_loop()
    last_latency_ms = 0.0   # tracks previous inference time for adaptive skip
    frame_counter = 0       # track frames for heartbeat messages
    last_heartbeat_frame = 0

    try:
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
    except Exception as exc:
        logger.error(f'Session error ({client}): {exc}', exc_info=True)
    finally:
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