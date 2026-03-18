"""
benchmark.py — MediaPipe Pose performance profiler for Jetson Nano
Usage:
    python edge/benchmark.py --width 640  --height 480  --frames 300
    python edge/benchmark.py --width 1280 --height 720  --frames 300
    python edge/benchmark.py --source path/to/video.mp4 --width 640 --height 480

Outputs:
  - A summary table printed to stdout
  - A JSON log saved to logs/benchmark_<WxH>_<timestamp>.json
  - A CSV log  saved to logs/benchmark_<WxH>_<timestamp>.csv
"""

import argparse
import csv
import json
import os
import time
from datetime import datetime
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
import psutil

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WARMUP_FRAMES = 30       # frames to discard before measurement begins
DEFAULT_FRAMES = 300     # frames to measure
LOG_DIR = Path(__file__).parent.parent / "logs"

mp_pose = mp.solutions.pose


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def percentile(data: list, p: float) -> float:
    return float(np.percentile(data, p))


def print_table(title: str, rows: list[tuple[str, str]]) -> None:
    col_w = max(len(r[0]) for r in rows) + 2
    print(f"\n{'─' * (col_w + 22)}")
    print(f"  {title}")
    print(f"{'─' * (col_w + 22)}")
    for label, value in rows:
        print(f"  {label:<{col_w}} {value}")
    print(f"{'─' * (col_w + 22)}")


# ---------------------------------------------------------------------------
# Core benchmark loop
# ---------------------------------------------------------------------------
def run_benchmark(
    source: str | int,
    width: int,
    height: int,
    num_frames: int,
    warmup: int,
) -> dict:

    process = psutil.Process(os.getpid())
    baseline_ram_mb = process.memory_info().rss / 1024 / 1024

    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"\n[INFO] Camera opened: {actual_w}×{actual_h}  "
          f"(requested {width}×{height})")

    frame_latencies_ms: list[float] = []
    cpu_samples: list[float]        = []
    ram_samples_mb: list[float]     = []
    frame_records: list[dict]       = []
    frames_detected = 0

    with mp_pose.Pose(
        model_complexity=0,
        smooth_landmarks=False,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:

        total_frames = warmup + num_frames
        collected = 0
        print(f"[INFO] Warming up ({warmup} frames) …", end="", flush=True)

        for frame_idx in range(total_frames):
            ret, frame = cap.read()
            if not ret:
                # Loop video sources
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
            if not ret:
                print("[WARN] Could not read frame — stopping early.")
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False

            t0 = time.perf_counter()
            results = pose.process(rgb)
            t1 = time.perf_counter()

            is_warmup = frame_idx < warmup
            if is_warmup:
                if frame_idx == warmup - 1:
                    print(" done.")
                    print(f"[INFO] Measuring {num_frames} frames …")
                continue

            latency_ms = (t1 - t0) * 1000
            cpu_pct    = psutil.cpu_percent(interval=None)
            ram_mb     = process.memory_info().rss / 1024 / 1024

            frame_latencies_ms.append(latency_ms)
            cpu_samples.append(cpu_pct)
            ram_samples_mb.append(ram_mb)

            detected = results.pose_landmarks is not None
            if detected:
                frames_detected += 1

            collected += 1
            frame_records.append({
                "frame":      collected,
                "latency_ms": round(latency_ms, 3),
                "cpu_pct":    round(cpu_pct, 1),
                "ram_mb":     round(ram_mb, 1),
                "detected":   detected,
            })

            if collected % 50 == 0:
                fps_so_far = 1000 / (sum(frame_latencies_ms) / len(frame_latencies_ms))
                print(f"  … {collected}/{num_frames} frames  "
                      f"(rolling mean FPS: {fps_so_far:.1f})")

    cap.release()

    # --- Aggregate stats ---------------------------------------------------
    mean_latency = float(np.mean(frame_latencies_ms))
    fps_values   = [1000 / l for l in frame_latencies_ms if l > 0]

    stats = {
        "resolution":        f"{actual_w}x{actual_h}",
        "frames_measured":   collected,
        "frames_detected":   frames_detected,
        "detection_rate_pct": round(frames_detected / max(collected, 1) * 100, 1),
        "fps": {
            "mean": round(float(np.mean(fps_values)),    2),
            "min":  round(float(np.min(fps_values)),     2),
            "max":  round(float(np.max(fps_values)),     2),
            "std":  round(float(np.std(fps_values)),     2),
        },
        "latency_ms": {
            "mean": round(mean_latency,                      2),
            "p50":  round(percentile(frame_latencies_ms, 50), 2),
            "p95":  round(percentile(frame_latencies_ms, 95), 2),
            "p99":  round(percentile(frame_latencies_ms, 99), 2),
        },
        "cpu_pct": {
            "mean": round(float(np.mean(cpu_samples)), 1),
            "peak": round(float(np.max(cpu_samples)),  1),
        },
        "ram_mb": {
            "baseline":     round(baseline_ram_mb, 1),
            "mean":         round(float(np.mean(ram_samples_mb)), 1),
            "peak":         round(float(np.max(ram_samples_mb)),  1),
        },
        "frame_records": frame_records,
    }
    return stats


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def save_results(stats: dict, width: int, height: int) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = LOG_DIR / f"benchmark_{width}x{height}_{ts}"

    # JSON — full record
    json_path = stem.with_suffix(".json")
    with open(json_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\n[INFO] JSON log → {json_path}")

    # CSV — per-frame rows
    csv_path = stem.with_suffix(".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["frame", "latency_ms", "cpu_pct", "ram_mb", "detected"]
        )
        writer.writeheader()
        writer.writerows(stats["frame_records"])
    print(f"[INFO] CSV log  → {csv_path}")


def print_summary(stats: dict) -> None:
    res = stats["resolution"]
    meets_target = "YES ✓" if stats["fps"]["mean"] >= 10 else "NO  ✗"

    print_table(
        f"FPS  ({res})",
        [
            ("Mean FPS",    f"{stats['fps']['mean']}"),
            ("Min FPS",     f"{stats['fps']['min']}"),
            ("Max FPS",     f"{stats['fps']['max']}"),
            ("Std Dev",     f"{stats['fps']['std']}"),
            ("10-15 FPS?",  meets_target),
        ],
    )
    print_table(
        f"Inference Latency  ({res})",
        [
            ("Mean (ms)", f"{stats['latency_ms']['mean']}"),
            ("P50  (ms)", f"{stats['latency_ms']['p50']}"),
            ("P95  (ms)", f"{stats['latency_ms']['p95']}"),
            ("P99  (ms)", f"{stats['latency_ms']['p99']}"),
        ],
    )
    print_table(
        f"CPU Usage  ({res})",
        [
            ("Mean (%)", f"{stats['cpu_pct']['mean']}"),
            ("Peak (%)", f"{stats['cpu_pct']['peak']}"),
        ],
    )
    print_table(
        f"Memory / RAM  ({res})",
        [
            ("Baseline (MB)",         f"{stats['ram_mb']['baseline']}"),
            ("Mean during run (MB)",  f"{stats['ram_mb']['mean']}"),
            ("Peak (MB)",             f"{stats['ram_mb']['peak']}"),
        ],
    )
    print_table(
        f"Detection  ({res})",
        [
            ("Frames measured",  str(stats["frames_measured"])),
            ("Frames detected",  str(stats["frames_detected"])),
            ("Detection rate",   f"{stats['detection_rate_pct']} %"),
        ],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark MediaPipe Pose on Jetson Nano"
    )
    parser.add_argument(
        "--source", default="0",
        help="Camera index (default: 0) or path to a video file",
    )
    parser.add_argument("--width",  type=int, default=640,  help="Capture width  (default: 640)")
    parser.add_argument("--height", type=int, default=480,  help="Capture height (default: 480)")
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES,
                        help=f"Frames to measure (default: {DEFAULT_FRAMES})")
    parser.add_argument("--warmup", type=int, default=WARMUP_FRAMES,
                        help=f"Warm-up frames to discard (default: {WARMUP_FRAMES})")
    args = parser.parse_args()

    # Resolve source: integer camera index or string file path
    source: str | int = args.source
    if args.source.isdigit():
        source = int(args.source)

    print("=" * 60)
    print(" MediaPipe Pose Benchmark — Jetson Nano")
    print(f" Resolution : {args.width}×{args.height}")
    print(f" Frames     : {args.frames}  (warm-up: {args.warmup})")
    print(f" Source     : {source}")
    print("=" * 60)

    stats = run_benchmark(
        source=source,
        width=args.width,
        height=args.height,
        num_frames=args.frames,
        warmup=args.warmup,
    )

    print_summary(stats)
    save_results(stats, args.width, args.height)


if __name__ == "__main__":
    main()
