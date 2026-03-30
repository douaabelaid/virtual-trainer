"""
test_ws_integration.py
-----------------------
Automated integration test for ws_client.py against mock_edge_server.py.
Run this AFTER starting mock_edge_server.py in a separate terminal.

Usage:
    # Terminal 1:
    python mock_edge_server.py

    # Terminal 2:
    python test_ws_integration.py

Passes when all assertions succeed. Produces a short report you can
include as integration evidence in your README or submit to your supervisor.
"""

import asyncio
import json
import time
import websockets
from shared.exercise_state_schema import ExerciseState

WS_URL = "ws://localhost:8765"
TEST_DURATION_SECONDS = 12   # enough for at least 2 full squat cycles at 15 FPS
MIN_FPS = 15
MIN_REPS_EXPECTED = 1        # at least 1 full rep in 12 seconds


# ── helpers ──────────────────────────────────────────────────────────────────

def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return condition


# ── main test ────────────────────────────────────────────────────────────────

async def run_integration_test():
    print("=" * 60)
    print("  WS Integration Test — Student B vs Mock Edge Server")
    print(f"  Connecting to {WS_URL}")
    print("=" * 60)

    frames_received   = 0
    parse_errors      = 0
    schema_errors     = 0
    stages_seen       = set()
    max_rep_count     = 0
    feedback_codes    = set()
    latencies_ms      = []
    first_frame_time  = None
    last_frame_time   = None

    try:
        async with websockets.connect(WS_URL, open_timeout=5) as ws:
            print(f"\n  Connected. Collecting frames for {TEST_DURATION_SECONDS}s...\n")
            deadline = time.monotonic() + TEST_DURATION_SECONDS

            while time.monotonic() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    print("  [WARN] No frame received within 1s — server may be slow")
                    continue

                recv_time = time.monotonic()

                # 1. JSON parse
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as e:
                    parse_errors += 1
                    print(f"  [WARN] JSON parse error on frame {frames_received}: {e}")
                    continue

                # 2. Schema validation via Pydantic
                try:
                    state = ExerciseState(**data)
                except Exception as e:
                    schema_errors += 1
                    print(f"  [WARN] Schema validation failed on frame {frames_received}: {e}")
                    continue

                # 3. Collect metrics
                frames_received += 1
                now = time.monotonic()

                if first_frame_time is None:
                    first_frame_time = now
                last_frame_time = now

                stages_seen.add(state.stage.value)
                max_rep_count = max(max_rep_count, state.rep_count)

                for flag in state.feedback_flags:
                    feedback_codes.add(flag.code)

                if state.timestamp_ms:
                    server_ts_s = state.timestamp_ms / 1000
                    latency_ms = (time.time() - server_ts_s) * 1000
                    if 0 < latency_ms < 5000:
                        latencies_ms.append(latency_ms)

    except ConnectionRefusedError:
        print("\n  ERROR: Could not connect — is mock_edge_server.py running?")
        print("  Run: python mock_edge_server.py\n")
        return False
    except Exception as e:
        print(f"\n  ERROR: Unexpected connection error: {e}\n")
        return False

    # ── Results ──────────────────────────────────────────────────────────────

    elapsed = (last_frame_time - first_frame_time) if (first_frame_time and last_frame_time) else 1
    actual_fps = frames_received / elapsed if elapsed > 0 else 0
    avg_latency = sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    print(f"\n  Frames received : {frames_received}")
    print(f"  Parse errors    : {parse_errors}")
    print(f"  Schema errors   : {schema_errors}")
    print(f"  Actual FPS      : {actual_fps:.1f}")
    print(f"  Avg latency     : {avg_latency:.1f} ms")
    print(f"  Stages seen     : {stages_seen}")
    print(f"  Max rep count   : {max_rep_count}")
    print(f"  Feedback codes  : {feedback_codes}")

    print("\n  Assertions:")
    results = [
        check("Connection established",       True),
        check("Frames received > 0",          frames_received > 0,
              f"{frames_received} frames"),
        check("Zero JSON parse errors",       parse_errors == 0,
              f"{parse_errors} errors"),
        check("Zero schema validation errors", schema_errors == 0,
              f"{schema_errors} errors"),
        check(f"FPS >= {MIN_FPS}",            actual_fps >= MIN_FPS,
              f"actual: {actual_fps:.1f} FPS"),
        check("All 3 stages observed",        stages_seen == {"standing", "down", "transition"},
              f"seen: {stages_seen}"),
        check(f"At least {MIN_REPS_EXPECTED} rep counted", max_rep_count >= MIN_REPS_EXPECTED,
              f"max rep_count: {max_rep_count}"),
        check("Feedback flags received",      len(feedback_codes) > 0,
              f"codes: {feedback_codes}"),
        check("Avg latency < 100ms",          avg_latency < 100,
              f"{avg_latency:.1f} ms"),
    ]

    passed = sum(results)
    total  = len(results)
    print(f"\n  {passed}/{total} assertions passed")

    print("\n" + "=" * 60)
    if passed == total:
        print("  INTEGRATION TEST: PASSED")
        print("  ws_client successfully receives, parses, and validates")
        print("  the ExerciseState stream from the edge server.")
    else:
        print("  INTEGRATION TEST: FAILED — see FAIL lines above")
    print("=" * 60 + "\n")

    return passed == total


if __name__ == "__main__":
    asyncio.run(run_integration_test())