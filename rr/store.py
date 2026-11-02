"""Dispatcher priority queue: SQLite in state/queue.db (state/ is git-ignored; data/ stays read-only).

RR_STATE_DIR overrides the folder (the tests point it at a temp dir).
"""
import csv
import io
import json
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUSES = ("open", "dispatched", "resolved", "dismissed")
COLUMNS = ("qid", "post_id", "text", "label", "event", "place", "status", "note", "created_at", "updated_at")
_lock = threading.Lock()
_ready = set()


def db_path():
    return Path(os.environ.get("RR_STATE_DIR") or ROOT / "state") / "queue.db"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _conn():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    if str(path) not in _ready:
        con.execute("""CREATE TABLE IF NOT EXISTS queue (
            qid INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id TEXT NOT NULL UNIQUE,
            text TEXT NOT NULL DEFAULT '',
            label TEXT,
            event TEXT,
            place TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL)""")
        con.commit()
        _ready.add(str(path))
    return con


@contextmanager
def _db():
    con = _conn()
    try:
        with con:
            yield con
    finally:
        con.close()


def _finite(x):
    f = float(x)
    return f if math.isfinite(f) else None


def _place(raw):
    """Stored place JSON -> {"name","lat","lng"} or None. Rows written before validation existed may hold NaN or
    Infinity, which Starlette refuses to send; such a place is dropped instead of breaking GET /api/queue."""
    try:
        p = json.loads(raw, parse_constant=lambda _c: None, parse_float=_finite) if raw else None
    except ValueError:
        return None
    if not isinstance(p, dict):
        return None
    lat, lng = p.get("lat"), p.get("lng")
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lng)):
        return None
    return p


def _item(row):
    if row is None:
        return None
    d = dict(row)
    d["place"] = _place(d["place"])
    return d


def list_items():
    """Newest first."""
    with _lock, _db() as con:
        rows = con.execute("SELECT * FROM queue ORDER BY created_at DESC, qid DESC").fetchall()
    return [_item(r) for r in rows]


def get(qid):
    with _lock, _db() as con:
        return _item(con.execute("SELECT * FROM queue WHERE qid = ?", (qid,)).fetchone())


def add(post_id, text, label=None, event=None, place=None):
    """Insert a post; idempotent on post_id (a repeat returns the existing item unchanged)."""
    now = _now()
    with _lock, _db() as con:
        con.execute("INSERT OR IGNORE INTO queue (post_id, text, label, event, place, status, note, created_at, "
                    "updated_at) VALUES (?, ?, ?, ?, ?, 'open', '', ?, ?)",
                    (str(post_id), text or "", label, event, json.dumps(place) if place else None, now, now))
        row = con.execute("SELECT * FROM queue WHERE post_id = ?", (str(post_id),)).fetchone()
    return _item(row)


def update(qid, status=None, note=None):
    """Change status and/or note. Returns the item, or None if qid does not exist."""
    if status is not None and status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(STATUSES)}")
    if not isinstance(qid, int) or not -2 ** 63 <= qid < 2 ** 63:  # outside SQLite INTEGER: cannot exist
        return None
    with _lock, _db() as con:
        row = con.execute("SELECT * FROM queue WHERE qid = ?", (qid,)).fetchone()
        if row is None:
            return None
        con.execute("UPDATE queue SET status = ?, note = ?, updated_at = ? WHERE qid = ?",
                    (status if status is not None else row["status"], note if note is not None else row["note"],
                     _now(), qid))
        return _item(con.execute("SELECT * FROM queue WHERE qid = ?", (qid,)).fetchone())


def clear():
    with _lock, _db() as con:
        con.execute("DELETE FROM queue")


def _cell(v):
    """Neutralise spreadsheet formula injection in exported text."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v  # numbers (negative lat/lng) cannot carry a formula; keep them numeric
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(label_names=None, critical=frozenset()):
    label_names = label_names or {}
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["qid", "post_id", "event", "label", "label_name", "critical", "status", "note", "place", "lat", "lng",
                "text", "created_at", "updated_at"])
    for it in list_items():
        p = it.get("place") or {}
        w.writerow([_cell(x) for x in (it["qid"], it["post_id"], it["event"], it["label"],
                                       label_names.get(it["label"], ""), it["label"] in critical, it["status"],
                                       it["note"], p.get("name"), p.get("lat"), p.get("lng"), it["text"],
                                       it["created_at"], it["updated_at"])])
    return buf.getvalue()
