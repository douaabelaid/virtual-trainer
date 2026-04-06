import asyncio
import json
import logging
import os
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
FRAME_SKIP = int(os.getenv('FRAME_SKIP', '2'))
TARGET_FPS = 30

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


@app.on_event('startup')
def startup():
    global pose_detector, exercise_detector, cap
    logger.info('Initialising PoseDetector ...')
    pose_detector = PoseDetector(model_complexity=0, target_fps=TARGET_FPS)
    logger.info('⏳ Pre-loading MediaPipe model...')
    cold_ms = pose_detector.warmup()
    logger.info(f'✅ Model warm — cold-start: {cold_ms:.1f} ms')
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
    logger.info(f'Server ready - ws://{HOST}:{PORT}/ws')

@app.on_event('shutdown')
def shutdown():
    if cap and cap.isOpened():
        cap.release()
    if pose_detector:
        pose_detector.close()
    logger.info('Resources released.')


def _filter_landmarks(landmarks):
    lm_map = {lm['name']: lm for lm in landmarks if 'name' in lm}
    return {name: lm_map[name] for name in _KEY_LANDMARKS
            if name in lm_map and lm_map[name].get('visible', False)}


def _build_output(state, result, coaching, filtered):
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
    logger.info(f'Client connected: {client}')
    frame_id = 0
    loop = asyncio.get_event_loop()

    try:
        while True:
            t0 = time.perf_counter()

            # Step 1: Capture frame
            ret, frame = await loop.run_in_executor(None, cap.read)
            if not ret or frame is None:
                logger.warning('Frame capture failed - skipping.')
                await asyncio.sleep(0.01)
                continue

            frame_id += 1

            # Step 2: Frame skipping
            if frame_id % FRAME_SKIP != 0:
                continue

            try:
                # Step 3: Pose detection
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                result = await loop.run_in_executor(None, pose_detector.detect, jpeg.tobytes())

                if not result.detected or not result.landmarks:
                    continue

                # Step 4: Filter landmarks
                filtered = _filter_landmarks(result.landmarks)
                if not filtered.get('left_knee') and not filtered.get('right_knee'):
                    logger.debug('No knee landmarks visible - skipping frame.')
                    continue

                # Step 5: Exercise detection
                state = exercise_detector.update(filtered)

                # Step 6: Feedback
                coaching = map_flags_to_coaching(state.feedback_flags)

                # Step 7: Send JSON
                output = _build_output(state, result, coaching, filtered)
                await websocket.send_text(json.dumps(output, separators=(',', ':')))

            except Exception as frame_exc:
                logger.error(f'Frame {frame_id} error: {frame_exc}', exc_info=True)
                continue

            # Step 8: FPS control
            elapsed = time.perf_counter() - t0
            sleep_for = (1.0 / TARGET_FPS) - elapsed
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)

    except WebSocketDisconnect:
        logger.info(f'Client disconnected: {client}')
    except Exception as exc:
        logger.error(f'Session error ({client}): {exc}', exc_info=True)
    finally:
        await websocket.close()


@app.get('/')
def index():
    return HTMLResponse('<html><body><h1>Virtual Trainer - Pose Backend</h1><p>ws://host:8000/ws</p></body></html>')


@app.get('/health')
def health():
    return {'status': 'ok', 'camera': cap.isOpened() if cap else False, 'fps_target': TARGET_FPS}


if __name__ == '__main__':
    uvicorn.run('edge.ws_server:app', host=HOST, port=PORT, reload=False)