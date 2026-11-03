"""rr.ingest: feed parsing, the worker cycle (dedupe, scrub, classify, queue push), and the API endpoint.

No network: the reddit/news fetchers are monkeypatched; the classifier is a stub.
"""
import os

os.environ["RR_WARM"] = "0"
os.environ["RR_SCRUBBER"] = "regex"  # fast and deterministic (same choice as tests/test_api.py)

import pytest  # noqa: E402

from rr import ingest, store  # noqa: E402

RSS = """<?xml version="1.0"?><rss version="2.0"><channel><title>SF Standard</title>
<item><title>Fire crews battle two-alarm blaze in the Mission</title>
<link>https://example.com/fire</link><guid>ex-1</guid>
<pubDate>Mon, 02 Nov 2026 15:04:05 -0800</pubDate>
<description><![CDATA[<p>Crews &amp; engines on scene; residents <b>trapped</b> inside.</p>]]></description></item>
<item><title>Item without guid still keeps its link identity</title><link>https://example.com/2</link></item>
<item><description>no title: skipped</description></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><entry>
<title>Quake shakes East Bay</title><id>tag:example,2026:q</id>
<link rel="self" href="https://example.com/self.xml"/>
<link rel="alternate" href="https://example.com/quake"/>
<updated>2026-11-02T10:00:00Z</updated>
<summary>Minor damage reported</summary></entry></feed>"""


def test_parse_rss():
    items = ingest.parse_feed(RSS, "SF Standard")
    assert len(items) == 2  # the title-less entry is dropped
    first = items[0]
    assert first["title"] == "Fire crews battle two-alarm blaze in the Mission"
    assert "trapped inside" in first["text"] and "<" not in first["text"] and "&amp;" not in first["text"]
    assert first["url"] == "https://example.com/fire"
    assert first["ts"] is not None and first["id"].startswith("news-")
    assert items[1]["url"] == "https://example.com/2"


def test_parse_atom_prefers_alternate_link():
    items = ingest.parse_feed(ATOM, "x")
    assert len(items) == 1
    assert items[0]["url"] == "https://example.com/quake"
    assert items[0]["ts"] is not None
    assert items[0]["text"] == "Quake shakes East Bay — Minor damage reported"


def test_parse_feed_rejects_garbage():
    with pytest.raises(ValueError):
        ingest.parse_feed("this is not xml", "bad")


def test_strip_html():
    assert ingest.strip_html("<p>a &amp; b</p><script>no()</script> <b>c</b>") == "a & b c"


# ---------------------------------------------------------------- worker
def fake_classify(texts):
    rows = [{"label": "requests_or_urgent_needs" if "trapped" in t.lower() else "not_humanitarian",
             "latency_ms": 1.0, "raw": "x"} for t in texts]
    return "Rescue Radar (test)", rows


REDDIT_ITEMS = [
    {"id": "reddit-t3_a1", "source": "reddit", "feed": "r/sanfrancisco", "ts": 1700000000000,
     "title": "Neighbor trapped after the porch collapsed, fire dept not here yet",
     "text": "Neighbor trapped after the porch collapsed, fire dept not here yet", "url": "https://www.reddit.com/x"},
    {"id": "reddit-t3_a2", "source": "reddit", "feed": "r/bayarea", "ts": 1700000001000,
     "title": "Best burrito in the Mission?", "text": "Best burrito in the Mission?", "url": None},
]


@pytest.fixture
def worker(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(ingest, "fetch_reddit", lambda client: list(REDDIT_ITEMS))
    monkeypatch.setattr(ingest, "fetch_news", lambda client: ([], {}))
    return ingest.Ingest(classify=fake_classify)


def test_cycle_classifies_and_queues_critical(worker):
    worker._cycle(client=None)
    snap = worker.snapshot()
    assert snap["enabled"] and snap["model"] == "Rescue Radar (test)" and snap["model_error"] is None
    assert len(snap["items"]) == 2
    by_id = {i["id"]: i for i in snap["items"]}
    crit = by_id["reddit-t3_a1"]
    assert crit["critical"] and crit["label"] == "requests_or_urgent_needs" and crit["queued"]
    assert by_id["reddit-t3_a2"]["label"] == "not_humanitarian" and not by_id["reddit-t3_a2"]["queued"]
    assert snap["items"][0]["ts"] >= snap["items"][1]["ts"]  # newest first
    queued = store.list_items()
    assert any(q["post_id"] == "reddit-t3_a1" for q in queued)
    assert all(q["post_id"] != "reddit-t3_a2" for q in queued)


def test_cycle_dedupes_and_persists(worker, tmp_path, monkeypatch):
    worker._cycle(client=None)
    worker._cycle(client=None)  # same items again: nothing doubles, queue stays idempotent
    snap = worker.snapshot()
    assert len(snap["items"]) == 2
    assert sum(q["post_id"] == "reddit-t3_a1" for q in store.list_items()) == 1
    # a fresh worker reloads the published window and classifies nothing again
    w2 = ingest.Ingest(classify=pytest.fail)
    assert len(w2.snapshot()["items"]) == 2
    assert w2.pending == []


def test_model_down_items_pend_then_recover(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
    monkeypatch.setattr(ingest, "fetch_reddit", lambda client: list(REDDIT_ITEMS))
    monkeypatch.setattr(ingest, "fetch_news", lambda client: ([], {}))

    def boom(texts):
        raise RuntimeError("FIREWORKS_API_KEY is not set")

    w = ingest.Ingest(classify=boom)
    w._cycle(client=None)
    snap = w.snapshot()
    assert "FIREWORKS_API_KEY" in snap["model_error"]
    assert len(snap["items"]) == 2 and all(i["label"] is None for i in snap["items"])  # published, unlabeled
    assert snap["n_pending"] == 2
    w.classify = fake_classify  # the model comes back: pending items get labeled in place
    w._cycle(client=None)
    snap = w.snapshot()
    assert snap["model_error"] is None and snap["n_pending"] == 0
    assert {i["label"] for i in snap["items"]} == {"requests_or_urgent_needs", "not_humanitarian"}


def test_reddit_idles_without_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_STATE_DIR", str(tmp_path))
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(ingest, "fetch_reddit",
                        lambda client: pytest.fail("reddit must not be fetched without credentials"))
    monkeypatch.setattr(ingest, "fetch_news", lambda client: ([], {}))
    w = ingest.Ingest(classify=fake_classify)
    w._cycle(client=None)
    reddit = next(s for s in w.snapshot()["sources"] if s["id"] == "reddit")
    assert reddit["enabled"] is False and "REDDIT_CLIENT_ID" in reddit["detail"]


def test_scrub_applies_to_published_text(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "sec")
    pii = [{"id": "reddit-t3_p", "source": "reddit", "feed": "r/sanfrancisco", "ts": 1700000000000,
            "title": "t", "text": "Call me at 415-555-0100, someone is trapped", "url": None}]
    monkeypatch.setattr(ingest, "fetch_reddit", lambda client: pii)
    monkeypatch.setattr(ingest, "fetch_news", lambda client: ([], {}))
    w = ingest.Ingest(classify=fake_classify)
    w._cycle(client=None)
    item = w.snapshot()["items"][0]
    assert "415-555-0100" not in item["text"]
    q = next(q for q in store.list_items() if q["post_id"] == "reddit-t3_p")
    assert "415-555-0100" not in q["text"]  # the queue only ever sees scrubbed text


def test_endpoint_reports_disabled_without_worker():
    from fastapi.testclient import TestClient
    from rr import server
    assert ingest._worker is None  # tests never start the singleton (TestClient below skips the lifespan)
    c = TestClient(server.app)
    r = c.get("/api/live/social")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False and body["items"] == [] and "detail" in body
