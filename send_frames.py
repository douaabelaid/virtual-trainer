"""
send_frames.py
Captures frames from a local webcam and sends them as base64-encoded JPEG
to the ws_server.py WebSocket server for MediaPipe pose processing.

Usage:
    python send_frames.py
    python send_frames.py --host localhost --port 8765 --exercise squat
    python send_frames.py --host unpendulously-cingulate-cortney.ngrok-free.dev --port 443 --ssl
"""

import asyncio
import argparse
import base64
import json
import logging
import sys
import os
import time

import cv2
import websockets

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from logic.exercise_detector import ExerciseDetector
from logic.feedback_mapper import map_flags_to_coaching

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("send_frames")


async def stream(uri: str, exercise: str, fps: int, show: bool) -> None:
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        logger.error("Cannot open camera (index 0). Check your webcam connection.")
        return

    # Set camera resolution to 640×480 for performance
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    frame_interval = 1.0 / fps
    frame_idx = 0
    detector = ExerciseDetector(exercise=exercise)

    logger.info(f"Connecting to {uri} …")
    try:
        async with websockets.connect(uri) as ws:
            logger.info(f"Connected! Streaming webcam at {fps} FPS → exercise: {exercise}")
            logger.info("Press Ctrl+C to stop.\n")

            # Inform server of the exercise upfront
            await ws.send(json.dumps({"type": "set_exercise", "exercise": exercise}))

            last_overlay: dict = {}

            async def receive_loop() -> None:
                """Print pose feedback received from the server."""
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    nonlocal last_overlay
                    last_overlay = data
                    fps_val  = data.get("fps", 0)
                    lat      = data.get("latency_ms", 0)
                    stage    = data.get("stage", "—")
                    reps     = data.get("rep_count", 0)
                    feedback = data.get("feedback", [])
                    fb_txt   = feedback[0]["message"] if feedback else "—"
                    print(
                        f"\r[✅ pose]  {fps_val:.1f} FPS  {lat:.1f} ms  "
                        f"stage={stage.upper():<12}  reps={reps}  {fb_txt:<35}",
                        end="", flush=True
                    )

            asyncio.ensure_future(receive_loop())

            while True:
                t0 = time.monotonic()

                ret, frame = cap.read()
                if not ret:
                    logger.warning("Frame capture failed — skipping.")
                    await asyncio.sleep(frame_interval)
                    continue

                # Encode frame to JPEG then base64
                _, buf = cv2.imencode(
                    ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                )
                b64 = base64.b64encode(buf).decode()

                payload = json.dumps(
                    {"type": "frame", "data": b64, "exercise": exercise},
                    separators=(",", ":"),
                )
                await ws.send(payload)
                frame_idx += 1

                if show:
                    overlay = last_overlay
                    label = (
                        f"#{frame_idx}  {overlay.get('fps', 0):.1f} FPS  "
                        f"{overlay.get('latency_ms', 0):.1f} ms  "
                        f"{'POSE OK' if overlay.get('detected') else 'NO POSE'}"
                    )
                    cv2.putText(
                        frame, label, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2,
                    )
                    cv2.imshow("send_frames — press Q to quit", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        logger.info("Quit key pressed.")
                        break

                # Maintain target FPS
                elapsed = time.monotonic() - t0
                sleep_for = frame_interval - elapsed
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

    except websockets.exceptions.ConnectionClosedError as exc:
        logger.error(f"Connection closed unexpectedly: {exc}")
    except ConnectionRefusedError:
        logger.error(f"Connection refused — is ws_server.py running at {uri}?")
    except asyncio.CancelledError:
        logger.info("Stopped by user.")
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    finally:
        cap.release()
        if show:
            cv2.destroyAllWindows()
        logger.info(f"Sent {frame_idx} frames total.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Webcam → ws_server frame sender"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server hostname or IP (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Server WebSocket port (default: 8765)",
    )
    parser.add_argument(
        "--exercise",
        default="squat",
        choices=["squat", "pushup", "lunge"],
        help="Exercise to track (default: squat)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=15,
        help="Target send rate in frames per second (default: 15)",
    )
    parser.add_argument(
        "--ssl",
        action="store_true",
        help="Use wss:// (TLS) instead of ws:// (required for ngrok / port 443)",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show a live preview window of the webcam feed",
    )
    args = parser.parse_args()

    scheme = "wss" if args.ssl else "ws"
    URI = f"{scheme}://{args.host}:{args.port}/ws"

    asyncio.run(stream(URI, args.exercise, args.fps, args.show))
