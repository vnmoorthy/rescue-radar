"""Live social and news ingestion for the Live city view (San Francisco).

rr.server starts one worker thread from its lifespan unless RR_INGEST=0. Each cycle polls public
sources, publishes new items (PII-scrubbed) to a rolling window the console reads at
GET /api/live/social, classifies them with the live Rescue Radar model, and pushes
rescue-critical ones into the dispatch queue (rr.store), where the triage workflow picks them up.

Sources:
  reddit  new posts from r/sanfrancisco + r/bayarea through Reddit's free OAuth API. Needs a
          "script" app's REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET (reddit.com/prefs/apps) in .env;
          until those exist the source idles and its status says what it needs. (Reddit's keyless
          .json endpoints return 403 to non-browser/datacenter traffic, so there is no keyless path.)
  news    San Francisco news RSS: SF Standard, SFist, KRON4, SFGate Bay Area. Keyless.

Items are published as soon as they arrive (label null, shown as pending) and labeled in place a
moment later, so a model outage shows content plus an honest model status instead of an empty
panel; raw unscrubbed text stays in memory only. Env: RR_INGEST=0 disables the worker,
RR_INGEST_INTERVAL seconds between cycles (default 120; news feeds re-fetch at most every 5 min).
Seen-ids and the published window persist in RR_STATE_DIR (default state/), so a restart neither
re-classifies nor blanks the panel.
"""
import hashlib
import html
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

from rr import env, scrub, store
from rr.labels import LABELS, RESCUE_CRITICAL

ROOT = Path(__file__).resolve().parent.parent
UA = "rescue-radar/1.0 (hackathon demo, live SF triage; github.com/vnmoorthy/rescue-radar)"
MAX_ITEMS = 300      # rolling window served to the console
MAX_CLASSIFY = 40    # items classified per cycle (bounds model cost on a cold start)
MAX_PENDING = 200    # unclassified backlog kept for retry
MAX_SEEN = 8000      # dedupe memory
TEXT_LIMIT = 1500
NEWS_EVERY = 300.0   # seconds between news-feed fetches (feeds update far slower than this)
WINDOW_MS = 48 * 3600 * 1000

NEWS_FEEDS = (
    ("SF Standard", "https://sfstandard.com/feed/"),
    ("SFist", "https://sfist.com/feed/"),
    ("KRON4", "https://www.kron4.com/feed/"),
    ("SFGate Bay Area", "https://www.sfgate.com/bayarea/feed/Bay-Area-News-429.php"),
)
SUBREDDITS = "sanfrancisco+bayarea"


def _now_ms():
    return int(time.time() * 1000)


def _state_path():
    return Path(os.environ.get("RR_STATE_DIR") or ROOT / "state") / "ingest_state.json"


def label_name(label):
    return label.replace("_", " ").capitalize() if label else None


# ---------------------------------------------------------------- feed parsing
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s):
    """Markup to plain text: tags out, entities decoded, whitespace collapsed."""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s or "")
    s = _TAG_RE.sub(" ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _child_text(el, *names):
    for ch in el:
        if _local(ch.tag) in names and (ch.text or "").strip():
            return ch.text.strip()
    return ""


def _entry_link(el):
    fallback = ""
    for ch in el:
        if _local(ch.tag) == "link":
            href = (ch.get("href") or "").strip() or (ch.text or "").strip()
            if href and (ch.get("rel") or "alternate") == "alternate":
                return href  # RSS <link>text</link>, or the Atom alternate link
            fallback = fallback or href
    return fallback


def _parse_ts(s):
    if not s:
        return None
    try:
        return int(parsedate_to_datetime(s).timestamp() * 1000)  # RFC 822 (RSS pubDate)
    except (TypeError, ValueError):
        pass
    try:
        return int(datetime.fromisoformat(s.strip().replace("Z", "+00:00")).timestamp() * 1000)  # Atom
    except ValueError:
        return None


def parse_feed(xml_text, feed_label):
    """RSS 2.0 or Atom -> [{id, ts, title, text, url}], namespace-agnostic; entries without a title are skipped."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"{feed_label}: not valid XML ({str(e)[:80]})")
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = strip_html(_child_text(el, "title"))
        url = _entry_link(el)
        guid = _child_text(el, "guid", "id") or url or title
        if not title or not guid:
            continue
        summary = strip_html(_child_text(el, "description", "summary"))
        text = title if not summary or summary.lower().startswith(title.lower()) else f"{title} — {summary}"
        out.append({"id": "news-" + hashlib.sha1(guid.encode("utf-8", "replace")).hexdigest()[:16],
                    "ts": _parse_ts(_child_text(el, "pubdate", "published", "updated", "date")),
                    "title": title, "text": text[:TEXT_LIMIT], "url": url or None})
    return out


def fetch_news(client):
    """Every news feed once -> (items, {feed label: error})."""
    items, errors = [], {}
    for label, url in NEWS_FEEDS:
        try:
            r = client.get(url, headers={
                "User-Agent": UA,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
            r.raise_for_status()
            for it in parse_feed(r.text, label):
                it["source"], it["feed"] = "news", label
                items.append(it)
        except Exception as e:  # one dead feed must not hide the others
            errors[label] = f"{type(e).__name__}: {str(e)[:120]}"
    return items, errors


# ---------------------------------------------------------------- reddit
_reddit_tok = {"token": None, "until": 0.0}


def reddit_creds():
    return os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")


def _reddit_token(client):
    if _reddit_tok["token"] and time.time() < _reddit_tok["until"]:
        return _reddit_tok["token"]
    cid, secret = reddit_creds()
    r = client.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                    auth=(cid, secret), headers={"User-Agent": UA})
    r.raise_for_status()
    d = r.json()
    if not d.get("access_token"):
        raise RuntimeError(f"Reddit auth refused: {str(d)[:120]}")
    _reddit_tok.update(token=d["access_token"], until=time.time() + float(d.get("expires_in") or 3600) - 60)
    return _reddit_tok["token"]


def fetch_reddit(client):
    """Newest public posts from the city subreddits (NSFW skipped)."""
    r = client.get(f"https://oauth.reddit.com/r/{SUBREDDITS}/new", params={"limit": "50", "raw_json": "1"},
                   headers={"Authorization": f"bearer {_reddit_token(client)}", "User-Agent": UA})
    if r.status_code in (401, 403):
        _reddit_tok["token"] = None  # token expired or revoked: mint a fresh one next cycle
    r.raise_for_status()
    out = []
    for c in (r.json().get("data") or {}).get("children") or []:
        d = c.get("data") or {}
        title = (d.get("title") or "").strip()
        if not d.get("name") or not title or d.get("over_18"):
            continue
        body = (d.get("selftext") or "").strip()
        out.append({"id": f"reddit-{d['name']}", "source": "reddit", "feed": f"r/{d.get('subreddit') or 'reddit'}",
                    "ts": int(d["created_utc"] * 1000) if d.get("created_utc") else None,
                    "title": title, "text": (f"{title}\n\n{body}" if body else title)[:TEXT_LIMIT],
                    "url": f"https://www.reddit.com{d['permalink']}" if d.get("permalink") else None})
    return out


# ---------------------------------------------------------------- worker
class Ingest:
    """One polling worker. classify(texts) -> (model name, [{label, latency_ms, raw}, ...]) or raises."""

    def __init__(self, classify=None, interval=None):
        self.classify = classify
        self.interval = float(interval or os.environ.get("RR_INGEST_INTERVAL") or 120)
        self.lock = threading.Lock()
        self.items = {}      # id -> published (scrubbed) item
        self.pending = []    # [(id, raw text)] newest first, awaiting classification (memory only: raw PII)
        self.seen = {}       # id -> first-seen ms, includes items that left the window
        self.sources = {
            "reddit": {"id": "reddit", "label": "Reddit", "enabled": False, "ok": None, "detail": None,
                       "last_poll": None, "n": 0},
            "news": {"id": "news", "label": "SF news RSS", "enabled": True, "ok": None, "detail": None,
                     "last_poll": None, "n": 0},
        }
        self.model = None
        self.model_error = None
        self.cycle_error = None
        self._stop = threading.Event()
        self._thread = None
        self._last_news = 0.0
        self._load_state()

    # ----- state
    def _load_state(self):
        try:
            d = json.loads(_state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(d, dict):
            seen = d.get("seen")
            if isinstance(seen, dict):
                self.seen = {str(k): v for k, v in seen.items() if isinstance(v, (int, float))}
            items = d.get("items")
            if isinstance(items, list):
                self.items = {it["id"]: it for it in items if isinstance(it, dict) and it.get("id")}
                # items the last run never labeled go back on the classify queue (scrubbed text: raw is gone)
                self.pending = [(it["id"], it.get("text") or "") for it in self.items.values()
                                if it.get("label") is None and it.get("text")]

    def _save_state(self):
        try:
            path = _state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            with self.lock:
                body = json.dumps({"seen": self.seen, "items": list(self.items.values())})
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(path)
        except OSError:
            pass

    # ----- lifecycle
    def start(self):
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="rr-ingest", daemon=True)
            self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    def _run(self):
        import httpx
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            while not self._stop.is_set():
                try:
                    self.cycle_error = None
                    self._cycle(client)
                except Exception as e:  # a bad cycle must never kill the worker
                    self.cycle_error = f"{type(e).__name__}: {str(e)[:200]}"
                self._stop.wait(self.interval)

    # ----- one cycle
    def _cycle(self, client):
        env.load_env()  # creds added to .env while the server runs are picked up without a restart
        now = _now_ms()
        fresh = []

        rs = self.sources["reddit"]
        cid, secret = reddit_creds()
        if not (cid and secret):
            rs.update(enabled=False, ok=None, detail="needs REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in .env "
                                                     "(free script app: reddit.com/prefs/apps)")
        else:
            rs.update(enabled=True, label=f"Reddit (r/{SUBREDDITS})")
            try:
                got = fetch_reddit(client)
                rs.update(ok=True, detail=None, last_poll=now, n=len(got))
                fresh.extend(got)
            except Exception as e:
                rs.update(ok=False, detail=f"{type(e).__name__}: {str(e)[:120]}", last_poll=now)

        ns = self.sources["news"]
        if time.time() - self._last_news >= NEWS_EVERY:
            self._last_news = time.time()
            got, errors = fetch_news(client)
            ns.update(ok=len(errors) < len(NEWS_FEEDS), last_poll=now, n=len(got),
                      detail="; ".join(f"{k}: {v}" for k, v in errors.items()) or None)
            fresh.extend(got)

        self._intake(fresh, now)
        self._classify_pending()
        self._save_state()

    def _intake(self, fresh, now):
        """Dedupe, scrub, publish (label null until classified), and remember raw text for the classifier."""
        new = [it for it in fresh if it["id"] not in self.seen]
        if not new:
            self._prune(now)
            return
        new.sort(key=lambda it: it.get("ts") or 0)
        scrubbed = scrub.scrub_many([it["text"] for it in new])
        with self.lock:
            for it, (red, reds) in zip(new, scrubbed):
                self.seen[it["id"]] = now
                self.items[it["id"]] = {
                    "id": it["id"], "source": it["source"], "feed": it.get("feed"),
                    "ts": it.get("ts") or now, "first_seen": now, "url": it.get("url"),
                    "text": red, "redactions": reds, "label": None, "label_name": None,
                    "critical": False, "latency_ms": None, "model": None, "queued": False,
                }
                self.pending.insert(0, (it["id"], it["text"]))
            del self.pending[MAX_PENDING:]
        self._prune(now)

    def _prune(self, now):
        with self.lock:
            keep = sorted(self.items.values(), key=lambda x: x["ts"], reverse=True)
            # the window counts from ingestion, not the published date: a feed that back-dates
            # entries (or a long first backfill) must not have them vanish before anyone sees them
            keep = [x for x in keep if now - (x.get("first_seen") or x["ts"]) <= WINDOW_MS][:MAX_ITEMS]
            self.items = {x["id"]: x for x in keep}
            if len(self.seen) > MAX_SEEN:
                for k in sorted(self.seen, key=self.seen.get)[:len(self.seen) - MAX_SEEN]:
                    del self.seen[k]

    def _classify_pending(self):
        if self.classify is None:
            self.model_error = "no classifier wired"
            return
        with self.lock:
            batch = [(i, t) for i, t in self.pending if i in self.items][:MAX_CLASSIFY]
        if not batch:
            return
        try:
            model, rows = self.classify([t for _, t in batch])
        except Exception as e:  # model down (e.g. no FIREWORKS_API_KEY): items stay pending, status says why
            self.model_error = str(getattr(e, "detail", None) or f"{type(e).__name__}: {str(e)[:200]}")
            return
        self.model, self.model_error = model, None
        done = set()
        with self.lock:
            for (iid, _), res in zip(batch, rows):
                done.add(iid)
                it = self.items.get(iid)
                if it is None:
                    continue
                label = res.get("label") if isinstance(res, dict) else None
                it.update(label=label, label_name=label_name(label), critical=label in RESCUE_CRITICAL,
                          latency_ms=res.get("latency_ms") if isinstance(res, dict) else None, model=model)
            self.pending = [(i, t) for i, t in self.pending if i not in done]
            critical = [it for it in self.items.values() if it["critical"] and not it["queued"]]
        for it in critical:  # scrubbed text only ever reaches the queue
            try:
                store.add(it["id"], it["text"], it["label"], None, None)
                with self.lock:
                    it["queued"] = True
            except Exception:
                pass  # queue db unavailable: the item still shows in the panel

    # ----- read side
    def snapshot(self):
        with self.lock:
            items = sorted(self.items.values(), key=lambda x: x["ts"], reverse=True)
            items = [{k: v for k, v in it.items() if k != "redactions"} for it in items]
            n_pending = len(self.pending)
        return {"enabled": True, "running": bool(self._thread and self._thread.is_alive()),
                "interval_s": self.interval, "model": self.model, "model_error": self.model_error,
                "cycle_error": self.cycle_error, "n_pending": n_pending,
                "sources": [dict(self.sources["reddit"]), dict(self.sources["news"])],
                "items": items, "generated_at": _now_ms()}


# ---------------------------------------------------------------- module singleton (rr.server uses this)
_worker = None


def start(classify=None):
    global _worker
    if _worker is None:
        _worker = Ingest(classify=classify).start()
    return _worker


def snapshot():
    if _worker is None:
        return {"enabled": False, "running": False, "items": [], "sources": [],
                "detail": "The ingest worker is not running (RR_INGEST=0, or the server has not started)."}
    return _worker.snapshot()


def stop():
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
