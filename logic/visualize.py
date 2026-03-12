import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import mediapipe as mp
import numpy as np
from logic.angle_utils import get_joint_angles
from logic.exercise_detector import ExerciseDetector
from shared.exercise_state_schema import ExerciseStage, FeedbackSeverity

# --- New MediaPipe Tasks API ---
BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
VisionRunningMode = mp.tasks.vision.RunningMode

# --- Pose connections for drawing skeleton manually ---
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24), (23, 25), (24, 26),
    (25, 27), (26, 28), (27, 29), (28, 30), (29, 31), (30, 32)
]

LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index"
]

# --- Download model if needed ---
MODEL_PATH = "pose_landmarker.task"
if not os.path.exists(MODEL_PATH):
    import urllib.request
    print("Downloading pose landmarker model (~5MB)...")
    urllib.request.urlretrieve(
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        MODEL_PATH
    )
    print("Model downloaded!")


def landmarks_to_dict(result):
    """Convert MediaPipe result to our landmark dict format."""
    landmarks = {}
    if result.pose_landmarks:
        for idx, lm in enumerate(result.pose_landmarks[0]):
            name = LANDMARK_NAMES[idx]
            landmarks[name] = {
                "x": lm.x,
                "y": lm.y,
                "z": lm.z,
                "visibility": lm.presence
            }
    return landmarks


def draw_skeleton(frame, result):
    """Manually draw skeleton using cv2 lines and circles."""
    if not result.pose_landmarks:
        return frame

    h, w = frame.shape[:2]
    lms = result.pose_landmarks[0]

    # Draw connections
    for start_idx, end_idx in POSE_CONNECTIONS:
        start = lms[start_idx]
        end = lms[end_idx]
        x1, y1 = int(start.x * w), int(start.y * h)
        x2, y2 = int(end.x * w), int(end.y * h)
        cv2.line(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

    # Draw joints
    for lm in lms:
        x, y = int(lm.x * w), int(lm.y * h)
        cv2.circle(frame, (x, y), 4, (255, 255, 255), -1)

    return frame


def draw_overlay(frame, state):
    """Draw rep count, stage and feedback on the frame."""
    cv2.rectangle(frame, (0, 0), (420, 170), (0, 0, 0), -1)

    cv2.putText(frame, f"Exercise: {state.exercise.value.upper()}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    stage_color = (0, 255, 0) if state.stage == ExerciseStage.STANDING else (0, 165, 255)
    cv2.putText(frame, f"Stage: {state.stage.value.upper()}",
                (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, stage_color, 2)

    cv2.putText(frame, f"Reps: {state.rep_count}",
                (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

    y = 135
    for flag in state.feedback_flags:
        if flag.severity == FeedbackSeverity.WARNING:
            color = (0, 165, 255)
        elif flag.severity == FeedbackSeverity.ERROR:
            color = (0, 0, 255)
        else:
            color = (0, 255, 0)
        cv2.putText(frame, f"{flag.code}: {flag.message}",
                    (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        y += 28

    return frame


def run(video_path: str, exercise: str = "squat"):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: Could not open video: {video_path}")
        return

    detector = ExerciseDetector(exercise=exercise)
    print(f"Running on: {video_path}")
    print("Press Q to quit, SPACE to pause")

    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionRunningMode.IMAGE
    )

    paused = False

    with PoseLandmarker.create_from_options(options) as landmarker:
        while True:
            if not paused:
                ret, frame = cap.read()
                if not ret:
                    print("Video ended.")
                    break

                frame = cv2.resize(frame, (960, 540))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                result = landmarker.detect(mp_image)

                frame = draw_skeleton(frame, result)
                landmarks = landmarks_to_dict(result)

                if landmarks:
                    state = detector.update(landmarks)
                    frame = draw_overlay(frame, state)

            cv2.imshow("Virtual Trainer - Visualizer", frame)
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                break
            elif key == ord(' '):
                paused = not paused

    cap.release()
    cv2.destroyAllWindows()
    print(f"\nFinal rep count: {detector.rep_count}")


if __name__ == "__main__":
    VIDEO_PATH = "test_squat.mp4"
    run(VIDEO_PATH, exercise="squat")