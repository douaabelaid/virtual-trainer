"""
BIOMECHANICS.PY
Analyses squat / pushup / plank from MediaPipe Pose 33-landmark output.
Consumed by ws_server.py — no camera dependency.

NOTE: This module uses the legacy MediaPipe solutions API (mp.solutions.pose).
It is NOT part of the main ws_server pipeline (which uses the Tasks API via
pose_detector.py). Keep this file separate from that pipeline.
"""
import logging
import mediapipe as mp
import numpy as np
from enum import Enum
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────────

class ExerciseType(Enum):
    SQUAT  = "squat"
    PUSHUP = "pushup"
    PLANK  = "plank"


class MovementPhase(Enum):
    IDLE       = "idle"
    DESCENDING = "descending"
    BOTTOM     = "bottom"
    ASCENDING  = "ascending"
    TOP        = "top"


# ── MediaPipe Pose landmark indices (from PoseLandmark enum) ────────────────
_PL            = mp.solutions.pose.PoseLandmark
NOSE           = _PL.NOSE.value
LEFT_EYE       = _PL.LEFT_EYE.value;       RIGHT_EYE       = _PL.RIGHT_EYE.value
LEFT_EAR       = _PL.LEFT_EAR.value;       RIGHT_EAR       = _PL.RIGHT_EAR.value
LEFT_SHOULDER  = _PL.LEFT_SHOULDER.value;  RIGHT_SHOULDER  = _PL.RIGHT_SHOULDER.value
LEFT_ELBOW     = _PL.LEFT_ELBOW.value;     RIGHT_ELBOW     = _PL.RIGHT_ELBOW.value
LEFT_WRIST     = _PL.LEFT_WRIST.value;     RIGHT_WRIST     = _PL.RIGHT_WRIST.value
LEFT_HIP       = _PL.LEFT_HIP.value;       RIGHT_HIP       = _PL.RIGHT_HIP.value
LEFT_KNEE      = _PL.LEFT_KNEE.value;      RIGHT_KNEE      = _PL.RIGHT_KNEE.value
LEFT_ANKLE     = _PL.LEFT_ANKLE.value;     RIGHT_ANKLE     = _PL.RIGHT_ANKLE.value


class BiomechanicsAnalyzer:
    """
    Stateful analyser for one mobile client session.
    Receives MediaPipe Pose 33 landmarks from PoseDetector.
    """

    VISIBILITY_THRESHOLD       = 0.3
    ASYMMETRY_THRESHOLD_SQUAT  = 15.0
    ASYMMETRY_THRESHOLD_PUSHUP = 20.0
    BACK_BENT_THRESHOLD        = 160.0
    KNEES_INWARD_RATIO         = 0.8

    def __init__(self, config: dict) -> None:
        self.config           = config
        self.current_exercise = ExerciseType.SQUAT
        self.current_phase    = MovementPhase.IDLE
        self.previous_phase   = MovementPhase.IDLE
        self.rep_count        = 0
        self.history_size     = 5
        self.angle_history: Dict[str, List[float]] = {
            'left_knee':  [], 'right_knee':  [],
            'left_hip':   [], 'right_hip':   [],
            'left_elbow': [], 'right_elbow': [],
        }
        logger.info("✅ BiomechanicsAnalyzer ready")

    # ── Config helpers ────────────────────────────────────────────────────────

    def _cfg(self, section: str, key: str, default):
        return self.config.get(section, {}).get(key, default)

    # ── Geometry ──────────────────────────────────────────────────────────────

    def calculate_angle(
        self,
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        p3: Tuple[float, float],
    ) -> float:
        v1 = np.array([p1[0] - p2[0], p1[1] - p2[1]])
        v2 = np.array([p3[0] - p2[0], p3[1] - p2[1]])
        n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
        if n1 == 0 or n2 == 0:
            return 0.0
        cos_a = np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_a)))

    def smooth_angle(self, angle: float, joint: str) -> float:
        if joint not in self.angle_history:
            return angle
        self.angle_history[joint].append(angle)
        if len(self.angle_history[joint]) > self.history_size:
            self.angle_history[joint].pop(0)
        return float(np.mean(self.angle_history[joint]))

    def get_landmark_coords(
        self,
        landmarks: List[Dict],
        idx: int,
    ) -> Tuple[float, float]:
        if idx >= len(landmarks):
            return (0.0, 0.0)
        lm = landmarks[idx]
        return (lm.get('x', 0.0), lm.get('y', 0.0))

    def _is_visible(self, landmarks: List[Dict], *ids: int) -> bool:
        return all(
            i < len(landmarks) and
            landmarks[i].get('visibility', 1.0) >= self.VISIBILITY_THRESHOLD
            for i in ids
        )

    # ── Phase & rep counting ──────────────────────────────────────────────────

    def _update_phase_and_count(
        self,
        new_phase:   MovementPhase,
        rep_trigger: MovementPhase,
        rep_name:    str = "Rep",
    ) -> None:
        if (self.previous_phase == rep_trigger and
                new_phase == MovementPhase.ASCENDING):
            self.rep_count += 1
            logger.info(f"🔢 {rep_name} #{self.rep_count}")
        self.previous_phase = new_phase
        self.current_phase  = new_phase

    # ── Squat ─────────────────────────────────────────────────────────────────

    def analyze_squat(self, landmarks: List[Dict]) -> Dict:
        l_hip  = self.get_landmark_coords(landmarks, LEFT_HIP)
        r_hip  = self.get_landmark_coords(landmarks, RIGHT_HIP)
        l_knee = self.get_landmark_coords(landmarks, LEFT_KNEE)
        r_knee = self.get_landmark_coords(landmarks, RIGHT_KNEE)
        l_ank  = self.get_landmark_coords(landmarks, LEFT_ANKLE)
        r_ank  = self.get_landmark_coords(landmarks, RIGHT_ANKLE)
        l_sho  = self.get_landmark_coords(landmarks, LEFT_SHOULDER)
        r_sho  = self.get_landmark_coords(landmarks, RIGHT_SHOULDER)

        lk = self.smooth_angle(
            self.calculate_angle(l_hip,  l_knee, l_ank),  'left_knee')
        rk = self.smooth_angle(
            self.calculate_angle(r_hip,  r_knee, r_ank),  'right_knee')
        lh = self.smooth_angle(
            self.calculate_angle(l_sho,  l_hip,  l_knee), 'left_hip')
        rh = self.smooth_angle(
            self.calculate_angle(r_sho,  r_hip,  r_knee), 'right_hip')

        avg_knee = (lk + rk) / 2
        avg_hip  = (lh + rh) / 2

        phase  = self._squat_phase(avg_knee)
        self._update_phase_and_count(phase, MovementPhase.BOTTOM, "Squat")
        errors = self._squat_errors(lk, rk, lh, rh, avg_knee, landmarks)

        return {
            'angles': {
                'left_knee':  round(lk, 1), 'right_knee': round(rk, 1),
                'left_hip':   round(lh, 1), 'right_hip':  round(rh, 1),
                'avg_knee':   round(avg_knee, 1),
                'avg_hip':    round(avg_hip,  1),
            },
            'phase':     phase,
            'errors':    errors,
            'rep_count': self.rep_count,
        }

    def _squat_phase(self, knee_angle: float) -> MovementPhase:
        min_k = self._cfg('squat', 'min_knee_angle', 85)
        max_k = self._cfg('squat', 'max_knee_angle', 160)
        if   knee_angle > max_k - 10:
            return MovementPhase.TOP
        elif knee_angle < min_k + 10:
            return MovementPhase.BOTTOM
        elif self.current_phase in (MovementPhase.TOP, MovementPhase.IDLE):
            return MovementPhase.DESCENDING
        else:
            return MovementPhase.ASCENDING

    def _squat_errors(
        self,
        lk: float, rk: float,
        lh: float, rh: float,
        avg_knee: float,
        landmarks: List[Dict],
    ) -> List[str]:
        errors = []
        min_k = self._cfg('squat', 'min_knee_angle', 85)

        if self.current_phase == MovementPhase.BOTTOM and avg_knee > min_k + 20:
            errors.append("depth_insufficient")
        if abs(lk - rk) > self.ASYMMETRY_THRESHOLD_SQUAT:
            errors.append("asymmetry")
        if self._is_visible(landmarks,
                            LEFT_KNEE, RIGHT_KNEE, LEFT_ANKLE, RIGHT_ANKLE):
            lkp = self.get_landmark_coords(landmarks, LEFT_KNEE)
            rkp = self.get_landmark_coords(landmarks, RIGHT_KNEE)
            lap = self.get_landmark_coords(landmarks, LEFT_ANKLE)
            rap = self.get_landmark_coords(landmarks, RIGHT_ANKLE)
            kd  = abs(lkp[0] - rkp[0])
            ad  = abs(lap[0] - rap[0])
            if ad > 0 and kd < ad * self.KNEES_INWARD_RATIO:
                errors.append("knees_inward")
        return errors

    # ── Pushup ────────────────────────────────────────────────────────────────

    def analyze_pushup(self, landmarks: List[Dict]) -> Dict:
        l_sho = self.get_landmark_coords(landmarks, LEFT_SHOULDER)
        r_sho = self.get_landmark_coords(landmarks, RIGHT_SHOULDER)
        l_elb = self.get_landmark_coords(landmarks, LEFT_ELBOW)
        r_elb = self.get_landmark_coords(landmarks, RIGHT_ELBOW)
        l_wri = self.get_landmark_coords(landmarks, LEFT_WRIST)
        r_wri = self.get_landmark_coords(landmarks, RIGHT_WRIST)
        l_hip = self.get_landmark_coords(landmarks, LEFT_HIP)

        le = self.smooth_angle(
            self.calculate_angle(l_sho, l_elb, l_wri), 'left_elbow')
        re = self.smooth_angle(
            self.calculate_angle(r_sho, r_elb, r_wri), 'right_elbow')
        avg_elbow  = (le + re) / 2
        back_angle = self.calculate_angle(
            l_sho, l_hip, (l_hip[0], l_hip[1] + 0.1))

        min_e = self._cfg('pushup', 'min_elbow_angle', 70)
        max_e = self._cfg('pushup', 'max_elbow_angle', 160)

        if   avg_elbow > max_e - 10:
            phase = MovementPhase.TOP
        elif avg_elbow < min_e + 10:
            phase = MovementPhase.BOTTOM
        elif self.current_phase in (MovementPhase.TOP, MovementPhase.IDLE):
            phase = MovementPhase.DESCENDING
        else:
            phase = MovementPhase.ASCENDING

        self._update_phase_and_count(phase, MovementPhase.BOTTOM, "Pushup")

        errors = []
        if abs(le - re) > self.ASYMMETRY_THRESHOLD_PUSHUP:
            errors.append("asymmetry")
        if back_angle < self.BACK_BENT_THRESHOLD:
            errors.append("back_bent")

        return {
            'angles': {
                'left_elbow':  round(le, 1),
                'right_elbow': round(re, 1),
                'avg_elbow':   round(avg_elbow, 1),
                'back':        round(back_angle, 1),
            },
            'phase':     phase,
            'errors':    errors,
            'rep_count': self.rep_count,
        }

    # ── Public API ────────────────────────────────────────────────────────────

    def set_exercise(self, exercise: ExerciseType) -> None:
        self.current_exercise = exercise
        self.reset()
        logger.info(f"🏋️  Exercise: {exercise.value}")

    def analyze(self, landmarks: List[Dict]) -> Dict:
        if   self.current_exercise == ExerciseType.SQUAT:
            return self.analyze_squat(landmarks)
        elif self.current_exercise == ExerciseType.PUSHUP:
            return self.analyze_pushup(landmarks)
        else:
            return {
                'angles': {}, 'phase': MovementPhase.IDLE,
                'errors': [], 'rep_count': 0,
            }

    def reset(self) -> None:
        self.rep_count      = 0
        self.current_phase  = MovementPhase.IDLE
        self.previous_phase = MovementPhase.IDLE
        for key in self.angle_history:
            self.angle_history[key] = []
        logger.info("🔄 Reset")