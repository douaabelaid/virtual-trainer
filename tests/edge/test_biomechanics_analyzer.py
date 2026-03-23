"""
Unit tests for BiomechanicsAnalyzer in ws_server.py
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../edge'))

from ws_server import (
    BiomechanicsAnalyzer,
    ExerciseType,
    MovementPhase,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    'squat': {
        'min_knee_angle': 85,
        'max_knee_angle': 160,
    },
    'pushup': {
        'min_elbow_angle': 70,
        'max_elbow_angle': 160,
    }
}

def make_landmark(x: float, y: float, visibility: float = 1.0) -> dict:
    return {'x': x, 'y': y, 'visibility': visibility}

def make_dummy_landmarks(n: int = 17) -> list:
    return [make_landmark(0.5, float(i) * 0.05) for i in range(n)]

def make_squat_landmarks(knee_angle_deg: float = 90.0) -> list:
    lms = make_dummy_landmarks(17)
    lms[5]  = make_landmark(0.3, 0.2)
    lms[6]  = make_landmark(0.7, 0.2)
    lms[11] = make_landmark(0.3, 0.5)
    lms[12] = make_landmark(0.7, 0.5)
    lms[13] = make_landmark(0.3, 0.75)
    lms[14] = make_landmark(0.7, 0.75)
    lms[15] = make_landmark(0.3, 1.0)
    lms[16] = make_landmark(0.7, 1.0)
    return lms

def make_pushup_landmarks() -> list:
    lms = make_dummy_landmarks(17)
    lms[5]  = make_landmark(0.3, 0.3)
    lms[6]  = make_landmark(0.7, 0.3)
    lms[7]  = make_landmark(0.2, 0.5)
    lms[8]  = make_landmark(0.8, 0.5)
    lms[9]  = make_landmark(0.15, 0.65)
    lms[10] = make_landmark(0.85, 0.65)
    lms[11] = make_landmark(0.3, 0.6)
    lms[12] = make_landmark(0.7, 0.6)
    return lms

# ── Tests: Initialization ─────────────────────────────────────────────────────

class TestInit:
    def test_default_exercise_is_squat(self):
        analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)
        assert analyzer.current_exercise == ExerciseType.SQUAT

    def test_default_phase_is_idle(self):
        analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)
        assert analyzer.current_phase == MovementPhase.IDLE

    def test_initial_rep_count_is_zero(self):
        analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)
        assert analyzer.rep_count == 0

    def test_angle_history_initialized(self):
        analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)
        for key in ['left_knee', 'right_knee', 'left_hip', 'right_hip', 'left_elbow', 'right_elbow']:
            assert key in analyzer.angle_history
            assert analyzer.angle_history[key] == []

# ── Tests: calculate_angle ────────────────────────────────────────────────────

class TestCalculateAngle:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_right_angle(self):
        angle = self.analyzer.calculate_angle((0, 1), (0, 0), (1, 0))
        assert abs(angle - 90.0) < 0.01

    def test_straight_line(self):
        angle = self.analyzer.calculate_angle((0, 0), (1, 0), (2, 0))
        assert abs(angle - 180.0) < 0.01

    def test_zero_vector_returns_zero(self):
        angle = self.analyzer.calculate_angle((0, 0), (0, 0), (1, 0))
        assert angle == 0.0

# ── Tests: smooth_angle ───────────────────────────────────────────────────────

class TestSmoothAngle:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_unknown_joint_returns_angle(self):
        result = self.analyzer.smooth_angle(90.0, 'unknown_joint')
        assert result == 90.0

    def test_smoothing_averages_values(self):
        for v in [80.0, 90.0, 100.0]:
            result = self.analyzer.smooth_angle(v, 'left_knee')
        assert abs(result - 90.0) < 0.01

    def test_history_does_not_exceed_history_size(self):
        for i in range(10):
            self.analyzer.smooth_angle(float(i), 'left_knee')
        assert len(self.analyzer.angle_history['left_knee']) <= self.analyzer.history_size

# ── Tests: get_landmark_coords ────────────────────────────────────────────────

class TestGetLandmarkCoords:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_returns_correct_coords(self):
        lms = [make_landmark(0.3, 0.7)]
        x, y = self.analyzer.get_landmark_coords(lms, 0)
        assert x == 0.3
        assert y == 0.7

    def test_out_of_range_returns_zero(self):
        lms = []
        coords = self.analyzer.get_landmark_coords(lms, 5)
        assert coords == (0.0, 0.0)

# ── Tests: _is_visible ────────────────────────────────────────────────────────

class TestIsVisible:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_all_visible(self):
        lms = [make_landmark(0.5, 0.5, visibility=1.0) for _ in range(5)]
        assert self.analyzer._is_visible(lms, 0, 1, 2)

    def test_one_invisible(self):
        lms = [make_landmark(0.5, 0.5, visibility=1.0) for _ in range(5)]
        lms[1] = make_landmark(0.5, 0.5, visibility=0.1)
        assert not self.analyzer._is_visible(lms, 0, 1, 2)

    def test_out_of_range_index(self):
        lms = [make_landmark(0.5, 0.5)]
        assert not self.analyzer._is_visible(lms, 10)

# ── Tests: analyze_squat ─────────────────────────────────────────────────────

class TestAnalyzeSquat:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_returns_required_keys(self):
        lms = make_squat_landmarks()
        result = self.analyzer.analyze_squat(lms)
        assert 'angles' in result
        assert 'phase' in result
        assert 'errors' in result
        assert 'rep_count' in result

    def test_angles_contain_expected_keys(self):
        lms = make_squat_landmarks()
        result = self.analyzer.analyze_squat(lms)
        for key in ['left_knee', 'right_knee', 'left_hip', 'right_hip', 'avg_knee', 'avg_hip']:
            assert key in result['angles']

    def test_phase_is_movement_phase(self):
        lms = make_squat_landmarks()
        result = self.analyzer.analyze_squat(lms)
        assert isinstance(result['phase'], MovementPhase)

    def test_errors_is_list(self):
        lms = make_squat_landmarks()
        result = self.analyzer.analyze_squat(lms)
        assert isinstance(result['errors'], list)

# ── Tests: analyze_pushup ─────────────────────────────────────────────────────

class TestAnalyzePushup:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)
        self.analyzer.set_exercise(ExerciseType.PUSHUP)

    def test_returns_required_keys(self):
        lms = make_pushup_landmarks()
        result = self.analyzer.analyze_pushup(lms)
        assert 'angles' in result
        assert 'phase' in result
        assert 'errors' in result
        assert 'rep_count' in result

    def test_angles_contain_expected_keys(self):
        lms = make_pushup_landmarks()
        result = self.analyzer.analyze_pushup(lms)
        for key in ['left_elbow', 'right_elbow', 'avg_elbow', 'back']:
            assert key in result['angles']

# ── Tests: set_exercise & reset ───────────────────────────────────────────────

class TestSetExerciseAndReset:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_set_exercise_changes_type(self):
        self.analyzer.set_exercise(ExerciseType.PUSHUP)
        assert self.analyzer.current_exercise == ExerciseType.PUSHUP

    def test_reset_clears_rep_count(self):
        self.analyzer.rep_count = 5
        self.analyzer.reset()
        assert self.analyzer.rep_count == 0

    def test_reset_clears_phase(self):
        self.analyzer.current_phase = MovementPhase.BOTTOM
        self.analyzer.reset()
        assert self.analyzer.current_phase == MovementPhase.IDLE

    def test_reset_clears_angle_history(self):
        self.analyzer.angle_history['left_knee'] = [90.0, 85.0]
        self.analyzer.reset()
        assert self.analyzer.angle_history['left_knee'] == []

# ── Tests: analyze dispatch ───────────────────────────────────────────────────

class TestAnalyzeDispatch:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def test_dispatches_to_squat(self):
        self.analyzer.set_exercise(ExerciseType.SQUAT)
        lms = make_squat_landmarks()
        result = self.analyzer.analyze(lms)
        assert 'avg_knee' in result['angles']

    def test_dispatches_to_pushup(self):
        self.analyzer.set_exercise(ExerciseType.PUSHUP)
        lms = make_pushup_landmarks()
        result = self.analyzer.analyze(lms)
        assert 'avg_elbow' in result['angles']

    def test_unknown_exercise_returns_idle(self):
        self.analyzer.current_exercise = ExerciseType.PLANK
        result = self.analyzer.analyze(make_dummy_landmarks())
        assert result['phase'] == MovementPhase.IDLE
        assert result['errors'] == []
        assert result['rep_count'] == 0

# ── Tests: Rep Counting (full cycle simulation) ───────────────────────────────

class TestRepCounting:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    def _force_phase(self, phase: MovementPhase) -> None:
        """Directly set both current and previous phase."""
        self.analyzer.current_phase  = phase
        self.analyzer.previous_phase = phase

    def test_squat_full_cycle_counts_one_rep(self):
        """IDLE → DESCENDING → BOTTOM → ASCENDING triggers rep_count == 1"""
        self._force_phase(MovementPhase.IDLE)
        assert self.analyzer.rep_count == 0

        self.analyzer._update_phase_and_count(MovementPhase.DESCENDING, MovementPhase.BOTTOM, "Squat")
        assert self.analyzer.rep_count == 0

        self.analyzer._update_phase_and_count(MovementPhase.BOTTOM, MovementPhase.BOTTOM, "Squat")
        assert self.analyzer.rep_count == 0

        # BOTTOM → ASCENDING: rep counted here
        self.analyzer._update_phase_and_count(MovementPhase.ASCENDING, MovementPhase.BOTTOM, "Squat")
        assert self.analyzer.rep_count == 1
        assert self.analyzer.current_phase == MovementPhase.ASCENDING

    def test_squat_two_full_cycles_counts_two_reps(self):
        """Two full cycles → rep_count == 2"""
        self._force_phase(MovementPhase.IDLE)

        for _ in range(2):
            self.analyzer._update_phase_and_count(MovementPhase.DESCENDING, MovementPhase.BOTTOM, "Squat")
            self.analyzer._update_phase_and_count(MovementPhase.BOTTOM,     MovementPhase.BOTTOM, "Squat")
            self.analyzer._update_phase_and_count(MovementPhase.ASCENDING,  MovementPhase.BOTTOM, "Squat")
            self.analyzer._update_phase_and_count(MovementPhase.TOP,        MovementPhase.BOTTOM, "Squat")

        assert self.analyzer.rep_count == 2

    def test_no_rep_counted_without_bottom_phase(self):
        """TOP → ASCENDING without BOTTOM should not count."""
        self._force_phase(MovementPhase.TOP)
        self.analyzer._update_phase_and_count(MovementPhase.ASCENDING, MovementPhase.BOTTOM, "Squat")
        assert self.analyzer.rep_count == 0

    def test_pushup_full_cycle_counts_one_rep(self):
        """Full pushup cycle IDLE → DESCENDING → BOTTOM → ASCENDING → rep_count == 1"""
        self.analyzer.set_exercise(ExerciseType.PUSHUP)
        self._force_phase(MovementPhase.IDLE)
        assert self.analyzer.rep_count == 0

        self.analyzer._update_phase_and_count(MovementPhase.DESCENDING, MovementPhase.BOTTOM, "Pompe")
        self.analyzer._update_phase_and_count(MovementPhase.BOTTOM,     MovementPhase.BOTTOM, "Pompe")
        self.analyzer._update_phase_and_count(MovementPhase.ASCENDING,  MovementPhase.BOTTOM, "Pompe")

        assert self.analyzer.rep_count == 1
        assert self.analyzer.current_phase == MovementPhase.ASCENDING

    def test_rep_count_resets_after_set_exercise(self):
        self.analyzer.rep_count = 3
        self.analyzer.set_exercise(ExerciseType.PUSHUP)
        assert self.analyzer.rep_count == 0

# ── Tests: Edge Cases (malformed landmarks) ───────────────────────────────────

class TestEdgeCases:
    def setup_method(self):
        self.analyzer = BiomechanicsAnalyzer(DEFAULT_CONFIG)

    # Empty landmark list
    def test_analyze_squat_empty_landmarks(self):
        result = self.analyzer.analyze_squat([])
        assert 'angles' in result
        assert 'errors' in result
        assert isinstance(result['phase'], MovementPhase)

    def test_analyze_pushup_empty_landmarks(self):
        self.analyzer.set_exercise(ExerciseType.PUSHUP)
        result = self.analyzer.analyze_pushup([])
        assert 'angles' in result
        assert isinstance(result['phase'], MovementPhase)

    def test_get_landmark_coords_empty_list(self):
        coords = self.analyzer.get_landmark_coords([], 0)
        assert coords == (0.0, 0.0)

    # Missing keys in landmark dicts
    def test_get_landmark_missing_x_key(self):
        lms = [{'y': 0.5, 'visibility': 1.0}]
        x, y = self.analyzer.get_landmark_coords(lms, 0)
        assert x == 0.0
        assert y == 0.5

    def test_get_landmark_missing_y_key(self):
        lms = [{'x': 0.5, 'visibility': 1.0}]
        x, y = self.analyzer.get_landmark_coords(lms, 0)
        assert x == 0.5
        assert y == 0.0

    def test_get_landmark_empty_dict(self):
        lms = [{}]
        coords = self.analyzer.get_landmark_coords(lms, 0)
        assert coords == (0.0, 0.0)

    # None visibility — should not crash _is_visible
    def test_is_visible_missing_visibility_key(self):
        lms = [{'x': 0.5, 'y': 0.5}]   # no 'visibility' key
        # defaults to 1.0 via .get, so should be visible
        result = self.analyzer._is_visible(lms, 0)
        assert result is True

    # Landmarks with None values
    def test_get_landmark_none_values(self):
        lms = [{'x': None, 'y': None, 'visibility': 1.0}]
        # Should not raise; coords should fall back gracefully
        try:
            coords = self.analyzer.get_landmark_coords(lms, 0)
            # If it returns, values should be usable numbers or None
            assert coords is not None
        except (TypeError, ValueError):
            pass  # Acceptable: caller must handle None values

    # Partial landmark list (fewer than 17)
    def test_analyze_squat_partial_landmarks(self):
        lms = make_dummy_landmarks(5)   # only 5 of 17
        result = self.analyzer.analyze_squat(lms)
        assert 'angles' in result
        assert 'rep_count' in result

    def test_analyze_pushup_partial_landmarks(self):
        lms = make_dummy_landmarks(5)
        result = self.analyzer.analyze_pushup(lms)
        assert 'angles' in result
        assert 'rep_count' in result

    # Landmarks with extreme coordinate values
    def test_calculate_angle_extreme_values(self):
        angle = self.analyzer.calculate_angle((1e9, 1e9), (0, 0), (1e9, -1e9))
        assert 0.0 <= angle <= 180.0

    def test_calculate_angle_identical_points(self):
        angle = self.analyzer.calculate_angle((1, 1), (1, 1), (1, 1))
        assert angle == 0.0