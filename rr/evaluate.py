"""Score every system on the shared held-out eval set and write results/metrics.json.

Only systems with a prediction for every eval tweet are scored, so all systems are compared on the same cases.
Statistics: exact McNemar test on per-tweet correctness, and a paired bootstrap (B resamples of tweets,
stratified by disaster) for 95% intervals on every metric and on every difference between systems.
usage: python -m rr.evaluate
"""
import json, math, time
from collections import Counter
from pathlib import Path

import numpy as np

from rr.labels import LABELS, RESCUE_CRITICAL

ROOT = Path(__file__).resolve().parent.parent
B = 5000
LAB = list(LABELS)
CRIT = np.array([lab in RESCUE_CRITICAL for lab in LAB])
# Serving prices, USD per 1M tokens. Frontier: Anthropic list price for Claude Opus 5.5 (measured tokens).
OPUS_IN, OPUS_OUT = 4.0, 20.0
# Open model: Fireworks Serverless Training API sampling rate for NVIDIA Nemotron 3.5 Super VL 120B, the exact path
# Rescue Radar is served through: $0.57 prefill / $1.44 sample per 1M tokens (published; includes a limited-time
# 50% discount, so the undiscounted rate is about 2x).
FW_IN, FW_OUT = 0.57, 1.44
SYSTEMS = {
    "rescue_radar": ("Rescue Radar (Nemotron 3.5 Super + LoRA, step 275: 8,800 examples seen)", "open-finetuned"),
    "rescue_radar_quick": ("Rescue Radar, small-data ablation (3,939 examples)", "open-finetuned"),
    "base_zero": ("Nemotron 3.5 Super, no fine-tuning", "open-base"),
    "opus_few": ("Claude Opus 5.5, 20-shot", "frontier"),
    "opus_zero": ("Claude Opus 5.5, zero-shot", "frontier"),
    "gpt_few": ("GPT-6.1 Terra, 20-shot", "frontier"),
    "gpt_zero": ("GPT-6.1 Terra, zero-shot", "frontier"),
}
# USD per 1M tokens for GPT-6.1 Terra: OpenAI list price, standard tier, short context (reasoning billed as output).
GPT_IN, GPT_OUT = 1.0, 5.0


def load_eval():
    return [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]


def load_preds(system, ids):
    """Rows aligned to ids (None where the system has no answer) and the coverage mask."""
    p = ROOT / "data" / "preds" / f"{system}.jsonl"
    if not p.exists():
        return None, None
    rows = {}
    for line in open(p):
        r = json.loads(line)
        rows[r["id"]] = r
    mask = np.array([i in rows for i in ids])
    if mask.sum() < 500:
        print(f"skip {system}: only {int(mask.sum())}/{len(ids)} predictions")
        return None, None
    if not mask.all():
        print(f"{system}: partial coverage {int(mask.sum())}/{len(ids)}, scored on the tweets it answered")
    return [rows.get(i) for i in ids], mask


def per_class(y, p):
    out = {}
    for c, lab in enumerate(LAB):
        tp = int(((p == c) & (y == c)).sum()); fp = int(((p == c) & (y != c)).sum()); fn = int(((p != c) & (y == c)).sum())
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[lab] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": int((y == c).sum())}
    return out


def scores(y, p):
    pc = per_class(y, p)
    yt, pt = CRIT[y], np.where(p >= 0, CRIT[np.clip(p, 0, None)], False)
    tp = int((yt & pt).sum()); fp = int((~yt & pt).sum()); fn = int((yt & ~pt).sum())
    cp = tp / (tp + fp) if tp + fp else 0.0
    cr = tp / (tp + fn) if tp + fn else 0.0
    return {"accuracy": round(float((y == p).mean()), 4),
            "macro_f1": round(float(np.mean([v["f1"] for v in pc.values()])), 4),
            "critical": {"precision": round(cp, 4), "recall": round(cr, 4),
                         "f1": round(2 * cp * cr / (cp + cr) if cp + cr else 0.0, 4), "support": int(yt.sum())},
            "per_class": pc}


def binary_counts(yt, pt):
    """The two eval functions that matter for a dispatch queue, as explicit counts: false negatives
    (a real plea for help the system never flags) and false positives (a false alarm a person must clear)."""
    tp = int((yt & pt).sum()); fp = int((~yt & pt).sum()); fn = int((yt & ~pt).sum()); tn = int((~yt & ~pt).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(2 * prec * rec / (prec + rec) if prec + rec else 0.0, 4),
            "fnr": round(fn / (tp + fn) if tp + fn else 0.0, 4),
            "fpr": round(fp / (fp + tn) if fp + tn else 0.0, 4),
            "accuracy": round((tp + tn) / max(tp + fp + fn + tn, 1), 4)}


def rescue_binary(ev, ids, y, preds, masks):
    """Collapse every system to the binary decision the priority queue makes (rescue-critical or not) and
    score it two ways: against the human labels, and against the TypeSafe (Jev) judge's independent
    classification of whether someone needs emergency assistance (data/preds/jev.jsonl, python -m rr.jev)."""
    out = {"systems": {}}
    yt = CRIT[y]
    jev_rows, jev_mask = load_preds("jev", ids)
    jev_bin = None
    if jev_rows is not None:
        jev_bin = np.array([bool(r) and r["pred"] == "critical" for r in jev_rows])
        meta_p = ROOT / "data" / "preds" / "jev.meta.json"
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        answered = [r for r in jev_rows if r]
        lat = np.array([r["latency"] for r in answered]) * 1000
        out["judge"] = {"name": meta.get("name") or "TypeSafe (Jev) judge", "model": meta.get("model"),
                        "question": meta.get("question"), "threshold": meta.get("threshold", 0.5),
                        "n": int(jev_mask.sum()),
                        "vs_human": binary_counts(yt[jev_mask], jev_bin[jev_mask]),
                        "latency_ms": {"p50": round(float(np.percentile(lat, 50)), 1),
                                       "p95": round(float(np.percentile(lat, 95)), 1)}}
    for key, p in preds.items():
        mask = masks[key]
        pt = np.where(p >= 0, CRIT[np.clip(p, 0, None)], False)
        entry = {"vs_human": binary_counts(yt[mask], pt[mask])}
        if jev_bin is not None:
            both = mask & jev_mask
            entry["vs_jev"] = {**binary_counts(jev_bin[both], pt[both]), "n": int(both.sum()),
                               "agreement": round(float((pt[both] == jev_bin[both]).mean()), 4)}
        out["systems"][key] = entry
    return out


def boot_metrics(y, p, idx):
    """Vectorized accuracy, macro-F1 and critical recall for every bootstrap resample (rows of idx)."""
    Y, P = y[idx], p[idx]
    acc = (Y == P).mean(1)
    f1s = []
    for c in range(len(LAB)):
        tp = ((P == c) & (Y == c)).sum(1); fp = ((P == c) & (Y != c)).sum(1); fn = ((P != c) & (Y == c)).sum(1)
        denom = 2 * tp + fp + fn
        f1s.append(np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0.0))
    yt = CRIT[Y]; pt = np.where(P >= 0, CRIT[np.clip(P, 0, None)], False)
    crec = (yt & pt).sum(1) / np.maximum(yt.sum(1), 1)
    return {"accuracy": acc, "macro_f1": np.mean(f1s, 0), "critical_recall": crec}


def mcnemar(ca, cb):
    a_only = int((ca & ~cb).sum()); b_only = int((~ca & cb).sum())
    n, k = a_only + b_only, min(a_only, b_only)
    if n == 0:
        return {"a_only": 0, "b_only": 0, "p": 1.0}
    tail = sum(math.comb(n, i) for i in range(k + 1))
    logp = math.log(2) + math.log(tail) - n * math.log(2)
    return {"a_only": a_only, "b_only": b_only, "p": float(min(1.0, math.exp(logp))) if logp > -700 else 0.0,
            "log10_p": round(min(0.0, logp / math.log(10)), 2)}


def ci(a):
    lo, hi = np.percentile(a, [2.5, 97.5])
    return [round(float(lo), 4), round(float(hi), 4)]


def strat_idx(ev_idx, mask, rng):
    """Bootstrap index matrix over the tweets in mask, resampling within each disaster."""
    parts = []
    for e in np.unique(ev_idx[mask]):
        pool = np.where(mask & (ev_idx == e))[0]
        parts.append(rng.choice(pool, size=(B, len(pool)), replace=True))
    return np.concatenate(parts, axis=1)


def main():
    ev = load_eval()
    ids = [r["id"] for r in ev]
    y = np.array([LAB.index(r["label"]) for r in ev])
    events = sorted({r["event"] for r in ev})
    ev_idx = np.array([events.index(r["event"]) for r in ev])
    rng = np.random.default_rng(2026)
    full_idx = strat_idx(ev_idx, np.ones(len(ev), bool), rng)

    systems, preds, masks = {}, {}, {}
    for key, (name, kind) in SYSTEMS.items():
        rows, mask = load_preds(key, ids)
        if rows is None:
            continue
        p = np.array([(LAB.index(r["pred"]) if r["pred"] in LAB else -1) if r else -2 for r in rows])
        preds[key], masks[key] = p, mask
        ym, pm = y[mask], p[mask]
        s_ = scores(ym, pm)
        answered = [r for r in rows if r]
        lat = np.array([r["latency"] for r in answered]) * 1000
        in_tok = np.array([r.get("in_tok", 0) for r in answered], dtype=float)
        out_tok = np.array([r.get("out_tok", 0) for r in answered], dtype=float)
        if key.startswith("opus"):
            per_post = (in_tok * OPUS_IN + out_tok * OPUS_OUT) / 1e6
            cost_note = "measured tokens x Anthropic list price ($4 in / $20 out per 1M tokens, thinking tokens included)"
        elif key.startswith("gpt"):
            per_post = (in_tok * GPT_IN + out_tok * GPT_OUT) / 1e6
            cost_note = "measured tokens x OpenAI list price ($1 in / $5 out per 1M tokens, reasoning tokens included)"
        else:
            per_post = (in_tok * FW_IN + out_tok * FW_OUT) / 1e6
            cost_note = (f"measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super (${FW_IN} prefill / "
                         f"${FW_OUT} sample per 1M tokens, includes a limited-time 50% discount; about 2x without it)")
        meta_p = ROOT / "data" / "preds" / f"{key}.meta.json"
        meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
        idx = full_idx if mask.all() else strat_idx(ev_idx, mask, rng)
        bt = boot_metrics(y, p, idx)
        per_event = {}
        for e_i, e in enumerate(events):
            m = mask & (ev_idx == e_i)
            se = scores(y[m], p[m])
            per_event[e] = {"n": int(m.sum()), "accuracy": se["accuracy"], "macro_f1": se["macro_f1"],
                            "critical_recall": se["critical"]["recall"], "critical_support": se["critical"]["support"]}
        cm = np.zeros((len(LAB), len(LAB)), dtype=int)
        for t, q in zip(ym, pm):
            if q >= 0:
                cm[t, q] += 1
        systems[key] = {
            "name": name, "kind": kind,
            "model": meta.get("model") or ("claude-opus-5-5" if key.startswith("opus") else "gpt-6.1-terra" if key.startswith("gpt") else None),
            "checkpoint": (meta.get("checkpoint") or {}).get("path"), "checkpoint_step": (meta.get("checkpoint") or {}).get("step"),
            "n": int(mask.sum()), "coverage": round(float(mask.mean()), 4),
            "coverage_note": None if mask.all() else "API spending cap reached mid-run; scored on the random subset it answered",
            "accuracy": s_["accuracy"], "macro_f1": s_["macro_f1"], "critical": s_["critical"],
            "ci95": {"accuracy": ci(bt["accuracy"]), "macro_f1": ci(bt["macro_f1"]), "critical_recall": ci(bt["critical_recall"])},
            "latency_ms": {"p50": round(float(np.percentile(lat, 50)), 1), "p95": round(float(np.percentile(lat, 95)), 1),
                           "mean": round(float(lat.mean()), 1)},
            "tokens": {"in_mean": round(float(in_tok.mean()), 1), "out_mean": round(float(out_tok.mean()), 1)},
            "cost_per_1k_usd": round(float(per_post.mean() * 1e3), 4), "cost_per_1m_usd": round(float(per_post.mean() * 1e6), 2),
            "cost_per_1m_usd_undiscounted": round(float(per_post.mean() * 1e6 * (2 if kind != "frontier" else 1)), 2),
            "cost_note": cost_note, "cost_measured": True,
            "no_answer": int((pm < 0).sum()),
            "pred_distribution": dict(Counter(LAB[q] if q >= 0 else "__no_answer__" for q in pm)),
            "per_event": per_event, "per_class": s_["per_class"], "confusion": {"labels": LAB, "matrix": cm.tolist()},
        }
        print(f"{key:20} n {int(mask.sum()):4}  acc {s_['accuracy']:.3f}  macroF1 {s_['macro_f1']:.3f}  crit R {s_['critical']['recall']:.3f} "
              f"P {s_['critical']['precision']:.3f}  p50 {systems[key]['latency_ms']['p50']:.0f}ms  $/1M {systems[key]['cost_per_1m_usd']}")

    ours = "rescue_radar" if "rescue_radar" in systems else ("rescue_radar_quick" if "rescue_radar_quick" in systems else None)
    complete_frontier = [k for k in systems if systems[k]["kind"] == "frontier" and systems[k]["coverage"] == 1.0]
    any_frontier = [k for k in systems if systems[k]["kind"] == "frontier"]
    # Headline = the strongest frontier system by macro-F1, even if its coverage is partial (the comparison is then
    # paired on the tweets both answered, and n is reported). Beating the weakest baseline would prove little.
    frontier = max(any_frontier, key=lambda k: systems[k]["macro_f1"]) if any_frontier else None
    comparisons = []
    if ours:
        for other in [k for k in systems if k != ours]:
            both = masks[ours] & masks[other]
            ca, cb = (preds[ours] == y)[both], (preds[other] == y)[both]
            idx = full_idx if both.all() else strat_idx(ev_idx, both, rng)
            ba, bb = boot_metrics(y, preds[ours], idx), boot_metrics(y, preds[other], idx)
            d = {m: ba[m] - bb[m] for m in ("accuracy", "macro_f1", "critical_recall")}
            sa, sb = scores(y[both], preds[ours][both]), scores(y[both], preds[other][both])
            comparisons.append({
                "a": ours, "b": other, "n": int(both.sum()), "metric": "accuracy",
                "a_on_shared": {"accuracy": sa["accuracy"], "macro_f1": sa["macro_f1"], "critical_recall": sa["critical"]["recall"]},
                "b_on_shared": {"accuracy": sb["accuracy"], "macro_f1": sb["macro_f1"], "critical_recall": sb["critical"]["recall"]},
                "delta": round(sa["accuracy"] - sb["accuracy"], 4),
                "delta_macro_f1": round(sa["macro_f1"] - sb["macro_f1"], 4),
                "delta_critical_recall": round(sa["critical"]["recall"] - sb["critical"]["recall"], 4),
                "mcnemar": mcnemar(ca, cb),
                "bootstrap": {"delta_ci95": ci(d["accuracy"]), "macro_f1_delta_ci95": ci(d["macro_f1"]),
                              "critical_recall_delta_ci95": ci(d["critical_recall"]),
                              "a_wins": int((d["macro_f1"] > 0).sum()), "n": B, "unit": "tweet, resampled within each disaster"},
            })
    # examples actually seen: the main run was frozen at step 275 of 432 (275 x 32 = 8,800 of a 13,839 pool)
    train_examples = {"rescue_radar": 8800, "rescue_radar_quick": 3939}
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "eval": {"n": len(ev), "events": {e: int((ev_idx == i).sum()) for i, e in enumerate(events)},
                 "train_events": 15, "test_events": 4, "train_examples": train_examples.get(ours), "train_pool": 13839 if ours == "rescue_radar" else 3939,
                 "split": "train on 15 disasters from 2016-2018, test on 4 unseen disasters from 2019",
                 "bootstrap_resamples": B, "preregistration": "guide/PREREGISTRATION.md",
                 "critical_support": int(CRIT[y].sum())},
        "systems": systems, "comparisons": comparisons,
        "rescue_binary": rescue_binary(ev, ids, y, preds, masks),
        "headline": {"ours": ours, "frontier": frontier, "base": "base_zero" if "base_zero" in systems else None},
    }
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "metrics.json").write_text(json.dumps(out, indent=1))
    for c in comparisons:
        print(f"{c['a']} vs {c['b']} (n={c['n']}): d_acc {c['delta']:+.3f} CI {c['bootstrap']['delta_ci95']}  d_macroF1 {c['delta_macro_f1']:+.3f} "
              f"CI {c['bootstrap']['macro_f1_delta_ci95']}  d_critR {c['delta_critical_recall']:+.3f} CI {c['bootstrap']['critical_recall_delta_ci95']}  McNemar p={c['mcnemar']['p']:.2e}")
    print("headline:", out["headline"])
    print("wrote results/metrics.json")


if __name__ == "__main__":
    main()
