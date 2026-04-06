"""
threshold_tuner.py
------------------
Analyzes angle logs from real-user sessions and suggests optimal
DOWN / STANDING thresholds for each exercise.

Usage:
    # 1. Collect a session log first (see session_recorder.py)
    python threshold_tuner.py --log session_log.json --exercise squat

    # 2. Or run on multiple logs at once (e.g. 3 users)
    python threshold_tuner.py --log user1.json user2.json user3.json --exercise squat
"""

import json
import argparse
import statistics
from pathlib import Path


# ─── Joints to analyse per exercise ──────────────────────────────────────────

EXERCISE_JOINTS = {
    "squat":  ["left_knee", "right_knee"],
    "pushup": ["left_elbow", "right_elbow"],
    "lunge":  ["left_knee", "right_knee"],
}

CURRENT_THRESHOLDS = {
    "squat":  {"down": 95,  "standing": 160},
    "pushup": {"down": 90,  "standing": 160},
    "lunge":  {"down": 90,  "standing": 160},
}


# ─── Loader ───────────────────────────────────────────────────────────────────

def load_logs(paths: list) -> list:
    frames = []
    for path in paths:
        p = Path(path)
        if not p.exists():
            print(f"[WARN] File not found: {path} — skipping")
            continue
        with open(p) as f:
            data = json.load(f)
        # Accept either a list of frames or a dict with a "frames" key
        if isinstance(data, list):
            frames.extend(data)
        elif isinstance(data, dict) and "frames" in data:
            frames.extend(data["frames"])
        else:
            print(f"[WARN] Unrecognised format in {path} — skipping")
    print(f"Loaded {len(frames)} frames from {len(paths)} file(s)\n")
    return frames


# ─── Analysis ─────────────────────────────────────────────────────────────────

def extract_angles(frames: list, joint: str) -> list:
    """Pull all non-None angle values for a joint across frames."""
    values = []
    for f in frames:
        angles = f.get("angles", {})
        v = angles.get(joint)
        if v is not None:
            values.append(v)
    return values


def extract_angles_by_stage(frames: list, joint: str, stage: str) -> list:
    """Pull angles for a joint only during a specific stage."""
    values = []
    for f in frames:
        if f.get("stage", "").lower() != stage.lower():
            continue
        angles = f.get("angles", {})
        v = angles.get(joint)
        if v is not None:
            values.append(v)
    return values


def percentile(data: list, p: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)


def suggest_thresholds(frames: list, exercise: str) -> dict:
    joints = EXERCISE_JOINTS.get(exercise)
    if not joints:
        print(f"[ERROR] Unknown exercise: {exercise}")
        return {}

    current = CURRENT_THRESHOLDS.get(exercise, {})
    results = {}

    print(f"{'═'*54}")
    print(f"  Exercise: {exercise.upper()}")
    print(f"{'═'*54}\n")

    for joint in joints:
        all_angles    = extract_angles(frames, joint)
        down_angles   = extract_angles_by_stage(frames, joint, "down")
        stand_angles  = extract_angles_by_stage(frames, joint, "standing")

        if not all_angles:
            print(f"  [{joint}] No data found — skipping\n")
            continue

        # Suggest DOWN threshold: 90th percentile of DOWN-stage angles
        # (most people's deepest point, with a little headroom)
        suggested_down = round(percentile(down_angles, 90), 1) if down_angles else current["down"]

        # Suggest STANDING threshold: 10th percentile of STANDING-stage angles
        # (most people's straightest point, conservatively)
        suggested_stand = round(percentile(stand_angles, 10), 1) if stand_angles else current["standing"]

        results[joint] = {
            "suggested_down":     suggested_down,
            "suggested_standing": suggested_stand,
        }

        # ── Report ────────────────────────────────────────────────────────────
        print(f"  Joint: {joint}")
        print(f"  {'─'*48}")

        if all_angles:
            print(f"  All angles  — min: {min(all_angles):.1f}°  max: {max(all_angles):.1f}°  "
                  f"mean: {statistics.mean(all_angles):.1f}°  stdev: {statistics.stdev(all_angles):.1f}°")

        if down_angles:
            print(f"  DOWN stage  — n={len(down_angles)}  "
                  f"min: {min(down_angles):.1f}°  p50: {percentile(down_angles,50):.1f}°  "
                  f"p90: {percentile(down_angles,90):.1f}°  max: {max(down_angles):.1f}°")
        else:
            print(f"  DOWN stage  — no labeled frames found (label frames with stage='down')")

        if stand_angles:
            print(f"  STAND stage — n={len(stand_angles)}  "
                  f"min: {min(stand_angles):.1f}°  p10: {percentile(stand_angles,10):.1f}°  "
                  f"p50: {percentile(stand_angles,50):.1f}°  max: {max(stand_angles):.1f}°")
        else:
            print(f"  STAND stage — no labeled frames found")

        print()
        print(f"  Current thresholds  →  down < {current['down']}°   standing > {current['standing']}°")
        print(f"  Suggested           →  down < {suggested_down}°   standing > {suggested_stand}°")

        # Flag if change is significant
        down_delta  = abs(suggested_down  - current["down"])
        stand_delta = abs(suggested_stand - current["standing"])
        if down_delta > 5 or stand_delta > 5:
            print(f"  ⚠  Notable difference — consider updating thresholds in exercise_detector.py")
        else:
            print(f"  ✓  Current thresholds look reasonable for this dataset")

        print()

    return results


def generate_patch(exercise: str, results: dict) -> str:
    """Print a ready-to-paste THRESHOLDS patch for exercise_detector.py."""
    if not results:
        return ""

    joints = list(results.keys())
    if not joints:
        return ""

    # Average across both joints
    avg_down  = round(statistics.mean(v["suggested_down"]     for v in results.values()))
    avg_stand = round(statistics.mean(v["suggested_standing"] for v in results.values()))

    patch = (
        f"\n{'─'*54}\n"
        f"  Suggested patch for exercise_detector.py → THRESHOLDS\n"
        f"{'─'*54}\n"
        f'  "{exercise}": {{\n'
        f'      "down":     {{"left_{joints[0].split("_")[1]}": {avg_down},  "right_{joints[0].split("_")[1]}": {avg_down}}},\n'
        f'      "standing": {{"left_{joints[0].split("_")[1]}": {avg_stand}, "right_{joints[0].split("_")[1]}": {avg_stand}}},\n'
        f"  }}\n"
        f"{'─'*54}\n"
    )
    return patch


# ─── Demo / synthetic data generator ─────────────────────────────────────────

def generate_demo_log(path: str = "demo_session.json"):
    """
    Generates a synthetic session log so you can run the tuner
    without a real session file yet.
    """
    import random
    random.seed(42)
    frames = []
    # Simulate 3 sets of 10 squats
    for rep in range(30):
        # Standing frames
        for _ in range(8):
            angle = random.gauss(170, 5)
            frames.append({
                "stage": "standing",
                "angles": {
                    "left_knee":  round(angle, 2),
                    "right_knee": round(angle + random.gauss(0, 2), 2),
                }
            })
        # Transition down
        for i in range(5):
            angle = 170 - i * 15 + random.gauss(0, 3)
            frames.append({
                "stage": "transition",
                "angles": {
                    "left_knee":  round(angle, 2),
                    "right_knee": round(angle + random.gauss(0, 2), 2),
                }
            })
        # Down frames (squat depth varies by simulated user)
        for _ in range(6):
            angle = random.gauss(88, 7)  # some users deeper, some shallower
            frames.append({
                "stage": "down",
                "angles": {
                    "left_knee":  round(angle, 2),
                    "right_knee": round(angle + random.gauss(0, 3), 2),
                }
            })
        # Transition up
        for i in range(5):
            angle = 88 + i * 16 + random.gauss(0, 3)
            frames.append({
                "stage": "transition",
                "angles": {
                    "left_knee":  round(angle, 2),
                    "right_knee": round(angle + random.gauss(0, 2), 2),
                }
            })

    with open(path, "w") as f:
        json.dump(frames, f, indent=2)
    print(f"Demo log written to {path} ({len(frames)} frames)\n")
    return path


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Threshold tuner for VPT exercise detector")
    parser.add_argument("--log",      nargs="+", help="Path(s) to session JSON log file(s)")
    parser.add_argument("--exercise", default="squat", choices=["squat", "pushup", "lunge"])
    parser.add_argument("--demo",     action="store_true", help="Generate and analyse a synthetic demo log")
    args = parser.parse_args()

    if args.demo:
        demo_path = generate_demo_log()
        frames = load_logs([demo_path])
    elif args.log:
        frames = load_logs(args.log)
    else:
        parser.print_help()
        return

    if not frames:
        print("[ERROR] No frames loaded. Check your log files.")
        return

    results = suggest_thresholds(frames, args.exercise)
    print(generate_patch(args.exercise, results))


if __name__ == "__main__":
    main()