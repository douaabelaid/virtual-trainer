"""
Unit tests for logic/angle_utils.py
Covers: calculate_angle, get_joint_angles
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import math
import pytest
from logic.angle_utils import calculate_angle, get_joint_angles


# ─── Helpers ──────────────────────────────────────────────────────────────────

def pt(x: float, y: float) -> dict:
    return {"x": x, "y": y}


# Full standing-upright landmark set (knees straight, back vertical)
STANDING_LANDMARKS = {
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

# Same set but shoulders shifted forward → torso leans forward (back angle < 150°)
FORWARD_LEAN_LANDMARKS = {
    **STANDING_LANDMARKS,
    "left_shoulder":  pt(0.60, 0.40),
    "right_shoulder": pt(0.70, 0.40),
}


# ─── calculate_angle ──────────────────────────────────────────────────────────

class TestCalculateAngle:

    def test_straight_line_returns_180(self):
        assert calculate_angle([0, 0], [1, 0], [2, 0]) == 180.0

    def test_right_angle_returns_90(self):
        assert calculate_angle([0, 1], [0, 0], [1, 0]) == 90.0

    def test_result_always_between_0_and_180(self):
        cases = [
            ([1, 0], [0, 0], [0, 1]),
            ([2, 3], [0, 0], [-1, 4]),
            ([5, 5], [0, 0], [-5, 5]),
            ([1, 0], [0, 0], [-1, 0]),
        ]
        for a, b, c in cases:
            angle = calculate_angle(a, b, c)
            assert 0 <= angle <= 180, f"Out of range for {a},{b},{c}: {angle}"

    def test_symmetric_order_gives_same_angle(self):
        """The angle at b is the same whether measured a→b→c or c→b→a."""
        a, b, c = [0, 2], [1, 0], [2, 2]
        assert calculate_angle(a, b, c) == calculate_angle(c, b, a)

    def test_45_degree_angle(self):
        a = [math.cos(0), math.sin(0)]
        b = [0.0, 0.0]
        c = [math.cos(math.radians(45)), math.sin(math.radians(45))]
        assert abs(calculate_angle(a, b, c) - 45.0) < 0.1

    def test_obtuse_angle_possible(self):
        angle = calculate_angle([-1, 0], [0, 0], [1, 1])
        assert 90 < angle < 180

    def test_result_is_rounded_to_two_decimals(self):
        angle = calculate_angle([0, 1], [0, 0], [1, 0])
        assert angle == round(angle, 2)

    def test_collinear_same_direction_returns_0(self):
        """When a, b, c are collinear and c is on the same side as a from b, the angle is 0°."""
        angle = calculate_angle([1, 0], [0, 0], [2, 0])
        assert angle == 0.0


# ─── get_joint_angles ─────────────────────────────────────────────────────────

class TestGetJointAngles:

    def test_returns_all_expected_keys_for_complete_landmarks(self):
        angles = get_joint_angles(STANDING_LANDMARKS)
        expected = {
            "left_knee", "right_knee",
            "left_hip",  "right_hip",
            "back",
            "left_elbow", "right_elbow",
        }
        for key in expected:
            assert key in angles, f"Missing angle key: '{key}'"

    def test_standing_knee_angles_are_near_180(self):
        angles = get_joint_angles(STANDING_LANDMARKS)
        assert angles["left_knee"]  > 160, f"left_knee={angles['left_knee']:.1f}"
        assert angles["right_knee"] > 160, f"right_knee={angles['right_knee']:.1f}"

    def test_upright_back_angle_is_near_180(self):
        angles = get_joint_angles(STANDING_LANDMARKS)
        assert angles["back"] > 150, f"back={angles['back']:.1f}"

    def test_elbow_angles_are_computed_and_valid(self):
        angles = get_joint_angles(STANDING_LANDMARKS)
        assert "left_elbow"  in angles
        assert "right_elbow" in angles
        assert 0 < angles["left_elbow"]  <= 180
        assert 0 < angles["right_elbow"] <= 180

    def test_missing_knee_landmark_omits_knee_angle(self):
        partial = {k: v for k, v in STANDING_LANDMARKS.items() if k != "left_knee"}
        angles = get_joint_angles(partial)
        assert "left_knee" not in angles

    def test_missing_knee_does_not_remove_other_angles(self):
        partial = {k: v for k, v in STANDING_LANDMARKS.items() if k != "left_knee"}
        angles = get_joint_angles(partial)
        assert "right_knee" in angles

    def test_missing_hip_omits_both_hip_and_knee_angles(self):
        partial = {k: v for k, v in STANDING_LANDMARKS.items()
                   if k not in ("left_hip", "right_hip")}
        angles = get_joint_angles(partial)
        assert "left_knee"  not in angles
        assert "right_knee" not in angles
        assert "left_hip"   not in angles
        assert "right_hip"  not in angles

    def test_empty_landmarks_returns_empty_dict(self):
        assert get_joint_angles({}) == {}

    def test_single_irrelevant_landmark_returns_empty(self):
        angles = get_joint_angles({"left_hip": pt(0.5, 0.4)})
        assert angles == {}

    def test_forward_lean_gives_back_angle_below_150(self):
        """
        Shoulders shifted horizontally forward relative to hips
        → torso inclines → back angle drops below 150°.
        """
        angles = get_joint_angles(FORWARD_LEAN_LANDMARKS)
        assert "back" in angles
        assert angles["back"] < 150, f"Expected back < 150, got {angles['back']:.1f}"

    def test_upright_landmark_gives_back_angle_above_150(self):
        angles = get_joint_angles(STANDING_LANDMARKS)
        assert angles["back"] > 150

    def test_fallback_single_side_back_angle_computed(self):
        """When only one side is visible the back angle falls back to single-side calc."""
        one_side = {
            "left_shoulder": pt(0.45, 0.20),
            "left_hip":      pt(0.45, 0.50),
        }
        angles = get_joint_angles(one_side)
        assert "back" in angles
        assert 0 < angles["back"] <= 180

    def test_bilateral_back_prefers_midpoint_over_single_side(self):
        """Both-sides calc and single-side calc give similar results for symmetric body."""
        both_sides_angles = get_joint_angles(STANDING_LANDMARKS)
        one_side = {
            "left_shoulder": pt(0.45, 0.20),
            "left_hip":      pt(0.45, 0.50),
        }
        one_side_angles = get_joint_angles(one_side)
        # Both should read as upright (> 150)
        assert both_sides_angles["back"] > 150
        assert one_side_angles["back"]   > 150

    def test_all_angle_values_are_floats(self):
        angles = get_joint_angles(STANDING_LANDMARKS)
        for name, value in angles.items():
            assert isinstance(value, float), f"{name} is not float: {type(value)}"
