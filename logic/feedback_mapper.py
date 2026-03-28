# feedback_mapper.py
# Maps feedback flag codes → coaching sentences for the voice layer (Phase 2)

FEEDBACK_MESSAGES = {

    # --- SQUAT ---
    "KNEE_CAVE": [
        "Drive your knees outward, don't let them collapse in.",
        "Push your knees out in line with your toes.",
        "Your knees are caving — spread them wide.",
    ],
    "TOO_SHALLOW": [
        "Go deeper! Break parallel for a proper squat.",
        "You're not going low enough — sink your hips down.",
        "Drive those hips below your knees.",
    ],
    "DEPTH_OK": [
        "Great depth! Keep it up.",
        "Perfect squat depth, well done.",
        "Excellent — you're hitting full depth.",
    ],
    "BACK_ANGLE": [
        "Keep your chest up and your back straight.",
        "Don't lean too far forward — stay upright.",
        "Brace your core and keep that back neutral.",
    ],

    # --- PUSH-UP ---
    "PUSHUP_TOO_SHALLOW": [
        "Go lower — bring your chest all the way to the ground.",
        "Not deep enough — push through the full range of motion.",
        "Chest needs to get closer to the floor.",
    ],
    "ELBOW_FLARE": [
        "Keep your elbows tucked closer to your body.",
        "Don't let your elbows flare out — keep them at 45 degrees.",
        "Tuck those elbows in for a safer push-up.",
    ],

    # --- LUNGE ---
    "KNEE_TOO_FORWARD": [
        "Your front knee is too far forward — keep it over your ankle.",
        "Step out further so your knee stays behind your toes.",
        "Drive that back knee down instead of pushing forward.",
    ],

    # --- GENERAL ---
    "GOOD_FORM": [
        "Great form! Keep going.",
        "Looking strong, perfect technique.",
        "Excellent work, stay focused.",
    ],
}

# Tracks which message index to use per code (rotates messages to avoid repetition)
_message_counter = {}


def get_coaching_message(code: str) -> str:
    """
    Returns a coaching sentence for a given feedback code.
    Rotates through available messages to avoid repetition.

    Parameters:
        code: feedback flag code e.g. "KNEE_CAVE"

    Returns:
        A coaching sentence string
    """
    messages = FEEDBACK_MESSAGES.get(code)

    if not messages:
        return f"Check your form on {code.replace('_', ' ').lower()}."

    # Rotate through messages
    idx = _message_counter.get(code, 0)
    message = messages[idx % len(messages)]
    _message_counter[code] = idx + 1

    return message


def map_flags_to_coaching(feedback_flags: list) -> list:
    """
    Takes a list of FeedbackFlag objects and returns a list of coaching sentences.
    Only maps WARNING and ERROR flags — ignores INFO unless it's DEPTH_OK.

    Parameters:
        feedback_flags: list of FeedbackFlag objects from ExerciseDetector

    Returns:
        list of coaching sentence strings
    """
    coaching = []

    for flag in feedback_flags:
        # Always include warnings and errors
        if flag.severity.value in ["warning", "error"]:
            message = get_coaching_message(flag.code)
            coaching.append({
                "code": flag.code,
                "severity": flag.severity.value,
                "message": message
            })
        # Only include info for positive feedback codes
        elif flag.severity.value == "info" and flag.code in ("DEPTH_OK", "GOOD_FORM"):
            message = get_coaching_message(flag.code)
            coaching.append({
                "code": flag.code,
                "severity": flag.severity.value,
                "message": message
            })

    return coaching


# --- TEST ---
if __name__ == "__main__":
    from shared.exercise_state_schema import FeedbackFlag, FeedbackSeverity

    test_flags = [
        FeedbackFlag(code="KNEE_CAVE",   message="Left knee caving inward", severity=FeedbackSeverity.WARNING),
        FeedbackFlag(code="TOO_SHALLOW", message="Squat not deep enough",   severity=FeedbackSeverity.WARNING),
        FeedbackFlag(code="DEPTH_OK",    message="Good depth",              severity=FeedbackSeverity.INFO),
        FeedbackFlag(code="BACK_ANGLE",  message="Keep your back straight", severity=FeedbackSeverity.WARNING),
    ]

    print("=== Feedback Mapper Test ===\n")
    coaching = map_flags_to_coaching(test_flags)
    for item in coaching:
        print(f"[{item['severity'].upper()}] {item['code']}")
        print(f"  → {item['message']}\n")

    print("--- Rotation test (same code 3x) ---")
    for i in range(3):
        print(f"  Rep {i+1}: {get_coaching_message('KNEE_CAVE')}")