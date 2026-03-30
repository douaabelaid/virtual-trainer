"""
session_recorder.py
-------------------
Wraps ws_client.py's receive loop and saves every processed frame
(landmarks, computed angles, detected stage, rep count) to a JSON log.

Use this during real-user test sessions — then feed the log to:
    python threshold_tuner.py --log session_log.json --exercise squat

Usage:
    python session_recorder.py --exercise squat --out session_user1.json
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import websockets
import json
import time
from pathlib import Path

from logic.exercise_detector import ExerciseDetector
from logic.angle_utils import get_joint_angles
from logic.feedback_mapper import map_flags_to_coaching

# ─── Config ───────────────────────────────────────────────────────────────────

URI                  = "wss://unpendulously-cingulate-cortney.ngrok-free.dev/ws"
LATENCY_THRESHOLD_MS = 100

# ─── Recorder ─────────────────────────────────────────────────────────────────

class SessionRecorder:
    def __init__(self, out_path: str, exercise: str):
        self.out_path = Path(out_path)
        self.exercise = exercise
        self.frames   = []
        self.start_ts = time.time()
        print(f"Recording session → {self.out_path}")

    def record(self, frame_id, latency_ms: int, landmarks: dict,
               angles: dict, stage: str, rep_count: int, coaching: list):
        self.frames.append({
            "frame_id":   frame_id,
            "latency_ms": latency_ms,
            "timestamp":  round(time.time() - self.start_ts, 3),
            "stage":      stage,
            "rep_count":  rep_count,
            "angles":     angles,
            "landmarks":  landmarks,
            "coaching":   coaching,
        })

    def save(self):
        payload = {
            "exercise":    self.exercise,
            "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "duration_s":  round(time.time() - self.start_ts, 1),
            "frame_count": len(self.frames),
            "frames":      self.frames,
        }
        with open(self.out_path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"\nSaved {len(self.frames)} frames → {self.out_path}")


# ─── Receive loop ─────────────────────────────────────────────────────────────

async def receive_and_record(websocket, detector: ExerciseDetector, recorder: SessionRecorder):
    async for message in websocket:
        now_ms = int(time.time() * 1000)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            continue

        frame_id   = data.get("frame_id", "?")
        frame_ts   = data.get("timestamp_ms", now_ms)
        latency_ms = now_ms - frame_ts

        if latency_ms > LATENCY_THRESHOLD_MS:
            print(f"  [SKIP] frame_id={frame_id} latency={latency_ms}ms")
            continue

        landmarks = data.get("landmarks") or data.get("landmarks_raw") or data
        if not landmarks or not isinstance(landmarks, dict):
            continue

        try:
            angles   = get_joint_angles(landmarks)
            state    = detector.update(landmarks)
            coaching = map_flags_to_coaching(state.feedback_flags)

            recorder.record(
                frame_id   = frame_id,
                latency_ms = latency_ms,
                landmarks  = landmarks,
                angles     = angles,
                stage      = state.stage.value,
                rep_count  = state.rep_count,
                coaching   = [{"code": c["code"], "severity": c["severity"]} for c in coaching],
            )

            print(f"  frame={frame_id} lat={latency_ms}ms stage={state.stage.value:<12} reps={state.rep_count}")

        except Exception as e:
            print(f"  [ERROR] frame_id={frame_id} — {e}")


# ─── Connect ──────────────────────────────────────────────────────────────────

async def connect(uri: str, exercise: str, out_path: str):
    detector = ExerciseDetector(exercise=exercise)
    recorder = SessionRecorder(out_path, exercise)

    print(f"Connecting to {uri} ...")
    try:
        async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
            print("Connected. Press Ctrl-C to stop and save.\n")
            await receive_and_record(ws, detector, recorder)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Connection error: {e}")
    finally:
        recorder.save()


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Record a VPT session to JSON")
    parser.add_argument("--exercise", default="squat", choices=["squat", "pushup", "lunge"])
    parser.add_argument("--out",      default=f"session_{int(time.time())}.json",
                        help="Output JSON file path")
    args = parser.parse_args()

    asyncio.run(connect(URI, args.exercise, args.out))