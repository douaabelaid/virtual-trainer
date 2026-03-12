import asyncio
import json
import time
import cv2
import mediapipe as mp
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

app = FastAPI()

# Allow external connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_landmarks_json(landmarks, timestamp_ms):
    """Convert MediaPipe landmarks to Douaa's expected format"""
    relevant_landmarks = {
        "left_knee": mp_pose.PoseLandmark.LEFT_KNEE,
        "right_knee": mp_pose.PoseLandmark.RIGHT_KNEE,
        "left_hip": mp_pose.PoseLandmark.LEFT_HIP,
        "right_hip": mp_pose.PoseLandmark.RIGHT_HIP,
        "left_ankle": mp_pose.PoseLandmark.LEFT_ANKLE,
        "right_ankle": mp_pose.PoseLandmark.RIGHT_ANKLE,
        "left_shoulder": mp_pose.PoseLandmark.LEFT_SHOULDER,
        "right_shoulder": mp_pose.PoseLandmark.RIGHT_SHOULDER,
        "left_elbow": mp_pose.PoseLandmark.LEFT_ELBOW,
        "right_elbow": mp_pose.PoseLandmark.RIGHT_ELBOW,
        "left_wrist": mp_pose.PoseLandmark.LEFT_WRIST,
        "right_wrist": mp_pose.PoseLandmark.RIGHT_WRIST,
    }

    landmark_data = {}
    for name, idx in relevant_landmarks.items():
        lm = landmarks.landmark[idx]
        landmark_data[name] = {
            "x": round(lm.x, 4),
            "y": round(lm.y, 4)
        }

    return {
        "timestamp_ms": timestamp_ms,
        "landmarks": landmark_data
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("Client connected!")

    cap = cv2.VideoCapture(0)

    with mp_pose.Pose(
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5
    ) as pose:

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            timestamp_ms = int(time.time() * 1000)

            # Process frame
            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image.flags.writeable = False
            results = pose.process(image)
            image.flags.writeable = True

            if results.pose_landmarks:
                data = get_landmarks_json(results.pose_landmarks, timestamp_ms)
                await websocket.send_text(json.dumps(data))

            # 15 FPS = wait 66ms
            await asyncio.sleep(0.066)

    cap.release()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)