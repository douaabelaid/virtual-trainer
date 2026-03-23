"""
BIOMECHANICS.PY - Analyse biomécanique des mouvements
Updated to COCO 17 keypoints (YOLOv8-pose)
Date: 2026
"""

import numpy as np
from enum import Enum
from typing import List, Dict, Tuple, Optional
import logging 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ExerciseType(Enum):
    SQUAT  = "squat"
    PUSHUP = "pushup"
    PLANK  = "plank"


class MovementPhase(Enum):
    IDLE       = "idle"
    STARTING   = "starting"
    DESCENDING = "descending"
    BOTTOM     = "bottom"
    ASCENDING  = "ascending"
    TOP        = "top"


# COCO 17 Keypoint IDs
NOSE           = 0
LEFT_EYE       = 1;  RIGHT_EYE      = 2
LEFT_EAR       = 3;  RIGHT_EAR      = 4
LEFT_SHOULDER  = 5;  RIGHT_SHOULDER = 6
LEFT_ELBOW     = 7;  RIGHT_ELBOW    = 8
LEFT_WRIST     = 9;  RIGHT_WRIST    = 10
LEFT_HIP       = 11; RIGHT_HIP      = 12
LEFT_KNEE      = 13; RIGHT_KNEE     = 14
LEFT_ANKLE     = 15; RIGHT_ANKLE    = 16


class BiomechanicsAnalyzer:
    """
    Analyse les angles et détecte les erreurs de posture
    Utilise les 17 keypoints COCO de YOLOv8-pose
    """

    def __init__(self, config: dict) -> None:
        self.config: dict = config
        self.current_exercise: ExerciseType = ExerciseType.SQUAT
        self.current_phase: MovementPhase = MovementPhase.IDLE
        self.rep_count: int = 0
        self.previous_phase: MovementPhase = MovementPhase.IDLE

        self.angle_history : Dict[str, List[float]] = {
            'left_knee':   [],
            'right_knee':  [],
            'left_hip':    [],
            'right_hip':   [],
            'left_elbow':  [],
            'right_elbow': []
        }
        self.history_size: int = 5
        logger.info("✅ BiomechanicsAnalyzer initialisé (COCO 17 keypoints)")

    #Maths 

    def calculate_angle(
        self,
        point1: Tuple[float, float],
        point2: Tuple[float, float],
        point3: Tuple[float, float]
    ) -> float:
        """Calcule l'angle formé par 3 points en degrés"""
        v1 = np.array([point1[0] - point2[0], point1[1] - point2[1]])
        v2 = np.array([point3[0] - point2[0], point3[1] - point2[1]])

        dot  = np.dot(v1, v2)
        mag1 = np.linalg.norm(v1)
        mag2 = np.linalg.norm(v2)

        if mag1 == 0 or mag2 == 0:
            return 0.0

        cos_a = np.clip(dot / (mag1 * mag2), -1.0, 1.0)
        return float(np.degrees(np.arccos(cos_a)))

    def smooth_angle(self, angle: float, joint_name: str) -> float:
        """Lisse l'angle avec moyenne mobile"""
        if joint_name not in self.angle_history:
            return angle
        self.angle_history[joint_name].append(angle)
        if len(self.angle_history[joint_name]) > self.history_size:
            self.angle_history[joint_name].pop(0)
        return float(np.mean(self.angle_history[joint_name]))

    def get_landmark_coords(
        self,
        landmarks: List[Dict],
        landmark_id: int
    ) -> Tuple[float, float]:
        """Extrait (x, y) normalisées d'un landmark"""
        if landmark_id >= len(landmarks):
            return (0.0, 0.0)
        lm = landmarks[landmark_id]
        return (lm.get('x', 0.0), lm.get('y', 0.0))  # safe .get instead of direct key access

    def _is_visible(
        self,
        landmarks: List[Dict],
        *ids: int,
        threshold: float = 0.3
    ) -> bool:
        """Vérifie que tous les landmarks sont suffisamment visibles"""
        return all(
            i < len(landmarks) and
            landmarks[i].get('visibility', 1.0) >= threshold
            for i in ids
        )

    # Squat 
    def analyze_squat(self, landmarks: List[Dict]) -> Dict:
        """Analyse le squat avec COCO 17 keypoints"""

        l_hip      = self.get_landmark_coords(landmarks, LEFT_HIP)
        r_hip      = self.get_landmark_coords(landmarks, RIGHT_HIP)
        l_knee     = self.get_landmark_coords(landmarks, LEFT_KNEE)
        r_knee     = self.get_landmark_coords(landmarks, RIGHT_KNEE)
        l_ankle    = self.get_landmark_coords(landmarks, LEFT_ANKLE)
        r_ankle    = self.get_landmark_coords(landmarks, RIGHT_ANKLE)
        l_shoulder = self.get_landmark_coords(landmarks, LEFT_SHOULDER)
        r_shoulder = self.get_landmark_coords(landmarks, RIGHT_SHOULDER)

        # Angles genoux : hanche → genou → cheville
        l_knee_angle = self.smooth_angle(
            self.calculate_angle(l_hip, l_knee, l_ankle), 'left_knee')
        r_knee_angle = self.smooth_angle(
            self.calculate_angle(r_hip, r_knee, r_ankle), 'right_knee')

        # Angles hanches : épaule → hanche → genou
        l_hip_angle = self.smooth_angle(
            self.calculate_angle(l_shoulder, l_hip, l_knee), 'left_hip')
        r_hip_angle = self.smooth_angle(
            self.calculate_angle(r_shoulder, r_hip, r_knee), 'right_hip')

        avg_knee = (l_knee_angle + r_knee_angle) / 2
        avg_hip  = (l_hip_angle  + r_hip_angle)  / 2

        # Phase et reps
        phase = self._determine_squat_phase(avg_knee, avg_hip)

        self._update_phase_and_count(
            new_phase=phase,
            rep_trigger_phase=MovementPhase.BOTTOM,
            rep_name="Répétition"
        )

        errors = self._detect_squat_errors(
            l_knee_angle, r_knee_angle,
            l_hip_angle,  r_hip_angle,
            avg_knee, landmarks
        )

        return {
            'angles': {
                'left_knee':  l_knee_angle,
                'right_knee': r_knee_angle,
                'left_hip':   l_hip_angle,
                'right_hip':  r_hip_angle,
                'avg_knee':   avg_knee,
                'avg_hip':    avg_hip
            },
            'phase':     phase,
            'errors':    errors,
            'rep_count': self.rep_count
        }

    def _determine_squat_phase(
        self,
        knee_angle: float,
        hip_angle: float
    ) -> MovementPhase:
        config = self.config.get('squat', {})
        min_k  = config.get('min_knee_angle', 85)
        max_k  = config.get('max_knee_angle', 160)

        if knee_angle > max_k - 10:
            return MovementPhase.TOP
        elif knee_angle < min_k + 10:
            return MovementPhase.BOTTOM
        elif self.current_phase in [MovementPhase.TOP, MovementPhase.IDLE]:
            return MovementPhase.DESCENDING
        else:
            return MovementPhase.ASCENDING

    def _detect_squat_errors(
        self,
        left_knee: float, right_knee: float,
        left_hip: float,  right_hip: float,
        avg_knee: float,
        landmarks: List[Dict]
    ) -> List[str]:
        errors = []
        config = self.config.get('squat', {})
        min_k  = config.get('min_knee_angle', 85)

        # 1. Profondeur insuffisante
        if (self.current_phase == MovementPhase.BOTTOM and
                avg_knee > min_k + 20):
            errors.append("depth_insufficient")

        # 2. Asymétrie
        if abs(left_knee - right_knee) > 15:
            errors.append("asymmetry")

        # 3. Valgus genoux vers l'intérieur
        if self._is_visible(
                landmarks,
                LEFT_KNEE, RIGHT_KNEE,
                LEFT_ANKLE, RIGHT_ANKLE):
            l_kp = self.get_landmark_coords(landmarks, LEFT_KNEE)
            r_kp = self.get_landmark_coords(landmarks, RIGHT_KNEE)
            l_ap = self.get_landmark_coords(landmarks, LEFT_ANKLE)
            r_ap = self.get_landmark_coords(landmarks, RIGHT_ANKLE)

            knee_dist  = abs(l_kp[0] - r_kp[0])
            ankle_dist = abs(l_ap[0] - r_ap[0])

            if ankle_dist > 0 and knee_dist < ankle_dist * 0.8:
                errors.append("knees_inward")

        return errors

    # ── Pushup ────────────────────────────────────────────────────────────────

    def analyze_pushup(self, landmarks: List[Dict]) -> Dict:
        """Analyse les pompes avec COCO 17 keypoints"""

        l_shoulder = self.get_landmark_coords(landmarks, LEFT_SHOULDER)
        r_shoulder = self.get_landmark_coords(landmarks, RIGHT_SHOULDER)
        l_elbow    = self.get_landmark_coords(landmarks, LEFT_ELBOW)
        r_elbow    = self.get_landmark_coords(landmarks, RIGHT_ELBOW)
        l_wrist    = self.get_landmark_coords(landmarks, LEFT_WRIST)
        r_wrist    = self.get_landmark_coords(landmarks, RIGHT_WRIST)
        l_hip      = self.get_landmark_coords(landmarks, LEFT_HIP)

        l_elbow_angle = self.smooth_angle(
            self.calculate_angle(l_shoulder, l_elbow, l_wrist), 'left_elbow')
        r_elbow_angle = self.smooth_angle(
            self.calculate_angle(r_shoulder, r_elbow, r_wrist), 'right_elbow')
        avg_elbow = (l_elbow_angle + r_elbow_angle) / 2

        back_angle = self.calculate_angle(
            l_shoulder, l_hip,
            (l_hip[0], l_hip[1] + 0.1))

        config = self.config.get('pushup', {})
        min_e  = config.get('min_elbow_angle', 70)
        max_e  = config.get('max_elbow_angle', 160)

        if avg_elbow > max_e - 10:
            phase = MovementPhase.TOP
        elif avg_elbow < min_e + 10:
            phase = MovementPhase.BOTTOM
        elif self.current_phase in [MovementPhase.TOP, MovementPhase.IDLE]:
            phase = MovementPhase.DESCENDING
        else:
            phase = MovementPhase.ASCENDING

        self._update_phase_and_count(
            new_phase=phase,
            rep_trigger_phase=MovementPhase.BOTTOM,
            rep_name="Pompe"
        )

        errors = []
        if abs(l_elbow_angle - r_elbow_angle) > 20:
            errors.append("asymmetry")
        if back_angle < 160:
            errors.append("back_bent")

        return {
            'angles': {
                'left_elbow':  l_elbow_angle,
                'right_elbow': r_elbow_angle,
                'avg_elbow':   avg_elbow,
                'back':        back_angle
            },
            'phase':     phase,
            'errors':    errors,
            'rep_count': self.rep_count
        }

    # ── Utils ─────────────────────────────────────────────────────────────────

    def set_exercise(self, exercise: ExerciseType):
        """Change l'exercice et réinitialise"""
        self.current_exercise = exercise
        self.reset()
        print(f"🏋️ Exercice: {exercise.value}")

    def analyze(self, landmarks: List[Dict]) -> Dict:
        """Dispatch vers le bon analyseur"""
        if self.current_exercise == ExerciseType.SQUAT:
            return self.analyze_squat(landmarks)
        elif self.current_exercise == ExerciseType.PUSHUP:
            return self.analyze_pushup(landmarks)
        else:
            return {
                'angles':    {},
                'phase':     MovementPhase.IDLE,
                'errors':    [],
                'rep_count': 0
            }

    def reset(self) -> None:
        """Réinitialise le compteur de répétitions"""
        self.rep_count      = 0
        self.current_phase  = MovementPhase.IDLE
        self.previous_phase = MovementPhase.IDLE
        for key in self.angle_history:
            self.angle_history[key] = []
        logger.info("🔄 Compteur réinitialisé")

    def _update_phase_and_count(
        self,
        new_phase: MovementPhase,
        rep_trigger_phase: MovementPhase,
        rep_name: str = "Répétition"
    ) -> None:
        """Update phase and increment rep count on BOTTOM → ASCENDING transition."""
        if self.previous_phase == rep_trigger_phase and new_phase == MovementPhase.ASCENDING:
            self.rep_count += 1
            logging.info(f"🔢 {rep_name} {self.rep_count} comptée !")
        self.previous_phase = new_phase
        self.current_phase  = new_phase