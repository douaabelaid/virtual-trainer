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

                # REMOVE the broken type/detected filters — server doesn't set these
                # Get landmarks — server sends as dict already
                landmarks = data.get("landmarks") or data.get("landmarks_raw") or {}
                if not landmarks or not isinstance(landmarks, dict):
                    continue

                state = detector.update(landmarks)
                coaching = map_flags_to_coaching(state.feedback_flags)

                print(f"\rStage: {state.stage.value.upper():<12} | Reps: {state.rep_count}", end="")
                if coaching:
                    print()
                    for item in coaching:
                        print(f"  [{item['severity'].upper()}] {item['message']}")

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

    # Auto-select wss:// for port 443 (ngrok) or explicit https ports
    scheme = "wss" if args.port == 443 else "ws"
    if args.port in (80, 443):
        URI = f"{scheme}://{args.host}/ws"
    else:
        URI = f"{scheme}://{args.host}:{args.port}/ws"
    asyncio.run(connect_with_retry(URI, args.exercise, args.retries))