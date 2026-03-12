import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
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

                # Handle both formats:
                # Format 1: raw landmarks dict directly
                # Format 2: wrapped in "landmarks_raw" key
                landmarks = data.get("landmarks", data.get("landmarks_raw", data))
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


if __name__ == "__main__":
    # Replace with Student A's IP address
    STUDENT_A_IP = "192.168.1.23"
    URI = f"ws://{STUDENT_A_IP}:8000/ws"
    EXERCISE = "squat"
    asyncio.run(connect(URI, EXERCISE))