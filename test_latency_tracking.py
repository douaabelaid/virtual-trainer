"""
Test script to demonstrate latency tracking system.

This script simulates frame processing with various latencies to show:
- Rolling average calculation
- P95 computation using numpy
- Warning logs for high latency
- Structured logging output
"""

import sys
import time
from collections import deque
from pathlib import Path

import numpy as np

# Add project root to path
_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))


def test_latency_tracking():
    """Simulate latency tracking with various scenarios."""
    
    print("=" * 70)
    print("Latency Tracking System Test")
    print("=" * 70)
    print()
    
    # Simulate latency samples
    inference_samples = deque(maxlen=100)
    e2e_samples = deque(maxlen=100)
    
    # Scenario 1: Normal operation (30-60ms)
    print("📊 Scenario 1: Normal operation (30-60ms latency)")
    for i in range(50):
        inf_latency = np.random.uniform(15, 30)
        e2e_latency = np.random.uniform(30, 60)
        inference_samples.append(inf_latency)
        e2e_samples.append(e2e_latency)
    
    stats = compute_stats(e2e_samples)
    print(f"   Avg: {stats['avg']:.2f}ms | P95: {stats['p95']:.2f}ms | P99: {stats['p99']:.2f}ms | Max: {stats['max']:.2f}ms")
    if stats['p95'] > 80:
        print("   ⚠️  WARNING: P95 > 80ms")
    else:
        print("   ✅ P95 within threshold")
    print()
    
    # Scenario 2: Moderate load (60-90ms)
    print("📊 Scenario 2: Moderate load (60-90ms latency)")
    for i in range(50):
        inf_latency = np.random.uniform(30, 45)
        e2e_latency = np.random.uniform(60, 90)
        inference_samples.append(inf_latency)
        e2e_samples.append(e2e_latency)
    
    stats = compute_stats(e2e_samples)
    print(f"   Avg: {stats['avg']:.2f}ms | P95: {stats['p95']:.2f}ms | P99: {stats['p99']:.2f}ms | Max: {stats['max']:.2f}ms")
    if stats['p95'] > 80:
        print("   ⚠️  WARNING: P95 > 80ms")
    else:
        print("   ✅ P95 within threshold")
    print()
    
    # Scenario 3: High load with spikes (70-130ms with outliers)
    print("📊 Scenario 3: High load with spikes (70-130ms, some >120ms)")
    high_latency_count = 0
    for i in range(50):
        inf_latency = np.random.uniform(35, 60)
        # 10% chance of spike
        if np.random.random() < 0.1:
            e2e_latency = np.random.uniform(120, 150)
            high_latency_count += 1
            print(f"   🚨 SPIKE: Frame {i} = {e2e_latency:.1f}ms > 120ms threshold")
        else:
            e2e_latency = np.random.uniform(70, 110)
        
        inference_samples.append(inf_latency)
        e2e_samples.append(e2e_latency)
    
    stats = compute_stats(e2e_samples)
    print(f"   Avg: {stats['avg']:.2f}ms | P95: {stats['p95']:.2f}ms | P99: {stats['p99']:.2f}ms | Max: {stats['max']:.2f}ms")
    print(f"   High latency frames (>120ms): {high_latency_count}")
    if stats['p95'] > 80:
        print("   ⚠️  WARNING: P95 > 80ms")
    else:
        print("   ✅ P95 within threshold")
    print()
    
    # Show final statistics
    print("=" * 70)
    print("Final Statistics (last 100 frames)")
    print("=" * 70)
    
    inf_stats = compute_stats(inference_samples)
    e2e_stats = compute_stats(e2e_samples)
    
    print("\nInference Latency (MediaPipe only):")
    print(f"   Avg:  {inf_stats['avg']:.2f}ms")
    print(f"   Min:  {inf_stats['min']:.2f}ms")
    print(f"   Max:  {inf_stats['max']:.2f}ms")
    print(f"   P95:  {inf_stats['p95']:.2f}ms")
    print(f"   P99:  {inf_stats['p99']:.2f}ms")
    
    print("\nEnd-to-End Latency (full pipeline):")
    print(f"   Avg:  {e2e_stats['avg']:.2f}ms")
    print(f"   Min:  {e2e_stats['min']:.2f}ms")
    print(f"   Max:  {e2e_stats['max']:.2f}ms")
    print(f"   P95:  {e2e_stats['p95']:.2f}ms {'⚠️' if e2e_stats['p95'] > 80 else '✅'}")
    print(f"   P99:  {e2e_stats['p99']:.2f}ms")
    
    print("\n" + "=" * 70)
    print("✅ Latency tracking system test complete!")
    print("=" * 70)


def compute_stats(samples_deque):
    """Compute latency statistics using numpy."""
    if not samples_deque:
        return {"avg": 0.0, "min": 0.0, "max": 0.0, "p95": 0.0, "p99": 0.0}
    
    samples = np.array(list(samples_deque))
    return {
        "avg": float(np.mean(samples)),
        "min": float(np.min(samples)),
        "max": float(np.max(samples)),
        "p95": float(np.percentile(samples, 95)),
        "p99": float(np.percentile(samples, 99)),
    }


if __name__ == "__main__":
    test_latency_tracking()
