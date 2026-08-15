"""Load test: fires N events at the running API concurrently and reports
throughput + latency distribution against the PRD's NFR target (100
events/sec, <500ms latency). This is the exact script used to produce the
numbers in the README's Performance section - run it yourself against
`docker compose up -d --build` to reproduce them.

Usage:
    python scripts/load_test.py [base_url] [n_events] [concurrency]
    python scripts/load_test.py http://localhost:5000 300 40
"""
import concurrent.futures
import statistics
import sys
import time

import requests

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5000"
N_EVENTS = int(sys.argv[2]) if len(sys.argv) > 2 else 300
CONCURRENCY = int(sys.argv[3]) if len(sys.argv) > 3 else 40


def make_event(i):
    vehicle_index = i % 20
    vehicle_id = f"veh_load_{vehicle_index}"
    # Each vehicle gets its own well-separated zone (10,000 units apart) so
    # this synthetic load doesn't accidentally cluster 20 unrelated
    # vehicles on top of each other - realistic fleets aren't bumper to
    # bumper, and the proximity feature's cost should reflect that (see
    # README's "A performance lesson").
    zone_offset = vehicle_index * 10000
    return {
        "source": "sensor",
        "vehicle_id": vehicle_id,
        "timestamp": f"2026-08-15T10:{(i // 60) % 60:02d}:{i % 60:02d}Z",
        "data": {
            "position": {"x": zone_offset + i, "y": zone_offset + i},
            "velocity": 10 + (i % 5),
            "confidence": 0.9,
            "status": "safe",
        },
    }


def post_one(i):
    event = make_event(i)
    t0 = time.perf_counter()
    resp = requests.post(f"{BASE_URL}/events", json=event, timeout=10)
    elapsed = time.perf_counter() - t0
    return resp.status_code, elapsed


def main():
    print(f"Firing {N_EVENTS} events at {BASE_URL} with concurrency={CONCURRENCY}...")
    start = time.perf_counter()
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for r in pool.map(post_one, range(N_EVENTS)):
            results.append(r)
    total_time = time.perf_counter() - start

    statuses = [s for s, _ in results]
    latencies = sorted(l for _, l in results)
    ok = sum(1 for s in statuses if s in (200, 201))

    print(f"\n== Results ==")
    print(f"Total wall time:      {total_time:.2f}s")
    print(f"Throughput:           {N_EVENTS / total_time:.1f} events/sec")
    print(f"Success rate:         {ok}/{N_EVENTS} ({100*ok/N_EVENTS:.1f}%)")
    print(f"Latency min/mean/p50: {latencies[0]*1000:.1f}ms / {statistics.mean(latencies)*1000:.1f}ms / {latencies[len(latencies)//2]*1000:.1f}ms")
    print(f"Latency p95/p99/max:  {latencies[int(len(latencies)*0.95)]*1000:.1f}ms / {latencies[int(len(latencies)*0.99)]*1000:.1f}ms / {latencies[-1]*1000:.1f}ms")

    under_500ms = sum(1 for l in latencies if l < 0.5)
    print(f"\nRequests under 500ms: {under_500ms}/{N_EVENTS} ({100*under_500ms/N_EVENTS:.1f}%)")
    print(f"Meets '100 events/sec' target: {'YES' if N_EVENTS/total_time >= 100 else 'NO'}")
    print(f"Meets '<500ms latency' target: {'YES' if latencies[int(len(latencies)*0.95)] < 0.5 else 'NO'} (p95)")


if __name__ == "__main__":
    main()
