import io
import cv2
import numpy as np
import mediapipe as mp
import time
from collections import deque
from typing import Any, Dict, NamedTuple

mp_pose = mp.solutions.pose

class PoseDetectionResult(NamedTuple):
    detected: bool
    landmarks: Any
    angles: Dict[str, float]
    fps: float
    latency_ms: float
    frame_idx: int
    error: str

def get_landmarks_from_result(results, image_shape):
    if not results.pose_landmarks:
        return [], {}, {}

    height, width = image_shape[:2]
    landmarks = []
    landmark_dict = {}
    for idx, lmk in enumerate(results.pose_landmarks.landmark):
        name = mp_pose.PoseLandmark(idx).name.lower()
        px, py = int(lmk.x * width), int(lmk.y * height)
        data = {
            "name": name,
            "x": float(lmk.x),
            "y": float(lmk.y),
            "z": float(lmk.z),
            "visibility": float(lmk.visibility),
            "px": px,
            "py": py,
            "visible": lmk.visibility > 0.98,
        }
        landmarks.append(data)
        landmark_dict[name] = data

    # Example angle calculation, real implementations should be more robust
    def angle(a, b, c):
        a = np.array([a["x"], a["y"]])
        b = np.array([b["x"], b["y"]])
        c = np.array([c["x"], c["y"]])
        ba = a - b
        bc = c - b
        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc))
        angle = np.arccos(cosine_angle)
        return np.degrees(angle)

    angles = {}
    try:
        angles["left_knee"] = angle(landmark_dict["left_hip"], landmark_dict["left_knee"], landmark_dict["left_ankle"])
        angles["right_knee"] = angle(landmark_dict["right_hip"], landmark_dict["right_knee"], landmark_dict["right_ankle"])
        angles["back"] = angle(landmark_dict["left_shoulder"], landmark_dict["left_hip"], landmark_dict["left_knee"])
        angles["left_elbow"] = angle(landmark_dict["left_shoulder"], landmark_dict["left_elbow"], landmark_dict["left_wrist"])
        angles["right_elbow"] = angle(landmark_dict["right_shoulder"], landmark_dict["right_elbow"], landmark_dict["right_wrist"])
    except Exception:
        pass

    return landmarks, landmark_dict, angles

class PoseDetector:
    def __init__(self,
                 model_complexity=1,
                 min_detection_conf=0.5,
                 min_tracking_conf=0.5,
                 target_fps=15):
        self.pose = mp_pose.Pose(
            model_complexity=model_complexity,
            min_detection_confidence=min_detection_conf,
            min_tracking_confidence=min_tracking_conf,
            enable_segmentation=False)
        self.last_time = time.time()
        self.target_fps = target_fps
        self._frame_times = deque(maxlen=30)
        self._frame_idx = 0

    def close(self):
        self.pose.close()

    def detect(self, jpeg_bytes):
        t0 = time.time()
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

        # Throttle input to not overload CPU
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

        start = time.perf_counter()
        results = self.pose.process(image_rgb)
        latency_ms = (time.perf_counter() - start) * 1000

        detected = results.pose_landmarks is not None
        landmarks, landmark_dict, angles = get_landmarks_from_result(results, image.shape)

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