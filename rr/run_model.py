"""Score an open model on the shared eval set through Fireworks serverless sampling.

systems:
  base_zero             Nemotron 3.5 Super, no fine-tuning (the "before")
  rescue_radar_quick    LoRA, 3,839 examples (final checkpoint of the quick run), ablation
  rescue_radar          LoRA, 13,839 examples (final checkpoint of the full run), the main system
Choice of the main system was fixed before any test-set scoring: the full run's final checkpoint.
usage: python -m rr.run_model <system>
"""
import json, sys, time
from pathlib import Path

from rr.infer import DEFAULT_BASE, SHORT, SamplerClassifier

ROOT = Path(__file__).resolve().parent.parent
CHUNK = 96


def final_checkpoint(tag):
    d = json.loads((ROOT / "data" / f"checkpoints{tag}.json").read_text())
    return d["base_model"], d["checkpoints"][-1]


def make(system):
    if system == "base_zero":
        return SamplerClassifier(DEFAULT_BASE), {"model": DEFAULT_BASE, "checkpoint": None}
    active = ROOT / "data" / "active_model.json"
    if system == "rescue_radar" and active.exists():
        a = json.loads(active.read_text())  # the pre-registered pick, frozen at the cutoff
        base, ck = a["base_model"], {"step": a["step"], "path": a["path"], "at": a["at"]}
    else:
        tag = "" if system == "rescue_radar_quick" else "_full"
        base, ck = final_checkpoint(tag)
    name = f"Rescue Radar: {SHORT.get(base, base)} + LoRA (step {ck['step']})"
    return SamplerClassifier(base, ck["path"], name), {"model": base, "checkpoint": ck}


def main(system):
    clf, info = make(system)
    final = ROOT / "data" / "preds" / f"{system}.jsonl"
    out = final.with_suffix(".jsonl.part")  # renamed to final only when complete, so readers never see half a run
    done = {json.loads(l)["id"] for l in open(out)} if out.exists() else set()
    rows = [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]
    rows = [r for r in rows if r["id"] not in done]
    print(f"{system}: {len(rows)} to go with {clf.name}", flush=True)
    t_start = time.time()
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        res = clf.classify([r["text"] for r in chunk], workers=32)
        with open(out, "a") as f:
            for r, p in zip(chunk, res):
                in_tok = len(clf._prompt(r["text"]).to_ints())
                f.write(json.dumps({"id": r["id"], "event": r["event"], "label": r["label"], "pred": p["label"],
                                    "raw": p["raw"], "latency": round(p["latency_ms"] / 1000, 3),
                                    "in_tok": in_tok, "out_tok": len(clf.tok.encode(p["raw"], add_special_tokens=False)) + 1}) + "\n")
        print(f"{system}: {i + len(chunk)}/{len(rows)} in {time.time() - t_start:.0f}s", flush=True)
    out.replace(final)
    meta = ROOT / "data" / "preds" / f"{system}.meta.json"
    meta.write_text(json.dumps({**info, "name": clf.name, "wall_secs": round(time.time() - t_start, 1), "n": len(rows)}, indent=1))
    print(f"{system}: finished in {time.time() - t_start:.0f}s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
