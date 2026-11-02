"""Run a system over the shared eval set and save one prediction row per tweet.

systems:
  opus_zero   frontier baseline, Claude Opus 5.5, zero-shot
  opus_few    frontier baseline, Claude Opus 5.5, 20-shot (2 fixed training examples per category)
  gpt_zero    frontier baseline, GPT-6.1 Terra, zero-shot (API default reasoning)
  gpt_few     frontier baseline, GPT-6.1 Terra, 20-shot (same 20 examples)
usage: python -m rr.baseline <system> [limit]
Resumable: rows already in data/preds/<system>.jsonl are skipped.
"""
import json, os, random, sys, threading, time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rr.env import load_env
from rr.labels import LABELS, SYSTEM, parse_label

env = load_env()
import anthropic  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PREDS = ROOT / "data" / "preds"
lock = threading.Lock()
EFFORT = os.environ.get("RR_EFFORT", "medium")


def few_shots():
    rows = [json.loads(l) for l in open(ROOT / "data" / "train_sft.jsonl")]
    by = defaultdict(list)
    for r in rows:
        by[r["messages"][-1]["content"]].append(r["messages"][-2]["content"].removeprefix("Post: "))
    rng = random.Random(3)
    return [{"text": t, "label": lab} for lab in LABELS for t in rng.sample(by[lab], 2)]


def run(system, limit=None):
    PREDS.mkdir(parents=True, exist_ok=True)
    out = PREDS / f"{system}.jsonl"
    done = {json.loads(l)["id"] for l in open(out)} if out.exists() else set()
    rows = [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]
    rows = [r for r in rows if r["id"] not in done][: limit or None]
    is_gpt = system.startswith("gpt_")
    if is_gpt:
        from openai import OpenAI
        oai = OpenAI(api_key=env["OPENAI_API_KEY"], max_retries=6)
    else:
        client = anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"], max_retries=6)
    shots = few_shots() if system.endswith("_few") else []
    shot_msgs = []
    for s in shots:
        shot_msgs += [{"role": "user", "content": f"Post: {s['text']}"}, {"role": "assistant", "content": s["label"]}]
    model = "gpt-6.1-terra" if is_gpt else env["BASELINE_MODEL"]
    print(f"{system}: {len(rows)} to go on {model}", flush=True)

    def one(r):
        t0 = time.time()
        if is_gpt:
            try:
                resp = oai.chat.completions.create(model=model, max_completion_tokens=4096,
                                                   messages=[{"role": "system", "content": SYSTEM}] + shot_msgs
                                                   + [{"role": "user", "content": f"Post: {r['text']}"}])
                raw = resp.choices[0].message.content or ""
                rec = {"id": r["id"], "event": r["event"], "label": r["label"],
                       "pred": parse_label(raw) if raw.strip() else "__no_answer__", "raw": raw[:80],
                       "latency": round(time.time() - t0, 3), "in_tok": resp.usage.prompt_tokens,
                       "out_tok": resp.usage.completion_tokens, "stop_reason": resp.choices[0].finish_reason}
            except Exception as e:
                print("error", r["id"], type(e).__name__, str(e)[:160], flush=True)
                return
            with lock:
                with open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")
            return
        try:
            # Opus 5.5 always thinks (adaptive); effort is the only control. Give it room to finish thinking
            # and answer, or the label gets cut off (an earlier run with max_tokens=24 did exactly that).
            resp = client.messages.create(model=model, max_tokens=4096, system=SYSTEM, thinking={"type": "adaptive"},
                                          output_config={"effort": EFFORT},
                                          messages=shot_msgs + [{"role": "user", "content": f"Post: {r['text']}"}])
            raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            pred = parse_label(raw) if raw.strip() else "__no_answer__"
            rec = {"id": r["id"], "event": r["event"], "label": r["label"], "pred": pred, "raw": raw[:80],
                   "latency": round(time.time() - t0, 3), "in_tok": resp.usage.input_tokens, "out_tok": resp.usage.output_tokens,
                   "stop_reason": resp.stop_reason, "effort": EFFORT}
        except Exception as e:
            print("error", r["id"], type(e).__name__, str(e)[:120], flush=True)
            return
        with lock:
            with open(out, "a") as f:
                f.write(json.dumps(rec) + "\n")

    t0 = time.time()
    with ThreadPoolExecutor(int(os.environ.get("RR_WORKERS", 24))) as ex:
        for i, _ in enumerate(ex.map(one, rows), 1):
            if i % 250 == 0:
                print(f"{system}: {i}/{len(rows)} in {time.time() - t0:.0f}s", flush=True)
    print(f"{system}: finished in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
