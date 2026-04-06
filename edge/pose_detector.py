import os
import cv2
import numpy as np
import mediapipe as mp
import time
from collections import deque
from typing import Any, Dict, NamedTuple

from mediapipe.tasks import python as _mp_tasks
from mediapipe.tasks.python import vision as _mp_vision

BaseOptions = mp.tasks.BaseOptions
PoseLandmarker = mp.tasks.vision.PoseLandmarker
PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
RunningMode = mp.tasks.vision.RunningMode

# MediaPipe Pose 33 landmarks using official PoseLandmark enum names
LANDMARK_NAMES = [
    "NOSE",
    "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER",
    "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER",
    "LEFT_EAR", "RIGHT_EAR",
    "MOUTH_LEFT", "MOUTH_RIGHT",
    "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "LEFT_ELBOW", "RIGHT_ELBOW",
    "LEFT_WRIST", "RIGHT_WRIST",
    "LEFT_PINKY", "RIGHT_PINKY",
    "LEFT_INDEX", "RIGHT_INDEX",
    "LEFT_THUMB", "RIGHT_THUMB",
    "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE",
    "LEFT_ANKLE", "RIGHT_ANKLE",
    "LEFT_HEEL", "RIGHT_HEEL",
    "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
]

class PoseDetectionResult(NamedTuple):
    detected: bool
    landmarks: Any
    fps: float
    latency_ms: float
    frame_idx: int
    error: str
    dropped_frames: int


def get_landmarks_from_result(detection_result, image_shape):
    """Extract clean landmark data from MediaPipe result.
    
    Returns list of landmarks with MediaPipe PoseLandmark names.
    No angle computation - pure landmark data only.
    """
    if not detection_result.pose_landmarks:
        return []

    height, width = image_shape[:2]
    landmarks = []

    for idx, lmk in enumerate(detection_result.pose_landmarks[0]):
        name = LANDMARK_NAMES[idx] if idx < len(LANDMARK_NAMES) else f"LANDMARK_{idx}"
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
        }
        landmarks.append(data)

    return landmarks


class PoseDetector:
    """MediaPipe Pose detector with latency tracking and frame skip logic.
    
    Phase 2 architecture: Clean landmark extraction only.
    No angle computation, no exercise logic.
    """
    
    def __init__(self,
                 model_complexity=1,
                 min_detection_conf=0.5,
                 min_tracking_conf=0.5,
                 target_fps=15,
                 max_latency_ms=100):
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
        self.max_latency_ms = max_latency_ms
        self._frame_times = deque(maxlen=30)
        self._latency_samples = deque(maxlen=100)  # For P95 calculation
        self._frame_idx = 0
        self._dropped_frames = 0

    def close(self):
        self._landmarker.close()

    def detect(self, jpeg_bytes):
        """Detect pose landmarks from JPEG frame with frame skip logic.
        
        Skips frames when latency > max_latency_ms to maintain real-time performance.
        Returns clean landmark data only (no angles, no logic).
        """
        npimg = np.frombuffer(jpeg_bytes, np.uint8)
        image = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        if image is None:
            return PoseDetectionResult(
                detected=False,
                landmarks=[],
                fps=0.0,
                latency_ms=0.0,
                frame_idx=self._frame_idx,
                error="frame_decode_error",
                dropped_frames=self._dropped_frames,
            )

        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        now = time.time()
        elapsed = now - self.last_time
        
        # Throttle to target FPS
        if elapsed < 1.0 / self.target_fps:
            return PoseDetectionResult(
                detected=False,
                landmarks=[],
                fps=self._calculate_fps(),
                latency_ms=elapsed * 1000,
                frame_idx=self._frame_idx,
                error="throttled",
                dropped_frames=self._dropped_frames,
            )

        self.last_time = now
        self._frame_idx += 1

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)

        start = time.perf_counter()
        detection_result = self._landmarker.detect(mp_image)
        latency_ms = (time.perf_counter() - start) * 1000
        
        # Track latency for P95 calculation
        self._latency_samples.append(latency_ms)
        
        # Frame skip logic: drop frame if latency exceeds threshold
        if latency_ms > self.max_latency_ms:
            self._dropped_frames += 1
            return PoseDetectionResult(
                detected=False,
                landmarks=[],
                fps=self._calculate_fps(),
                latency_ms=latency_ms,
                frame_idx=self._frame_idx,
                error="latency_exceeded",
                dropped_frames=self._dropped_frames,
            )

        detected = bool(detection_result.pose_landmarks)
        landmarks = get_landmarks_from_result(detection_result, image.shape)

        self._frame_times.append(now)
        fps = self._calculate_fps()

        return PoseDetectionResult(
            detected=detected,
            landmarks=landmarks,
            fps=fps,
            latency_ms=latency_ms,
            frame_idx=self._frame_idx,
            error="",
            dropped_frames=self._dropped_frames,
        )
    
    def _calculate_fps(self) -> float:
        """Calculate current FPS from frame time samples."""
        if len(self._frame_times) > 1:
            return len(self._frame_times) / (self._frame_times[-1] - self._frame_times[0])
        return 0.0
    
    def get_latency_stats(self) -> Dict[str, float]:
        """Get latency statistics for monitoring.
        
        Returns:
            dict with avg, min, max, p95 latency in milliseconds
        """
        if not self._latency_samples:
            return {"avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0}
        
        samples = sorted(self._latency_samples)
        return {
            "avg": sum(samples) / len(samples),
            "min": samples[0],
            "max": samples[-1],
            "p95": samples[int(len(samples) * 0.95)] if len(samples) > 0 else 0.0,
        }