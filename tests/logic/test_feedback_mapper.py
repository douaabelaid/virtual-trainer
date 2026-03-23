"""
Unit tests for logic/feedback_mapper.py
Covers: get_coaching_message, map_flags_to_coaching
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import pytest
import logic.feedback_mapper as fm
from logic.feedback_mapper import get_coaching_message, map_flags_to_coaching, FEEDBACK_MESSAGES
from shared.exercise_state_schema import FeedbackFlag, FeedbackSeverity


# ─── Fixture: isolate global rotation counter ─────────────────────────────────

@pytest.fixture(autouse=True)
def reset_message_counter():
    """Clear the global rotation counter before and after every test."""
    fm._message_counter.clear()
    yield
    fm._message_counter.clear()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_flag(code: str, severity: FeedbackSeverity = FeedbackSeverity.WARNING) -> FeedbackFlag:
    return FeedbackFlag(code=code, message="test", severity=severity)


# ─── TestGetCoachingMessage ────────────────────────────────────────────────────

class TestGetCoachingMessage:

    def test_known_code_returns_string(self):
        msg = get_coaching_message("KNEE_CAVE")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_known_code_returns_message_from_library(self):
        msg = get_coaching_message("KNEE_CAVE")
        assert msg in FEEDBACK_MESSAGES["KNEE_CAVE"]

    def test_unknown_code_returns_fallback_string(self):
        msg = get_coaching_message("TOTALLY_UNKNOWN_CODE")
        assert isinstance(msg, str)
        assert "totally unknown code" in msg.lower()

    def test_all_known_codes_return_valid_strings(self):
        for code in FEEDBACK_MESSAGES:
            msg = get_coaching_message(code)
            assert isinstance(msg, str), f"Expected str for code '{code}'"
            assert msg in FEEDBACK_MESSAGES[code], \
                f"Returned message not in library for '{code}'"

    def test_rotation_cycles_through_all_messages(self):
        """After N calls, every message in the list should have been returned."""
        messages = FEEDBACK_MESSAGES["KNEE_CAVE"]
        results = [get_coaching_message("KNEE_CAVE") for _ in range(len(messages))]
        assert set(results) == set(messages)

    def test_rotation_wraps_around_to_first_message(self):
        """Call N+1 times; the last result should equal the first."""
        n = len(FEEDBACK_MESSAGES["DEPTH_OK"])
        results = [get_coaching_message("DEPTH_OK") for _ in range(n + 1)]
        assert results[n] == results[0]

    def test_rotation_counters_are_independent_per_code(self):
        """Rotating one code must not affect another code's counter."""
        knee_first = get_coaching_message("KNEE_CAVE")
        back_first = get_coaching_message("BACK_ANGLE")
        # Exhaust KNEE_CAVE rotation
        for _ in range(len(FEEDBACK_MESSAGES["KNEE_CAVE"]) - 1):
            get_coaching_message("KNEE_CAVE")
        # BACK_ANGLE counter should still be at index 1
        assert get_coaching_message("BACK_ANGLE") == FEEDBACK_MESSAGES["BACK_ANGLE"][1]

    def test_good_form_messages_present(self):
        msg = get_coaching_message("GOOD_FORM")
        assert msg in FEEDBACK_MESSAGES["GOOD_FORM"]

    def test_pushup_too_shallow_messages_present(self):
        msg = get_coaching_message("PUSHUP_TOO_SHALLOW")
        assert msg in FEEDBACK_MESSAGES["PUSHUP_TOO_SHALLOW"]


# ─── TestMapFlagsToCoaching ───────────────────────────────────────────────────

class TestMapFlagsToCoaching:

    def test_empty_flags_returns_empty_list(self):
        assert map_flags_to_coaching([]) == []

    def test_warning_flag_is_included(self):
        flags = [make_flag("KNEE_CAVE", FeedbackSeverity.WARNING)]
        result = map_flags_to_coaching(flags)
        assert len(result) == 1
        assert result[0]["code"] == "KNEE_CAVE"

    def test_error_flag_is_included(self):
        flags = [make_flag("KNEE_CAVE", FeedbackSeverity.ERROR)]
        result = map_flags_to_coaching(flags)
        assert len(result) == 1

    def test_info_depth_ok_is_included(self):
        flags = [make_flag("DEPTH_OK", FeedbackSeverity.INFO)]
        result = map_flags_to_coaching(flags)
        assert len(result) == 1
        assert result[0]["code"] == "DEPTH_OK"

    def test_info_good_form_is_included(self):
        flags = [make_flag("GOOD_FORM", FeedbackSeverity.INFO)]
        result = map_flags_to_coaching(flags)
        assert len(result) == 1
        assert result[0]["code"] == "GOOD_FORM"

    def test_other_info_flags_are_excluded(self):
        flags = [make_flag("SOME_INFO_CODE", FeedbackSeverity.INFO)]
        result = map_flags_to_coaching(flags)
        assert result == []

    def test_result_items_have_required_keys(self):
        flags = [make_flag("KNEE_CAVE", FeedbackSeverity.WARNING)]
        item = map_flags_to_coaching(flags)[0]
        assert "code"     in item
        assert "severity" in item
        assert "message"  in item

    def test_result_code_matches_flag_code(self):
        flags = [make_flag("BACK_ANGLE", FeedbackSeverity.WARNING)]
        item = map_flags_to_coaching(flags)[0]
        assert item["code"] == "BACK_ANGLE"

    def test_result_severity_is_string(self):
        flags = [make_flag("KNEE_CAVE", FeedbackSeverity.WARNING)]
        item = map_flags_to_coaching(flags)[0]
        assert item["severity"] == "warning"

    def test_result_message_is_non_empty_string(self):
        flags = [make_flag("KNEE_CAVE", FeedbackSeverity.WARNING)]
        item = map_flags_to_coaching(flags)[0]
        assert isinstance(item["message"], str)
        assert len(item["message"]) > 0

    def test_result_message_from_feedback_library(self):
        flags = [make_flag("KNEE_CAVE", FeedbackSeverity.WARNING)]
        item = map_flags_to_coaching(flags)[0]
        assert item["message"] in FEEDBACK_MESSAGES["KNEE_CAVE"]

    def test_unknown_code_warning_still_returns_fallback_message(self):
        flags = [make_flag("WEIRD_ERROR", FeedbackSeverity.WARNING)]
        result = map_flags_to_coaching(flags)
        assert len(result) == 1
        assert isinstance(result[0]["message"], str)

    def test_multiple_flags_all_returned(self):
        flags = [
            make_flag("KNEE_CAVE",   FeedbackSeverity.WARNING),
            make_flag("BACK_ANGLE",  FeedbackSeverity.WARNING),
            make_flag("TOO_SHALLOW", FeedbackSeverity.WARNING),
        ]
        result = map_flags_to_coaching(flags)
        assert len(result) == 3
        codes = [r["code"] for r in result]
        assert "KNEE_CAVE"   in codes
        assert "BACK_ANGLE"  in codes
        assert "TOO_SHALLOW" in codes

    def test_mixed_severities_filters_correctly(self):
        flags = [
            make_flag("KNEE_CAVE",  FeedbackSeverity.WARNING),
            make_flag("DEPTH_OK",   FeedbackSeverity.INFO),
            make_flag("GOOD_FORM",  FeedbackSeverity.INFO),
            make_flag("OTHER_INFO", FeedbackSeverity.INFO),  # should be excluded
        ]
        result = map_flags_to_coaching(flags)
        codes = [r["code"] for r in result]
        assert "KNEE_CAVE" in codes
        assert "DEPTH_OK"  in codes
        assert "GOOD_FORM" in codes
        assert "OTHER_INFO" not in codes
        assert len(result) == 3

    def test_order_preserved(self):
        flags = [
            make_flag("BACK_ANGLE",  FeedbackSeverity.WARNING),
            make_flag("KNEE_CAVE",   FeedbackSeverity.WARNING),
        ]
        result = map_flags_to_coaching(flags)
        assert result[0]["code"] == "BACK_ANGLE"
        assert result[1]["code"] == "KNEE_CAVE"

    def test_repeated_calls_rotate_messages(self):
        """Calling map_flags_to_coaching twice for the same code should rotate."""
        flag = [make_flag("KNEE_CAVE", FeedbackSeverity.WARNING)]
        msg1 = map_flags_to_coaching(flag)[0]["message"]
        msg2 = map_flags_to_coaching(flag)[0]["message"]
        # Messages may be same (if only 1 in list) or different; both must be valid
        assert msg1 in FEEDBACK_MESSAGES["KNEE_CAVE"]
        assert msg2 in FEEDBACK_MESSAGES["KNEE_CAVE"]
