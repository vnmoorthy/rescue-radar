"""Score the TypeSafe (Jev) judge on the shared eval set: one calibrated yes/no judgment per post.

TypeSafe (https://api.typesafe.ai) is a judgment-only model: it answers named questions about text with
calibrated probabilities (a "noul"), no free text. We ask it one question per post — does someone here need
emergency assistance? — and read the probability. At the 0.5 threshold that is an independent binary
classifier for exactly the decision Rescue Radar's priority queue makes, from a system that shares no
training, prompt or provider with ours or with the frontier baselines.

Writes data/preds/jev.jsonl: {id, event, label, noul, pred, latency, in_tok, out_tok}, where pred is
"critical" or "not_critical". Resumable: rows already written are skipped, like every prediction script.
usage: python -m rr.jev
"""
import json, os, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from rr.env import load_env

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://api.typesafe.ai"
MODEL = "jev-latest"
CHUNK = 96
WORKERS = 16
THRESHOLD = 0.5

QUESTION = ("Does the author of this post, or someone the post describes, need emergency assistance right now: "
            "rescue, urgent help or supplies, medical attention, or a person who is injured, dead, trapped or missing?")
STATE = "A public social media post written during a natural disaster:\n{text}"


def judge_one(client, key, text):
    t0 = time.time()
    r = client.post(f"{BASE}/v1/systemone", headers={"Authorization": f"Bearer {key}"},
                    json={"state": STATE.format(text=text),
                          "questions": {"emergency": {"type": "noul", "instructions": QUESTION}},
                          "model": MODEL})
    r.raise_for_status()
    d = r.json()
    noul = float(d["answers"]["emergency"]["noul"])
    usage = d.get("usage") or {}
    return {"noul": noul, "model": d.get("model"), "latency": round(time.time() - t0, 3),
            "in_tok": int(usage.get("input_tokens") or 0), "out_tok": int(usage.get("output_tokens") or 0)}


def main():
    env = load_env()
    key = env.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY missing from .env")
    final = ROOT / "data" / "preds" / "jev.jsonl"
    out = final.with_suffix(".jsonl.part")  # renamed to final only when complete, so readers never see half a run
    done = {json.loads(l)["id"] for l in open(out)} if out.exists() else set()
    if final.exists():
        done |= {json.loads(l)["id"] for l in open(final)}
    rows = [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]
    rows = [r for r in rows if r["id"] not in done]
    print(f"jev: {len(rows)} to go with TypeSafe {MODEL}", flush=True)
    t_start, model_seen = time.time(), None
    with httpx.Client(timeout=30) as client:
        for i in range(0, len(rows), CHUNK):
            chunk = rows[i:i + CHUNK]

            def one(r, _c=client):
                for attempt in range(4):
                    try:
                        return judge_one(_c, key, r["text"])
                    except (httpx.HTTPError, KeyError, ValueError):
                        if attempt == 3:
                            raise
                        time.sleep(2 ** attempt)

            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                res = list(ex.map(one, chunk))
            with open(out, "a") as f:
                for r, p in zip(chunk, res):
                    model_seen = p["model"] or model_seen
                    f.write(json.dumps({"id": r["id"], "event": r["event"], "label": r["label"], "noul": p["noul"],
                                        "pred": "critical" if p["noul"] >= THRESHOLD else "not_critical",
                                        "latency": p["latency"], "in_tok": p["in_tok"], "out_tok": p["out_tok"]}) + "\n")
            print(f"jev: {i + len(chunk)}/{len(rows)} in {time.time() - t_start:.0f}s", flush=True)
    out.replace(final)
    meta = ROOT / "data" / "preds" / "jev.meta.json"
    meta.write_text(json.dumps({"model": model_seen or MODEL, "name": f"TypeSafe (Jev) judge, {model_seen or MODEL}",
                                "question": QUESTION, "state_template": STATE, "threshold": THRESHOLD,
                                "wall_secs": round(time.time() - t_start, 1), "n": len(rows)}, indent=1))
    print(f"jev: finished in {time.time() - t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
