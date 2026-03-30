"""
Live Camera Test — Virtual Personal Trainer
============================================
Connects to your PC camera and shows in real-time:
  - Pose landmarks overlaid on the video feed
  - Joint angles for each key joint
  - Exercise stage (STANDING / DOWN / TRANSITION)
  - Rep counter
  - Feedback messages from the logic layer

Uses the MediaPipe Tasks API (mediapipe 0.10+).

Press 'q' to quit.
Press 's' to switch exercise: squat → pushup → lunge → squat
"""

import sys
import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from logic.angle_utils import get_joint_angles
from logic.exercise_detector import ExerciseDetector
from logic.feedback_mapper import get_coaching_message

# ─── Landmark indices (MediaPipe Pose 33 keypoints) ──────────────────────────
LM = {
    "nose": 0,
    "left_shoulder": 11, "right_shoulder": 12,
    "left_elbow": 13,    "right_elbow": 14,
    "left_wrist": 15,    "right_wrist": 16,
    "left_hip": 23,      "right_hip": 24,
    "left_knee": 25,     "right_knee": 26,
    "left_ankle": 27,    "right_ankle": 28,
}

# Skeleton connections (pairs of landmark indices)
POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
    (11, 23), (12, 24), (23, 24),
    (23, 25), (24, 26), (25, 27), (26, 28),
    (27, 29), (28, 30), (29, 31), (30, 32),
]

# ─── Colour palette ───────────────────────────────────────────────────────────
GREEN  = (0, 255, 0)
YELLOW = (0, 255, 255)
RED    = (0, 0, 255)
WHITE  = (255, 255, 255)
CYAN   = (255, 255, 0)
BLACK  = (0, 0, 0)
SEVERITY_COLOUR = {"info": GREEN, "warning": YELLOW, "error": RED}

# ─── Overlay helpers ──────────────────────────────────────────────────────────

def draw_panel(img, lines, x, y, line_h=22, padding=8, text_scale=0.55, colour=WHITE):
    if not lines:
        return
    max_w = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, text_scale, 1)[0][0]
                for l in lines) + padding * 2
    panel_h = len(lines) * line_h + padding * 2
    overlay = img.copy()
    cv2.rectangle(overlay, (x, y), (x + max_w, y + panel_h), BLACK, -1)
    cv2.addWeighted(overlay, 0.55, img, 0.45, 0, img)
    for i, line in enumerate(lines):
        cv2.putText(img, line,
                    (x + padding, y + padding + (i + 1) * line_h - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, text_scale, colour, 1, cv2.LINE_AA)


def draw_skeleton(img, landmarks, h, w):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in POSE_CONNECTIONS:
        if a < len(pts) and b < len(pts):
            cv2.line(img, pts[a], pts[b], WHITE, 2, cv2.LINE_AA)
    for pt in pts:
        cv2.circle(img, pt, 3, GREEN, -1, cv2.LINE_AA)


def draw_angle_on_joint(img, landmarks, h, w, joint_name, angle):
    idx = LM.get(joint_name)
    if idx is None or idx >= len(landmarks):
        return
    lm = landmarks[idx]
    cx, cy = int(lm.x * w), int(lm.y * h)
    cv2.putText(img, f"{angle:.0f}deg",
                (cx + 8, cy - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, CYAN, 1, cv2.LINE_AA)
    cv2.circle(img, (cx, cy), 6, CYAN, -1)


def build_landmark_dict(landmarks):
    return {name: {"x": landmarks[idx].x, "y": landmarks[idx].y}
            for name, idx in LM.items()}


# ─── Main live camera loop ────────────────────────────────────────────────────

def run_live_test():
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "pose_landmarker.task")
    if not os.path.exists(model_path):
        print(f"ERROR: Model file not found at {model_path}")
        return

    exercises = ["squat", "pushup", "lunge"]
    ex_idx = 0
    detector = ExerciseDetector(exercises[ex_idx])

    # ── Build landmarker (VIDEO mode = synchronous per-frame) ──
    base_options = mp_python.BaseOptions(model_asset_path=model_path)
    options = mp_vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open camera.")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    feedback_display = []
    frame_id = 0
    fps_start = time.time()
    fps = 0.0

    print("Live camera test started. Press 'q' to quit, 's' to switch exercise.")

    with mp_vision.PoseLandmarker.create_from_options(options) as landmarker:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("ERROR: Failed to grab frame.")
                break

            frame_id += 1
            now = time.time()
            timestamp_ms = int(now * 1000)

            if frame_id % 30 == 0:
                fps = 30 / (now - fps_start + 1e-9)
                fps_start = now

            h, w = frame.shape[:2]

            # ── Inference ──
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(mp_image, timestamp_ms)

            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]  # first (only) pose

                # ── Draw skeleton ──
                draw_skeleton(frame, landmarks, h, w)

                # ── Build dict & run logic ──
                landmark_dict = build_landmark_dict(landmarks)
                state = detector.update(landmark_dict)
                angles = get_joint_angles(landmark_dict)

                # ── Draw angles on joints ──
                for joint, angle in angles.items():
                    draw_angle_on_joint(frame, landmarks, h, w, joint, angle)

                # ── Collect feedback ──
                for flag in state.feedback_flags:
                    msg = get_coaching_message(flag.code)
                    col = SEVERITY_COLOUR.get(flag.severity.value, WHITE)
                    feedback_display.append((msg, col, now + 3.0))

                # ── Top-left: exercise info ──
                stage_colour = {"standing": GREEN, "down": RED,
                                "transition": YELLOW}.get(state.stage.value, WHITE)
                draw_panel(frame, [
                    f"Exercise : {state.exercise.value.upper()}",
                    f"Stage    : {state.stage.value.upper()}",
                    f"Reps     : {state.rep_count}",
                    f"FPS      : {fps:.1f}",
                    f"Frame ID : {frame_id}",
                    f"Time(ms) : {timestamp_ms}",
                ], x=10, y=10, colour=stage_colour)

                # ── Top-right: joint angles ──
                draw_panel(frame,
                    ["-- Joint Angles --"] + [
                        f"{k.replace('_',' ').title():<18}: {v:.1f}deg"
                        for k, v in angles.items()
                    ],
                    x=w - 290, y=10, colour=CYAN)

            else:
                draw_panel(frame, ["No pose detected - step back"],
                           x=10, y=10, colour=YELLOW)

            # ── Bottom: feedback ──
            feedback_display = [(m, c, e) for m, c, e in feedback_display if e > now]
            if feedback_display:
                fb_lines = ["-- Feedback --"] + [m for m, _, _ in feedback_display[-4:]]
                draw_panel(frame, fb_lines,
                           x=10, y=h - len(fb_lines) * 24 - 20,
                           colour=YELLOW, line_h=24)

            cv2.putText(frame, "Q: Quit | S: Switch exercise",
                        (w // 2 - 140, h - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1, cv2.LINE_AA)

            cv2.imshow("Virtual Trainer - Live Camera Test", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('s'):
                ex_idx = (ex_idx + 1) % len(exercises)
                detector = ExerciseDetector(exercises[ex_idx])
                feedback_display.clear()
                print(f"Switched to: {exercises[ex_idx].upper()}")

    cap.release()
    cv2.destroyAllWindows()
    print("Live camera test ended.")


if __name__ == "__main__":
    run_live_test()
