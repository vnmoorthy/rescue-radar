"""scripts/render_docs.py: helpers never crash on missing values, and templates render without metrics."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("render_docs", ROOT / "scripts" / "render_docs.py")
rd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rd)


def test_helpers_format_numbers():
    assert rd.pct(0.8123) == "81.2%"
    assert rd.pts(0.123) == "+12.3 pts"
    assert rd.pts(-0.05) == "-5.0 pts"
    assert rd.pval(1e-20) == "p < 0.001"
    assert rd.pval(0.0123) == "p = 0.012"
    assert rd.num(3001) == "3,001"
    assert rd.usd(120) == "$120"
    assert rd.ms(312.4) == "312 ms"
    assert rd.ci([0.79, 0.83]) == "79.0% to 83.0%"
    assert rd.ci_side([0.01, 0.05]) == "above"
    assert rd.ci_side([-0.02, 0.05]) == "spans"


def test_helpers_return_na_for_missing():
    missing = rd.make_env().undefined(name="missing")
    for fn in (rd.pct, rd.pts, rd.usd, rd.ms, rd.pval, rd.num, rd.ci, rd.ci_pts):
        assert fn(None) == "n/a"
        assert fn(missing) == "n/a"
        assert fn("not a number") == "n/a"
    assert rd.ratio(None, 2) == "n/a"
    assert rd.label_name("requests_or_urgent_needs") == "Requests or urgent needs"
    assert rd.event_name("midwestern_us_floods_2019") == "Midwestern US Floods (2019)"


def test_templates_render_without_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr(rd, "METRICS", tmp_path / "missing.json")
    warnings = []
    ctx = rd.build_context(warn=warnings.append)
    assert ctx["m"] == {} and warnings
    env = rd.make_env()
    templates = rd.find_templates()
    assert any(t.name == "README.template.md" for t in templates)
    for tpl in templates:
        text = rd.render_one(env, tpl, ctx)
        assert text.strip()


def test_templates_render_with_partial_metrics(monkeypatch, tmp_path):
    partial = {"eval": {"n": 10}, "systems": {"opus_few": {"name": "Claude", "macro_f1": 0.5}},
               "comparisons": [], "headline": {"ours": None, "frontier": "opus_few"}}
    p = tmp_path / "metrics.json"
    p.write_text(json.dumps(partial))
    monkeypatch.setattr(rd, "METRICS", p)
    ctx = rd.build_context(warn=lambda msg: None)
    env = rd.make_env()
    readme = next(t for t in rd.find_templates() if t.name == "README.template.md")
    text = rd.render_one(env, readme, ctx)
    assert "50.0%" in text and "n/a" in text
