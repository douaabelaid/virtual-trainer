"""
live_demo.py — Virtual Trainer live camera demo
------------------------------------------------
Opens the webcam, runs MediaPipe PoseLandmarker (v0.10+ tasks API),
feeds landmarks into ExerciseDetector, and overlays real-time feedback.

Usage:
    python3 live_demo.py                        # squat, camera 0
    python3 live_demo.py --exercise pushup
    python3 live_demo.py --exercise lunge
    python3 live_demo.py --simulate             # no camera needed
    python3 live_demo.py --simulate --exercise pushup
    python3 live_demo.py --camera 1

Controls (window must be focused):
    Q  — quit
    R  — reset rep counter
    S/P/L — switch to Squat / Pushup / Lunge on the fly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import math
import time
import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from mediapipe.tasks.python.vision import PoseLandmarkerOptions, RunningMode

from logic.exercise_detector import ExerciseDetector
from logic.feedback_mapper import map_flags_to_coaching

_LANDMARK_NAMES = [p.name.lower() for p in mp_vision.PoseLandmark]
_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "pose_landmarker.task")

FONT = cv2.FONT_HERSHEY_SIMPLEX
W, H = 1280, 720
SEVERITY_COLOR = {
    "info":    (0, 220, 0),
    "warning": (0, 165, 255),
    "error":   (0, 0, 230),
}


# ── Synthetic landmark generators ─────────────────────────────────────────────

def _lerp(a, b, t):
    return a + (b - a) * t


def _make_squat_landmarks(t):
    hip_y    = _lerp(0.50, 0.60, t)
    knee_x_l = _lerp(0.43, 0.30, t)
    knee_y   = _lerp(0.68, 0.72, t)
    knee_x_r = _lerp(0.57, 0.70, t)
    return {
        "left_shoulder":  {"x": 0.45, "y": 0.22},
        "right_shoulder": {"x": 0.55, "y": 0.22},
        "left_hip":       {"x": 0.45, "y": hip_y},
        "right_hip":      {"x": 0.55, "y": hip_y},
        "left_knee":      {"x": knee_x_l, "y": knee_y},
        "right_knee":     {"x": knee_x_r, "y": knee_y},
        "left_ankle":     {"x": 0.43, "y": 0.85},
        "right_ankle":    {"x": 0.57, "y": 0.85},
        "left_elbow":     {"x": 0.35, "y": 0.38},
        "left_wrist":     {"x": 0.30, "y": 0.53},
        "right_elbow":    {"x": 0.65, "y": 0.38},
        "right_wrist":    {"x": 0.70, "y": 0.53},
    }


def _make_pushup_landmarks(t):
    # Top (t=0): elbows near shoulders, wrists below → elbow ~170°
    # Bottom (t=1): elbows at centre, wrists close inward/upward → elbow ~74°
    elbow_x_l = _lerp(0.35, 0.50, t)
    elbow_x_r = _lerp(0.65, 0.50, t)
    wrist_x_l = _lerp(0.28, 0.58, t)
    wrist_x_r = _lerp(0.72, 0.42, t)
    wrist_y   = _lerp(0.48, 0.22, t)
    return {
        "left_shoulder":  {"x": 0.40, "y": 0.20},
        "right_shoulder": {"x": 0.60, "y": 0.20},
        "left_hip":       {"x": 0.40, "y": 0.50},
        "right_hip":      {"x": 0.60, "y": 0.50},
        "left_knee":      {"x": 0.40, "y": 0.70},
        "right_knee":     {"x": 0.60, "y": 0.70},
        "left_ankle":     {"x": 0.40, "y": 0.90},
        "right_ankle":    {"x": 0.60, "y": 0.90},
        "left_elbow":     {"x": elbow_x_l, "y": 0.33},
        "left_wrist":     {"x": wrist_x_l, "y": wrist_y},
        "right_elbow":    {"x": elbow_x_r, "y": 0.33},
        "right_wrist":    {"x": wrist_x_r, "y": wrist_y},
    }


def _make_lunge_landmarks(t):
    hip_y    = _lerp(0.50, 0.62, t)
    knee_x_l = _lerp(0.43, 0.28, t)
    knee_y   = _lerp(0.68, 0.74, t)
    return {
        "left_shoulder":  {"x": 0.45, "y": 0.22},
        "right_shoulder": {"x": 0.55, "y": 0.22},
        "left_hip":       {"x": 0.45, "y": hip_y},
        "right_hip":      {"x": 0.55, "y": hip_y},
        "left_knee":      {"x": knee_x_l, "y": knee_y},
        "right_knee":     {"x": 0.57, "y": _lerp(0.68, 0.75, t)},
        "left_ankle":     {"x": 0.43, "y": 0.85},
        "right_ankle":    {"x": 0.57, "y": 0.85},
        "left_elbow":     {"x": 0.35, "y": 0.38},
        "left_wrist":     {"x": 0.30, "y": 0.53},
        "right_elbow":    {"x": 0.65, "y": 0.38},
        "right_wrist":    {"x": 0.70, "y": 0.53},
    }


_FACTORIES = {"squat": _make_squat_landmarks,
              "pushup": _make_pushup_landmarks,
              "lunge": _make_lunge_landmarks}


def _simulate_landmarks(exercise, elapsed_s):
    rep_period = 3.0
    phase = (elapsed_s % rep_period) / rep_period
    t = phase * 2 if phase <= 0.5 else (1.0 - phase) * 2
    t = (1 - math.cos(t * math.pi)) / 2
    return _FACTORIES[exercise](t)


def _draw_sim_skeleton(frame, lm_dict, fw, fh):
    CONNS = [
        ("left_shoulder", "right_shoulder"),
        ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
        ("left_hip", "right_hip"),
        ("left_hip", "left_knee"), ("right_hip", "right_knee"),
        ("left_knee", "left_ankle"), ("right_knee", "right_ankle"),
        ("left_shoulder", "left_elbow"), ("right_shoulder", "right_elbow"),
        ("left_elbow", "left_wrist"), ("right_elbow", "right_wrist"),
    ]
    pts = {n: (int(v["x"] * fw), int(v["y"] * fh)) for n, v in lm_dict.items()}
    for a, b in CONNS:
        if a in pts and b in pts:
            cv2.line(frame, pts[a], pts[b], (0, 180, 255), 3, cv2.LINE_AA)
    for pt in pts.values():
        cv2.circle(frame, pt, 6, (0, 255, 120), -1, cv2.LINE_AA)


# ── HUD ───────────────────────────────────────────────────────────────────────

def draw_hud(frame, exercise, stage, reps, coaching, fps, person_detected, simulate=False):
    h, w = frame.shape[:2]
    ov = frame.copy()
    cv2.rectangle(ov, (0, 0), (w, 70), (20, 20, 20), -1)
    cv2.addWeighted(ov, 0.55, frame, 0.45, 0, frame)

    title = exercise.upper() + ("  [SIMULATE]" if simulate else "")
    cv2.putText(frame, title, (15, 48), FONT, 1.2, (255, 255, 255), 2, cv2.LINE_AA)

    stage_color = {"standing": (80,200,80), "down": (80,80,240),
                   "transition": (80,200,210)}.get(stage, (200,200,200))
    cv2.putText(frame, stage.upper(), (w//2-70, 48), FONT, 1.1, stage_color, 2, cv2.LINE_AA)
    cv2.putText(frame, f"REPS: {reps}", (w-200, 48), FONT, 1.1, (255,255,255), 2, cv2.LINE_AA)
    cv2.putText(frame, f"FPS {fps:.0f}", (10, h-15), FONT, 0.6, (160,160,160), 1, cv2.LINE_AA)

    if not person_detected and not simulate:
        msg = "No person detected"
        tw = cv2.getTextSize(msg, FONT, 1.0, 2)[0][0]
        cv2.putText(frame, msg, ((w-tw)//2, h//2), FONT, 1.0, (0,60,230), 2, cv2.LINE_AA)
        return

    if coaching:
        ph = 40 + len(coaching) * 38
        ov2 = frame.copy()
        cv2.rectangle(ov2, (0, h-ph), (w, h), (20,20,20), -1)
        cv2.addWeighted(ov2, 0.55, frame, 0.45, 0, frame)
        for i, item in enumerate(coaching):
            col = SEVERITY_COLOR.get(item["severity"], (255,255,255))
            y = h - ph + 36 + i*38
            cv2.putText(frame, f"[{item['severity'].upper()}]",
                        (15, y), FONT, 0.65, col, 2, cv2.LINE_AA)
            cv2.putText(frame, item["message"],
                        (130, y), FONT, 0.65, (240,240,240), 1, cv2.LINE_AA)

    hint = "Q:quit  R:reset  S/P/L:exercise"
    tw = cv2.getTextSize(hint, FONT, 0.5, 1)[0][0]
    cv2.putText(frame, hint, (w-tw-10, h-10), FONT, 0.5, (120,120,120), 1, cv2.LINE_AA)


# ── Simulation mode ───────────────────────────────────────────────────────────

def run_simulate(exercise):
    detector         = ExerciseDetector(exercise=exercise)
    current_exercise = exercise
    start_time       = time.time()
    prev_time        = start_time
    last_coaching    = []
    last_stage       = "standing"
    last_reps        = 0

    print(f"[SIMULATE] Virtual Trainer — {exercise.upper()}")
    print("           1 synthetic rep every ~3 s  |  Q to quit\n")

    while True:
        now       = time.time()
        fps       = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        lm_dict = _simulate_landmarks(current_exercise, now - start_time)
        state   = detector.update(lm_dict)
        last_coaching = map_flags_to_coaching(state.feedback_flags)
        last_stage    = state.stage.value
        last_reps     = state.rep_count

        frame = np.full((H, W, 3), (25, 25, 35), dtype=np.uint8)
        _draw_sim_skeleton(frame, lm_dict, W, H)
        draw_hud(frame, current_exercise, last_stage,
                 last_reps, last_coaching, fps,
                 person_detected=True, simulate=True)

        cv2.imshow("Virtual Trainer — Simulation", frame)

        coaching_txt = " | ".join(
            f"[{c['severity'].upper()}] {c['message']}" for c in last_coaching) or "—"
        print(f"\rStage: {last_stage.upper():12}  Reps: {last_reps:3}  {coaching_txt}   ",
              end="", flush=True)

        key = cv2.waitKey(33) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("r"):
            detector.reset(); start_time = time.time()
            last_coaching = []; last_stage = "standing"; last_reps = 0
            print("\nReset.")
        elif key in (ord("s"), ord("S")):
            current_exercise = "squat"; detector = ExerciseDetector("squat")
            start_time = time.time(); last_coaching = []; print("\nSwitched to SQUAT")
        elif key in (ord("p"), ord("P")):
            current_exercise = "pushup"; detector = ExerciseDetector("pushup")
            start_time = time.time(); last_coaching = []; print("\nSwitched to PUSHUP")
        elif key in (ord("l"), ord("L")):
            current_exercise = "lunge"; detector = ExerciseDetector("lunge")
            start_time = time.time(); last_coaching = []; print("\nSwitched to LUNGE")

    cv2.destroyAllWindows()
    print(f"\n\nSession ended — {last_reps} reps completed.")


# ── Live camera mode ──────────────────────────────────────────────────────────

def landmarks_to_dict(pose_landmarks):
    return {
        _LANDMARK_NAMES[idx]: {
            "x": round(lm.x, 4), "y": round(lm.y, 4), "z": round(lm.z, 4),
            "visibility": round(getattr(lm, "visibility", 1.0) or 1.0, 4),
        }
        for idx, lm in enumerate(pose_landmarks) if idx < len(_LANDMARK_NAMES)
    }


def _draw_skeleton(frame, pose_landmarks, fw, fh):
    pts = [(int(lm.x*fw), int(lm.y*fh)) for lm in pose_landmarks]
    for s, e in mp_vision.PoseLandmarksConnections.POSE_LANDMARKS:
        if s < len(pts) and e < len(pts):
            cv2.line(frame, pts[s], pts[e], (0,180,255), 2, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(frame, pt, 4, (0,255,120), -1, cv2.LINE_AA)


def run_camera(exercise, camera_index):
    if not os.path.exists(_MODEL_PATH):
        print(f"ERROR: Model file not found: {_MODEL_PATH}")
        sys.exit(1)

    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {camera_index}.")
        print("Tip: run with --simulate to test without a camera.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    detector         = ExerciseDetector(exercise=exercise)
    current_exercise = exercise
    prev_time        = time.time()
    last_coaching    = []
    last_stage       = "standing"
    last_reps        = 0

    base_opts = mp_python.BaseOptions(model_asset_path=_MODEL_PATH)
    opts = PoseLandmarkerOptions(
        base_options=base_opts, running_mode=RunningMode.IMAGE, num_poses=1,
        min_pose_detection_confidence=0.55,
        min_pose_presence_confidence=0.55,
        min_tracking_confidence=0.55,
    )

    with mp_vision.PoseLandmarker.create_from_options(opts) as landmarker:
        print(f"Virtual Trainer — {exercise.upper()} | Q to quit")
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            now = time.time(); fps = 1.0/max(now-prev_time,1e-6); prev_time = now
            fh2, fw2 = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
            if result.pose_landmarks:
                pose_lms = result.pose_landmarks[0]
                _draw_skeleton(frame, pose_lms, fw2, fh2)
                state = detector.update(landmarks_to_dict(pose_lms))
                last_coaching = map_flags_to_coaching(state.feedback_flags)
                last_stage    = state.stage.value
                last_reps     = state.rep_count
            draw_hud(frame, current_exercise, last_stage,
                     last_reps, last_coaching, fps,
                     person_detected=bool(result.pose_landmarks))
            cv2.imshow("Virtual Trainer — Live Demo", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"): break
            elif key == ord("r"):
                detector.reset(); last_coaching=[]; last_stage="standing"; last_reps=0
            elif key in (ord("s"),ord("S")):
                current_exercise="squat"; detector=ExerciseDetector("squat"); last_coaching=[]
            elif key in (ord("p"),ord("P")):
                current_exercise="pushup"; detector=ExerciseDetector("pushup"); last_coaching=[]
            elif key in (ord("l"),ord("L")):
                current_exercise="lunge"; detector=ExerciseDetector("lunge"); last_coaching=[]
    cap.release()
    cv2.destroyAllWindows()
    print(f"\nSession ended — {last_reps} reps completed.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Virtual Trainer live demo")
    parser.add_argument("--exercise", default="squat",
                        choices=["squat", "pushup", "lunge"])
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--simulate", action="store_true",
                        help="Run with synthetic landmarks — no camera needed")
    args = parser.parse_args()

    if args.simulate:
        run_simulate(args.exercise)
    else:
        run_camera(args.exercise, args.camera)
