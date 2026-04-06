import os
import cv2
import numpy as np
import mediapipe as mp
import time
from collections import deque
from typing import Any, Dict, NamedTuple

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
RunningMode = mp.tasks.vision.RunningMode

LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear",
    "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky",
    "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
    "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]

class PoseDetectionResult(NamedTuple):
    detected: bool
    landmarks: Any
    angles: Dict[str, float]
    fps: float
    latency_ms: float
    frame_idx: int
    error: str


def _angle(a, b, c):
    a = np.array([a["x"], a["y"]])
    b = np.array([b["x"], b["y"]])
    c = np.array([c["x"], c["y"]])
    ba = a - b
    bc = c - b
    denom = np.linalg.norm(ba) * np.linalg.norm(bc)
    if denom == 0:
        return 0.0
    cosine_angle = np.clip(np.dot(ba, bc) / denom, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine_angle)))


def get_landmarks_from_result(detection_result, image_shape):
    if not detection_result.pose_landmarks:
        return [], {}, {}

    height, width = image_shape[:2]
    landmarks = []
    landmark_dict = {}

    for idx, lmk in enumerate(detection_result.pose_landmarks[0]):
        name = LANDMARK_NAMES[idx] if idx < len(LANDMARK_NAMES) else f"landmark_{idx}"
        px, py = int(lmk.x * width), int(lmk.y * height)
        visibility = float(lmk.visibility) if lmk.visibility is not None else 0.0
        data = {
            "name": name,
            "x": float(lmk.x),
            "y": float(lmk.y),
            "z": float(lmk.z),
            "visibility": visibility,
            "px": px,
            "py": py,
            "visible": visibility > 0.98,
        }
        landmarks.append(data)
        landmark_dict[name] = data

    angles = {}
    try:
        angles["left_knee"] = _angle(landmark_dict["left_hip"], landmark_dict["left_knee"], landmark_dict["left_ankle"])
        angles["right_knee"] = _angle(landmark_dict["right_hip"], landmark_dict["right_knee"], landmark_dict["right_ankle"])
        angles["back"] = _angle(landmark_dict["left_shoulder"], landmark_dict["left_hip"], landmark_dict["left_knee"])
        angles["left_elbow"] = _angle(landmark_dict["left_shoulder"], landmark_dict["left_elbow"], landmark_dict["left_wrist"])
        angles["right_elbow"] = _angle(landmark_dict["right_shoulder"], landmark_dict["right_elbow"], landmark_dict["right_wrist"])
    except Exception:
        pass

    return landmarks, landmark_dict, angles


class PoseDetector:
    def __init__(self,
                 model_complexity=1,
                 min_detection_conf=0.5,
                 min_tracking_conf=0.5,
                 target_fps=15):
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pose_landmarker.task")
        if not os.path.exists(model_path):
            model_path = "pose_landmarker.task"

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=model_path),
            running_mode=RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=min_detection_conf,
            min_pose_presence_confidence=min_detection_conf,
            min_tracking_confidence=min_tracking_conf,
            output_segmentation_masks=False,
        )
        self._landmarker = PoseLandmarker.create_from_options(options)
        self.last_time = time.time()
        self.target_fps = target_fps
        self._frame_times = deque(maxlen=30)
        self._frame_idx = 0

    def close(self):
        self._landmarker.close()

    def detect(self, jpeg_bytes):
        npimg = np.frombuffer(jpeg_bytes, np.uint8)
        image = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if image is None:
            return PoseDetectionResult(
                detected=False,
                landmarks=[],
                angles={},
                fps=0.0,
                latency_ms=0.0,
                frame_idx=self._frame_idx,
                error="frame_decode_error"
            )

        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        now = time.time()
        elapsed = now - self.last_time
        if elapsed < 1.0 / self.target_fps:
            return PoseDetectionResult(
                detected=False,
                landmarks=[],
                angles={},
                fps=1.0 / (self._frame_times[-1] - self._frame_times[0]) if len(self._frame_times) > 1 else 0.0,
                latency_ms=elapsed * 1000,
                frame_idx=self._frame_idx,
                error="throttled"
            )

        self.last_time = now
        self._frame_idx += 1

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

        start = time.perf_counter()
        detection_result = self._landmarker.detect(mp_image)
        latency_ms = (time.perf_counter() - start) * 1000

        detected = bool(detection_result.pose_landmarks)
        landmarks, landmark_dict, angles = get_landmarks_from_result(detection_result, image.shape)

        self._frame_times.append(now)
        fps = len(self._frame_times) / (self._frame_times[-1] - self._frame_times[0]) if len(self._frame_times) > 1 else 0.0

        return PoseDetectionResult(
            detected=detected,
            landmarks=landmarks,
            angles=angles,
            fps=fps,
            latency_ms=latency_ms,
            frame_idx=self._frame_idx,
            error=""
        )