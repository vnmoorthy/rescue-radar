"""Rescue Radar backend: FastAPI app serving /api/* (contract: guide/API.md) and the dispatch console at /.

Run:  .venv/bin/python -m rr.server          (RR_PORT, default 8787; RR_HOST, default 127.0.0.1)
Env:  RR_WARM=0      skip pre-scrubbing the replays in a background thread at startup
      RR_SCRUBBER=regex  force the regex PII scrubber instead of Microsoft Presidio
      RR_STATE_DIR   where queue.db and the scrub cache live (default state/)
      RR_INGEST=0    skip the live social/news ingest worker (rr.ingest: Reddit + SF news RSS -> classifier -> queue)
      RR_LIVE_MODEL  which weights the live console serves (read only by this server; rr.run_model and rr.promote
                     never see it): unset or "scored" = the checkpoint the benchmark scored as Rescue Radar
                     (data/preds/<ours>.meta.json), "<system>" = that scored system's checkpoint, "latest" =
                     rr.infer.get_classifier() (data/active_model.json, else the newest training checkpoint)
The live model loads lazily on the first classify request, never at import.
"""
import hashlib
import html
import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Literal, Optional, Union

from fastapi import FastAPI, HTTPException
from fastapi import Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt, StrictStr
from typing_extensions import Annotated

from rr import geo, ingest, scrub, store
from rr.labels import LABELS, RESCUE_CRITICAL

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("RR_DATA_DIR") or ROOT / "data")
RESULTS = ROOT / "results" / "metrics.json"
WEB = ROOT / "web"
DOCS_DATA = ROOT / "docs" / "data"  # the static export; served at /data so the console's fallback is never stale
# "ours" in replays: the full fine-tune's predictions once that run is COMPLETE, else the quick run's. rr.run_model
# appends 96 rows at a time and writes <system>.meta.json only after the last chunk, so a predictions file counts
# only when its .meta.json exists or it covers every eval post; a run in progress (or one that died) never
# replaces a complete one. (rr/evaluate.py should apply the same rule to headline.ours.)
OURS_PREDS_CHAIN, FRONTIER_PREDS = ("rescue_radar", "rescue_radar_quick"), "opus_few"
OURS_PREDS = OURS_PREDS_CHAIN[0]


def _finite_float(x):
    f = float(x)
    return f if math.isfinite(f) else None


def finite_loads(s):
    """json.loads that turns NaN / Infinity / overflowing numbers into None. Python's json accepts those tokens but
    Starlette refuses to send them, so a data file must never be able to turn a response into a 500."""
    return json.loads(s, parse_constant=lambda _c: None, parse_float=_finite_float)


def _read_json(path):
    try:
        return finite_loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def preds_complete(system):
    """True once data/preds/<system>.jsonl is finished: its .meta.json exists or it has a row for every eval post."""
    if not (DATA / "preds" / f"{system}.jsonl").exists():
        return False
    if (DATA / "preds" / f"{system}.meta.json").exists():
        return True
    ids = {str(r["id"]) for r in eval_rows() if isinstance(r, dict) and "id" in r}
    return bool(ids) and ids <= set(preds(system))


def ours_system():
    for system in OURS_PREDS_CHAIN:
        if preds_complete(system):
            return system
    for system in reversed(OURS_PREDS_CHAIN):  # nothing complete yet: the quick run's file (partial coverage shows)
        if (DATA / "preds" / f"{system}.jsonl").exists():
            return system
    return OURS_PREDS

try:  # rr.frontier loads .env through rr.env.load_env(); keep the server up even if that fails
    from rr import frontier as _frontier
    from rr.frontier import FRONTIER_NAME, PRICE_IN, PRICE_OUT
    _frontier_import_error = None
except Exception as e:  # pragma: no cover - only without .env / anthropic
    _frontier, PRICE_IN, PRICE_OUT = None, None, None
    FRONTIER_NAME = "Claude Opus 5.5 (20-shot)"
    _frontier_import_error = f"{type(e).__name__}: {str(e)[:160]}"

EVENT_INFO = {
    "hurricane_dorian_2019": {"name": "Hurricane Dorian", "type": "hurricane", "year": 2019,
                              "country": "The Bahamas and US Southeast", "center": [26.5, -77.5], "zoom": 7},
    "cyclone_idai_2019": {"name": "Cyclone Idai", "type": "cyclone", "year": 2019,
                          "country": "Mozambique, Zimbabwe and Malawi", "center": [-19.5, 34.8], "zoom": 6},
    "pakistan_earthquake_2019": {"name": "Pakistan earthquake", "type": "earthquake", "year": 2019,
                                 "country": "Pakistan (Mirpur, Azad Kashmir)", "center": [33.1, 73.7], "zoom": 8},
    "midwestern_us_floods_2019": {"name": "Midwestern US floods", "type": "flood", "year": 2019,
                                  "country": "United States (Nebraska and Iowa)", "center": [41.3, -96.0], "zoom": 6},
}


def label_name(label):
    return label.replace("_", " ").capitalize() if label else None


def post_ts(post_id):
    """Twitter snowflake -> post time in ms."""
    return (int(post_id) >> 22) + 1288834974657


# ---------------------------------------------------------------- data files (re-read when they change on disk)
_file_cache, _file_lock = {}, threading.Lock()


def _jsonl(path):
    """Rows of a JSONL file, cached by (mtime, size). Missing file -> []. Half-written last lines are skipped."""
    path = Path(path)
    try:
        st = path.stat()
    except FileNotFoundError:
        return []
    key = (st.st_mtime_ns, st.st_size)
    with _file_lock:
        hit = _file_cache.get(str(path))
        if hit and hit[0] == key:
            return hit[1]
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(finite_loads(line))
                except ValueError:
                    continue
    with _file_lock:
        _file_cache[str(path)] = (key, rows)
    return rows


def eval_rows():
    return _jsonl(DATA / "eval.jsonl")


def preds(system):
    """{post id: prediction row} for data/preds/<system>.jsonl ({} if the file is not there yet)."""
    return {str(r["id"]): r for r in _jsonl(DATA / "preds" / f"{system}.jsonl") if "id" in r}


def events():
    rows = eval_rows()
    out = []
    ids = list(EVENT_INFO) + sorted({r["event"] for r in rows} - set(EVENT_INFO))
    for eid in ids:
        ev_rows = [r for r in rows if r["event"] == eid]
        if not ev_rows:
            continue
        info = EVENT_INFO.get(eid) or {"name": label_name(eid), "type": "disaster", "year": None, "country": None,
                                       "center": None, "zoom": None}
        ts = [post_ts(r["id"]) for r in ev_rows]
        out.append({"id": eid, **info, "n_posts": len(ev_rows),
                    "n_critical": sum(r.get("label") in RESCUE_CRITICAL for r in ev_rows),
                    "first_ts": min(ts), "last_ts": max(ts)})
    return out


# ---------------------------------------------------------------- PII scrub cache for replays
_scrub_cache, _scrub_lock = None, threading.Lock()


def _scrub_cache_path():
    version = getattr(scrub, "RULES_VERSION", 1)
    suffix = "" if version == 1 else f"_v{version}"
    return Path(os.environ.get("RR_STATE_DIR") or ROOT / "state") / f"scrub_cache_{scrub.mode()}{suffix}.json"


def scrub_cached(texts):
    """scrub.scrub_many with a cache (memory + state/scrub_cache_<engine>.json) so replays redact once."""
    global _scrub_cache
    with _scrub_lock:
        scrub.scrub_many([])  # loads the engine, so mode() is final before we pick the cache file
        path = _scrub_cache_path()
        if _scrub_cache is None or _scrub_cache[0] != path:
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                data = {}
            _scrub_cache = (path, data)
        cache = _scrub_cache[1]
        key = {t: hashlib.sha1(t.encode("utf-8")).hexdigest() for t in texts}
        missing = list({t for t in texts if key[t] not in cache})
        if missing:
            for t, res in zip(missing, scrub.scrub_many(missing)):
                cache[key[t]] = [res[0], res[1]]
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(cache))
                tmp.replace(path)
            except OSError:
                pass
        return [tuple(cache[key[t]]) for t in texts]


def build_replay(event_id):
    ev = next((e for e in events() if e["id"] == event_id), None)
    if ev is None:
        raise HTTPException(404, f"Unknown event '{event_id}'. Known: {', '.join(e['id'] for e in events())}")
    rows = sorted((r for r in eval_rows() if r["event"] == event_id), key=lambda r: (post_ts(r["id"]), r["id"]))
    scrubbed = scrub_cached([r.get("text") or "" for r in rows])
    ours_key = ours_system()
    ours, front = preds(ours_key), preds(FRONTIER_PREDS)
    posts = []
    for r, (red, _) in zip(rows, scrubbed):
        pid = str(r["id"])
        o, f = ours.get(pid), front.get(pid)
        posts.append({
            # tweets arrive HTML-escaped (&amp;); decode after scrubbing so every consumer gets plain text
            "id": pid, "ts": post_ts(pid), "text": html.unescape(red), "place": geo.locate(red, event_id),
            "truth": r.get("label"), "truth_critical": r.get("label") in RESCUE_CRITICAL,
            "ours": _pred_view(o, cost=False), "frontier": _pred_view(f, cost=True)})
    return {"event": ev, "posts": posts, "systems": {"ours": ours_key, "frontier": FRONTIER_PREDS},
            "coverage": {"ours": sum(p["ours"] is not None for p in posts),
                         "frontier": sum(p["frontier"] is not None for p in posts)}}


def _pred_view(row, cost):
    if not row or not row.get("pred"):
        return None
    lat = row.get("latency")
    out = {"label": row["pred"], "critical": row["pred"] in RESCUE_CRITICAL,
           "latency_ms": round(lat * 1000, 1) if isinstance(lat, (int, float)) else None}
    if cost:
        it, ot = row.get("in_tok"), row.get("out_tok")
        out["cost_usd"] = ((it * PRICE_IN + ot * PRICE_OUT) / 1e6
                           if isinstance(it, (int, float)) and isinstance(ot, (int, float)) and PRICE_IN is not None
                           else None)
    return out


# ---------------------------------------------------------------- live models
_model_error = None
_live, _live_lock = {}, threading.Lock()


def live_target():
    """The checkpoint the live console serves, or None to defer to rr.infer.get_classifier().

    Default (RR_LIVE_MODEL unset or "scored"): the checkpoint the benchmark scored as Rescue Radar, read from
    data/preds/<ours_system()>.meta.json, so the console runs exactly the weights behind the replay and the Benchmark
    (and follows them when the pre-registered main run finishes scoring, without a restart). RR_LIVE_MODEL=<system>
    pins another scored system; RR_LIVE_MODEL=latest defers to rr.infer. RR_MODE=base always defers to rr.infer."""
    if os.environ.get("RR_MODE") == "base":
        return None
    want = (os.environ.get("RR_LIVE_MODEL") or "scored").strip()
    if want == "latest":
        return None
    system = ours_system() if want == "scored" else want
    meta = _read_json(DATA / "preds" / f"{system}.meta.json")
    ck = meta.get("checkpoint") if isinstance(meta, dict) else None
    if not isinstance(ck, dict) or not ck.get("path") or not meta.get("model"):
        return None
    return {"system": system, "base_model": meta["model"], "path": ck["path"], "step": ck.get("step"),
            "name": meta.get("name") or f"Rescue Radar (step {ck.get('step')})"}


def _classifier():
    """The live Rescue Radar model: the scored checkpoint (see live_target), else rr.infer's cached singleton."""
    t = live_target()
    if t is None:
        from rr.infer import get_classifier
        return get_classifier()
    key = (t["base_model"], t["path"])
    with _live_lock:
        clf = _live.get(key)
        if clf is None:
            from rr.infer import SamplerClassifier
            clf = SamplerClassifier(t["base_model"], t["path"], t["name"])
            _live.clear()
            _live[key] = clf
        return clf


def _frontier_classify(text):
    if _frontier is None:
        raise RuntimeError(f"Frontier baseline unavailable ({_frontier_import_error}).")
    return _frontier.classify_frontier(text)


def _unavailable(e, who):
    msg = str(e) if isinstance(e, RuntimeError) else f"{who} unavailable: {type(e).__name__}: {str(e)[:200]}"
    return HTTPException(503, msg or f"{who} unavailable.")


def _run_ours(texts):
    global _model_error
    try:
        clf = _classifier()
        res = clf.classify(list(texts))
    except Exception as e:  # RuntimeError from rr.infer, or anything else while loading: 503, never a crash
        _model_error = str(e)[:300]
        raise _unavailable(e, "Rescue Radar model")
    _model_error = None
    return clf, res


def _classified(text, res, model, scrubbed=None, event=None):
    red, reds = scrubbed if scrubbed is not None else scrub.scrub(text)
    label = res.get("label")
    # place from the redacted text: a pin must never put back a street the scrubber removed
    return {"label": label, "label_name": label_name(label), "critical": label in RESCUE_CRITICAL,
            "latency_ms": res.get("latency_ms"), "model": model, "redacted_text": red, "redactions": reds,
            "place": geo.locate(red, event), "raw": res.get("raw")}


def model_info():
    """name/kind/ready/loaded/error, plus scored (true when the live weights are exactly a scored system's
    checkpoint), system (that system) and step."""
    info = {"name": "Rescue Radar", "kind": "base" if os.environ.get("RR_MODE") == "base" else "finetuned",
            "ready": False, "loaded": False, "error": _model_error, "scored": False, "system": None, "step": None}
    try:
        import rr.infer as inf
    except Exception as e:
        info["error"] = f"{type(e).__name__}: {str(e)[:160]}"
        return info
    has_key = bool(os.environ.get("FIREWORKS_API_KEY"))
    t = live_target()
    if t is not None:
        loaded = (t["base_model"], t["path"]) in _live
        info.update(name=t["name"], kind="finetuned", ready=has_key or loaded, loaded=loaded, scored=True,
                    system=t["system"], step=t["step"])
        if loaded:
            info["error"] = None
        elif not has_key and not info["error"]:
            info["error"] = "FIREWORKS_API_KEY is not set."
        return info
    clf = getattr(inf, "_clf", None)
    if clf is not None:
        return {**info, "name": clf.name, "kind": clf.kind, "ready": True, "loaded": True, "error": None,
                "step": _step_of(getattr(clf, "path", None))}
    if info["kind"] == "base":
        base = os.environ.get("RR_BASE", inf.DEFAULT_BASE)
        info["name"] = f"{inf.SHORT.get(base, base)} (base, no fine-tuning)"
        info["ready"] = has_key
    else:
        try:
            ck = inf.latest_checkpoint()
        except Exception:
            ck = None
        if ck:
            info["name"] = ck.get("name") or "Rescue Radar (fine-tuned)"
            info["step"] = ck.get("step")
        info["ready"] = bool(ck) and has_key
        if not ck and not info["error"]:
            info["error"] = "No fine-tuned checkpoint found yet."
    if not has_key and not info["error"]:
        info["error"] = "FIREWORKS_API_KEY is not set."
    return info


def _step_of(path):
    import re
    m = re.search(r"-s0*(\d+)-", str(path or ""))
    return int(m.group(1)) if m else None


def training_info(system=None):
    """Examples / batch / steps of the run behind a system, read from the training log header
    ("3939 examples, batch 32, 123 steps" in data/train.out or data/train_full.out)."""
    import re
    system = system or ours_system()
    tag = {"rescue_radar_quick": "", "rescue_radar": "_full"}.get(system)
    if tag is None:
        return None
    try:
        with open(DATA / f"train{tag}.out", encoding="utf-8") as f:
            head = f.read(4096)
    except OSError:
        return None
    m = re.search(r"(\d+) examples, batch (\d+), (\d+) steps", head)
    if not m:
        return None
    return {"system": system, "examples": int(m.group(1)), "batch": int(m.group(2)), "steps": int(m.group(3)),
            "source": f"data/train{tag}.out"}


def frontier_name():
    """The frontier model that will answer right now (rr.frontier may fall back from Claude to GPT)."""
    fn = getattr(_frontier, "frontier_name", None)
    try:
        return fn() if fn else FRONTIER_NAME
    except Exception:
        return FRONTIER_NAME


def frontier_info():
    mode = os.environ.get("RR_FRONTIER", "auto")
    keys = {"claude": ["ANTHROPIC_API_KEY"], "gpt": ["OPENAI_API_KEY"]}.get(mode, ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"])
    ready = _frontier is not None and any(os.environ.get(k) for k in keys)
    return {"name": frontier_name(), "ready": ready,
            "error": None if ready else (_frontier_import_error or f"{' / '.join(keys)} not set.")}


# ---------------------------------------------------------------- app
def _warm():
    for ev in events():
        try:
            build_replay(ev["id"])
        except Exception:
            pass


def _ingest_classify(texts):
    """rr.ingest's bridge into the live model: (model name, prediction rows). Raises while it is unavailable."""
    clf, res = _run_ours(texts)
    return clf.name, res


@asynccontextmanager
async def lifespan(app):
    if os.environ.get("RR_WARM", "1") != "0":
        threading.Thread(target=_warm, name="rr-warm", daemon=True).start()
    if os.environ.get("RR_INGEST", "1") != "0":
        ingest.start(classify=_ingest_classify)
    yield


app = FastAPI(title="Rescue Radar", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
                   allow_methods=["*"], allow_headers=["*"])


def _safe(s, limit=1000):
    """Text that can always be encoded as UTF-8 (lone surrogates become '?')."""
    return str(s).encode("utf-8", "replace").decode("utf-8")[:limit]


@app.exception_handler(RequestValidationError)
async def _validation_error(request, exc):
    """422 as {"detail": str} (guide/API.md), without echoing the input back."""
    parts = []
    for e in exc.errors():
        if e.get("type") == "json_invalid":
            parts.append("body is not valid JSON")
            continue
        loc = [str(x) for x in (e.get("loc") or ())]
        where = ".".join(loc[1:]) or (loc[0] if loc else "request")
        parts.append(f"{where}: {e.get('msg', 'invalid value')}")
    return JSONResponse({"detail": _safe("; ".join(parts) or "invalid request")}, status_code=422)


class TextIn(BaseModel):
    text: str = Field(..., max_length=5000)


class BatchIn(BaseModel):
    texts: List[str] = Field(..., max_length=200)


class PlaceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    lat: float = Field(..., ge=-90, le=90, allow_inf_nan=False)
    lng: float = Field(..., ge=-180, le=180, allow_inf_nan=False)


class QueueIn(BaseModel):
    post_id: Optional[Union[Annotated[StrictStr, Field(max_length=200)], StrictInt]] = None
    text: str = Field("", max_length=5000)
    label: Optional[str] = Field(None, max_length=64)
    event: Optional[str] = Field(None, max_length=100)
    place: Optional[PlaceIn] = None


class QueuePatch(BaseModel):
    status: Optional[Literal["open", "dispatched", "resolved", "dismissed"]] = None
    note: Optional[str] = Field(None, max_length=2000)


def _need_text(text):
    if not text or not text.strip():
        raise HTTPException(422, "text must not be empty")
    return text


@app.get("/api/health")
def health():
    sc = scrub.status()
    return {"ok": True, "model": model_info(), "frontier": frontier_info(), "scrubber": sc["engine"],
            "scrubber_ready": sc["loaded"], "scrubber_error": sc["error"]}


@app.get("/api/meta")
def meta():
    m = model_info()
    return {"labels": [{"id": k, "name": label_name(k), "definition": v, "critical": k in RESCUE_CRITICAL}
                       for k, v in LABELS.items()],
            "events": events(),
            "model": {"name": m["name"], "kind": m["kind"], "scored": m.get("scored"), "system": m.get("system"),
                      "step": m.get("step")},
            "frontier": {"name": frontier_name()}, "training": training_info(),
            "scrubber": scrub.mode(), "static": False}


@app.get("/api/replay/{event_id}")
def replay(event_id: str):
    return build_replay(event_id)


@app.post("/api/classify")
def classify(body: TextIn):
    text = _need_text(body.text)
    clf, res = _run_ours([text])
    return _classified(text, res[0], clf.name)


@app.post("/api/classify_batch")
def classify_batch(body: BatchIn):
    texts = body.texts
    if any(not t or not t.strip() for t in texts):
        raise HTTPException(422, "texts must not contain empty strings")
    if any(len(t) > 5000 for t in texts):
        raise HTTPException(422, "each text must be at most 5000 characters")
    if not texts:
        return {"results": [], "total_ms": 0.0}
    t0 = time.time()
    clf, res = _run_ours(texts)
    total = round((time.time() - t0) * 1000, 1)
    scrubbed = scrub.scrub_many(texts)
    return {"results": [_classified(t, r, clf.name, s) for t, r, s in zip(texts, res, scrubbed)], "total_ms": total}


@app.post("/api/compare")
def compare(body: TextIn):
    text = _need_text(body.text)
    with ThreadPoolExecutor(2) as ex:
        f_ours, f_front = ex.submit(_run_ours, [text]), ex.submit(_frontier_classify, text)
        errors, ours, front = [], None, None
        try:
            clf, res = f_ours.result()
            ours = _classified(text, res[0], clf.name)
        except HTTPException as e:
            errors.append(f"Rescue Radar: {e.detail}")
        try:
            fr = f_front.result()
        except Exception as e:
            errors.append(f"Frontier: {_unavailable(e, 'Frontier baseline').detail}")
    if errors:
        raise HTTPException(503, " | ".join(errors))
    label = fr.get("label")
    frontier = {"label": label, "label_name": label_name(label), "critical": label in RESCUE_CRITICAL,
                "latency_ms": fr.get("latency_ms"), "cost_usd": fr.get("cost_usd"),
                "model": fr.get("model") or frontier_name(), "in_tok": fr.get("in_tok"), "out_tok": fr.get("out_tok")}
    return {"ours": ours, "frontier": frontier}


@app.get("/api/live/social")
def live_social():
    """The social/news ingest window: items (scrubbed, newest first), source statuses, model status."""
    return ingest.snapshot()


@app.get("/api/queue")
def queue_list():
    return {"items": store.list_items()}


@app.post("/api/queue")
def queue_add(body: QueueIn):
    text = _need_text(body.text)
    if body.label is not None and body.label not in LABELS:
        raise HTTPException(422, f"label must be one of {', '.join(LABELS)}")
    known = {e["id"] for e in events()} | set(EVENT_INFO)
    if body.event is not None and body.event not in known:
        raise HTTPException(422, f"event must be one of {', '.join(sorted(known))} (or null)")
    red, _ = scrub.scrub(text)
    post_id = str(body.post_id) if body.post_id not in (None, "") else (
        "live-" + hashlib.sha1(text.encode("utf-8", "surrogatepass")).hexdigest()[:16])
    place = body.place.model_dump() if body.place else geo.locate(red, body.event)
    return store.add(post_id, red, body.label, body.event, place)


@app.patch("/api/queue/{qid}")
def queue_patch(body: QueuePatch, qid: int = PathParam(..., ge=1, le=2 ** 63 - 1)):
    if body.status is None and body.note is None:
        raise HTTPException(422, "send status and/or note")
    item = store.update(qid, body.status, body.note)
    if item is None:
        raise HTTPException(404, f"queue item {qid} not found")
    return item


@app.delete("/api/queue")
def queue_clear():
    store.clear()
    return {"ok": True}


@app.get("/api/queue.csv")
def queue_csv():
    body = store.to_csv({k: label_name(k) for k in LABELS}, RESCUE_CRITICAL)
    # UTF-8 byte-order mark first, so Excel decodes Urdu, accents and emoji instead of guessing Windows-1252
    return Response("\ufeff" + body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="rescue-radar-queue.csv"'})


@app.get("/api/results")
def results():
    try:
        data = finite_loads(RESULTS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"status": "pending"}
    except (OSError, ValueError) as e:
        return {"status": "pending", "error": f"results/metrics.json unreadable: {type(e).__name__}"}
    if not isinstance(data, dict):
        return {"status": "pending", "error": "results/metrics.json is not a JSON object"}
    return data


@app.get("/api/train_log")
def train_log():
    runs = {}
    for p in sorted(DATA.glob("train_log*.jsonl")):
        tag = p.stem[len("train_log"):].lstrip("_-") or "quick"
        # rows whose step or loss is missing or non-finite (a diverging run logs NaN) are skipped
        runs[tag] = [{k: r.get(k) for k in ("step", "loss", "secs", "at")} for r in _jsonl(p)
                     if isinstance(r, dict) and isinstance(r.get("step"), (int, float))
                     and isinstance(r.get("loss"), (int, float)) and not isinstance(r.get("loss"), bool)]
    return {"runs": runs}


class _Web(StaticFiles):
    """web/ at /, but a clean 404 (not a crash) while the console has not been built yet."""

    async def check_config(self):
        if not WEB.is_dir():
            raise HTTPException(404, "The dispatch console (web/) is not built yet. The API is at /api/*.")
        await super().check_config()


if DOCS_DATA.is_dir():
    # The console's static fallback reads ./data: serve the current export (docs/data), not web/data's dev fixtures.
    app.mount("/data", StaticFiles(directory=DOCS_DATA), name="recorded")
app.mount("/", _Web(directory=WEB, html=True, check_dir=False), name="web")


def main():
    import uvicorn
    uvicorn.run(app, host=os.environ.get("RR_HOST", "127.0.0.1"), port=int(os.environ.get("RR_PORT", "8787")))


if __name__ == "__main__":
    main()
