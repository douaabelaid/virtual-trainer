"""
Unit tests for logic/exercise_detector.py
Covers: ExerciseDetector.__init__, reset, detect_stage, update, check_feedback
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
from logic.exercise_detector import ExerciseDetector
from shared.exercise_state_schema import (
    ExerciseState, ExerciseStage, ExerciseType, FeedbackSeverity,
)


# ─── Landmark helpers ─────────────────────────────────────────────────────────

def pt(x: float, y: float) -> dict:
    return {"x": x, "y": y}


# Standing: knees 180° (straight legs), back 180° (upright)
SQUAT_STANDING = {
    "left_shoulder":  pt(0.45, 0.20),
    "right_shoulder": pt(0.55, 0.20),
    "left_hip":       pt(0.45, 0.50),
    "right_hip":      pt(0.55, 0.50),
    "left_knee":      pt(0.45, 0.75),
    "right_knee":     pt(0.55, 0.75),
    "left_ankle":     pt(0.45, 0.90),
    "right_ankle":    pt(0.55, 0.90),
    "left_elbow":     pt(0.35, 0.35),
    "left_wrist":     pt(0.30, 0.50),
    "right_elbow":    pt(0.65, 0.35),
    "right_wrist":    pt(0.70, 0.50),
}

# Deep squat: both knees ~90° → avg 90 < 95 → DOWN.  Back upright (180°).
SQUAT_DOWN = {
    "left_shoulder":  pt(0.45, 0.30),
    "right_shoulder": pt(0.55, 0.30),
    "left_hip":       pt(0.43, 0.52),
    "right_hip":      pt(0.57, 0.52),
    "left_knee":      pt(0.30, 0.65),   # knee angle ≈ 90°
    "right_knee":     pt(0.70, 0.65),   # knee angle ≈ 90°
    "left_ankle":     pt(0.43, 0.78),
    "right_ankle":    pt(0.57, 0.78),
    "left_elbow":     pt(0.35, 0.40),
    "left_wrist":     pt(0.30, 0.55),
    "right_elbow":    pt(0.65, 0.40),
    "right_wrist":    pt(0.70, 0.55),
}

# Partial squat: knees ~140° → 95 < 140 < 160 → TRANSITION
SQUAT_TRANSITION = {
    "left_shoulder":  pt(0.45, 0.25),
    "right_shoulder": pt(0.55, 0.25),
    "left_hip":       pt(0.45, 0.52),
    "right_hip":      pt(0.55, 0.52),
    "left_knee":      pt(0.40, 0.65),   # knee angle ≈ 140°
    "right_knee":     pt(0.60, 0.65),   # knee angle ≈ 140°
    "left_ankle":     pt(0.45, 0.80),
    "right_ankle":    pt(0.55, 0.80),
    "left_elbow":     pt(0.35, 0.38),
    "left_wrist":     pt(0.30, 0.53),
    "right_elbow":    pt(0.65, 0.38),
    "right_wrist":    pt(0.70, 0.53),
}

# Deep squat with forward lean: back ≈ 129° < 150 → BACK_ANGLE fires
LEAN_DOWN = {
    **SQUAT_DOWN,
    "left_shoulder":  pt(0.60, 0.40),
    "right_shoulder": pt(0.70, 0.40),
}

# Transition with forward lean: BACK_ANGLE should fire in TRANSITION too
LEAN_TRANSITION = {
    **SQUAT_TRANSITION,
    "left_shoulder":  pt(0.60, 0.35),
    "right_shoulder": pt(0.70, 0.35),
}

# Asymmetric knees in squat: |left(≈59°) - right(90°)| = 31° > 15 → KNEE_CAVE
KNEE_CAVE_DOWN = {
    **SQUAT_DOWN,
    "left_knee": pt(0.20, 0.65),   # more lateral → angle ≈ 59°
}

# Pushup top: elbows 180° (arms fully extended)
PUSHUP_STANDING = {
    "left_shoulder":  pt(0.40, 0.20),
    "right_shoulder": pt(0.60, 0.20),
    "left_hip":       pt(0.40, 0.50),
    "right_hip":      pt(0.60, 0.50),
    "left_knee":      pt(0.40, 0.70),
    "right_knee":     pt(0.60, 0.70),
    "left_ankle":     pt(0.40, 0.90),
    "right_ankle":    pt(0.60, 0.90),
    "left_elbow":     pt(0.35, 0.35),
    "left_wrist":     pt(0.30, 0.50),
    "right_elbow":    pt(0.65, 0.35),
    "right_wrist":    pt(0.70, 0.50),
}

# Pushup bottom: elbows ≈ 79° → avg 79 < 90 → DOWN
PUSHUP_DOWN = {
    "left_shoulder":  pt(0.40, 0.20),
    "right_shoulder": pt(0.60, 0.20),
    "left_hip":       pt(0.40, 0.50),
    "right_hip":      pt(0.60, 0.50),
    "left_knee":      pt(0.40, 0.70),
    "right_knee":     pt(0.60, 0.70),
    "left_ankle":     pt(0.40, 0.90),
    "right_ankle":    pt(0.60, 0.90),
    "left_elbow":     pt(0.50, 0.35),
    "left_wrist":     pt(0.60, 0.25),
    "right_elbow":    pt(0.50, 0.35),
    "right_wrist":    pt(0.40, 0.25),
}

# Pushup mid-way: elbows ≈ 101° → 90 < 101 < 160 → TRANSITION
PUSHUP_TRANSITION = {
    **PUSHUP_STANDING,
    "left_elbow":  pt(0.55, 0.30),
    "left_wrist":  pt(0.65, 0.20),
    "right_elbow": pt(0.45, 0.30),
    "right_wrist": pt(0.35, 0.20),
}

# Lunge: both knees ~75° < 80 → KNEE_TOO_FORWARD on both sides
LUNGE_KNEE_FORWARD = {
    **SQUAT_STANDING,
    "left_hip":   pt(0.43, 0.48),
    "left_knee":  pt(0.25, 0.62),
    "left_ankle": pt(0.43, 0.76),
    "right_hip":   pt(0.57, 0.48),
    "right_knee":  pt(0.75, 0.62),
    "right_ankle": pt(0.57, 0.76),
}


# ─── TestExerciseDetectorInit ─────────────────────────────────────────────────

class TestExerciseDetectorInit:

    def test_default_exercise_is_squat(self):
        d = ExerciseDetector()
        assert d.exercise == ExerciseType.SQUAT

    def test_custom_exercise_accepted(self):
        assert ExerciseDetector("pushup").exercise == ExerciseType.PUSHUP
        assert ExerciseDetector("lunge").exercise  == ExerciseType.LUNGE

    def test_initial_stage_is_standing(self):
        assert ExerciseDetector().stage == ExerciseStage.STANDING

    def test_initial_rep_count_is_zero(self):
        assert ExerciseDetector().rep_count == 0

    def test_invalid_exercise_raises(self):
        with pytest.raises(ValueError):
            ExerciseDetector("burpee")


# ─── TestReset ────────────────────────────────────────────────────────────────

class TestReset:

    def test_reset_clears_rep_count(self):
        d = ExerciseDetector("squat")
        d.update(SQUAT_STANDING)
        d.update(SQUAT_DOWN)
        d.update(SQUAT_STANDING)
        assert d.rep_count == 1
        d.reset()
        assert d.rep_count == 0

    def test_reset_restores_standing_stage(self):
        d = ExerciseDetector("squat")
        d.update(SQUAT_DOWN)
        assert d.stage == ExerciseStage.DOWN
        d.reset()
        assert d.stage == ExerciseStage.STANDING

    def test_reset_on_fresh_detector_is_idempotent(self):
        d = ExerciseDetector("squat")
        d.reset()
        assert d.rep_count == 0
        assert d.stage == ExerciseStage.STANDING


# ─── TestDetectStage ──────────────────────────────────────────────────────────

class TestDetectStage:

    # Squat
    def test_squat_down_when_avg_knee_below_threshold(self):
        d = ExerciseDetector("squat")
        angles = {"left_knee": 88.0, "right_knee": 90.0}         # avg 89 < 95
        assert d.detect_stage(angles) == ExerciseStage.DOWN

    def test_squat_standing_when_avg_knee_above_threshold(self):
        d = ExerciseDetector("squat")
        angles = {"left_knee": 170.0, "right_knee": 175.0}        # avg 172.5 > 160
        assert d.detect_stage(angles) == ExerciseStage.STANDING

    def test_squat_transition_between_thresholds(self):
        d = ExerciseDetector("squat")
        angles = {"left_knee": 130.0, "right_knee": 140.0}        # avg 135, 95<135<160
        assert d.detect_stage(angles) == ExerciseStage.TRANSITION

    def test_squat_defaults_missing_knee_to_180(self):
        d = ExerciseDetector("squat")
        # Only one knee → avg = (90 + 180) / 2 = 135 → TRANSITION
        angles = {"left_knee": 90.0}
        assert d.detect_stage(angles) == ExerciseStage.TRANSITION

    # Push-up
    def test_pushup_down_when_avg_elbow_below_threshold(self):
        d = ExerciseDetector("pushup")
        angles = {"left_elbow": 85.0, "right_elbow": 80.0}        # avg 82.5 < 90
        assert d.detect_stage(angles) == ExerciseStage.DOWN

    def test_pushup_standing_when_avg_elbow_above_threshold(self):
        d = ExerciseDetector("pushup")
        angles = {"left_elbow": 165.0, "right_elbow": 170.0}      # avg 167.5 > 160
        assert d.detect_stage(angles) == ExerciseStage.STANDING

    def test_pushup_transition_between_thresholds(self):
        d = ExerciseDetector("pushup")
        angles = {"left_elbow": 110.0, "right_elbow": 120.0}      # avg 115
        assert d.detect_stage(angles) == ExerciseStage.TRANSITION

    # Lunge (shares squat knee thresholds)
    def test_lunge_down_when_avg_knee_below_threshold(self):
        d = ExerciseDetector("lunge")
        angles = {"left_knee": 88.0, "right_knee": 88.0}
        assert d.detect_stage(angles) == ExerciseStage.DOWN

    def test_lunge_standing_when_avg_knee_above_threshold(self):
        d = ExerciseDetector("lunge")
        angles = {"left_knee": 170.0, "right_knee": 170.0}
        assert d.detect_stage(angles) == ExerciseStage.STANDING


# ─── TestUpdate ───────────────────────────────────────────────────────────────

class TestUpdate:

    def test_returns_exercise_state_instance(self):
        state = ExerciseDetector("squat").update(SQUAT_STANDING)
        assert isinstance(state, ExerciseState)

    def test_exercise_field_matches_constructor(self):
        state = ExerciseDetector("pushup").update(PUSHUP_STANDING)
        assert state.exercise == ExerciseType.PUSHUP

    def test_stage_field_reflects_detected_stage(self):
        state = ExerciseDetector("squat").update(SQUAT_DOWN)
        assert state.stage == ExerciseStage.DOWN

    def test_timestamp_ms_is_positive(self):
        state = ExerciseDetector("squat").update(SQUAT_STANDING)
        assert state.timestamp_ms > 0

    def test_joint_angles_present_in_state(self):
        state = ExerciseDetector("squat").update(SQUAT_STANDING)
        assert state.joint_angles is not None

    def test_rep_counted_after_down_then_standing(self):
        d = ExerciseDetector("squat")
        d.update(SQUAT_STANDING)
        d.update(SQUAT_DOWN)
        d.update(SQUAT_STANDING)
        assert d.rep_count == 1

    def test_no_rep_counted_without_going_down(self):
        d = ExerciseDetector("squat")
        for _ in range(5):
            d.update(SQUAT_STANDING)
        assert d.rep_count == 0

    def test_multiple_reps_counted_correctly(self):
        d = ExerciseDetector("squat")
        for _ in range(4):
            d.update(SQUAT_STANDING)
            d.update(SQUAT_DOWN)
            d.update(SQUAT_STANDING)
        assert d.rep_count == 4

    def test_rep_not_counted_on_down_only(self):
        d = ExerciseDetector("squat")
        d.update(SQUAT_STANDING)
        d.update(SQUAT_DOWN)
        assert d.rep_count == 0      # still in DOWN — not finished yet

    def test_pushup_reps_counted(self):
        d = ExerciseDetector("pushup")
        for _ in range(3):
            d.update(PUSHUP_STANDING)
            d.update(PUSHUP_DOWN)
            d.update(PUSHUP_STANDING)
        assert d.rep_count == 3

    def test_feedback_flags_list_in_state(self):
        state = ExerciseDetector("squat").update(SQUAT_STANDING)
        assert isinstance(state.feedback_flags, list)

    def test_landmarks_raw_preserved_in_state(self):
        state = ExerciseDetector("squat").update(SQUAT_STANDING)
        assert state.landmarks_raw == SQUAT_STANDING


# ─── TestCheckFeedbackSquat ───────────────────────────────────────────────────

class TestCheckFeedbackSquat:

    def test_knee_cave_fires_when_knees_asymmetric(self):
        d = ExerciseDetector("squat")
        state = d.update(KNEE_CAVE_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "KNEE_CAVE" in codes

    def test_no_knee_cave_when_knees_symmetric(self):
        d = ExerciseDetector("squat")
        state = d.update(SQUAT_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "KNEE_CAVE" not in codes

    def test_depth_ok_fires_when_squat_deep_enough(self):
        """avg knee ≈ 90° < 110 in DOWN stage → DEPTH_OK."""
        d = ExerciseDetector("squat")
        state = d.update(SQUAT_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "DEPTH_OK" in codes

    def test_too_shallow_fires_via_direct_check_feedback(self):
        """
        TOO_SHALLOW requires stage=DOWN AND avg_knee > 110.
        These conditions cannot both arise from detect_stage in the same update call,
        so we test check_feedback directly by setting stage manually.
        """
        d = ExerciseDetector("squat")
        d.stage = ExerciseStage.DOWN
        flags = d.check_feedback({"left_knee": 115.0, "right_knee": 120.0})
        codes = [f.code for f in flags]
        assert "TOO_SHALLOW" in codes

    def test_no_depth_check_outside_down_stage(self):
        d = ExerciseDetector("squat")
        state = d.update(SQUAT_STANDING)
        codes = [f.code for f in state.feedback_flags]
        assert "DEPTH_OK"    not in codes
        assert "TOO_SHALLOW" not in codes

    def test_back_angle_fires_in_down_stage(self):
        """Forward-leaning torso (back ≈ 129°) while in DOWN → BACK_ANGLE."""
        d = ExerciseDetector("squat")
        state = d.update(LEAN_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "BACK_ANGLE" in codes

    def test_back_angle_fires_in_transition_stage(self):
        """Back check also active during TRANSITION."""
        d = ExerciseDetector("squat")
        state = d.update(LEAN_TRANSITION)
        codes = [f.code for f in state.feedback_flags]
        assert "BACK_ANGLE" in codes

    def test_back_angle_suppressed_in_standing_stage(self):
        """Back check is skipped when stage is STANDING."""
        d = ExerciseDetector("squat")
        # Force standing stage, then call check_feedback with a leaning back
        d.stage = ExerciseStage.STANDING
        flags = d.check_feedback({"left_knee": 170.0, "right_knee": 172.0, "back": 100.0})
        codes = [f.code for f in flags]
        assert "BACK_ANGLE" not in codes

    def test_good_form_emitted_when_no_issues_in_down(self):
        """GOOD_FORM should appear when in DOWN with no warnings."""
        d = ExerciseDetector("squat")
        state = d.update(SQUAT_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "GOOD_FORM" in codes

    def test_good_form_suppressed_when_warnings_present(self):
        """GOOD_FORM must NOT appear alongside warnings (e.g., BACK_ANGLE)."""
        d = ExerciseDetector("squat")
        state = d.update(LEAN_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "GOOD_FORM" not in codes

    def test_good_form_not_emitted_during_standing(self):
        """GOOD_FORM only makes sense at full depth, not while standing."""
        d = ExerciseDetector("squat")
        state = d.update(SQUAT_STANDING)
        codes = [f.code for f in state.feedback_flags]
        assert "GOOD_FORM" not in codes


# ─── TestCheckFeedbackPushup ──────────────────────────────────────────────────

class TestCheckFeedbackPushup:

    def test_elbow_flare_fires_when_elbows_asymmetric(self):
        d = ExerciseDetector("pushup")
        d.stage = ExerciseStage.STANDING
        flags = d.check_feedback({"left_elbow": 100.0, "right_elbow": 120.0})
        codes = [f.code for f in flags]
        assert "ELBOW_FLARE" in codes

    def test_no_elbow_flare_when_elbows_symmetric(self):
        d = ExerciseDetector("pushup")
        flags = d.check_feedback({"left_elbow": 95.0, "right_elbow": 97.0})
        codes = [f.code for f in flags]
        assert "ELBOW_FLARE" not in codes

    def test_pushup_too_shallow_fires_via_direct_check_feedback(self):
        d = ExerciseDetector("pushup")
        d.stage = ExerciseStage.DOWN
        flags = d.check_feedback({"left_elbow": 115.0, "right_elbow": 120.0})
        codes = [f.code for f in flags]
        assert "PUSHUP_TOO_SHALLOW" in codes

    def test_pushup_depth_ok_fires_when_deep_enough(self):
        """avg elbow ≈ 79° < 110 in DOWN → DEPTH_OK."""
        d = ExerciseDetector("pushup")
        state = d.update(PUSHUP_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "DEPTH_OK" in codes

    def test_pushup_good_form_emitted_in_down_with_no_issues(self):
        d = ExerciseDetector("pushup")
        state = d.update(PUSHUP_DOWN)
        codes = [f.code for f in state.feedback_flags]
        assert "GOOD_FORM" in codes

    def test_pushup_stage_detection_via_landmarks(self):
        d = ExerciseDetector("pushup")
        assert d.update(PUSHUP_STANDING).stage == ExerciseStage.STANDING
        d2 = ExerciseDetector("pushup")
        assert d2.update(PUSHUP_DOWN).stage == ExerciseStage.DOWN
        d3 = ExerciseDetector("pushup")
        assert d3.update(PUSHUP_TRANSITION).stage == ExerciseStage.TRANSITION


# ─── TestCheckFeedbackLunge ───────────────────────────────────────────────────

class TestCheckFeedbackLunge:

    def test_knee_too_forward_fires_for_left_knee(self):
        d = ExerciseDetector("lunge")
        flags = d.check_feedback({"left_knee": 75.0, "right_knee": 170.0})
        codes = [f.code for f in flags]
        assert "KNEE_TOO_FORWARD" in codes

    def test_knee_too_forward_fires_for_right_knee(self):
        d = ExerciseDetector("lunge")
        flags = d.check_feedback({"left_knee": 170.0, "right_knee": 75.0})
        codes = [f.code for f in flags]
        assert "KNEE_TOO_FORWARD" in codes

    def test_knee_too_forward_fires_for_both_knees(self):
        d = ExerciseDetector("lunge")
        flags = d.check_feedback({"left_knee": 70.0, "right_knee": 72.0})
        count = sum(1 for f in flags if f.code == "KNEE_TOO_FORWARD")
        assert count == 2

    def test_no_knee_too_forward_when_knees_ok(self):
        d = ExerciseDetector("lunge")
        flags = d.check_feedback({"left_knee": 85.0, "right_knee": 90.0})
        codes = [f.code for f in flags]
        assert "KNEE_TOO_FORWARD" not in codes

    def test_lunge_knee_too_forward_via_landmarks(self):
        d = ExerciseDetector("lunge")
        state = d.update(LUNGE_KNEE_FORWARD)
        codes = [f.code for f in state.feedback_flags]
        assert "KNEE_TOO_FORWARD" in codes


# ─── TestFeedbackSeverities ───────────────────────────────────────────────────

class TestFeedbackSeverities:

    def test_all_flags_have_valid_severity(self):
        valid = set(FeedbackSeverity)
        for landmarks in (SQUAT_STANDING, SQUAT_DOWN, LEAN_DOWN, KNEE_CAVE_DOWN,
                          PUSHUP_DOWN, LEAN_TRANSITION):
            exercise = "pushup" if landmarks in (PUSHUP_DOWN,) else "squat"
            state = ExerciseDetector(exercise).update(landmarks)
            for flag in state.feedback_flags:
                assert flag.severity in valid, \
                    f"Invalid severity '{flag.severity}' in flag '{flag.code}'"

    def test_knee_cave_is_warning(self):
        state = ExerciseDetector("squat").update(KNEE_CAVE_DOWN)
        cave = next(f for f in state.feedback_flags if f.code == "KNEE_CAVE")
        assert cave.severity == FeedbackSeverity.WARNING

    def test_depth_ok_is_info(self):
        state = ExerciseDetector("squat").update(SQUAT_DOWN)
        ok = next(f for f in state.feedback_flags if f.code == "DEPTH_OK")
        assert ok.severity == FeedbackSeverity.INFO

    def test_good_form_is_info(self):
        state = ExerciseDetector("squat").update(SQUAT_DOWN)
        gf = next(f for f in state.feedback_flags if f.code == "GOOD_FORM")
        assert gf.severity == FeedbackSeverity.INFO

    def test_back_angle_is_warning(self):
        state = ExerciseDetector("squat").update(LEAN_DOWN)
        ba = next(f for f in state.feedback_flags if f.code == "BACK_ANGLE")
        assert ba.severity == FeedbackSeverity.WARNING
