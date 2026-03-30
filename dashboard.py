"""
dashboard.py
------------
Rich terminal dashboard for live VPT sessions.
Shows rep count, stage, latency, feedback, and a mini angle graph — all in the terminal.

Usage:
    python dashboard.py --exercise squat

Requires: pip install rich
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import websockets
import json
import time
import argparse
from collections import deque

try:
    from rich.live import Live
    from rich.table import Table
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    from rich.console import Console
    from rich import box
except ImportError:
    print("Dashboard requires 'rich'. Install it with:  pip install rich")
    sys.exit(1)

from logic.exercise_detector import ExerciseDetector
from logic.angle_utils import get_joint_angles
from logic.feedback_mapper import map_flags_to_coaching

# ─── Config ───────────────────────────────────────────────────────────────────

URI                  = "wss://unpendulously-cingulate-cortney.ngrok-free.dev/ws"
LATENCY_THRESHOLD_MS = 100
HISTORY_LEN          = 20   # frames to keep for sparkline

console = Console()

# ─── State ────────────────────────────────────────────────────────────────────

class DashboardState:
    def __init__(self, exercise: str):
        self.exercise       = exercise
        self.stage          = "—"
        self.rep_count      = 0
        self.latency_ms     = 0
        self.latency_hist   = deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.angle_hist     = deque([0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self.feedback       = []
        self.skipped        = 0
        self.processed      = 0
        self.errors         = 0
        self.connected      = False
        self.last_frame_id  = "—"
        self.session_start  = time.time()
        self.angles         = {}

    def elapsed(self) -> str:
        s = int(time.time() - self.session_start)
        return f"{s//60:02d}:{s%60:02d}"

    def skip_pct(self) -> float:
        total = self.processed + self.skipped
        return (self.skipped / total * 100) if total > 0 else 0.0

    def avg_latency(self) -> float:
        vals = [v for v in self.latency_hist if v > 0]
        return sum(vals) / len(vals) if vals else 0.0


# ─── Sparkline ────────────────────────────────────────────────────────────────

SPARKS = " ▁▂▃▄▅▆▇█"

def sparkline(values: deque, lo: float = 0, hi: float = 200) -> str:
    result = ""
    for v in values:
        idx = int((v - lo) / max(hi - lo, 1) * (len(SPARKS) - 1))
        idx = max(0, min(idx, len(SPARKS) - 1))
        result += SPARKS[idx]
    return result


# ─── Render ───────────────────────────────────────────────────────────────────

STAGE_COLORS = {
    "standing":  "green",
    "down":      "cyan",
    "transition": "yellow",
    "—":         "dim",
}

def render(state: DashboardState) -> Panel:
    stage_color = STAGE_COLORS.get(state.stage, "white")

    # ── Top row: reps + stage + latency ───────────────────────────────────────
    status_table = Table.grid(padding=(0, 3))
    status_table.add_column(justify="center", min_width=12)
    status_table.add_column(justify="center", min_width=16)
    status_table.add_column(justify="center", min_width=16)
    status_table.add_column(justify="center", min_width=14)

    conn_text = Text("● LIVE", style="bold green") if state.connected else Text("○ CONNECTING", style="bold yellow")

    status_table.add_row(
        Text(str(state.rep_count), style="bold white", justify="center"),
        Text(state.stage.upper(), style=f"bold {stage_color}", justify="center"),
        Text(f"{state.latency_ms} ms", style="bold green" if state.latency_ms < 60 else
             ("yellow" if state.latency_ms < 100 else "bold red"), justify="center"),
        conn_text,
    )
    status_table.add_row(
        Text("reps", style="dim"),
        Text("stage", style="dim"),
        Text("latency", style="dim"),
        Text("status", style="dim"),
    )

    # ── Sparklines ────────────────────────────────────────────────────────────
    spark_table = Table.grid(padding=(0, 2))
    spark_table.add_column(min_width=14)
    spark_table.add_column()

    lat_spark   = sparkline(state.latency_hist, 0, 150)
    angle_spark = sparkline(state.angle_hist, 60, 180)
    lat_color   = "green" if state.avg_latency() < 60 else ("yellow" if state.avg_latency() < 100 else "red")

    spark_table.add_row(Text("latency",  style="dim"), Text(lat_spark,   style=lat_color))
    spark_table.add_row(Text("knee ang", style="dim"), Text(angle_spark, style="cyan"))

    # ── Angles ────────────────────────────────────────────────────────────────
    angle_table = Table(box=box.SIMPLE, show_header=True, header_style="dim", padding=(0,1))
    angle_table.add_column("Joint",    style="dim",   min_width=14)
    angle_table.add_column("Angle",    justify="right", min_width=8)
    for joint in ["left_knee", "right_knee", "left_hip", "right_hip", "back"]:
        v = state.angles.get(joint)
        if v is not None:
            color = "cyan" if v < 100 else ("green" if v > 155 else "yellow")
            angle_table.add_row(joint.replace("_", " "), Text(f"{v:.1f}°", style=color))

    # ── Feedback ──────────────────────────────────────────────────────────────
    feedback_table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
    feedback_table.add_column(min_width=10)
    feedback_table.add_column()

    sev_colors = {"error": "bold red", "warning": "yellow", "info": "dim green"}
    if state.feedback:
        for item in state.feedback[-4:]:  # show last 4
            sev   = item.get("severity", "info")
            color = sev_colors.get(sev, "white")
            feedback_table.add_row(
                Text(f"[{sev.upper()}]", style=color),
                Text(item.get("message", ""), style="white"),
            )
    else:
        feedback_table.add_row("", Text("No feedback — looking good!", style="dim green"))

    # ── Stats footer ──────────────────────────────────────────────────────────
    stats = (
        f"  elapsed [bold]{state.elapsed()}[/]  │  "
        f"frame [bold]{state.last_frame_id}[/]  │  "
        f"processed [bold]{state.processed}[/]  │  "
        f"skipped [bold]{state.skipped}[/] ([yellow]{state.skip_pct():.1f}%[/])  │  "
        f"errors [bold]{state.errors}[/]"
    )

    # ── Compose ───────────────────────────────────────────────────────────────
    layout = Table.grid(padding=(0, 2))
    layout.add_column(ratio=1)
    layout.add_column(ratio=1)

    layout.add_row(
        Panel(status_table,  title="[bold]Status[/]",   border_style="bright_black"),
        Panel(spark_table,   title="[bold]Trends[/]",   border_style="bright_black"),
    )
    layout.add_row(
        Panel(angle_table,   title="[bold]Angles[/]",   border_style="bright_black"),
        Panel(feedback_table,title="[bold]Feedback[/]", border_style="bright_black"),
    )

    return Panel(
        layout,
        title=f"[bold white]VPT Live Dashboard[/] — [cyan]{state.exercise.upper()}[/]",
        subtitle=stats,
        border_style="blue",
        padding=(0, 1),
    )


# ─── Receive loop ─────────────────────────────────────────────────────────────

async def receive_loop(websocket, detector: ExerciseDetector,
                       state: DashboardState, live: Live):
    state.connected = True
    async for message in websocket:
        now_ms = int(time.time() * 1000)

        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            state.errors += 1
            live.update(render(state))
            continue

        frame_id   = data.get("frame_id", "?")
        frame_ts   = data.get("timestamp_ms", now_ms)
        latency_ms = now_ms - frame_ts

        state.last_frame_id = frame_id
        state.latency_ms    = latency_ms
        state.latency_hist.append(latency_ms)

        if latency_ms > LATENCY_THRESHOLD_MS:
            state.skipped += 1
            live.update(render(state))
            continue

        landmarks = data.get("landmarks") or data.get("landmarks_raw") or data
        if not landmarks or not isinstance(landmarks, dict):
            state.errors += 1
            live.update(render(state))
            continue

        try:
            angles   = get_joint_angles(landmarks)
            state_ex = detector.update(landmarks)
            coaching = map_flags_to_coaching(state_ex.feedback_flags)

            state.stage      = state_ex.stage.value
            state.rep_count  = state_ex.rep_count
            state.angles     = angles
            state.feedback   = coaching
            state.processed += 1

            # Track avg knee angle for sparkline
            lk = angles.get("left_knee", 0)
            rk = angles.get("right_knee", 0)
            if lk and rk:
                state.angle_hist.append((lk + rk) / 2)

        except Exception:
            state.errors += 1

        live.update(render(state))


# ─── Connect ──────────────────────────────────────────────────────────────────

async def connect(uri: str, exercise: str):
    detector = ExerciseDetector(exercise=exercise)
    state    = DashboardState(exercise)

    with Live(render(state), console=console, refresh_per_second=15, screen=True) as live:
        attempt = 0
        while attempt < 5:
            try:
                async with websockets.connect(uri, ping_interval=20, ping_timeout=10) as ws:
                    attempt = 0
                    state.connected = True
                    live.update(render(state))
                    await receive_loop(ws, detector, state, live)

            except websockets.exceptions.ConnectionClosedOK:
                break
            except (websockets.exceptions.ConnectionClosedError, OSError):
                attempt += 1
                state.connected = False
                live.update(render(state))
                await asyncio.sleep(2 ** attempt)
            except KeyboardInterrupt:
                break

    console.print("\n[bold green]Session ended.[/]")
    console.print(f"  Total reps     : [bold]{state.rep_count}[/]")
    console.print(f"  Frames processed: [bold]{state.processed}[/]")
    console.print(f"  Frames skipped  : [bold]{state.skipped}[/] ({state.skip_pct():.1f}%)")
    console.print(f"  Avg latency     : [bold]{state.avg_latency():.1f}ms[/]")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VPT live terminal dashboard")
    parser.add_argument("--exercise", default="squat", choices=["squat", "pushup", "lunge"])
    parser.add_argument("--uri",      default=URI)
    args = parser.parse_args()

    asyncio.run(connect(args.uri, args.exercise))