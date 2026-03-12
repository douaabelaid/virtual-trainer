import asyncio
import json
import time
import cv2
import mediapipe as mp
from fastapi import FastAPI, WebSocket
import uvicorn

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

app = FastAPI()

def get_landmarks_json(landmarks, timestamp_ms):
    """Convert MediaPipe landmarks to JSON format"""
    landmark_data = {}
    for idx, landmark in enumerate(landmarks.landmark):
        landmark_data[mp_pose.PoseLandmark(idx).name] = {
            "x": round(landmark.x, 4),
            "y": round(landmark.y, 4),
            "z": round(landmark.z, 4),
            "visibility": round(landmark.visibility, 4)
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