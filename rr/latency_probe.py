"""Latency of one dispatcher request at a time (no concurrency), for our model and the live frontier model.

The benchmark runs 16-32 requests in parallel, so its latency includes queueing on shared capacity. This probe sends
N posts one by one, the way a single dispatcher action would, and writes results/latency_probe.json.
usage: python -m rr.latency_probe [n]
"""
import json, random, sys, time
from pathlib import Path

import numpy as np

from rr.frontier import classify_frontier, frontier_name
from rr.infer import get_classifier

ROOT = Path(__file__).resolve().parent.parent


def main(n=30):
    rows = [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]
    sample = random.Random(5).sample(rows, n)
    clf = get_classifier()
    clf.classify([sample[0]["text"]])  # warm-up: first call hot-loads the adapter
    ours, front = [], []
    for r in sample:
        t0 = time.time(); clf.classify([r["text"]], workers=1); ours.append((time.time() - t0) * 1000)
        try:
            t0 = time.time(); classify_frontier(r["text"]); front.append((time.time() - t0) * 1000)
        except RuntimeError as e:
            print("frontier unavailable:", e)
    out = {"n": n, "mode": "sequential, one request at a time, after one warm-up call",
           "ours": {"name": clf.name, "p50_ms": round(float(np.percentile(ours, 50)), 1), "p95_ms": round(float(np.percentile(ours, 95)), 1)},
           "frontier": {"name": frontier_name(), "p50_ms": round(float(np.percentile(front, 50)), 1) if front else None,
                        "p95_ms": round(float(np.percentile(front, 95)), 1) if front else None},
           "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "latency_probe.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
