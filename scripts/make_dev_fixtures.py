"""Build dev fixtures for the dispatch console's static adapter (web/data/).

Reads the real held-out eval set and recorded predictions, never calls a model:
  data/eval.jsonl, data/preds/<system>.jsonl, data/train_log*.jsonl, results/metrics.json (if present)
Writes (same names as the static export, see guide/API.md):
  web/data/meta.json, web/data/replay/<event>.json, web/data/results.json, web/data/train_log.json

results.json is a copy of results/metrics.json when it exists. Before the official evaluation lands, it is a
dev preview computed here from the recorded predictions (real numbers, flagged "dev_preview": true) so the
Benchmark view can be exercised. `ours` in replay posts is null until data/preds/rescue_radar.jsonl exists.

Run:  .venv/bin/python scripts/make_dev_fixtures.py [--out web/data]
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rr.labels import LABELS, RESCUE_CRITICAL  # noqa: E402

try:  # prices live with the frontier client; importing it loads .env only through rr.env.load_env()
    from rr.frontier import FRONTIER_NAME, PRICE_IN, PRICE_OUT
except Exception:  # pragma: no cover
    FRONTIER_NAME, PRICE_IN, PRICE_OUT = "Claude Opus 5.5 (20-shot)", 5.0, 25.0

EVENTS = {
    "hurricane_dorian_2019": {"name": "Hurricane Dorian", "type": "hurricane", "year": 2019,
                              "country": "Bahamas, United States", "center": [27.4, -78.6], "zoom": 5},
    "cyclone_idai_2019": {"name": "Cyclone Idai", "type": "cyclone", "year": 2019,
                          "country": "Mozambique, Zimbabwe, Malawi", "center": [-18.6, 33.9], "zoom": 6},
    "pakistan_earthquake_2019": {"name": "Pakistan Earthquake", "type": "earthquake", "year": 2019,
                                 "country": "Pakistan", "center": [33.2, 73.6], "zoom": 7},
    "midwestern_us_floods_2019": {"name": "Midwestern US Floods", "type": "flood", "year": 2019,
                                  "country": "United States", "center": [41.3, -95.8], "zoom": 5},
}

# Small per-event gazetteer, most specific first. (aliases, display name, lat, lng)
GAZ = {
    "hurricane_dorian_2019": [
        (["marsh harbour", "marsh harbor"], "Marsh Harbour, Abaco", 26.541, -77.063),
        (["hope town"], "Hope Town, Abaco", 26.540, -76.958),
        (["treasure cay"], "Treasure Cay, Abaco", 26.668, -77.283),
        (["freeport"], "Freeport, Grand Bahama", 26.533, -78.697),
        (["nassau"], "Nassau, Bahamas", 25.048, -77.355),
        (["ocracoke"], "Ocracoke, NC", 35.115, -75.981),
        (["outer banks", "obx"], "Outer Banks, NC", 35.558, -75.467),
        (["hatteras"], "Cape Hatteras, NC", 35.251, -75.529),
        (["wilmington"], "Wilmington, NC", 34.226, -77.945),
        (["charleston"], "Charleston, SC", 32.776, -79.931),
        (["myrtle beach"], "Myrtle Beach, SC", 33.689, -78.887),
        (["savannah"], "Savannah, GA", 32.081, -81.091),
        (["jacksonville"], "Jacksonville, FL", 30.332, -81.656),
        (["daytona"], "Daytona Beach, FL", 29.211, -81.023),
        (["cape canaveral", "brevard"], "Cape Canaveral, FL", 28.392, -80.608),
        (["orlando"], "Orlando, FL", 28.538, -81.379),
        (["palm beach"], "Palm Beach, FL", 26.715, -80.053),
        (["miami"], "Miami, FL", 25.762, -80.192),
        (["halifax"], "Halifax, NS", 44.649, -63.576),
        (["abaco", "abacos"], "Abaco Islands, Bahamas", 26.470, -77.080),
        (["grand bahama"], "Grand Bahama", 26.650, -78.350),
        (["bahamas", "bahamian"], "The Bahamas", 25.700, -77.600),
        (["puerto rico"], "Puerto Rico", 18.221, -66.590),
        (["north carolina"], "North Carolina", 35.760, -79.019),
        (["south carolina"], "South Carolina", 33.836, -81.164),
        (["georgia"], "Georgia, US", 32.679, -83.223),
        (["florida"], "Florida", 27.995, -81.760),
        (["nova scotia"], "Nova Scotia", 44.682, -63.744),
    ],
    "cyclone_idai_2019": [
        (["beira"], "Beira, Mozambique", -19.844, 34.839),
        (["buzi", "búzi"], "Búzi, Mozambique", -19.875, 34.620),
        (["dondo"], "Dondo, Mozambique", -19.609, 34.743),
        (["nhamatanda"], "Nhamatanda, Mozambique", -19.266, 34.208),
        (["chimoio"], "Chimoio, Mozambique", -19.116, 33.483),
        (["chimanimani"], "Chimanimani, Zimbabwe", -19.801, 32.870),
        (["chipinge"], "Chipinge, Zimbabwe", -20.188, 32.624),
        (["mutare"], "Mutare, Zimbabwe", -18.971, 32.671),
        (["harare"], "Harare, Zimbabwe", -17.829, 31.053),
        (["blantyre"], "Blantyre, Malawi", -15.787, 35.006),
        (["nsanje"], "Nsanje, Malawi", -16.920, 35.262),
        (["maputo"], "Maputo, Mozambique", -25.969, 32.573),
        (["sofala"], "Sofala, Mozambique", -19.200, 34.600),
        (["manica"], "Manica, Mozambique", -18.940, 32.880),
        (["mozambique", "moçambique"], "Mozambique", -18.665, 35.530),
        (["zimbabwe"], "Zimbabwe", -19.015, 29.155),
        (["malawi"], "Malawi", -13.254, 34.302),
        (["madagascar"], "Madagascar", -18.767, 46.869),
    ],
    "pakistan_earthquake_2019": [
        (["mirpur"], "Mirpur, AJK", 33.148, 73.751),
        (["jatlan"], "Jatlan, AJK", 33.030, 73.850),
        (["mangla"], "Mangla, AJK", 33.140, 73.640),
        (["bhimber"], "Bhimber, AJK", 32.975, 74.078),
        (["kotli"], "Kotli, AJK", 33.518, 73.902),
        (["jhelum"], "Jhelum, Punjab", 32.941, 73.727),
        (["gujrat"], "Gujrat, Punjab", 32.574, 74.079),
        (["muzaffarabad"], "Muzaffarabad, AJK", 34.370, 73.471),
        (["rawalpindi", "pindi"], "Rawalpindi", 33.598, 73.044),
        (["islamabad"], "Islamabad", 33.684, 73.048),
        (["lahore"], "Lahore", 31.549, 74.343),
        (["peshawar"], "Peshawar", 34.015, 71.580),
        (["azad kashmir", "ajk", "azad jammu"], "Azad Kashmir", 33.900, 73.800),
        (["kashmir"], "Kashmir region", 33.900, 74.000),
        (["pakistan"], "Pakistan", 31.000, 72.600),
    ],
    "midwestern_us_floods_2019": [
        (["offutt"], "Offutt AFB, NE", 41.118, -95.912),
        (["pacific junction"], "Pacific Junction, IA", 41.019, -95.800),
        (["council bluffs"], "Council Bluffs, IA", 41.262, -95.861),
        (["omaha"], "Omaha, NE", 41.257, -95.934),
        (["fremont"], "Fremont, NE", 41.433, -96.498),
        (["lincoln"], "Lincoln, NE", 40.814, -96.703),
        (["grand island"], "Grand Island, NE", 40.925, -98.342),
        (["sioux city"], "Sioux City, IA", 42.500, -96.400),
        (["davenport"], "Davenport, IA", 41.524, -90.578),
        (["kansas city"], "Kansas City, MO", 39.100, -94.578),
        (["st. louis", "st louis", "saint louis"], "St. Louis, MO", 38.627, -90.199),
        (["pine ridge"], "Pine Ridge, SD", 43.026, -102.556),
        (["nebraska"], "Nebraska", 41.492, -99.902),
        (["iowa"], "Iowa", 41.878, -93.098),
        (["missouri"], "Missouri", 37.964, -91.832),
        (["kansas"], "Kansas", 39.012, -98.484),
        (["south dakota"], "South Dakota", 43.969, -99.902),
        (["minnesota"], "Minnesota", 46.730, -94.686),
        (["wisconsin"], "Wisconsin", 43.784, -88.788),
        (["illinois"], "Illinois", 40.633, -89.398),
    ],
}
_GAZ_RE = {ev: [(re.compile(r"(?<![\w])#?(" + "|".join(re.escape(a) for a in al) + r")(?![\w])", re.I), name, lat, lng)
                for al, name, lat, lng in rows] for ev, rows in GAZ.items()}

URL = re.compile(r"https?://\S+|www\.\S+", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
MENTION = re.compile(r"(?<![\w])@\w{1,15}")
PHONE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]?\d{3,4}[\s.-]?\d{3,4}(?!\w)")


def scrub(text):
    """Dev stand-in for rr/scrub.py: URLs, emails, phone numbers and @handles."""
    text = URL.sub("[URL]", text)
    text = EMAIL.sub("[EMAIL]", text)
    text = PHONE.sub("[PHONE]", text)
    text = MENTION.sub("@user", text)
    return text.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<").strip()


def place_for(text, event):
    for rx, name, lat, lng in _GAZ_RE.get(event, []):
        if rx.search(text):
            return {"name": name, "lat": lat, "lng": lng}
    return None


def ts_of(tweet_id):
    return (int(tweet_id) >> 22) + 1288834974657


def read_jsonl(p):
    with open(p) as f:
        return [json.loads(line) for line in f if line.strip()]


# ---------- dev-preview metrics (only used when results/metrics.json is absent) ----------
def _f1s(y, p, labels):
    out, pairs = {}, Counter(zip(y, p))
    tps = {c: pairs.get((c, c), 0) for c in labels}
    py, pp = Counter(y), Counter(p)
    for c in labels:
        tp = tps[c]
        fp = pp.get(c, 0) - tp
        fn = py.get(c, 0) - tp
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        out[c] = {"precision": pr, "recall": rc, "f1": 2 * pr * rc / (pr + rc) if pr + rc else 0.0,
                  "support": tp + fn}
    return out


def _scores(y, p):
    labels = [c for c in LABELS if c in set(y) | set(p)]
    pc = _f1s(y, p, labels)
    yt = [a in RESCUE_CRITICAL for a in y]
    pt = [b in RESCUE_CRITICAL for b in p]
    tp = sum(1 for a, b in zip(yt, pt) if a and b)
    fp = sum(1 for a, b in zip(yt, pt) if not a and b)
    fn = sum(1 for a, b in zip(yt, pt) if a and not b)
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return {"accuracy": sum(a == b for a, b in zip(y, p)) / max(1, len(y)),
            "macro_f1": sum(v["f1"] for v in pc.values()) / max(1, len(pc)),
            "critical": {"precision": pr, "recall": rc, "f1": 2 * pr * rc / (pr + rc) if pr + rc else 0.0},
            "per_class": pc}


def dev_metrics(eval_rows, preds):
    import numpy as np
    rng = np.random.default_rng(0)
    by_id = {r["id"]: r for r in eval_rows}
    systems, names = {}, {"opus_few": FRONTIER_NAME, "opus_zero": "Claude Opus 5.5 (zero-shot)",
                          "base_zero": "Nemotron 3.5 Super (base, no fine-tuning)",
                          "rescue_radar": "Rescue Radar (Nemotron 3.5 Super + LoRA)",
                          "rescue_radar_quick": "Rescue Radar quick run (ablation)"}
    for sysname, rows in preds.items():
        rows = [r for r in rows if r["id"] in by_id]
        if not rows:
            continue
        y = [by_id[r["id"]]["label"] for r in rows]
        p = [r["pred"] for r in rows]
        s = _scores(y, p)
        ev = [r["event"] for r in rows]
        boots = {"accuracy": [], "macro_f1": [], "critical_recall": []}
        idx_by_ev = defaultdict(list)
        for i, e in enumerate(ev):
            idx_by_ev[e].append(i)
        for _ in range(300):
            ii = np.concatenate([rng.choice(v, len(v)) for v in idx_by_ev.values()])
            yy, pp = [y[i] for i in ii], [p[i] for i in ii]
            b = _scores(yy, pp)
            boots["accuracy"].append(b["accuracy"]); boots["macro_f1"].append(b["macro_f1"])
            boots["critical_recall"].append(b["critical"]["recall"])
        lat = sorted(r["latency"] * 1000 for r in rows if r.get("latency") is not None)
        cost = [(r["in_tok"] * PRICE_IN + r["out_tok"] * PRICE_OUT) / 1e6 for r in rows
                if r.get("in_tok") is not None and r.get("out_tok") is not None]
        per_event = {}
        for e, ids in idx_by_ev.items():
            se = _scores([y[i] for i in ids], [p[i] for i in ids])
            per_event[e] = {"n": len(ids), "accuracy": se["accuracy"], "macro_f1": se["macro_f1"],
                            "critical_recall": se["critical"]["recall"]}
        labs = list(LABELS)
        mat = [[0] * len(labs) for _ in labs]
        for a, b in zip(y, p):
            mat[labs.index(a)][labs.index(b)] += 1
        systems[sysname] = {
            "name": names.get(sysname, sysname), "kind": "frontier" if sysname.startswith("opus") else "open",
            "n": len(rows), "accuracy": s["accuracy"], "macro_f1": s["macro_f1"], "critical": s["critical"],
            "ci95": {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in boots.items()},
            "latency_ms": ({"p50": lat[len(lat) // 2], "p95": lat[int(len(lat) * 0.95)],
                            "mean": sum(lat) / len(lat)} if lat else None),
            "cost_per_1m_usd": (sum(cost) / len(cost) * 1e6) if cost else None,
            "cost_note": ("measured: API token counts x list price" if cost else None),
            "per_event": per_event, "per_class": s["per_class"], "confusion": {"labels": labs, "matrix": mat},
        }
    comps = []
    a_sys = "rescue_radar" if "rescue_radar" in preds else None
    b_sys = "opus_few" if "opus_few" in preds else None
    pairs = [(a_sys, b_sys)] if a_sys and b_sys else ([("opus_few", "opus_zero")] if "opus_zero" in preds and b_sys else [])
    for a, b in pairs:
        pa = {r["id"]: r["pred"] for r in preds[a]}
        pb = {r["id"]: r["pred"] for r in preds[b]}
        ids = [i for i in by_id if i in pa and i in pb]
        ca = [pa[i] == by_id[i]["label"] for i in ids]
        cb = [pb[i] == by_id[i]["label"] for i in ids]
        a_only = sum(1 for x, z in zip(ca, cb) if x and not z)
        b_only = sum(1 for x, z in zip(ca, cb) if z and not x)
        from math import comb
        n = a_only + b_only
        k = min(a_only, b_only)
        p_val = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
        ca_np, cb_np = np.array(ca, float), np.array(cb, float)
        evs = np.array([by_id[i]["event"] for i in ids])
        groups = [np.where(evs == e)[0] for e in sorted(set(evs))]
        deltas = []
        for _ in range(1000):
            ii = np.concatenate([rng.choice(g, len(g)) for g in groups])
            deltas.append(ca_np[ii].mean() - cb_np[ii].mean())
        comps.append({"a": a, "b": b, "metric": "accuracy", "delta": float(ca_np.mean() - cb_np.mean()),
                      "mcnemar": {"a_only": a_only, "b_only": b_only, "p": p_val},
                      "bootstrap": {"delta_ci95": [float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))],
                                    "a_wins": int(sum(d > 0 for d in deltas)), "n": 1000,
                                    "unit": "tweet, stratified by event"}})
    ev_counts = Counter(r["event"] for r in eval_rows)
    return {
        "generated_at": None, "dev_preview": True,
        "generated_by": "scripts/make_dev_fixtures.py from data/preds (dev preview; official numbers come from rr/evaluate.py)",
        "eval": {"n": len(eval_rows), "events": dict(ev_counts), "test_events": len(ev_counts),
                 "split": "train on 2016-2018 disasters, test on 4 unseen 2019 disasters"},
        "systems": systems, "comparisons": comps,
        "headline": {"ours": "rescue_radar" if "rescue_radar" in systems else None,
                     "frontier": "opus_few" if "opus_few" in systems else None},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "web" / "data"))
    args = ap.parse_args()
    out = Path(args.out)
    (out / "replay").mkdir(parents=True, exist_ok=True)

    eval_rows = read_jsonl(ROOT / "data" / "eval.jsonl")
    preds = {p.stem: read_jsonl(p) for p in sorted((ROOT / "data" / "preds").glob("*.jsonl"))}
    ours = {r["id"]: r for r in preds.get("rescue_radar", [])}
    front = {r["id"]: r for r in preds.get("opus_few", [])}

    metrics_path = ROOT / "results" / "metrics.json"
    results = json.loads(metrics_path.read_text()) if metrics_path.exists() else dev_metrics(eval_rows, preds)
    (out / "results.json").write_text(json.dumps(results, indent=1))

    by_event = defaultdict(list)
    for r in eval_rows:
        o, f = ours.get(r["id"]), front.get(r["id"])
        fcost = None
        if f and f.get("in_tok") is not None and f.get("out_tok") is not None:
            fcost = round((f["in_tok"] * PRICE_IN + f["out_tok"] * PRICE_OUT) / 1e6, 7)
        by_event[r["event"]].append({
            "id": r["id"], "ts": ts_of(r["id"]), "text": scrub(r["text"]), "place": place_for(r["text"], r["event"]),
            "truth": r["label"], "truth_critical": r["label"] in RESCUE_CRITICAL,
            "ours": ({"label": o["pred"], "critical": o["pred"] in RESCUE_CRITICAL,
                      "latency_ms": round(o["latency"] * 1000, 1) if o.get("latency") is not None else None} if o else None),
            "frontier": ({"label": f["pred"], "critical": f["pred"] in RESCUE_CRITICAL,
                          "latency_ms": round(f["latency"] * 1000, 1) if f.get("latency") is not None else None,
                          "cost_usd": fcost} if f else None),
        })

    events = []
    for eid, info in EVENTS.items():
        posts = sorted(by_event.get(eid, []), key=lambda p: p["ts"])
        ev = {"id": eid, **info, "n_posts": len(posts), "n_critical": sum(p["truth_critical"] for p in posts)}
        events.append(ev)
        (out / "replay" / f"{eid}.json").write_text(json.dumps({"event": ev, "posts": posts}, separators=(",", ":")))

    model = {"name": "Rescue Radar (Nemotron 3.5 Super + LoRA)", "kind": "finetuned"}
    rr_sys = (results.get("systems") or {}).get("rescue_radar") or {}
    if rr_sys.get("name"):
        model["name"] = rr_sys["name"]
    meta = {"labels": [{"id": k, "name": k.replace("_", " ").capitalize(), "definition": v,
                        "critical": k in RESCUE_CRITICAL} for k, v in LABELS.items()],
            "events": events, "model": model, "frontier": {"name": FRONTIER_NAME}, "static": True}
    (out / "meta.json").write_text(json.dumps(meta, indent=1))

    runs = {}
    for p in sorted((ROOT / "data").glob("train_log*.jsonl")):
        tag = p.stem.replace("train_log", "").strip("_") or "quick"
        runs[tag] = read_jsonl(p)
    (out / "train_log.json").write_text(json.dumps({"runs": runs}))

    placed = sum(1 for v in by_event.values() for p in v if p["place"])
    print(f"wrote {out}: {len(events)} events, {len(eval_rows)} posts ({placed} placed), "
          f"ours={'yes' if ours else 'pending'}, frontier={'yes' if front else 'missing'}, "
          f"results={'metrics.json' if metrics_path.exists() else 'dev preview'}, runs={list(runs)}")


if __name__ == "__main__":
    main()
