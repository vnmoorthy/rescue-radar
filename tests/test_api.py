"""API tests: every endpoint in guide/API.md, with the live models replaced by fakes (no network, no keys)."""
import csv
import io
import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["RR_WARM"] = "0"
os.environ["RR_SCRUBBER"] = "regex"  # fast and deterministic; Presidio is exercised by the live server

from fastapi.testclient import TestClient  # noqa: E402

from rr import geo, scrub, server, store  # noqa: E402
from rr.labels import LABELS, RESCUE_CRITICAL  # noqa: E402

if server._frontier is not None:  # no live Claude probe from the tests (rr.frontier probes on first frontier_name())
    with server._frontier._lock:
        server._frontier._state["probed"] = True


class FakeClassifier:
    name, kind = "Fake Rescue Radar", "finetuned"

    def __init__(self):
        self.calls = 0

    def classify(self, texts):
        self.calls += 1
        return [{"label": "requests_or_urgent_needs" if "trapped" in t.lower() else "other_relevant_information",
                 "latency_ms": 12.5, "raw": "x"} for t in texts]


def fake_frontier(text):
    return {"label": "caution_and_advice", "latency_ms": 900.0, "in_tok": 1800, "out_tok": 9,
            "cost_usd": (1800 * 5 + 9 * 25) / 1e6, "model": "Fake Frontier"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_STATE_DIR", str(tmp_path / "state"))
    fake = FakeClassifier()
    monkeypatch.setattr(server, "_classifier", lambda: fake)
    monkeypatch.setattr(server, "_frontier_classify", fake_frontier)
    c = TestClient(server.app)
    c.fake = fake
    return c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert {"name", "kind", "ready"} <= set(d["model"]) and {"name", "ready"} <= set(d["frontier"])
    assert d["scrubber"] in ("presidio", "regex")


def test_meta(client):
    d = client.get("/api/meta").json()
    assert d["static"] is False
    assert len(d["labels"]) == 10
    assert {x["id"] for x in d["labels"] if x["critical"]} == RESCUE_CRITICAL
    assert all({"id", "name", "definition", "critical"} <= set(x) for x in d["labels"])
    ids = [e["id"] for e in d["events"]]
    assert set(ids) == {"hurricane_dorian_2019", "cyclone_idai_2019", "pakistan_earthquake_2019",
                        "midwestern_us_floods_2019"}
    rows = [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]
    assert sum(e["n_posts"] for e in d["events"]) == len(rows)
    for e in d["events"]:
        assert {"id", "name", "type", "year", "country", "center", "zoom", "n_posts", "n_critical"} <= set(e)
        assert e["n_critical"] == sum(r["event"] == e["id"] and r["label"] in RESCUE_CRITICAL for r in rows)
        assert len(e["center"]) == 2
    assert {"name", "kind"} <= set(d["model"]) and "name" in d["frontier"]


def test_replay(client):
    d = client.get("/api/replay/midwestern_us_floods_2019").json()
    posts = d["posts"]
    assert d["event"]["id"] == "midwestern_us_floods_2019" and len(posts) == d["event"]["n_posts"]
    assert [p["ts"] for p in posts] == sorted(p["ts"] for p in posts)
    keys = {"id", "ts", "text", "place", "truth", "truth_critical", "ours", "frontier"}
    assert all(keys <= set(p) for p in posts)
    assert posts[0]["ts"] == (int(posts[0]["id"]) >> 22) + 1288834974657
    assert not any(re.search(r"(?<![\w@])@\w", p["text"]) for p in posts)  # handles are redacted
    assert any(p["place"] for p in posts)
    for p in posts:
        if p["place"]:
            assert {"name", "lat", "lng"} <= set(p["place"])
    front = server.preds("opus_few")
    with_front = [p for p in posts if p["frontier"]]
    if front:
        assert with_front
        p = with_front[0]
        row = front[p["id"]]
        if "in_tok" in row:
            want = (row["in_tok"] * server.PRICE_IN + row["out_tok"] * server.PRICE_OUT) / 1e6  # rr.frontier prices
            assert p["frontier"]["cost_usd"] == pytest.approx(want)
        assert p["frontier"]["critical"] == (p["frontier"]["label"] in RESCUE_CRITICAL)
    assert d["systems"]["ours"] == server.ours_system()
    if not server.preds(server.ours_system()):
        assert all(p["ours"] is None for p in posts)
    assert not any("&amp;" in p["text"] for p in posts)  # HTML entities decoded
    assert client.get("/api/replay/nope").status_code == 404


def test_classify(client):
    r = client.post("/api/classify", json={"text": "Family trapped on roof in Marsh Harbour, call 242-555-0199"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert {"label", "label_name", "critical", "latency_ms", "model", "redacted_text", "redactions", "place"} <= set(d)
    assert d["label"] == "requests_or_urgent_needs" and d["critical"] is True
    assert d["label_name"] == "Requests or urgent needs" and d["model"] == "Fake Rescue Radar"
    assert "[PHONE]" in d["redacted_text"] and "555-0199" not in d["redacted_text"]
    red = d["redactions"][0]
    assert red["type"] == "PHONE" and d["redacted_text"][red["start"]:red["end"]] == "[PHONE]"
    assert d["place"]["name"] == "Marsh Harbour"
    assert client.post("/api/classify", json={"text": "  "}).status_code == 422
    assert client.post("/api/classify", json={}).status_code == 422


def test_classify_unavailable(client, monkeypatch):
    def boom():
        raise RuntimeError("FIREWORKS_API_KEY is not set, so the Rescue Radar model is unavailable.")
    monkeypatch.setattr(server, "_classifier", boom)
    r = client.post("/api/classify", json={"text": "help"})
    assert r.status_code == 503 and "FIREWORKS_API_KEY" in r.json()["detail"]
    r = client.post("/api/compare", json={"text": "help"})
    assert r.status_code == 503 and "Rescue Radar" in r.json()["detail"]


def test_classify_batch(client):
    texts = ["trapped in Beira", "Thoughts and prayers", "Email me at a.b@example.com"]
    d = client.post("/api/classify_batch", json={"texts": texts}).json()
    assert len(d["results"]) == 3 and "total_ms" in d
    assert d["results"][0]["critical"] and d["results"][0]["place"]["name"] == "Beira"
    assert d["results"][1]["place"] is None
    assert "[EMAIL]" in d["results"][2]["redacted_text"]
    assert client.fake.calls == 1
    assert client.post("/api/classify_batch", json={"texts": ["x"] * 201}).status_code == 422
    assert client.post("/api/classify_batch", json={"texts": []}).json() == {"results": [], "total_ms": 0.0}


def test_compare(client, monkeypatch):
    d = client.post("/api/compare", json={"text": "People trapped in Chimanimani"}).json()
    assert d["ours"]["label"] == "requests_or_urgent_needs" and d["ours"]["place"]["name"] == "Chimanimani"
    f = d["frontier"]
    assert {"label", "label_name", "critical", "latency_ms", "cost_usd", "model"} <= set(f)
    assert f["label_name"] == "Caution and advice" and f["critical"] is False
    assert f["cost_usd"] == pytest.approx((1800 * 5 + 9 * 25) / 1e6)

    def no_key(text):
        raise RuntimeError("ANTHROPIC_API_KEY is not set, so the frontier comparison is unavailable.")
    monkeypatch.setattr(server, "_frontier_classify", no_key)
    r = client.post("/api/compare", json={"text": "x"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_queue(client):
    assert client.get("/api/queue").json() == {"items": []}
    body = {"post_id": "1168139805810728960", "text": "Trapped at 305 N Palmetto St, call @bob or 919-966-3658",
            "label": "requests_or_urgent_needs", "event": "hurricane_dorian_2019",
            "place": {"name": "Freeport", "lat": 26.533, "lng": -78.696}}
    a = client.post("/api/queue", json=body).json()
    assert a["status"] == "open" and a["note"] == "" and a["place"]["name"] == "Freeport"
    assert "[ADDRESS]" in a["text"] and "[HANDLE]" in a["text"] and "[PHONE]" in a["text"]
    assert {"qid", "post_id", "text", "label", "event", "place", "status", "note", "created_at",
            "updated_at"} <= set(a)
    again = client.post("/api/queue", json=body).json()
    assert again["qid"] == a["qid"]  # idempotent on post_id
    b = client.post("/api/queue", json={"post_id": 42, "text": "Missing child in Mirpur", "label":
                                        "missing_or_found_people", "event": "pakistan_earthquake_2019"}).json()
    assert b["place"]["name"] == "Mirpur" and b["post_id"] == "42"
    live = client.post("/api/queue", json={"text": "typed live", "label": "requests_or_urgent_needs"}).json()
    assert live["post_id"].startswith("live-") and live["place"] is None
    items = client.get("/api/queue").json()["items"]
    assert [i["qid"] for i in items] == [live["qid"], b["qid"], a["qid"]]  # newest first

    p = client.patch(f"/api/queue/{a['qid']}", json={"status": "dispatched", "note": "Team 4"}).json()
    assert p["status"] == "dispatched" and p["note"] == "Team 4"
    p = client.patch(f"/api/queue/{a['qid']}", json={"status": "resolved"}).json()
    assert p["status"] == "resolved" and p["note"] == "Team 4"
    assert client.patch(f"/api/queue/{a['qid']}", json={"status": "bogus"}).status_code == 422
    assert client.patch(f"/api/queue/{a['qid']}", json={}).status_code == 422
    assert client.patch("/api/queue/99999", json={"status": "open"}).status_code == 404
    assert client.post("/api/queue", json={"post_id": "x", "text": "t", "label": "nope"}).status_code == 422

    r = client.get("/api/queue.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert r.content.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM so Excel does not guess Windows-1252
    rows = list(csv.DictReader(io.StringIO(r.text.lstrip("\ufeff"))))
    assert len(rows) == 3 and {"qid", "status", "text", "label_name", "place", "lat", "lng"} <= set(rows[0])

    assert client.delete("/api/queue").json() == {"ok": True}
    assert client.get("/api/queue").json() == {"items": []}


def test_results(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS", tmp_path / "metrics.json")
    assert client.get("/api/results").json() == {"status": "pending"}
    (tmp_path / "metrics.json").write_text(json.dumps({"systems": {"rescue_radar": {"accuracy": None}}}))
    assert client.get("/api/results").json() == {"systems": {"rescue_radar": {"accuracy": None}}}


def test_train_log(client):
    runs = client.get("/api/train_log").json()["runs"]
    for p in (ROOT / "data").glob("train_log*.jsonl"):
        tag = p.stem[len("train_log"):].lstrip("_-") or "quick"
        assert tag in runs
    if (ROOT / "data" / "train_log.jsonl").exists():
        assert runs["quick"] and {"step", "loss", "secs", "at"} == set(runs["quick"][0])


def test_console_mount(client):
    r = client.get("/")
    if (ROOT / "web" / "index.html").exists():
        assert r.status_code == 200 and "html" in r.headers["content-type"]
    else:
        assert r.status_code == 404
    assert client.get("/api/does-not-exist").status_code == 404


def test_geo():
    rows = [json.loads(l) for l in open(ROOT / "data" / "eval.jsonl")]
    named = set()
    for r in rows:
        named |= {geo.PLACES[i][0] for i, _, _ in geo.find_places(r["text"], r["event"])}
    assert len(named) >= 60
    assert geo.locate("Thoughts and prayers to everyone") is None
    assert geo.locate("") is None
    assert geo.locate("Earthquake hits Azad Kashmir")["name"] == "Azad Kashmir"  # longest match beats Kashmir
    assert geo.locate("#MirpurAzadKashmir needs help")["name"] == "Mirpur"
    assert geo.locate("water rising on the Missouri River")["name"] == "Missouri River"
    assert geo.locate("flooding in NEBRASKA", "midwestern_us_floods_2019")["name"] == "Nebraska"
    assert geo.locate("Nebraska", "cyclone_idai_2019") is None  # event-scoped
    assert geo.locate("Nebraskan") is None  # word boundary


def test_scrub_regex():
    text = "Call +1 (242) 555-0100, mail jo@x.org, ping @jo_x, see https://t.co/abc. 7800 Indrio Rd. In 2019-2020."
    red, reds = scrub.scrub(text)
    assert {x["type"] for x in reds} == {"PHONE", "EMAIL", "HANDLE", "URL", "ADDRESS"}
    assert "2019-2020" in red and "555-0100" not in red and "@jo_x" not in red
    for x in reds:
        assert red[x["start"]:x["end"]] == f"[{x['type']}]"
    assert scrub.scrub("[PHONE] stays")[0] == "[PHONE] stays"


def test_store_rejects_bad_status(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_STATE_DIR", str(tmp_path))
    it = store.add("p1", "t")
    with pytest.raises(ValueError):
        store.update(it["qid"], "lost")


def test_export_static(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import export_static
    export_static.export(tmp_path)
    meta = json.loads((tmp_path / "data" / "meta.json").read_text())
    assert meta["static"] is True
    for ev in meta["events"]:
        rp = json.loads((tmp_path / "data" / "replay" / f"{ev['id']}.json").read_text())
        assert len(rp["posts"]) == ev["n_posts"]
    assert "runs" in json.loads((tmp_path / "data" / "train_log.json").read_text())
    assert json.loads((tmp_path / "data" / "results.json").read_text())
    assert not (tmp_path / "deck").exists()
    if (ROOT / "web" / "index.html").exists():
        assert (tmp_path / "index.html").exists()


def test_queue_validation(client):
    nan = '{"post_id":"nan-1","text":"nan place","label":"requests_or_urgent_needs","place":{"name":"X","lat":NaN,"lng":Infinity}}'
    r = client.post("/api/queue", content=nan, headers={"content-type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    assert client.get("/api/queue").status_code == 200
    for bad in ({}, {"text": "   "}, {"post_id": True, "text": "bool id"}, {"text": "x", "event": "made_up_event"},
                {"text": "x", "post_id": "p" * 201}, {"text": "x", "place": {"name": "X", "lat": 91, "lng": 0}}):
        r = client.post("/api/queue", json=bad)
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), bad
    ok = client.post("/api/queue", json={"text": "ok", "place": {"name": "Freeport", "lat": 26.533, "lng": -78.696}})
    assert ok.status_code == 200 and ok.json()["place"]["lat"] == 26.533
    # a surrogate half of an emoji, and over-long input: 422 with a short str detail, never an echo or a 500
    r = client.post("/api/queue", content='{"text":"Trapped near Beira \\ud83d help"}', headers={"content-type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)
    r = client.post("/api/classify", json={"text": "x" * 5001})
    assert r.status_code == 422 and len(r.text) < 300 and "xxxx" not in r.text
    assert client.post("/api/classify", json={}).json()["detail"] == "text: Field required"
    for qid in ("9223372036854775808", "99999999999999999999", "-9223372036854775809", "0", "abc"):
        r = client.patch(f"/api/queue/{qid}", json={"status": "open"})
        assert r.status_code == 422 and isinstance(r.json()["detail"], str), qid
    assert client.patch("/api/queue/9223372036854775807", json={"status": "open"}).status_code == 404


def test_non_finite_data_files(client, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "RESULTS", tmp_path / "metrics.json")
    (tmp_path / "metrics.json").write_text('{"systems": {"x": {"accuracy": NaN, "macro_f1": 1e400}}}')
    assert client.get("/api/results").json() == {"systems": {"x": {"accuracy": None, "macro_f1": None}}}
    d = tmp_path / "data"
    d.mkdir()
    (d / "train_log_full.jsonl").write_text('{"step": 1, "loss": NaN, "secs": 1, "at": "x"}\n'
                                             '{"step": 2, "loss": 3.5, "secs": Infinity, "at": "y"}\n')
    monkeypatch.setattr(server, "DATA", d)
    r = client.get("/api/train_log")
    assert r.status_code == 200 and r.json()["runs"]["full"] == [{"step": 2, "loss": 3.5, "secs": None, "at": "y"}]


def test_ours_system_ignores_partial_runs(monkeypatch, tmp_path):
    d = tmp_path / "data"
    (d / "preds").mkdir(parents=True)
    rows = [{"id": str(i), "event": "e", "text": "t", "label": "other_relevant_information"} for i in range(5)]
    (d / "eval.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    pred = lambda rs: "".join(json.dumps({"id": r["id"], "pred": "other_relevant_information"}) + "\n" for r in rs)
    (d / "preds" / "rescue_radar_quick.jsonl").write_text(pred(rows))
    (d / "preds" / "rescue_radar_quick.meta.json").write_text("{}")
    monkeypatch.setattr(server, "DATA", d)
    (d / "preds" / "rescue_radar.jsonl").write_text(pred(rows[:2]))  # run_model's first chunk, no .meta.json yet
    assert server.ours_system() == "rescue_radar_quick"
    (d / "preds" / "rescue_radar.jsonl").write_text(pred(rows))  # every eval post answered
    assert server.ours_system() == "rescue_radar"


def test_live_model_is_the_scored_checkpoint(monkeypatch, tmp_path):
    d = tmp_path / "data"
    (d / "preds").mkdir(parents=True)
    (d / "eval.jsonl").write_text(json.dumps({"id": "1", "event": "e", "text": "t", "label": "x"}) + "\n")
    (d / "preds" / "rescue_radar_quick.jsonl").write_text(json.dumps({"id": "1", "pred": "x"}) + "\n")
    (d / "preds" / "rescue_radar_quick.meta.json").write_text(json.dumps(
        {"model": "base/m", "checkpoint": {"step": 123, "path": "acct/run/rr-s0123-x"}, "name": "RR (step 123)"}))
    monkeypatch.setattr(server, "DATA", d)
    monkeypatch.delenv("RR_LIVE_MODEL", raising=False)
    t = server.live_target()
    assert t["path"] == "acct/run/rr-s0123-x" and t["system"] == "rescue_radar_quick" and t["step"] == 123
    m = server.model_info()
    assert m["scored"] is True and m["name"] == "RR (step 123)" and m["step"] == 123
    monkeypatch.setenv("RR_LIVE_MODEL", "latest")
    assert server.live_target() is None and server.model_info()["scored"] is False


def test_person_filter_keeps_people_with_storm_first_names():
    def person(text, span):
        s = text.index(span)
        return scrub._person_ok(text, s, s + len(span))
    assert person("My brother Michael Brown is trapped on the roof, please help", "Michael Brown")
    assert person("Andrew and Florence Smith are missing near Freeport", "Florence Smith")
    assert person("Andrew and Florence Smith are missing near Freeport", "Andrew")
    assert person("Call Maria at 242-555-0187", "Maria")
    assert person("Still recovering from Hurricane Maria in Puerto Rico", "Hurricane Maria") is None
    assert person("Still recovering from Hurricane Maria in Puerto Rico", "Maria") is None
    assert person("Cyclone Kenneth makes landfall", "Kenneth") is None
    assert person("Dorian is now a category 5", "Dorian") is None


def test_triage_add_to_queue_payload(client):
    """QA r1 blocker: the Triage view's 'Add to queue' must send a payload POST /api/queue accepts (event null)."""
    src = (ROOT / "web" / "views" / "triage.js").read_text()
    assert "event: 'triage'" not in src and "event: null" in src
    body = {"post_id": "triage-abc123", "text": "We are trapped in the attic", "label": "requests_or_urgent_needs",
            "event": None, "place": None}
    r = client.post("/api/queue", json=body)
    assert r.status_code == 200, r.text
    assert any(i["post_id"] == "triage-abc123" for i in client.get("/api/queue").json()["items"])
    assert client.post("/api/queue", json={**body, "post_id": "triage-x", "event": "triage"}).status_code == 422
