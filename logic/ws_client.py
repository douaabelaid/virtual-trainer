import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import argparse
import websockets
import json
from logic.exercise_detector import ExerciseDetector
from logic.feedback_mapper import map_flags_to_coaching

async def connect(uri: str, exercise: str = "squat"):
    detector = ExerciseDetector(exercise=exercise)
    print(f"Connecting to {uri}...")

    async with websockets.connect(uri) as websocket:
        print("Connected! Receiving landmarks...\n")

        async for message in websocket:
            try:
                data = json.loads(message)

                # Server sends landmarks as a list: [{"name":"left_knee","x":..,"y":..}, ...]
                # angle_utils expects a dict:          {"left_knee": {"x":..,"y":..}, ...}
                raw = data.get("landmarks", data.get("landmarks_raw", data))
                if not raw:
                    continue
                if isinstance(raw, list):
                    landmarks = {lm["name"]: lm for lm in raw if "name" in lm}
                else:
                    landmarks = raw
                if not landmarks:
                    continue

                # Run exercise detection
                state = detector.update(landmarks)

                # Get coaching messages
                coaching = map_flags_to_coaching(state.feedback_flags)

                # Display live output
                print(f"Stage: {state.stage.value.upper():12} | Reps: {state.rep_count}", end="")

                if coaching:
                    print()
                    for item in coaching:
                        print(f"  [{item['severity'].upper()}] {item['message']}")
                else:
                    print()

            except json.JSONDecodeError:
                print("Invalid JSON received")
            except Exception as e:
                print(f"Error: {e}")


async def connect_with_retry(uri: str, exercise: str = "squat", max_retries: int = 5):
    """Attempt to connect, automatically retrying with exponential backoff on failure."""
    delay = 2
    for attempt in range(1, max_retries + 1):
        try:
            await connect(uri, exercise)
            return  # clean exit (e.g., server closed connection intentionally)
        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.WebSocketException,
                OSError) as exc:
            print(f"Connection error: {exc}")
            if attempt < max_retries:
                print(f"Reconnecting in {delay}s… (attempt {attempt}/{max_retries})")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)  # cap backoff at 30 s
            else:
                print("Max retries reached. Exiting.")
                raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Virtual Trainer WebSocket client")
    parser.add_argument("--host",     default="192.168.1.23",
                        help="Edge server IP address (default: 192.168.1.23)")
    parser.add_argument("--port",     type=int, default=8000,
                        help="Edge server port (default: 8000)")
    parser.add_argument("--exercise", default="squat",
                        choices=["squat", "pushup", "lunge"],
                        help="Exercise to track (default: squat)")
    parser.add_argument("--retries",  type=int, default=5,
                        help="Max reconnect attempts (default: 5)")
    args = parser.parse_args()

    URI = f"ws://{args.host}:{args.port}/ws"
    asyncio.run(connect_with_retry(URI, args.exercise, args.retries))