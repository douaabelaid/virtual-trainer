"""
benchmark.py — MediaPipe Pose performance profiler
Tests the edge server that processes frames streamed from a mobile app.
No camera required — uses synthetic frames to simulate mobile input.

Usage:
    python edge/benchmark.py
    python edge/benchmark.py --frames 500
    python edge/benchmark.py --width 1280 --height 720
"""

import argparse
import csv
import json
import os
import subprocess
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
WARMUP_FRAMES  = 30
DEFAULT_FRAMES = 300
LOG_DIR        = Path(__file__).parent.parent / "logs"

mp_pose = mp.solutions.pose


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def print_table(title: str, rows: list) -> None:
    col_w = max(len(r[0]) for r in rows) + 2
    print(f"\n{'─' * (col_w + 22)}")
    print(f"  {title}")
    print(f"{'─' * (col_w + 22)}")
    for label, value in rows:
        print(f"  {label:<{col_w}} {value}")
    print(f"{'─' * (col_w + 22)}")


def print_summary(stats: dict) -> None:
    res    = stats["resolution"]
    target = "YES ✓" if stats["fps"]["mean"] >= 15 else "NO  ✗"

    print_table(f"FPS  ({res})", [
        ("Mean FPS",          f"{stats['fps']['mean']}"),
        ("Min  FPS",          f"{stats['fps']['min']}"),
        ("Max  FPS",          f"{stats['fps']['max']}"),
        ("Std  Dev",          f"{stats['fps']['std']}"),
        ("P95  FPS",          f"{stats['fps']['p95']}"),
        ("≥ 15 FPS target?",  target),
    ])
    print_table(f"Inference Latency  ({res})", [
        ("Mean (ms)", f"{stats['latency_ms']['mean']}"),
        ("Min  (ms)", f"{stats['latency_ms']['min']}"),
        ("Max  (ms)", f"{stats['latency_ms']['max']}"),
        ("P50  (ms)", f"{stats['latency_ms']['p50']}"),
        ("P95  (ms)", f"{stats['latency_ms']['p95']}"),
        ("P99  (ms)", f"{stats['latency_ms']['p99']}"),
    ])
    print_table(f"CPU Usage  ({res})", [
        ("Mean (%)", f"{stats['cpu_pct']['mean']}"),
        ("Peak (%)", f"{stats['cpu_pct']['peak']}"),
    ])
    print_table(f"Memory / RAM  ({res})", [
        ("Baseline (MB)",        f"{stats['ram_mb']['baseline']}"),
        ("Mean during run (MB)", f"{stats['ram_mb']['mean']}"),
        ("Peak (MB)",            f"{stats['ram_mb']['peak']}"),
    ])
    print_table(f"Detection  ({res})", [
        ("Frames measured", str(stats["frames_measured"])),
        ("Frames detected", str(stats["frames_detected"])),
        ("Detection rate",  f"{stats['detection_rate_pct']} %"),
    ])


# ---------------------------------------------------------------------------
# Core benchmark loop
# ---------------------------------------------------------------------------
def run_benchmark(
    source=0,
    width=640,
    height=480,
    n_frames=300,
    warmup=30,
    model_complexity=1,
) -> dict:

    process         = psutil.Process(os.getpid())
    baseline_ram_mb = process.memory_info().rss / 1024 / 1024

    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # No camera: generate synthetic JPEG frames (simulates mobile input)
    use_synthetic = not cap.isOpened() or cap.get(cv2.CAP_PROP_FRAME_WIDTH) == 0
    if use_synthetic:
        print("[WARN] No camera found — using synthetic frames (simulates mobile stream).")
        cap.release()
        cap = None

    def read_frame():
        if use_synthetic:
            return True, np.zeros((height, width, 3), dtype=np.uint8)
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        return ok, frame

    frame_latencies_ms: list = []
    cpu_samples:        list = []
    ram_samples_mb:     list = []
    frame_records:      list = []
    frames_detected          = 0

    with mp_pose.Pose(
        model_complexity=model_complexity,
        smooth_landmarks=False,
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:

        total     = warmup + n_frames
        collected = 0
        print(f"[INFO] Warming up ({warmup} frames) …", end="", flush=True)

        for frame_idx in range(total):
            ok, frame = read_frame()
            if not ok:
                print("[WARN] Could not read frame — stopping early.")
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False

            t0      = time.perf_counter()
            results = pose.process(rgb)
            t1      = time.perf_counter()

            if frame_idx < warmup:
                if frame_idx == warmup - 1:
                    print(" done.")
                    print(f"[INFO] Measuring {n_frames} frames …")
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
                rolling_fps = 1000 / (sum(frame_latencies_ms) / len(frame_latencies_ms))
                print(f"  … {collected}/{n_frames} frames  "
                      f"(rolling mean FPS: {rolling_fps:.1f})")

    if cap is not None:
        cap.release()

    if len(frame_latencies_ms) == 0:
        print("[ERROR] No frames were processed. Cannot compute stats.")
        return None

    lat = np.array(frame_latencies_ms)
    cpu = np.array(cpu_samples)
    ram = np.array(ram_samples_mb)
    fps = 1000.0 / lat

    return {
        "resolution":         f"{width}×{height}",
        "frames_measured":    collected,
        "frames_detected":    frames_detected,
        "detection_rate_pct": round(frames_detected / collected * 100, 1) if collected else 0,
        "fps": {
            "mean": round(float(fps.mean()), 2),
            "min":  round(float(fps.min()),  2),
            "max":  round(float(fps.max()),  2),
            "std":  round(float(fps.std()),  2),
            "p95":  round(float(np.percentile(fps, 95)), 2),
        },
        "latency_ms": {
            "mean": round(float(lat.mean()), 2),
            "min":  round(float(lat.min()),  2),
            "max":  round(float(lat.max()),  2),
            "p50":  round(float(np.percentile(lat, 50)), 2),
            "p95":  round(float(np.percentile(lat, 95)), 2),
            "p99":  round(float(np.percentile(lat, 99)), 2),
        },
        "cpu_pct": {
            "mean": round(float(cpu.mean()), 1),
            "peak": round(float(cpu.max()),  1),
        },
        "ram_mb": {
            "baseline": round(baseline_ram_mb, 1),
            "mean":     round(float(ram.mean()), 1),
            "peak":     round(float(ram.max()),  1),
        },
        "frame_records": frame_records,
    }


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def save_results(stats: dict, width: int, height: int) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = LOG_DIR / f"benchmark_{width}x{height}_{ts}"

    # JSON
    json_path = stem.with_suffix(".json")
    with open(json_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"[INFO] JSON  → {json_path}")

    # CSV
    csv_path = stem.with_suffix(".csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["frame", "latency_ms", "cpu_pct", "ram_mb", "detected"])
        writer.writeheader()
        writer.writerows(stats["frame_records"])
    print(f"[INFO] CSV   → {csv_path}")

    # HTML
    html_path = stem.with_suffix(".html")
    _save_html_report(stats, html_path, width, height, ts)
    print(f"[INFO] HTML  → {html_path}")

    return html_path


def _save_html_report(stats: dict, path: Path, width: int, height: int, ts: str) -> None:
    frames  = [r["frame"]      for r in stats["frame_records"]]
    lats    = [r["latency_ms"] for r in stats["frame_records"]]
    cpus    = [r["cpu_pct"]    for r in stats["frame_records"]]
    rams    = [r["ram_mb"]     for r in stats["frame_records"]]
    fps_per = [round(1000 / l, 1) if l > 0 else 0 for l in lats]
    meets   = "✅ YES" if stats["fps"]["mean"] >= 15 else "❌ NO"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <title>Benchmark — Virtual Trainer Edge Server</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
  <style>
    body       {{ font-family:Arial,sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }}
    h1         {{ color:#38bdf8; }}
    h2         {{ color:#7dd3fc; margin-top:32px; }}
    .subtitle  {{ color:#94a3b8; margin-bottom:24px; }}
    .grid      {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px; margin:24px 0; }}
    .card      {{ background:#1e293b; border-radius:12px; padding:20px; text-align:center; }}
    .card .v   {{ font-size:2rem; font-weight:bold; color:#38bdf8; }}
    .card .l   {{ font-size:0.85rem; color:#94a3b8; margin-top:4px; }}
    .chart-box {{ background:#1e293b; border-radius:12px; padding:20px; margin:16px 0; }}
    canvas     {{ max-height:260px; }}
    table      {{ width:100%; border-collapse:collapse; background:#1e293b; border-radius:8px; overflow:hidden; }}
    th         {{ background:#0ea5e9; color:#fff; padding:10px 14px; text-align:left; }}
    td         {{ padding:8px 14px; border-bottom:1px solid #334155; }}
    tr:last-child td {{ border:none; }}
    .badge     {{ display:inline-block; padding:4px 12px; border-radius:999px;
                  background:#0ea5e9; color:#fff; font-size:0.8rem; margin-left:8px; }}
  </style>
</head>
<body>
  <h1>📊 Virtual Trainer — Edge Server Benchmark</h1>
  <p class="subtitle">
    Simulates <b>mobile app frame stream</b> → MediaPipe Pose inference
    &nbsp;|&nbsp; Resolution: <b>{width}×{height}</b>
    &nbsp;|&nbsp; Date: <b>{ts}</b>
    &nbsp;|&nbsp; Meets 15 FPS target: <b>{meets}</b>
  </p>

  <div class="grid">
    <div class="card"><div class="v">{stats['fps']['mean']}</div><div class="l">Mean FPS</div></div>
    <div class="card"><div class="v">{stats['fps']['min']}</div><div class="l">Min FPS</div></div>
    <div class="card"><div class="v">{stats['fps']['max']}</div><div class="l">Max FPS</div></div>
    <div class="card"><div class="v">{stats['latency_ms']['mean']} ms</div><div class="l">Mean Latency</div></div>
    <div class="card"><div class="v">{stats['latency_ms']['p95']} ms</div><div class="l">P95 Latency</div></div>
    <div class="card"><div class="v">{stats['cpu_pct']['mean']} %</div><div class="l">Mean CPU</div></div>
    <div class="card"><div class="v">{stats['ram_mb']['peak']} MB</div><div class="l">Peak RAM</div></div>
    <div class="card"><div class="v">{stats['detection_rate_pct']} %</div><div class="l">Detection Rate</div></div>
  </div>

  <h2>⚡ FPS per Frame</h2>
  <div class="chart-box"><canvas id="fpsChart"></canvas></div>

  <h2>⏱️ Inference Latency (ms)</h2>
  <div class="chart-box"><canvas id="latChart"></canvas></div>

  <h2>🖥️ CPU & RAM Usage</h2>
  <div class="chart-box"><canvas id="sysChart"></canvas></div>

  <h2>📋 Full Stats</h2>
  <table>
    <tr><th>Metric</th><th>Value</th></tr>
    <tr><td>Frames measured</td><td>{stats['frames_measured']}</td></tr>
    <tr><td>Frames detected</td><td>{stats['frames_detected']}</td></tr>
    <tr><td>Detection rate</td><td>{stats['detection_rate_pct']} %</td></tr>
    <tr><td>Mean FPS</td><td>{stats['fps']['mean']}</td></tr>
    <tr><td>Min / Max FPS</td><td>{stats['fps']['min']} / {stats['fps']['max']}</td></tr>
    <tr><td>Std Dev FPS</td><td>{stats['fps']['std']}</td></tr>
    <tr><td>Mean latency</td><td>{stats['latency_ms']['mean']} ms</td></tr>
    <tr><td>P50 latency</td><td>{stats['latency_ms']['p50']} ms</td></tr>
    <tr><td>P95 latency</td><td>{stats['latency_ms']['p95']} ms</td></tr>
    <tr><td>P99 latency</td><td>{stats['latency_ms']['p99']} ms</td></tr>
    <tr><td>Mean CPU</td><td>{stats['cpu_pct']['mean']} %</td></tr>
    <tr><td>Peak CPU</td><td>{stats['cpu_pct']['peak']} %</td></tr>
    <tr><td>Baseline RAM</td><td>{stats['ram_mb']['baseline']} MB</td></tr>
    <tr><td>Mean RAM</td><td>{stats['ram_mb']['mean']} MB</td></tr>
    <tr><td>Peak RAM</td><td>{stats['ram_mb']['peak']} MB</td></tr>
  </table>

  <script>
    const frames = {frames};
    const fps    = {fps_per};
    const lats   = {lats};
    const cpus   = {cpus};
    const rams   = {rams};

    const opts = {{ responsive:true, animation:false,
      scales: {{
        x: {{ ticks:{{color:'#94a3b8'}}, grid:{{color:'#334155'}} }},
        y: {{ ticks:{{color:'#94a3b8'}}, grid:{{color:'#334155'}} }}
      }},
      plugins: {{ legend:{{ labels:{{color:'#e2e8f0'}} }} }}
    }};

    const line = (label, data, color) => ({{
      labels: frames,
      datasets: [{{ label, data, borderColor:color, backgroundColor:color+'22',
        fill:true, pointRadius:0, borderWidth:1.5, tension:0.3 }}]
    }});

    new Chart(document.getElementById('fpsChart'),
      {{ type:'line', data: line('FPS', fps, '#38bdf8'), options: opts }});
    new Chart(document.getElementById('latChart'),
      {{ type:'line', data: line('Latency ms', lats, '#f59e0b'), options: opts }});
    new Chart(document.getElementById('sysChart'), {{
      type:'line',
      data: {{
        labels: frames,
        datasets: [
          {{ label:'CPU %',  data:cpus, borderColor:'#f87171', backgroundColor:'#f8717122',
             fill:true, pointRadius:0, borderWidth:1.5, tension:0.3 }},
          {{ label:'RAM MB', data:rams, borderColor:'#a78bfa', backgroundColor:'#a78bfa22',
             fill:true, pointRadius:0, borderWidth:1.5, tension:0.3 }}
        ]
      }},
      options: opts
    }});
  </script>
</body>
</html>"""

    with open(path, "w") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark MediaPipe Pose — Virtual Trainer Edge Server"
    )
    parser.add_argument("--source", default="0",
        help="Camera index or video file path (default: synthetic frames)")
    parser.add_argument("--width",  type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--frames", type=int, default=DEFAULT_FRAMES)
    parser.add_argument("--warmup", type=int, default=WARMUP_FRAMES)
    args = parser.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source

    print("=" * 60)
    print(" Virtual Trainer — Edge Server Benchmark")
    print(" (Simulates mobile app frame stream)")
    print(f" Resolution : {args.width}×{args.height}")
    print(f" Frames     : {args.frames}  (warm-up: {args.warmup})")
    print(f" Source     : {'synthetic frames' if source == 0 else source}")
    print("=" * 60)

    stats = run_benchmark(
        source=source,
        width=args.width,
        height=args.height,
        n_frames=args.frames,
        warmup=args.warmup,
    )

    if stats is None:
        print("[ERROR] Benchmark failed — no frames processed.")
        return

    print_summary(stats)
    html_path = save_results(stats, args.width, args.height)

    # Open HTML report in host browser
    subprocess.run(
        ["bash", "-c", f'"$BROWSER" {html_path} 2>/dev/null || true'],
        check=False
    )
    print(f"\n[INFO] Open report manually if browser did not launch:")
    print(f"  $BROWSER {html_path}")


if __name__ == "__main__":
    main()
