#!/usr/bin/env python3
"""Render the repo's doc templates with live numbers.

Every *.template.md and *.template.html file in the repo (skipping .venv, node_modules, .git and data/) is
rendered with Jinja2 to the same path without ".template":

    README.template.md               -> README.md
    guide/DEMO_RUNBOOK.template.md   -> guide/DEMO_RUNBOOK.md

Numbers come only from results/metrics.json and the files in data/, read at render time. Anything missing
renders as "n/a", so this works before, during and after the benchmark lands.

usage:
    python scripts/render_docs.py              render every template
    python scripts/render_docs.py --check      exit 1 if a rendered file is out of date
    python scripts/render_docs.py FILE [...]   render only these templates

Template context:
    m              results/metrics.json ({} if missing)
    ours           m.systems[m.headline.ours]
    frontier       m.systems[m.headline.frontier]
    frontier_zero  m.systems.opus_zero
    base           m.systems.base_zero
    quick          m.systems.rescue_radar_quick (ablation)
    cmp            first comparison with a == headline.ours and b == headline.frontier
    cmps           every comparison whose a == headline.ours
    d              facts computed from data/ (eval size, events, label counts, training runs, ...)
    integ          which optional integrations the code actually has (presidio, azure, ...)
    rows           result-table rows: ours, opus_few, opus_zero, base_zero (+ ablation), each {key, s, name, ours, frontier}
    ours_train     {examples, batch, steps, source} of the run behind headline.ours, read from the training log
                   header in data/train.out or data/train_full.out (not hard-coded in rr/evaluate.py)
    ours_run       d.runs entry of that run; headline_ablation: headline.ours is the small-data run
    pct pts usd ms pval num ci ci_pts ci_side ratio f label_name event_name shield   helpers ("n/a" on missing)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.parse
from collections import Counter
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, FileSystemLoader, Undefined, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

METRICS = ROOT / "results" / "metrics.json"
DATA = ROOT / "data"
SKIP_DIRS = {".venv", "venv", "node_modules", ".git", "__pycache__", ".pytest_cache", "data"}
NA = "n/a"
REPO = "https://github.com/vnmoorthy/rescue-radar"
SITE = "https://vnmoorthy.github.io/rescue-radar/"
BANNER = "<!-- Generated from {src} by scripts/render_docs.py. Edit the template, then re-run the script. -->\n"


# ---------------------------------------------------------------------------------------------- helpers
def f(x):
    """Float value of x, or None for missing, undefined, non-numeric, bool or non-finite input."""
    if x is None or isinstance(x, (Undefined, bool)):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def pct(x, digits=1):
    """0.8123 -> '81.2%'."""
    v = f(x)
    return NA if v is None else f"{v * 100:.{digits}f}%"


def pts(x, digits=1):
    """0.123 -> '+12.3 pts' (a difference of two proportions, in percentage points)."""
    v = f(x)
    return NA if v is None else f"{v * 100:+.{digits}f} pts"


def usd(x):
    """120 -> '$120', 3.5 -> '$3.50', 0.0042 -> '$0.0042'."""
    v = f(x)
    if v is None:
        return NA
    if v == 0:
        return "$0"
    if abs(v) >= 100:
        return f"${v:,.0f}"
    if abs(v) >= 1:
        return f"${v:,.2f}"
    return f"${v:.2g}" if abs(v) < 0.0001 else f"${v:.4f}"


def ms(x):
    """312.5 -> '313 ms', 1520 -> '1.52 s'."""
    v = f(x)
    if v is None:
        return NA
    return f"{v:,.0f} ms" if abs(v) < 1000 else f"{v / 1000:,.2f} s"


def pval(x):
    """1e-20 -> 'p < 0.001', 0.0123 -> 'p = 0.012', 0.42 -> 'p = 0.42'."""
    v = f(x)
    if v is None or v < 0:
        return NA
    if v < 0.001:
        return "p < 0.001"
    if v < 0.1:
        return f"p = {v:.3f}"
    return f"p = {v:.2f}"


def num(x, digits=None):
    """3001 -> '3,001', 0.5 -> '0.50'."""
    v = f(x)
    if v is None:
        return NA
    if digits is None and v.is_integer():
        return f"{int(v):,}"
    return f"{v:,.{2 if digits is None else digits}f}"


def _pair(x):
    try:
        lo, hi = f(x[0]), f(x[1])
    except Exception:
        return None
    return None if lo is None or hi is None else (lo, hi)


def ci(x, digits=1):
    """[0.79, 0.83] -> '79.0% to 83.0%'."""
    p = _pair(x)
    return NA if p is None else f"{pct(p[0], digits)} to {pct(p[1], digits)}"


def ci_pts(x, digits=1):
    """[0.10, 0.14] -> '+10.0 to +14.0 pts'."""
    p = _pair(x)
    return NA if p is None else f"{p[0] * 100:+.{digits}f} to {p[1] * 100:+.{digits}f} pts"


def ratio(a, b, digits=1):
    """ratio(120, 10) -> '12.0x'. n/a unless both are positive."""
    va, vb = f(a), f(b)
    if va is None or vb is None or va <= 0 or vb <= 0:
        return NA
    return f"{va / vb:,.{digits}f}x"


def ci_side(x):
    """Where a 95% interval of a difference sits: 'above' 0, 'below' 0, 'spans' 0, or None if missing."""
    p = _pair(x)
    if p is None:
        return None
    return "above" if p[0] > 0 else ("below" if p[1] < 0 else "spans")


def label_name(k):
    """'requests_or_urgent_needs' -> 'Requests or urgent needs' (the API.md display rule)."""
    if k is None or isinstance(k, Undefined) or not str(k):
        return NA
    return str(k).replace("_", " ").capitalize()


def event_name(e):
    """'midwestern_us_floods_2019' -> 'Midwestern US Floods (2019)'."""
    if e is None or isinstance(e, Undefined) or not str(e):
        return NA
    parts = str(e).split("_")
    year = parts.pop() if parts and parts[-1].isdigit() else None
    special = {"us": "US", "aug": "Aug."}
    name = " ".join(special.get(w, w.capitalize()) for w in parts)
    return f"{name} ({year})" if year else name


def shield(label, message, color="informational", logo=None, logo_color="white"):
    """A shields.io static badge URL with correct escaping."""
    def esc(s):
        s = "" if s is None or isinstance(s, Undefined) else str(s)
        return urllib.parse.quote(s.replace("-", "--").replace("_", "__"), safe="")
    url = f"https://img.shields.io/badge/{esc(label)}-{esc(message)}-{urllib.parse.quote(str(color), safe='')}"
    if logo:
        url += f"?logo={urllib.parse.quote(str(logo), safe='')}&logoColor={urllib.parse.quote(str(logo_color), safe='')}"
    return url


# ------------------------------------------------------------------------------------------- inputs
def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def read_jsonl(path):
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        return None
    return rows


def count_lines(path):
    try:
        with open(path, "rb") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return None


def _show(path):
    try:
        return Path(path).relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_metrics(warn):
    m = read_json(METRICS)
    if m is None:
        if METRICS.exists():
            warn(f"{_show(METRICS)} is not valid JSON; rendering every number as n/a")
        else:
            warn(f"{_show(METRICS)} not found; rendering every number as n/a")
        return {}
    if not isinstance(m, dict):
        warn("results/metrics.json is not a JSON object; rendering every number as n/a")
        return {}
    return m


def train_runs():
    """Per training run (data/train_log<tag>.jsonl + data/checkpoints<tag>.json): steps, wall time, checkpoints."""
    runs = {}
    for p in sorted(DATA.glob("train_log*.jsonl")):
        tag = p.stem[len("train_log"):]
        log = read_jsonl(p) or []
        secs = [f(r.get("secs")) for r in log if f(r.get("secs")) is not None]
        losses = [f(r.get("loss")) for r in log if f(r.get("loss")) is not None]
        ck = read_json(DATA / f"checkpoints{tag}.json") or {}
        cks = ck.get("checkpoints") or []
        k = max(1, min(10, len(losses) // 4)) if losses else 0
        runs[tag or "quick"] = {
            "tag": tag,
            "steps": len(log),
            "train_minutes": sum(secs) / 60 if secs else None,
            "secs_per_step": sum(secs) / len(secs) if secs else None,
            "loss_start": sum(losses[:k]) / k if k else None,
            "loss_end": sum(losses[-k:]) / k if k else None,
            "loss_window": k,
            "started": log[0].get("at") if log else None,
            "finished": log[-1].get("at") if log else None,
            "base_model": ck.get("base_model"),
            "checkpoints": len(cks),
            "last_checkpoint_step": cks[-1].get("step") if cks else None,
        }
    return runs


def dedup_stats():
    """Re-derive the train/test overlap that rr.prep removes. Needs data/raw (local only, gitignored)."""
    try:
        from rr.prep import EVENTS, RAW, TEST_EVENTS, norm
    except Exception:
        return {}
    if not RAW.exists():
        return {}
    train, test = [], []
    for e in EVENTS:
        rows = []
        for split in ("train", "dev", "test"):
            p = RAW / e / f"{split}.json"
            if not p.exists():
                return {}
            try:
                rows += json.loads(p.read_text())
            except ValueError:
                return {}
        (test if e in TEST_EVENTS else train).extend(rows)
    keys = {norm(r.get("tweet_text", "")) for r in test}
    overlap = sum(1 for r in train if norm(r.get("tweet_text", "")) in keys)
    return {"raw_train_n": len(train), "raw_test_n": len(test), "dedup_removed": overlap}


def data_stats():
    d = {}
    try:
        from rr.labels import LABELS, RESCUE_CRITICAL
    except Exception:
        LABELS, RESCUE_CRITICAL = {}, set()
    d["labels"] = [{"id": k, "name": label_name(k), "definition": v, "critical": k in RESCUE_CRITICAL}
                   for k, v in LABELS.items()]
    d["labels_n"] = len(LABELS) or None
    d["critical_labels"] = [k for k in LABELS if k in RESCUE_CRITICAL]

    try:
        from rr.prep import EVENTS, TEST_EVENTS
        d["train_event_ids"] = [e for e in EVENTS if e not in TEST_EVENTS]
        d["test_event_ids"] = [e for e in EVENTS if e in TEST_EVENTS]
        d["train_events_n"] = len(d["train_event_ids"])
        d["all_events_n"] = len(EVENTS)
    except Exception:
        pass

    ev = read_jsonl(DATA / "eval.jsonl")
    if ev:
        events = Counter(r.get("event") for r in ev)
        labels = Counter(r.get("label") for r in ev)
        d["eval_n"] = len(ev)
        d["eval_events"] = dict(events.most_common())
        d["test_events_n"] = len(events)
        d["eval_labels"] = {k: labels.get(k, 0) for k in LABELS} if LABELS else dict(labels)
        d["eval_critical_n"] = sum(labels.get(k, 0) for k in RESCUE_CRITICAL)
        d["eval_critical_share"] = d["eval_critical_n"] / len(ev)
        top_event, top_n = events.most_common(1)[0]
        d["eval_top_event"], d["eval_top_event_share"] = top_event, top_n / len(ev)
    d["test_full_n"] = count_lines(DATA / "test_full.jsonl")
    d["train_sft_n"] = count_lines(DATA / "train_sft.jsonl")

    d["runs"] = train_runs()
    preds = {}
    for p in sorted((DATA / "preds").glob("*.jsonl")):
        meta = read_json(p.with_suffix(".meta.json")) or {}
        n = count_lines(p)
        wall = f(meta.get("wall_secs"))
        preds[p.stem] = {"rows": n, "name": meta.get("name"), "wall_secs": wall,
                         "posts_per_sec": (f(meta.get("n")) / wall) if wall and f(meta.get("n")) else None}
    d["preds"] = preds
    d["active_model"] = read_json(DATA / "active_model.json") or {}
    d.update(dedup_stats())
    return d


def integrations():
    """What the code really integrates, so the docs never claim more than the code does."""
    src = ""
    for p in sorted((ROOT / "rr").glob("*.py")):
        try:
            src += p.read_text(errors="ignore") + "\n"
        except OSError:
            pass
    try:
        req = (ROOT / "requirements.txt").read_text(errors="ignore").lower()
    except OSError:
        req = ""

    def imports(mod):
        return re.search(rf"^\s*(from|import)\s+{mod}\b", src, re.M) is not None

    def requires(pkg):
        return re.search(rf"^\s*{re.escape(pkg)}\b", req, re.M) is not None

    return {
        "presidio": imports("presidio_analyzer") or imports("presidio_anonymizer") or requires("presidio"),
        "azure_language": imports(r"azure\.ai\.textanalytics") or requires("azure-ai-textanalytics"),
        "azure_inference": imports(r"azure\.ai\.inference") or requires("azure-ai-inference"),
        "foundry": imports(r"azure\.ai\.projects") or requires("azure-ai-projects"),
        "scrub": (ROOT / "rr" / "scrub.py").exists(),
        "geo": (ROOT / "rr" / "geo.py").exists(),
        "server": (ROOT / "rr" / "server.py").exists(),
        "evaluate": (ROOT / "rr" / "evaluate.py").exists(),
        "export_static": (ROOT / "scripts" / "export_static.py").exists(),
        "requirements": bool(req),
    }


def train_header(system):
    """{examples, batch, steps, source} from the first lines of the training log of the run behind a system."""
    tag = {"rescue_radar_quick": "", "rescue_radar": "_full"}.get(system)
    if tag is None:
        return {}
    p = DATA / f"train{tag}.out"
    try:
        head = p.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return {}
    mm = re.search(r"(\d+) examples, batch (\d+), (\d+) steps", head)
    if not mm:
        return {}
    return {"examples": int(mm.group(1)), "batch": int(mm.group(2)), "steps": int(mm.group(3)),
            "source": f"data/train{tag}.out"}


def build_context(warn=lambda msg: print(f"warning: {msg}", file=sys.stderr)):
    m = load_metrics(warn)
    systems = m.get("systems") if isinstance(m.get("systems"), dict) else {}
    # Display names of our runs carry the training-set size from the training log header, not the value hard-coded in
    # rr/evaluate.py (which said 3,839 for a 3,939-example run).
    systems = dict(systems)
    for key, label in (("rescue_radar_quick", "Rescue Radar, small-data run"), ("rescue_radar", "Rescue Radar, main run")):
        th = train_header(key)
        if isinstance(systems.get(key), dict) and th.get("examples"):
            systems[key] = {**systems[key], "name": f"{label} ({th['examples']:,} examples)"}
    head = m.get("headline") if isinstance(m.get("headline"), dict) else {}
    ours_key = head.get("ours") or "rescue_radar"
    frontier_key = head.get("frontier") or "opus_few"
    comps = [c for c in (m.get("comparisons") or []) if isinstance(c, dict)]
    cmp = next((c for c in comps if c.get("a") == ours_key and c.get("b") == frontier_key), {})
    if m:
        for key in (ours_key, frontier_key, "opus_zero", "base_zero"):
            if key not in systems:
                warn(f"metrics.json has no system '{key}' yet; its numbers render as n/a")
        if not cmp:
            warn(f"metrics.json has no comparison {ours_key} vs {frontier_key} yet; statistics render as n/a")
    names = {"rescue_radar": "Rescue Radar (Nemotron 3.5 Super + LoRA)", "opus_few": "Claude Opus 5.5, 20-shot",
             "opus_zero": "Claude Opus 5.5, zero-shot", "base_zero": "Nemotron 3.5 Super, no fine-tuning",
             "rescue_radar_quick": "Rescue Radar, small-data ablation",
             "gpt_few": "GPT-6.1 Terra, 20-shot", "gpt_zero": "GPT-6.1 Terra, zero-shot"}
    rows, seen = [], set()
    for key in (ours_key, "opus_few", "opus_zero", "gpt_few", "gpt_zero", "base_zero", "rescue_radar_quick"):
        if key in seen or (key == "rescue_radar_quick" and key not in systems):
            continue
        seen.add(key)
        s = systems.get(key) or {}
        rows.append({"key": key, "s": s, "name": s.get("name") or names.get(key, key),
                     "ours": key == ours_key, "frontier": key == frontier_key})
    name_of = lambda k: (systems.get(k) or {}).get("name") or names.get(k, k)
    return {
        "rows": rows, "ours_name": name_of(ours_key), "frontier_name": name_of(frontier_key),
        "cmp_by_b": {c.get("b"): c for c in comps if c.get("a") == ours_key}, "ci_side": ci_side,
        "m": m, "systems": systems, "comparisons": comps, "metrics_ready": bool(systems),
        "ours_key": ours_key, "frontier_key": frontier_key,
        "ours": systems.get(ours_key) or {}, "frontier": systems.get(frontier_key) or {},
        "frontier_zero": systems.get("opus_zero") or {}, "base": systems.get("base_zero") or {},
        "quick": systems.get("rescue_radar_quick") or {},
        "cmp": cmp, "cmps": [c for c in comps if c.get("a") == ours_key],
        "d": (d := data_stats()), "integ": integrations(), "repo": REPO, "site": SITE,
        "ours_train": train_header(ours_key), "headline_ablation": ours_key == "rescue_radar_quick",
        "ours_run": ((d.get("runs") or {}).get("_full" if ours_key == "rescue_radar" else "quick") or {})
        if isinstance(d, dict) else {},
        "pct": pct, "pts": pts, "usd": usd, "ms": ms, "pval": pval, "num": num, "ci": ci, "ci_pts": ci_pts,
        "ratio": ratio, "f": f, "label_name": label_name, "event_name": event_name, "shield": shield,
    }


# ------------------------------------------------------------------------------------------- render
def find_templates():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(n for n in dirnames if n not in SKIP_DIRS and not n.startswith(".venv"))
        for name in sorted(filenames):
            if name.endswith((".template.md", ".template.html")):
                out.append(Path(dirpath) / name)
    return out


def target_of(tpl):
    return tpl.with_name(tpl.name.replace(".template.", ".", 1))


def make_env():
    return Environment(loader=FileSystemLoader(str(ROOT)), undefined=ChainableUndefined,
                       autoescape=select_autoescape(["html"]), keep_trailing_newline=True,
                       trim_blocks=True, lstrip_blocks=True)


def render_one(env, tpl, ctx):
    rel = tpl.relative_to(ROOT).as_posix()
    text = env.get_template(rel).render(**ctx)
    if tpl.name.endswith(".md"):
        text = BANNER.format(src=rel) + text
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="*", help="templates to render (default: all)")
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if any output is out of date")
    args = ap.parse_args(argv)

    templates = [Path(p).resolve() for p in args.files] if args.files else find_templates()
    if not templates:
        print("no *.template.md / *.template.html files found")
        return 0
    ctx = build_context()
    env = make_env()
    failed, stale = [], []
    for tpl in templates:
        out = target_of(tpl)
        rel_in, rel_out = tpl.relative_to(ROOT).as_posix(), out.relative_to(ROOT).as_posix()
        try:
            text = render_one(env, tpl, ctx)
        except Exception as e:  # keep going: one broken template must not block the others
            failed.append(rel_in)
            print(f"error: {rel_in}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        old = out.read_text() if out.exists() else None
        if old == text:
            print(f"up to date  {rel_out}")
        elif args.check:
            stale.append(rel_out)
            print(f"stale       {rel_out}")
        else:
            out.write_text(text)
            print(f"rendered    {rel_in} -> {rel_out}")
    if failed:
        print(f"{len(failed)} template(s) failed: {', '.join(failed)}", file=sys.stderr)
    if stale:
        print(f"{len(stale)} file(s) out of date; run python scripts/render_docs.py", file=sys.stderr)
    return 1 if failed or stale else 0


if __name__ == "__main__":
    sys.exit(main())
