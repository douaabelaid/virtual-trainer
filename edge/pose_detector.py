import cv2
import mediapipe as mp
import json
import time

# ---------------------------------------------------------------------------
# Jetson Nano optimisation settings
# ---------------------------------------------------------------------------
CAPTURE_WIDTH  = 640   # capture at 640x480 — enough for accurate detection
CAPTURE_HEIGHT = 480
INFER_WIDTH    = 320   # downscale before MediaPipe to cut inference cost
INFER_HEIGHT   = 240
TARGET_FPS     = 15    # hard cap: skip frames when camera runs faster
DISPLAY_EVERY  = 1     # show every N-th processed frame (raise to 2 to save GPU time)
# ---------------------------------------------------------------------------

mp_pose    = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Build landmark-name lookup once at import time to avoid per-frame enum calls
_LANDMARK_NAMES = [lm.name for lm in mp_pose.PoseLandmark]

# Slim drawing spec — thinner lines render faster on a small GPU
_LANDMARK_STYLE    = mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=1, circle_radius=2)
_CONNECTION_STYLE  = mp_drawing.DrawingSpec(color=(0, 200, 255), thickness=1)


def get_landmarks_json(landmarks, timestamp_ms):
    """Return a dict with timestamp and all 33 landmark coordinates."""
    return {
        "timestamp_ms": timestamp_ms,
        "landmarks": {
            _LANDMARK_NAMES[idx]: {
                "x":          round(lm.x,          4),
                "y":          round(lm.y,          4),
                "z":          round(lm.z,          4),
                "visibility": round(lm.visibility, 4),
            }
            for idx, lm in enumerate(landmarks.landmark)
        },
    }


def run():
    cap = cv2.VideoCapture(0)

    # Request a smaller buffer so we always get the latest frame
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS,          TARGET_FPS)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)          # discard stale frames

    frame_interval = 1.0 / TARGET_FPS              # minimum seconds per frame
    prev_time      = time.time()
    display_count  = 0

    # model_complexity=0  → lightest model (~6 MB, fastest on CPU/GPU)
    # smooth_landmarks=False → skip the EMA smoother (saves ~2 ms/frame)
    # enable_segmentation=False → don't compute the segmentation mask
    with mp_pose.Pose(
        model_complexity=0,
        smooth_landmarks=False,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # --- hard FPS cap: drop frames that arrive too early ----------
            now = time.time()
            elapsed = now - prev_time
            if elapsed < frame_interval:
                continue
            prev_time = now
            timestamp_ms = int(now * 1000)
            # ---------------------------------------------------------------

            # Downscale for inference (nearest-neighbour is fastest)
            small = cv2.resize(frame, (INFER_WIDTH, INFER_HEIGHT),
                               interpolation=cv2.INTER_NEAREST)

            # BGR → RGB, mark non-writeable to avoid a copy inside MediaPipe
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = pose.process(rgb)

            if results.pose_landmarks:
                # Draw skeleton on the small frame (cheap) then upscale for display
                rgb.flags.writeable = True
                bgr_small = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                mp_drawing.draw_landmarks(
                    bgr_small,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=_LANDMARK_STYLE,
                    connection_drawing_spec=_CONNECTION_STYLE,
                )
                display_frame = cv2.resize(bgr_small, (CAPTURE_WIDTH, CAPTURE_HEIGHT),
                                           interpolation=cv2.INTER_NEAREST)

                # Emit 33-landmark JSON
                data = get_landmarks_json(results.pose_landmarks, timestamp_ms)
                print(json.dumps(data))
            else:
                display_frame = frame

            # --- FPS overlay -----------------------------------------------
            fps = 1.0 / max(elapsed, 1e-6)
            cv2.putText(display_frame, f"FPS: {fps:.1f}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 255, 0), 2, cv2.LINE_AA)
            # ---------------------------------------------------------------

            # Only blit every DISPLAY_EVERY frames to save display overhead
            display_count += 1
            if display_count % DISPLAY_EVERY == 0:
                cv2.imshow("VPT - Pose Detector", display_frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
