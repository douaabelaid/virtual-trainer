import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from logic.angle_utils import calculate_angle, get_joint_angles
from logic.exercise_detector import ExerciseDetector
from shared.exercise_state_schema import ExerciseStage, FeedbackSeverity

# ─── Fixtures (reusable test data) ───────────────────────────────────────────

standing_landmarks = {
    "left_hip":       {"x": 0.50, "y": 0.40},
    "left_knee":      {"x": 0.50, "y": 0.60},
    "left_ankle":     {"x": 0.50, "y": 0.80},
    "right_hip":      {"x": 0.60, "y": 0.40},
    "right_knee":     {"x": 0.60, "y": 0.60},
    "right_ankle":    {"x": 0.60, "y": 0.80},
    "left_shoulder":  {"x": 0.50, "y": 0.20},
    "right_shoulder": {"x": 0.60, "y": 0.20},
    "left_elbow":     {"x": 0.40, "y": 0.35},
    "left_wrist":     {"x": 0.35, "y": 0.50},
    "right_elbow":    {"x": 0.70, "y": 0.35},
    "right_wrist":    {"x": 0.75, "y": 0.50},
}

down_landmarks = {
    "left_hip":       {"x": 0.50, "y": 0.60},
    "left_knee":      {"x": 0.40, "y": 0.70},
    "left_ankle":     {"x": 0.50, "y": 0.80},
    "right_hip":      {"x": 0.60, "y": 0.60},
    "right_knee":     {"x": 0.70, "y": 0.70},
    "right_ankle":    {"x": 0.60, "y": 0.80},
    "left_shoulder":  {"x": 0.50, "y": 0.40},
    "right_shoulder": {"x": 0.60, "y": 0.40},
    "left_elbow":     {"x": 0.40, "y": 0.50},
    "left_wrist":     {"x": 0.35, "y": 0.60},
    "right_elbow":    {"x": 0.70, "y": 0.50},
    "right_wrist":    {"x": 0.75, "y": 0.60},
}

# ─── Test 1: calculate_angle ──────────────────────────────────────────────────

def test_straight_line_is_180():
    angle = calculate_angle([0, 0], [1, 0], [2, 0])
    assert angle == 180.0, f"Expected 180, got {angle}"

def test_right_angle_is_90():
    angle = calculate_angle([0, 1], [0, 0], [1, 0])
    assert angle == 90.0, f"Expected 90, got {angle}"

def test_angle_never_exceeds_180():
    angle = calculate_angle([1, 0], [0, 0], [0, 1])
    assert 0 <= angle <= 180, f"Angle out of range: {angle}"

# ─── Test 2: get_joint_angles ─────────────────────────────────────────────────

def test_standing_knees_near_180():
    angles = get_joint_angles(standing_landmarks)
    assert angles["left_knee"] > 160, "Standing left knee should be > 160"
    assert angles["right_knee"] > 160, "Standing right knee should be > 160"

def test_down_knees_near_90():
    angles = get_joint_angles(down_landmarks)
    assert angles["left_knee"] < 100, "Down left knee should be < 100"
    assert angles["right_knee"] < 100, "Down right knee should be < 100"

def test_missing_landmark_returns_no_angle():
    incomplete = {"left_hip": {"x": 0.5, "y": 0.4}}
    angles = get_joint_angles(incomplete)
    assert "left_knee" not in angles, "Should not compute angle with missing landmarks"

# ─── Test 3: ExerciseDetector stage detection ─────────────────────────────────

def test_standing_stage_detected():
    detector = ExerciseDetector(exercise="squat")
    state = detector.update(standing_landmarks)
    assert state.stage == ExerciseStage.STANDING

def test_down_stage_detected():
    detector = ExerciseDetector(exercise="squat")
    state = detector.update(down_landmarks)
    assert state.stage in [ExerciseStage.DOWN, ExerciseStage.TRANSITION]

# ─── Test 4: Rep counter ──────────────────────────────────────────────────────

def test_one_rep_counted():
    detector = ExerciseDetector(exercise="squat")
    detector.update(standing_landmarks)
    detector.update(down_landmarks)
    detector.update(standing_landmarks)
    assert detector.rep_count == 1, f"Expected 1 rep, got {detector.rep_count}"

def test_three_reps_counted():
    detector = ExerciseDetector(exercise="squat")
    for _ in range(3):
        detector.update(standing_landmarks)
        detector.update(down_landmarks)
        detector.update(standing_landmarks)
    assert detector.rep_count == 3, f"Expected 3 reps, got {detector.rep_count}"

def test_no_rep_if_never_goes_down():
    detector = ExerciseDetector(exercise="squat")
    for _ in range(5):
        detector.update(standing_landmarks)
    assert detector.rep_count == 0

# ─── Test 5: Feedback engine ──────────────────────────────────────────────────

def test_back_angle_feedback_fires():
    detector = ExerciseDetector(exercise="squat")
    state = detector.update(down_landmarks)
    codes = [f.code for f in state.feedback_flags]
    assert "BACK_ANGLE" in codes, "Expected BACK_ANGLE feedback"

def test_feedback_has_severity():
    detector = ExerciseDetector(exercise="squat")
    state = detector.update(down_landmarks)
    for flag in state.feedback_flags:
        assert flag.severity in [
            FeedbackSeverity.INFO,
            FeedbackSeverity.WARNING,
            FeedbackSeverity.ERROR
        ]