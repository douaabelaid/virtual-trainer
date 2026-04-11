"""
pose_detector.py
Decodes JPEG frames, runs MediaPipe Pose, returns landmarks + joint angles.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import os

import cv2
import mediapipe as mp




from mediapipe.tasks import python as _mp_tasks
from mediapipe.tasks.python import vision as _mp_vision

import numpy as np

_TASK_MODEL = os.path.join(os.path.dirname(__file__), "..", "pose_landmarker.task")

logger = logging.getLogger("pose_detector")

# ── 33 MediaPipe landmark names ───────────────────────────────────────────────
LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
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

# ── Joint angle triplets (vertex is the middle landmark) ─────────────────────
ANGLE_TRIPLETS: dict[str, tuple[str, str, str]] = {
    "left_knee":      ("left_hip",       "left_knee",      "left_ankle"),
    "right_knee":     ("right_hip",      "right_knee",     "right_ankle"),
    "left_hip":       ("left_shoulder",  "left_hip",       "left_knee"),
    "right_hip":      ("right_shoulder", "right_hip",      "right_knee"),
    "left_elbow":     ("left_shoulder",  "left_elbow",     "left_wrist"),
    "right_elbow":    ("right_shoulder", "right_elbow",    "right_wrist"),
    "left_shoulder":  ("left_elbow",     "left_shoulder",  "left_hip"),
    "right_shoulder": ("right_elbow",    "right_shoulder", "right_hip"),
}

TARGET_FPS     = 15
FRAME_INTERVAL = 1.0 / TARGET_FPS   # 66.7 ms


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class PoseResult:
    detected:   bool
    landmarks:  list                  # 33 dicts or []
    angles:     dict                  # joint_name → float degrees
    fps:        float
    latency_ms: float
    frame_idx:  int
    error:      Optional[str] = None


# ── Detector ──────────────────────────────────────────────────────────────────

class PoseDetector:
    """
    Wraps MediaPipe Pose for a single client session.

    detector = PoseDetector()
    result   = detector.detect(jpeg_bytes)
    detector.close()
    """

    def __init__(
        self,
        model_complexity:   int   = 1,
        min_detection_conf: float = 0.5,
        min_tracking_conf:  float = 0.5,
        target_fps:         int   = TARGET_FPS,
        min_visibility:     float = 0.5,
    ) -> None:
        self._min_visibility  = min_visibility
        self._frame_interval  = 1.0 / target_fps
        self._target_fps      = target_fps
        self._fps_ema         = float(target_fps)
        self._frame_idx       = 0
        self._last_t          = 0.0

        _model_path = os.path.join(os.path.dirname(__file__), "..", "pose_landmarker.task")
        _base_opts  = _mp_tasks.BaseOptions(model_asset_path=_model_path)
        _options    = _mp_vision.PoseLandmarkerOptions(
            base_options=_base_opts,
            running_mode=_mp_vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=min_detection_conf,
            min_pose_presence_confidence=min_detection_conf,
            min_tracking_confidence=min_tracking_conf,
            output_segmentation_masks=False,
        )
        self._pose = _mp_vision.PoseLandmarker.create_from_options(_options)
        logger.info(
            f"✅ PoseDetector ready  "
            f"(complexity={model_complexity}, target={target_fps} FPS)"
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        if self._pose is not None:
            self._pose.close()
            self._pose = None
            logger.info("🔒 PoseDetector closed")

    def __enter__(self):  return self
    def __exit__(self, *_): self.close()

    # ── Main API ──────────────────────────────────────────────────────────────

    def detect_bgr(self, frame: np.ndarray) -> "PoseResult":
        """
        Process a raw BGR frame directly (no JPEG encode/decode round-trip).
        Use this when the frame comes from a local webcam — saves ~5-10 ms
        per frame compared to detect(jpeg_bytes).
        """
        t0 = time.perf_counter()

        if self._frame_idx > 0 and (t0 - self._last_t) < self._frame_interval:
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1), latency_ms=0.0,
                frame_idx=self._frame_idx, error="throttled",
            )

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        try:
            results = self._pose.process(rgb)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error(f"MediaPipe error: {exc}", exc_info=True)
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1), latency_ms=0.0,
                frame_idx=self._frame_idx, error=f"mediapipe_error: {exc}",
            )

        t1              = time.perf_counter()
        elapsed         = t1 - self._last_t if self._last_t else 1.0 / self._target_fps
        self._fps_ema   = 0.8 * self._fps_ema + 0.2 * (1.0 / elapsed)
        self._last_t    = t1
        self._frame_idx += 1
        latency_ms      = (t1 - t0) * 1000

        if not results.pose_landmarks:
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1),
                latency_ms=round(latency_ms, 2),
                frame_idx=self._frame_idx,
            )

        h, w    = frame.shape[:2]
        lm_list = []
        lm_map: dict[str, dict] = {}
        for i, lm in enumerate(results.pose_landmarks.landmark):
            name    = LANDMARK_NAMES[i] if i < len(LANDMARK_NAMES) else f"lm_{i}"
            visible = lm.visibility >= self._min_visibility
            entry   = {
                "name": name, "x": round(lm.x, 4), "y": round(lm.y, 4),
                "z": round(lm.z, 4), "visibility": round(lm.visibility, 3),
                "px": int(lm.x * w), "py": int(lm.y * h), "visible": visible,
            }
            lm_list.append(entry)
            lm_map[name] = entry

        return PoseResult(
            detected=True, landmarks=lm_list, angles=_compute_angles(lm_map),
            fps=round(self._fps_ema, 1), latency_ms=round(latency_ms, 2),
            frame_idx=self._frame_idx,
        )

    def detect(self, jpeg_bytes: bytes) -> PoseResult:
        """
        Process one JPEG frame received from the mobile app.
        Returns PoseResult with landmarks and joint angles.
        Throttles to target_fps — returns error="throttled" if called too fast.
        """
        t0 = time.perf_counter()

        # ── FPS throttle ──────────────────────────────────────────────────────
        if self._frame_idx > 0 and (t0 - self._last_t) < self._frame_interval:
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1), latency_ms=0.0,
                frame_idx=self._frame_idx, error="throttled",
            )

        # ── Decode JPEG → BGR frame ───────────────────────────────────────────
        try:
            arr   = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("imdecode returned None — invalid JPEG")
        except Exception as exc:
            logger.warning(f"Decode error: {exc}")
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1), latency_ms=0.0,
                frame_idx=self._frame_idx, error=f"decode_error: {exc}",
            )

        # ── MediaPipe inference ───────────────────────────────────────────────
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results  = self._pose.detect(mp_image)
        except Exception as exc:
            logger.error(f"MediaPipe error: {exc}", exc_info=True)
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1), latency_ms=0.0,
                frame_idx=self._frame_idx, error=f"mediapipe_error: {exc}",
            )

        # ── Update timing ─────────────────────────────────────────────────────
        t1              = time.perf_counter()
        elapsed         = t1 - self._last_t if self._last_t else 1.0 / self._target_fps
        instant_fps     = 1.0 / elapsed
        self._fps_ema   = 0.8 * self._fps_ema + 0.2 * instant_fps   # EMA
        self._last_t    = t1
        self._frame_idx += 1
        latency_ms      = (t1 - t0) * 1000

        # ── No person in frame ────────────────────────────────────────────────
        if not results.pose_landmarks:
            return PoseResult(
                detected=False, landmarks=[], angles={},
                fps=round(self._fps_ema, 1),
                latency_ms=round(latency_ms, 2),
                frame_idx=self._frame_idx,
            )

        # ── Build landmark list ───────────────────────────────────────────────
        h, w    = frame.shape[:2]
        lm_list = []
        lm_map: dict[str, dict] = {}

        for i, lm in enumerate(results.pose_landmarks[0]):
            name    = LANDMARK_NAMES[i] if i < len(LANDMARK_NAMES) else f"lm_{i}"
            visible = lm.visibility >= self._min_visibility
            entry   = {
                "name":       name,
                "x":          round(lm.x, 4),        # normalised 0–1
                "y":          round(lm.y, 4),
                "z":          round(lm.z, 4),        # depth (hips = 0)
                "visibility": round(lm.visibility, 3),
                "px":         int(lm.x * w),         # pixel x
                "py":         int(lm.y * h),         # pixel y
                "visible":    visible,
            }
            lm_list.append(entry)
            lm_map[name] = entry

        # ── Compute joint angles ──────────────────────────────────────────────
        angles = _compute_angles(lm_map)

        return PoseResult(
            detected=True,
            landmarks=lm_list,
            angles=angles,
            fps=round(self._fps_ema, 1),
            latency_ms=round(latency_ms, 2),
            frame_idx=self._frame_idx,
        )

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def frame_count(self) -> int:
        return self._frame_idx

    @property
    def current_fps(self) -> float:
        return round(self._fps_ema, 1)


# ── Geometry ──────────────────────────────────────────────────────────────────

def _vec2d(a: dict, b: dict) -> np.ndarray:
    """Vector from b → a using normalised x, y."""
    return np.array([a["x"] - b["x"], a["y"] - b["y"]], dtype=np.float32)


def _angle_deg(v1: np.ndarray, v2: np.ndarray) -> float:
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cos_a = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
    return round(float(np.degrees(np.arccos(cos_a))), 1)


def _compute_angles(lm_map: dict) -> dict:
    angles: dict[str, float] = {}

    for joint, (a_name, b_name, c_name) in ANGLE_TRIPLETS.items():
        a = lm_map.get(a_name)
        b = lm_map.get(b_name)
        c = lm_map.get(c_name)
        if not (a and b and c):
            continue
        if not (a["visible"] and b["visible"] and c["visible"]):
            continue
        angles[joint] = _angle_deg(_vec2d(a, b), _vec2d(c, b))

    # Symmetric averages for convenience (avg_knee, avg_hip, etc.)
    for part in ("knee", "hip", "elbow", "shoulder"):
        l = angles.get(f"left_{part}")
        r = angles.get(f"right_{part}")
        if l is not None and r is not None:
            angles[f"avg_{part}"] = round((l + r) / 2, 1)
        elif l is not None:
            angles[f"avg_{part}"] = l
        elif r is not None:
            angles[f"avg_{part}"] = r

    return angles


# ── Webcam live demo (python edge/pose_detector.py) ───────────────────────────

if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    mp_drawing       = mp.solutions.drawing_utils
    mp_drawing_styles = mp.solutions.drawing_styles
    mp_pose          = mp.solutions.pose

    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        logger.error("❌ Cannot open webcam (index 0)")
        sys.exit(1)

    logger.info("📷 Webcam opened — press Q to quit")

    with mp_pose.Pose(
        model_complexity=1,
        smooth_landmarks=True,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("⚠️  Failed to read frame")
                break

            h, w = frame.shape[:2]

            # MediaPipe requires RGB, non-writeable for performance
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = pose.process(rgb)
            rgb.flags.writeable = True

            # Draw skeleton overlay
            if results.pose_landmarks:
                mp_drawing.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
                )

                # Build landmark JSON and print to terminal
                lm_list = []
                lm_map: dict[str, dict] = {}
                for i, lm in enumerate(results.pose_landmarks.landmark):
                    name    = LANDMARK_NAMES[i] if i < len(LANDMARK_NAMES) else f"lm_{i}"
                    visible = lm.visibility >= 0.5
                    entry   = {
                        "name":       name,
                        "x":          round(lm.x, 4),
                        "y":          round(lm.y, 4),
                        "z":          round(lm.z, 4),
                        "visibility": round(lm.visibility, 3),
                        "px":         int(lm.x * w),
                        "py":         int(lm.y * h),
                        "visible":    visible,
                    }
                    lm_list.append(entry)
                    lm_map[name] = entry

                angles = _compute_angles(lm_map)
                payload = {"landmarks": lm_list, "angles": angles}
                print(json.dumps(payload, separators=(",", ":")), flush=True)

                # Overlay FPS / angle hints on frame
                cv2.putText(
                    frame,
                    f"left_knee:{angles.get('left_knee', '--')}  "
                    f"right_knee:{angles.get('right_knee', '--')}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2,
                )
            else:
                cv2.putText(
                    frame, "No pose detected", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2,
                )

            cv2.imshow("Pose Detector", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()
    logger.info("👋 Webcam closed")
