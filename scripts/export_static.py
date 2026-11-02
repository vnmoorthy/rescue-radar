"""Build the GitHub Pages site (served from docs/): the console plus the data its static adapter reads.

    .venv/bin/python scripts/export_static.py [--out docs]

Copies web/ into docs/ (except web/data/, the dev fixtures) and writes the API responses as JSON:
    docs/data/meta.json              GET /api/meta with "static": true
    docs/data/replay/<event_id>.json GET /api/replay/<event_id>
    docs/data/results.json           GET /api/results
    docs/data/train_log.json         GET /api/train_log
Never touches docs/deck/ or docs/img/ (owned by the deck). Needs no network and no API keys: it calls the FastAPI
app in-process, never loads a live model and never probes the frontier API. Replay text is PII-scrubbed exactly as
the live API does it.

Refuses to export (exit 1) when results/metrics.json is pending or any replay is missing Rescue Radar predictions
for some posts, so docs/ never ships a partial run. --allow-partial overrides that for local previews.
"""
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("RR_WARM", "0")

PROTECTED = {"deck", "img"}  # docs/ subfolders other agents own
SKIP_FROM_WEB = {"data"}     # dev fixtures; docs/data is generated below


def copy_web(out):
    web = ROOT / "web"
    if not web.is_dir():
        print("web/ not found: skipped copying the console")
        return 0
    n = 0
    for src in sorted(web.rglob("*")):
        rel = src.relative_to(web)
        if rel.parts[0] in SKIP_FROM_WEB or rel.parts[0] in PROTECTED or any(p.startswith(".") for p in rel.parts):
            continue
        dst = out / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    return n


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return path


def _no_frontier_probe():
    """rr.frontier starts a live Claude request on its first frontier_name() call in auto mode; the export must not."""
    try:
        from rr import frontier
        with frontier._lock:
            frontier._state["probed"] = True
    except Exception:
        pass


def export(out, allow_partial=False):
    _no_frontier_probe()
    from fastapi.testclient import TestClient
    from rr.server import app

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)

    def get(path):
        r = client.get(path)
        if r.status_code != 200:
            raise SystemExit(f"{path} -> {r.status_code}: {r.text[:200]}")
        return r.json()

    n_files = copy_web(out)
    meta = get("/api/meta")
    meta["static"] = True
    # The static site only shows recorded predictions, so name the model that recorded them (not whichever
    # checkpoint is newest right now, which may still be training).
    from rr.server import DATA, ours_system
    rec = DATA / "preds" / f"{ours_system()}.meta.json"
    try:
        rec_name = json.loads(rec.read_text()).get("name")
    except (OSError, ValueError):
        rec_name = None
    if rec_name:
        meta["model"] = {**meta.get("model", {}), "name": rec_name, "recorded": ours_system()}
    results = get("/api/results")
    # The static replay shows the recorded frontier predictions (opus_few), so name that system, not whichever
    # frontier model would answer a live call right now.
    from rr.server import FRONTIER_PREDS
    rec_front = ((results.get("systems") or {}).get(FRONTIER_PREDS) or {}).get("name") if isinstance(results, dict) else None
    if rec_front:
        meta["frontier"] = {**meta.get("frontier", {}), "name": rec_front, "recorded": FRONTIER_PREDS}
    replays = {ev["id"]: get(f"/api/replay/{ev['id']}") for ev in meta["events"]}
    problems = []
    if not isinstance(results, dict) or results.get("status") == "pending" or not results.get("systems"):
        problems.append("/api/results is pending (results/metrics.json missing or unreadable)")
    for eid, rp in replays.items():
        cov, n = (rp.get("coverage") or {}).get("ours", 0), len(rp.get("posts") or [])
        if cov < n:
            problems.append(f"replay {eid}: Rescue Radar predictions for {cov}/{n} posts "
                            f"({(rp.get('systems') or {}).get('ours')})")
    if problems:
        msg = "export_static: refusing to export partial data:\n  " + "\n  ".join(problems)
        if not allow_partial:
            raise SystemExit(msg + "\nFinish scoring first, or pass --allow-partial for a local preview.")
        print(msg.replace("refusing to export", "exporting anyway (--allow-partial)"))
    written = [write_json(out / "data" / "meta.json", meta)]
    for eid, rp in replays.items():
        written.append(write_json(out / "data" / "replay" / f"{eid}.json", rp))
    written.append(write_json(out / "data" / "results.json", results))
    written.append(write_json(out / "data" / "train_log.json", get("/api/train_log")))
    (out / ".nojekyll").touch()
    print(f"copied {n_files} console files from web/ into {out}")
    for p in written:
        print(f"wrote {p.relative_to(out)} ({p.stat().st_size // 1024} KB)")
    print(f"scrubber: {meta.get('scrubber')}")
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "docs"), help="output folder (default docs/)")
    ap.add_argument("--allow-partial", action="store_true",
                    help="export even if results are pending or a replay lacks Rescue Radar predictions")
    a = ap.parse_args()
    export(a.out, allow_partial=a.allow_partial)


if __name__ == "__main__":
    main()
