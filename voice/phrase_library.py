"""
phrase_library.py
All coaching phrases that will be pre-synthesised at startup.
Keys are stable identifiers — used to name cache files.
"""

ALL_PHRASES: dict[str, str] = {

    # ── SQUAT ────────────────────────────────────────────────────────────────
    "KNEE_CAVE_0":          "Drive your knees outward, don't let them collapse in.",
    "KNEE_CAVE_1":          "Push your knees out in line with your toes.",
    "KNEE_CAVE_2":          "Your knees are caving — spread them wide.",

    "TOO_SHALLOW_0":        "Go deeper! Break parallel for a proper squat.",
    "TOO_SHALLOW_1":        "You're not going low enough — sink your hips down.",
    "TOO_SHALLOW_2":        "Drive those hips below your knees.",

    "DEPTH_OK_0":           "Great depth! Keep it up.",
    "DEPTH_OK_1":           "Perfect squat depth, well done.",
    "DEPTH_OK_2":           "Excellent — you're hitting full depth.",

    "BACK_ANGLE_0":         "Keep your chest up and your back straight.",
    "BACK_ANGLE_1":         "Don't lean too far forward — stay upright.",
    "BACK_ANGLE_2":         "Brace your core and keep that back neutral.",

    # ── PUSH-UP ──────────────────────────────────────────────────────────────
    "PUSHUP_TOO_SHALLOW_0": "Go lower — bring your chest all the way to the ground.",
    "PUSHUP_TOO_SHALLOW_1": "Not deep enough — push through the full range of motion.",
    "PUSHUP_TOO_SHALLOW_2": "Chest needs to get closer to the floor.",

    "ELBOW_FLARE_0":        "Keep your elbows tucked closer to your body.",
    "ELBOW_FLARE_1":        "Don't let your elbows flare out — keep them at 45 degrees.",
    "ELBOW_FLARE_2":        "Tuck those elbows in for a safer push-up.",

    # ── LUNGE ──────────────────────────────────────────────────────���─────────
    "KNEE_TOO_FORWARD_0":   "Your front knee is too far forward — keep it over your ankle.",
    "KNEE_TOO_FORWARD_1":   "Step out further so your knee stays behind your toes.",
    "KNEE_TOO_FORWARD_2":   "Drive that back knee down instead of pushing forward.",

    # ── GENERAL ──────────────────────────────────────────────────────────────
    "GOOD_FORM_0":          "Great form! Keep going.",
    "GOOD_FORM_1":          "Looking strong, perfect technique.",
    "GOOD_FORM_2":          "Excellent work, stay focused.",

    # ── REP MILESTONES ───────────────────────────────────────────────────────
    "REP_1":                "Rep 1 — great start!",
    "REP_5":                "Rep 5 — keep going, you're halfway there.",
    "REP_10":               "10 reps — well done, that's a full set!",
    "REP_MILESTONE_5":      "5 reps complete, excellent effort.",
    "REP_MILESTONE_10":     "10 reps complete, outstanding work.",

    # ── WARM-UP / SESSION ────────────────────────────────────────────────────
    "SESSION_START":        "Let's get started. Focus on your form.",
    "SESSION_END":          "Great session. Rest up and recover well.",
    "WARMUP_DONE":          "Warm-up complete. Time to work.",

    # ── ADDITIONAL CORRECTIONS ─────────────────────────────────────────
    "HEELS_DOWN_0":         "Keep your heels planted firmly on the floor.",
    "HEELS_DOWN_1":         "Don't lift your heels, drive through your midfoot.",
    "BREATHING_SQUAT":      "Inhale on the way down, exhale as you push up.",
    "CORE_SAG_0":           "Don't let your hips sag, keep your core tight.",
    "CORE_SAG_1":           "Squeeze your glutes to keep your body in a straight line.",
    "NECK_NEUTRAL_0":       "Look slightly ahead, keep your neck neutral.",
    "BREATHING_PUSHUP":     "Breathe in as you lower, breathe out as you push up.",
    "LUNGE_DEPTH_0":        "Lower your back knee until it almost touches the floor.",
    "LUNGE_DEPTH_1":        "Go a bit deeper on that lunge to get the full stretch.",
    "LUNGE_BALANCE_0":      "Keep your core braced and chest up for better balance.",

    # ── PACING & MOTIVATION ──────────────────────────────────────────
    "PACE_FAST_0":          "Slow down, control the eccentric movement.",
    "PACE_FAST_1":          "Don't rush, focus on the muscle contraction.",
    "PACE_SLOW_0":          "Good control, now drive up a little bit faster.",
    "MOTIVATION_0":         "Push through the burn, you got this!",
    "MOTIVATION_1":         "Stay strong, finish the set.",
    "MOTIVATION_2":         "Almost there, give it your absolute all.",

    # ── ADDITIONAL MILESTONES ────────────────────────────────────────
    "REP_2":                "Two reps down.",
    "REP_3":                "Three. Keep the rhythm.",
    "REP_4":                "Four. Good control.",
    "REP_15":               "Fifteen reps. Incredible work!",
    "REP_20":               "Twenty reps! Amazing endurance.",
}