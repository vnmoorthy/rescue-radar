#!/usr/bin/env python3
"""Build deck/RescueRadar.pptx: the 11-slide Rescue Radar pitch deck (native 16:9, python-pptx).

Every number is read at build time: benchmark results from results/metrics.json, the hook post and the
Hurricane Dorian slice from the static replay export (docs/data/replay/, else web/data/replay/, else
data/eval.jsonl). Anything missing renders as "n/a". Nothing is hardcoded.

Each slide gets speaker notes, a slide transition (p:transition) and staggered fade-in entrance animations
for its key shapes (p:timing, auto-starting with the slide).

Look: the dark "Sunrise" theme from guide/THEME.md (warm near-black, sunrise amber, ember for rescue-critical), the
thin amber sunrise streak as the motif (before every kicker and above the footer), Work Sans for type and JetBrains
Mono for data. A PowerPoint typeface takes one name, so every run also carries a pitch-family hint: where Work Sans
is not installed, Office falls back to Arial (Windows) or Helvetica (macOS), and Courier New for the mono face.

Run:  .venv/bin/python deck/build_pptx.py [--out deck/RescueRadar.pptx]
"""
import argparse
import json
import math
import random
import re
import sys
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NA = "n/a"
CRIT = {"requests_or_urgent_needs", "injured_or_dead_people", "missing_or_found_people"}
REPO, SITE = "github.com/vnmoorthy/rescue-radar", "vnmoorthy.github.io/rescue-radar"

# Palette: the dark "Sunrise" tokens from guide/THEME.md (alpha tokens pre-blended over --bg / --panel).
BG, BG_ELEV, PANEL, PANEL2, LINE, LINE2 = "11120F", "161713", "1B1C18", "23241F", "2C2D29", "3A3A36"
TEXT, MUTED, DIM = "F4F1EA", "B8B5AB", "8C8A81"          # --text, --text-2, --text-3
ACCENT, ACCENT2, OK = "F2A93B", "FFD27A", "7BC79A"        # sunrise amber, streak highlight, "measured"
RED, RED2, ORANGE = "FF5B3A", "FF8A4C", "FF8A4C"          # --critical (ember) and its family
CRIT_SOFT, CRIT_LINE, AMBER_SOFT, MOAT_LINE = "321C15", "702F20", "2C2414", "7B5F30"
OPUS, OPUS0, BASE = "D6D2C7", "9E9C93", "6F6D66"          # calm, desaturated comparison systems
CAT = {"requests_or_urgent_needs": "FF5B3A", "injured_or_dead_people": "FF8A4C", "missing_or_found_people": "FFB089"}
# Work Sans (JetBrains Mono for data). Fallbacks come from the pitch-family hint set in set_font():
# sans -> Arial / Helvetica, fixed -> Courier New. The theme's heading and body fonts are Work Sans too.
DISPLAY = SANS = "Work Sans"
MONO = "JetBrains Mono"
NSP = "http://schemas.openxmlformats.org/presentationml/2006/main"
ANS = "http://schemas.openxmlformats.org/drawingml/2006/main"


# ------------------------------------------------------------------------------------------ formatting
def f(x):
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def pct(x, d=1):
    v = f(x)
    if v is None:
        return NA
    from decimal import Decimal, ROUND_HALF_UP  # half-up on the decimal value, same rule as the docs and the web deck
    return f"{(Decimal(repr(v)) * 100).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP):.{d}f}%"


def pts(x, d=1):
    v = f(x)
    return NA if v is None else f"{v * 100:+.{d}f} pts"


def usd(x):
    v = f(x)
    if v is None:
        return NA
    return f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"


def ms(x):
    v = f(x)
    if v is None:
        return NA
    return f"{v:,.0f} ms" if abs(v) < 1000 else f"{v / 1000:,.2f} s"


def pval(x):
    v = f(x)
    if v is None or v < 0:
        return NA
    return "p < 0.001" if v < 0.001 else (f"p = {v:.3f}" if v < 0.1 else f"p = {v:.2f}")


def num(x):
    v = f(x)
    if v is None:
        return NA
    return f"{int(v):,}" if v.is_integer() else f"{v:,.2f}"


def ratio(a, b):
    va, vb = f(a), f(b)
    return None if va is None or vb is None or va <= 0 or vb <= 0 else va / vb


def label_name(k):
    return NA if not k else str(k).replace("_", " ").capitalize()


def g(d, *path):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


# ------------------------------------------------------------------------------------------------ data
def load_json(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def regex_scrub(t):
    t = re.sub(r"https?://\S+", "[link]", t)
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email]", t)
    t = re.sub(r"@\w{1,30}", "@[user]", t)
    t = re.sub(r"\+?\d[\d\s().-]{7,}\d", "[phone]", t)
    t = t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", t).strip()


def scrub(t):
    """PII redaction: the project's scrubber when importable, then a regex pass as a safety net."""
    try:
        from rr.scrub import scrub as rr_scrub
        r = rr_scrub(t)
        if isinstance(r, dict):
            r = r.get("redacted_text") or r.get("text") or t
        t = r if isinstance(r, str) else t
    except Exception:
        pass
    return regex_scrub(t)


def load_replay():
    for p in (ROOT / "docs/data/replay/hurricane_dorian_2019.json", ROOT / "web/data/replay/hurricane_dorian_2019.json"):
        d = load_json(p)
        if d:
            posts = d.get("posts", []) if isinstance(d, dict) else d
            return [x for x in posts if isinstance(x, dict) and x.get("text")], (d.get("event") if isinstance(d, dict) else None)
    posts = []
    try:
        with open(ROOT / "data/eval.jsonl") as fh:
            for line in fh:
                r = json.loads(line)
                if r.get("event") == "hurricane_dorian_2019":
                    posts.append({"id": r["id"], "text": r["text"], "truth": r["label"],
                                  "truth_critical": r["label"] in CRIT, "place": None, "ours": None})
    except (OSError, ValueError):
        pass
    for p in posts:
        p["ts"] = (int(p["id"]) >> 22) + 1288834974657
    return sorted(posts, key=lambda p: p["ts"]), None


HOOK_ID = "1168306378944987141"  # hand-checked: a real plea for help from Abaco during Dorian (same pin as the web deck)


def ckpt_seen(m):
    """(step, examples seen) of the scored headline checkpoint: checkpoint_step x batch from the training log."""
    try:
        key = (m.get("headline") or {}).get("ours") or "rescue_radar"
        step = int(((m.get("systems") or {}).get(key) or {}).get("checkpoint_step"))
        tag = "_full" if key == "rescue_radar" else ""
        mm = re.search(r"(\d+) examples, batch (\d+)", (ROOT / "data" / f"train{tag}.out").read_text(errors="replace")[:4096])
        return step, min(int(mm.group(1)), step * int(mm.group(2)))
    except Exception:
        return None, None


def train_examples(m):
    """Training-set size of the headline run from its training log header (data/train.out or data/train_full.out),
    falling back to metrics.json (whose hard-coded value was wrong for the small-data run)."""
    hl = (m.get("headline") or {}).get("ours") if isinstance(m, dict) else None
    tag = {"rescue_radar_quick": "", "rescue_radar": "_full"}.get(hl)
    if tag is not None:
        try:
            mm = re.search(r"(\d+) examples, batch", (ROOT / "data" / f"train{tag}.out").read_text(errors="replace")[:4096])
            if mm:
                return int(mm.group(1))
        except OSError:
            pass
    return (m.get("eval") or {}).get("train_examples") if isinstance(m, dict) else None


def pick_hook(posts):
    pinned = next((p for p in posts if str(p.get("id")) == HOOK_ID), None)
    if pinned:
        return pinned
    kw = re.compile(r"\b(help|rescue|rescued|trapped|stuck|need|needs|please|water|roof|stranded|missing|urgent|sos|boat)\b", re.I)
    best, bs = None, -1
    for p in posts:
        lab = p.get("truth")
        if not (lab in ("requests_or_urgent_needs", "missing_or_found_people") or p.get("truth_critical") is True):
            continue
        t = scrub(p["text"])
        if not 50 <= len(t) <= 170:
            continue
        s = (3 if lab == "requests_or_urgent_needs" else 1) + len(kw.findall(t))
        s -= 1 if re.search(r"\[(link|phone|email)\]", t) else 0
        s -= 2 if t.startswith("RT ") else 0
        s -= 2 if t.startswith("@") else 0
        if s > bs:
            best, bs = p, s
    return best


class Data:
    def __init__(self):
        self.m = load_json(ROOT / "results/metrics.json") or {}
        if not isinstance(self.m, dict) or self.m.get("status") == "pending":
            self.m = {}
        sysd = self.m.get("systems") if isinstance(self.m.get("systems"), dict) else {}
        hl = self.m.get("headline") if isinstance(self.m.get("headline"), dict) else {}
        self.ours_key = hl.get("ours") or "rescue_radar"
        self.front_key = hl.get("frontier") or "opus_few"
        self.systems = sysd
        self.ours = sysd.get(self.ours_key) or {}
        self.front = sysd.get(self.front_key) or {}
        self.front_name = self.front.get("name") or "Claude Opus 5.5"
        self.ev = self.m.get("eval") or {}
        self.cmp = self._comparisons()
        self.posts, self.event = load_replay()
        self.src = "ours" if any(g(p, "ours", "label") for p in self.posts) else "truth"
        self.hook = pick_hook(self.posts)
        n = f(g(self.event, "n_posts")) or (len(self.posts) or None)
        crit = sum(1 for p in self.posts if p.get("truth_critical") is True or p.get("truth") in CRIT)
        self.dorian_n = n
        self.dorian_share = crit / len(self.posts) if self.posts else None

    def _comparisons(self):
        out = {}
        comps = [c for c in (self.m.get("comparisons") or []) if isinstance(c, dict)]
        for c in comps:
            flip = c.get("a") == self.front_key and c.get("b") == self.ours_key
            if not (flip or (c.get("a") == self.ours_key and c.get("b") == self.front_key)):
                continue
            sg = -1 if flip else 1
            bs = c.get("bootstrap") or {}

            def iv(x):
                if not (isinstance(x, list) and len(x) == 2 and f(x[0]) is not None and f(x[1]) is not None):
                    return None
                return [-x[1], -x[0]] if flip else list(x)

            def dd(x):
                return None if f(x) is None else sg * f(x)

            mc = c.get("mcnemar")
            if mc and flip:
                mc = {"a_only": mc.get("b_only"), "b_only": mc.get("a_only"), "p": mc.get("p")}
            wins, n = f(bs.get("a_wins")), f(bs.get("n"))
            if flip and wins is not None and n is not None:
                wins = n - wins
            embedded = "macro_f1_delta_ci95" in bs or f(c.get("delta_macro_f1")) is not None

            def put(k, delta, ci, mcn, w):
                out.setdefault(k, {"delta": delta, "ci": ci, "mcnemar": mcn, "wins": w, "n": n, "unit": bs.get("unit")})

            put(c.get("metric") or "accuracy", dd(c.get("delta")), iv(bs.get("delta_ci95")), mc, None if embedded else wins)
            if embedded:
                put("macro_f1", dd(c.get("delta_macro_f1")), iv(bs.get("macro_f1_delta_ci95")), None, wins)
                put("critical_recall", dd(c.get("delta_critical_recall")), iv(bs.get("critical_recall_delta_ci95")), None, None)
        for k, getter in (("macro_f1", lambda s: s.get("macro_f1")), ("accuracy", lambda s: s.get("accuracy")),
                          ("critical_recall", lambda s: g(s, "critical", "recall"))):
            if k not in out and f(getter(self.ours)) is not None and f(getter(self.front)) is not None:
                out[k] = {"delta": f(getter(self.ours)) - f(getter(self.front)), "ci": None, "mcnemar": None,
                          "wins": None, "n": None, "unit": None}
        return out

    def delta(self, k):
        return g(self.cmp, k, "delta")


# --------------------------------------------------------------------------------------------- drawing
def rgb(h):
    return RGBColor.from_string(h)


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.layout = self.prs.slide_layouts[6]  # blank

    def slide(self, bg=None, footer=True):
        s = self.prs.slides.add_slide(self.layout)
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = rgb(BG)
        # Faint full-bleed background art (deck/bg/, pre-faded over BG so text stays readable); first shape = bottom.
        p = ROOT / "deck" / "bg" / f"{bg}.jpg" if bg else None
        if p and p.exists():
            s.shapes.add_picture(str(p), 0, 0, self.prs.slide_width, self.prs.slide_height)
        s._anim = []
        streak(s, 0.75, 7.04, 11.83, name="Footer streak")
        if footer:
            text(s, 0.75, 7.13, 4.0, 0.2, "RESCUE RADAR", size=9, color=MUTED, bold=True, track=2.5, name="Footer wordmark")
            text(s, 9.58, 7.13, 3.0, 0.2, "", size=9, color=DIM, font=MONO, align="r", name="Footer page")
        return s

    def finish(self):
        """Page numbers ("04 / 10") once the slide count is known."""
        total = len(self.prs.slides)
        for i, sl in enumerate(self.prs.slides, 1):
            for sh in sl.shapes:
                if sh.name == "Footer page":
                    sh.text_frame.paragraphs[0].runs[0].text = f"{i:02d} / {total:02d}"


def shape(s, kind, x, y, w, h, fill=None, line=None, lw=1.0, adj=None, name=None, anim=False):
    sh = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        sh.fill.solid()
        sh.fill.fore_color.rgb = rgb(fill)
    else:
        sh.fill.background()
    if line:
        sh.line.color.rgb = rgb(line)
        sh.line.width = Pt(lw)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    if adj is not None:
        sh.adjustments[0] = adj
    if name:
        sh.name = name
    if anim:
        s._anim.append(sh)
    return sh


def rect(s, x, y, w, h, fill=None, line=None, **kw):
    return shape(s, MSO_SHAPE.RECTANGLE, x, y, w, h, fill, line, **kw)


def card(s, x, y, w, h, fill=PANEL, line=LINE, **kw):
    return shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h, fill, line, adj=kw.pop("adj", 0.06), **kw)


def oval(s, cx, cy, r, fill=None, line=None, lw=1.0, **kw):
    return shape(s, MSO_SHAPE.OVAL, cx - r, cy - r, 2 * r, 2 * r, fill, line, lw=lw, **kw)


def hline(s, x1, y1, x2, y2, color=LINE2, w=1.25, dash=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    if dash:
        ln = c.line._get_or_add_ln()
        d = etree.SubElement(ln, qn("a:prstDash"))
        d.set("val", "dash")
    return c


def set_font(run, name):
    """Typeface plus a pitch-family hint, so a machine without Work Sans / JetBrains Mono falls back to
    Arial or Helvetica (sans) and Courier New (mono) instead of the Office default."""
    run.font.name = name
    latin = run._r.get_or_add_rPr().find(qn("a:latin"))
    if latin is not None:
        latin.set("pitchFamily", "49" if name == MONO else "34")
        latin.set("charset", "0")


def bulletize(p, color, indent=0.17):
    """A real hanging bullet (buChar) so wrapped lines align with the text, not the dot."""
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(int(Inches(indent))))
    pPr.set("indent", str(-int(Inches(indent))))
    for xml in (f'<a:buClr xmlns:a="{ANS}"><a:srgbClr val="{color}"/></a:buClr>', f'<a:buSzPct xmlns:a="{ANS}" val="100000"/>',
                f'<a:buFont xmlns:a="{ANS}" typeface="Arial" pitchFamily="34" charset="0"/>', f'<a:buChar xmlns:a="{ANS}" char="•"/>'):
        pPr.append(etree.fromstring(xml))


def text(s, x, y, w, h, content, size=16, color=TEXT, bold=False, font=SANS, align="l", anchor="t",
         spacing=None, line_spacing=None, anim=False, name=None, track=None, bullet=None):
    """content: str (\n = new paragraph) or list of paragraphs, each a str or list of (text, opts) runs.
    track: letter spacing in points (wordmark, eyebrows). bullet: color of a hanging bullet on every paragraph."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    paras = content.split("\n") if isinstance(content, str) else content
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
        if line_spacing:
            p.line_spacing = line_spacing
        if spacing is not None and i > 0:
            p.space_before = Pt(spacing)
        runs = [(para, {})] if isinstance(para, str) else para
        for txt, o in runs:
            r = p.add_run()
            r.text = txt
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            set_font(r, o.get("font", font))
            r.font.color.rgb = rgb(o.get("color", color))
            if o.get("track", track):
                r._r.get_or_add_rPr().set("spc", str(int(o.get("track", track) * 100)))
        if bullet:
            bulletize(p, bullet)
    if name:
        tb.name = name
    if anim:
        s._anim.append(tb)
    return tb


def streak(s, x, y, w, h=0.02, glow=0.7, name="Sunrise streak"):
    """The Sunrise motif: a thin line, transparent -> amber -> pale gold -> amber -> transparent, at 70% opacity."""
    sh = rect(s, x, y, w, h, name=name)
    a = int(glow * 100000)
    gs = "".join(f'<a:gs pos="{p}"><a:srgbClr val="{c}"><a:alpha val="{al}"/></a:srgbClr></a:gs>' for p, c, al in
                 ((0, ACCENT, 0), (30000, ACCENT, a), (50000, ACCENT2, a), (70000, ACCENT, a), (100000, ACCENT, 0)))
    grad = etree.fromstring(f'<a:gradFill xmlns:a="{ANS}" rotWithShape="1"><a:gsLst>{gs}</a:gsLst>'
                            '<a:lin ang="0" scaled="0"/></a:gradFill>')
    nf = sh._element.spPr.find(qn("a:noFill"))
    nf.addprevious(grad)
    nf.getparent().remove(nf)
    return sh


def eyebrow(s, x, y, label, w=10.0):
    """Section eyebrow as in the web deck: a short streak, then tracked uppercase amber."""
    streak(s, x, y + 0.115, 0.4, name="Eyebrow streak")
    text(s, x + 0.55, y, w, 0.3, label.upper(), size=12, color=ACCENT, bold=True, track=1.7)


def header(s, n, kicker, title, accent=None, size=36):
    eyebrow(s, 0.75, 0.5, f"{n:02d}  ·  {kicker}")
    lines = []
    for ln in title.split("\n"):
        if accent and accent in ln:
            a, b = ln.split(accent, 1)
            lines.append([(a, {}), (accent, {"color": ACCENT}), (b, {})])
        else:
            lines.append(ln)
    text(s, 0.75, 0.88, 11.8, 1.3, lines, size=size, font=DISPLAY, line_spacing=0.95, name="Title")


def chip(s, x, y, label, size=9):
    color = CAT.get(label, MUTED)
    t = label_name(label).upper()
    w = 0.12 + len(t) * size * 0.0085
    card(s, x, y, w, 0.24, fill=PANEL2, line=color if label in CRIT else LINE2, adj=0.2, lw=0.75)
    text(s, x, y + 0.035, w, 0.2, t, size=size, color=color if label in CRIT else MUTED, font=MONO, bold=True, align="c")
    return w


def radar(s, cx, cy, rmax, seed):
    for i in range(1, 6):
        oval(s, cx, cy, rmax * i / 5, line=LINE, lw=1.0)
    hline(s, cx - rmax, cy, cx + rmax, cy, color=LINE, w=0.75)
    hline(s, cx, cy - rmax, cx, cy + rmax, color=LINE, w=0.75)
    sweep = shape(s, MSO_SHAPE.PIE, cx - rmax, cy - rmax, 2 * rmax, 2 * rmax, fill=AMBER_SOFT, name="Radar sweep")
    try:
        sweep.adjustments[0], sweep.adjustments[1] = 200.0, 250.0
    except Exception:
        pass
    rnd = random.Random(seed)
    for i in range(18):
        a, rr = rnd.random() * 2 * math.pi, 0.15 + rnd.random() * 0.8
        crit = i < 4
        oval(s, cx + math.cos(a) * rr * rmax, cy + math.sin(a) * rr * rmax, 0.07 if crit else 0.045,
             fill=RED if crit else DIM, anim=crit)


# ------------------------------------------------------------------------------------ transitions, anim
def add_transition_and_timing(slide, kind="fade"):
    sld = slide._element
    for tag in ("p:transition", "p:timing"):
        for e in sld.findall(qn(tag)):
            sld.remove(e)
    trans = {"fade": '<p:transition spd="med"><p:fade/></p:transition>',
             "push": '<p:transition spd="med"><p:push dir="u"/></p:transition>',
             "wipe": '<p:transition spd="med"><p:wipe dir="r"/></p:transition>'}[kind]
    spids = [sh.shape_id for sh in slide._anim]
    timing = ""
    if spids:
        ids = iter(range(5, 10000))
        pars, blds = [], []
        for i, spid in enumerate(spids):
            a, b, c = next(ids), next(ids), next(ids)
            pars.append(
                f'<p:par><p:cTn id="{a}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" grpId="0" '
                f'nodeType="withEffect"><p:stCondLst><p:cond delay="{250 + i * 160}"/></p:stCondLst><p:childTnLst>'
                f'<p:set><p:cBhvr><p:cTn id="{b}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
                f'</p:cTn><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility'
                f'</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
                f'<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{c}" dur="500"/><p:tgtEl>'
                f'<p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect></p:childTnLst></p:cTn></p:par>')
            blds.append(f'<p:bldP spid="{spid}" grpId="0" animBg="1"/>')
        timing = (
            '<p:timing><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
            '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
            '<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0">'
            '<p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst><p:par><p:cTn id="4" fill="hold"><p:stCondLst>'
            '<p:cond delay="0"/></p:stCondLst><p:childTnLst>' + "".join(pars) +
            '</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn>'
            '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
            '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
            '</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst><p:bldLst>' + "".join(blds) + '</p:bldLst></p:timing>')
    frag = etree.fromstring(f'<root xmlns:p="{NSP}">{trans}{timing}</root>')
    anchor = sld.find(qn("p:clrMapOvr"))
    idx = (list(sld).index(anchor) + 1) if anchor is not None else len(sld)
    for i, child in enumerate(list(frag)):
        sld.insert(idx + i, child)


def notes(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt


def apply_theme(prs):
    """Work Sans and the Sunrise accents in the deck theme, so text and shapes added later in PowerPoint match."""
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    part = prs.slide_masters[0].part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    ns = {"a": ANS}
    for latin in root.findall(".//a:majorFont/a:latin", ns) + root.findall(".//a:minorFont/a:latin", ns):
        latin.attrib.pop("panose", None)
        latin.set("typeface", SANS)
        latin.set("pitchFamily", "34")
        latin.set("charset", "0")
    scheme = root.find(".//a:clrScheme", ns)
    if scheme is not None:
        scheme.set("name", "Rescue Radar Sunrise")
        for tag_, val in (("accent1", ACCENT), ("accent2", RED), ("accent3", OK), ("accent4", "8FB4D8"),
                          ("accent5", "A9A5D6"), ("accent6", "C79FBF"), ("hlink", ACCENT), ("folHlink", ACCENT2)):
            el = scheme.find(f"a:{tag_}", ns)
            if el is not None:
                for c in list(el):
                    el.remove(c)
                etree.SubElement(el, qn("a:srgbClr")).set("val", val)
    fonts = root.find(".//a:fontScheme", ns)
    if fonts is not None:
        fonts.set("name", "Rescue Radar Sunrise")
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# ---------------------------------------------------------------------------------------------- slides
def build(D, out):
    deck = Deck()
    o, fr = D.ours, D.front
    fname = D.front_name

    # 1 ---------------------------------------------------------------- title + hook
    s = deck.slide("01-title", footer=False)
    radar(s, 10.55, 3.75, 2.75, 7)
    eyebrow(s, 0.75, 0.75, "Fireworks: Deploy  ·  San Francisco", w=7.0)
    text(s, 0.75, 1.1, 7.2, 2.4, [[("Rescue", {})], [("Radar", {"color": ACCENT})]], size=80, font=DISPLAY,
         line_spacing=0.9, anim=True, name="Title")
    text(s, 0.75, 3.45, 6.9, 1.0, "Reads every public post during a disaster, finds the people asking to be rescued, "
         "and puts them in a dispatcher's queue in real time.", size=18, color=MUTED, anim=True)
    card(s, 0.75, 4.65, 6.9, 1.95, fill=PANEL, line=LINE2, anim=True, name="Hook card")
    if D.hook:
        hook_txt = "“" + scrub(D.hook["text"]) + "”"
        lab = g(D.hook, "ours", "label") or D.hook.get("truth")
        who = "Rescue Radar →" if g(D.hook, "ours", "label") else "Human label →"
    else:
        hook_txt, lab, who = "A real public post from Hurricane Dorian (2019) appears here once the replay data is exported.", None, ""
    text(s, 1.0, 4.82, 6.4, 0.25, "HURRICANE DORIAN · 2019 · PUBLIC POST · PII SCRUBBED", size=10,
         color=DIM, font=MONO, bold=True, anim=True)
    text(s, 1.0, 5.1, 6.4, 1.0, hook_txt, size=13.5, color=TEXT, anim=True)
    if lab:
        text(s, 1.0, 6.26, 1.7, 0.24, who, size=10, color=DIM, font=MONO)
        chip(s, 2.6, 6.23, lab)
    hook_say = ("This was posted publicly during Hurricane Dorian in 2019: someone in Abaco lost contact with a friend, and a "
                "cousin's church shelter had its roof ripped off, with people stuck by flooding. They asked strangers online for help. "
                if D.hook and str(D.hook.get("id")) == HOOK_ID else
                "This was posted publicly during Hurricane Dorian in 2019. Describe only what the post itself says. ")
    notes(s, "Open on the post, not the logo. Read it aloud, slowly.\n" + hook_say +
             "Rescue Radar exists so a post like this never sits unread.\n"
             "Transition: fade.")
    add_transition_and_timing(s, "fade")

    # 2 ---------------------------------------------------------------- problem
    s = deck.slide("02-problem")
    header(s, 2, "The problem", "When the phones jam,\nthe pleas go public", accent="public")
    beats = [("01", "Emergency lines saturate", "In a major disaster, call volume outruns 911 and emergency lines. Many callers never get through."),
             ("02", "Pleas move to social media", "People post wherever someone might see it: the street, the water level, who is trapped."),
             ("03", "Nobody can read it all", "Rescue requests are a thin slice of a firehose of news, prayers and opinion.")]
    for i, (n_, h, b) in enumerate(beats):
        y = 2.35 + i * 1.5
        text(s, 0.75, y, 0.9, 0.7, n_, size=34, bold=True, font=DISPLAY, color=RED if i == 2 else DIM, anim=True)
        text(s, 1.65, y, 5.9, 1.3, [[(h, {"size": 20, "bold": True, "color": TEXT})], [(b, {"size": 15, "color": MUTED})]],
             spacing=4, anim=True)
    card(s, 7.9, 2.3, 4.7, 4.4, fill=BG_ELEV, line=LINE)
    for i, p in enumerate(D.posts[:9]):
        crit_ = p.get("truth") in CRIT
        t = scrub(p["text"])
        text(s, 8.1, 2.45 + i * 0.27, 4.3, 0.25, (t[:48] + "…") if len(t) > 48 else t, size=9,
             color=RED2 if crit_ else BASE, font=MONO)
    if not D.posts:
        text(s, 8.1, 2.5, 4.3, 0.5, "Replay data pending.", size=12, color=DIM, font=MONO)
    text(s, 8.15, 5.05, 2.2, 0.75, num(D.dorian_n), size=40, bold=True, font=DISPLAY, anim=True)
    text(s, 8.15, 5.85, 2.2, 0.6, "posts in the Hurricane Dorian test slice", size=12, color=MUTED, anim=True)
    text(s, 10.45, 5.05, 2.0, 0.75, pct(D.dorian_share), size=40, bold=True, font=DISPLAY, color=RED, anim=True)
    text(s, 10.45, 5.85, 2.0, 0.6, "are rescue-critical, by human label", size=12, color=MUTED, anim=True)
    notes(s, "When a hurricane or earthquake hits, emergency lines saturate. People who cannot get through post publicly: "
             "the street, the water level, who is trapped.\n"
             f"But those pleas are needles in a haystack. In our Hurricane Dorian test slice of {num(D.dorian_n)} posts, "
             f"only {pct(D.dorian_share)} are rescue-critical. No team can read the rest in time.\n"
             "Transition: push up.")
    add_transition_and_timing(s, "push")

    # 3 ---------------------------------------------------------------- who
    s = deck.slide("03-who")
    header(s, 3, "Who it is for", "Built for the people\nwho send the boats")
    who = [("Dispatchers", "911 centers and public-safety answering points that need overflow triage when the lines jam."),
           ("Emergency operations centers", "City, county and state EOCs building one picture of who needs help, and where."),
           ("NGOs and volunteer rescue", "Relief organizations and volunteer boat crews that already act on public requests.")]
    for i, (h, b) in enumerate(who):
        x = 0.75 + i * 4.0
        card(s, x, 2.35, 3.75, 2.55, anim=True)
        oval(s, x + 0.55, 2.9, 0.28, fill=AMBER_SOFT)
        text(s, x + 0.27, 2.74, 0.56, 0.32, str(i + 1), size=16, bold=True, font=DISPLAY, color=ACCENT, align="c")
        text(s, x + 0.3, 3.35, 3.2, 1.5, [[(h, {"size": 19, "bold": True})], [(b, {"size": 14, "color": MUTED})]],
             spacing=6, anim=True)
    card(s, 0.75, 5.2, 11.75, 1.35, fill=CRIT_SOFT, line=CRIT_LINE, anim=True)
    text(s, 1.05, 5.4, 2.0, 0.9, "JOB TO BE DONE", size=12, color="FFB089", bold=True, track=1.5, anim=True)
    text(s, 3.1, 5.38, 9.1, 1.0, "When a disaster swamps our lines, help me find every public cry for rescue, see where it is, "
         "and hand it to a team before the window closes.", size=18, color=TEXT, anim=True)
    notes(s, "Three users: 911 dispatchers who need overflow triage, emergency operations centers building a common picture, "
             "and NGOs and volunteer boat crews who already act on public requests.\n"
             "One job: find every public cry for rescue, see where it is, and hand it to a team before the window closes.\n"
             "Transition: fade.")
    add_transition_and_timing(s, "fade")

    # 4 ---------------------------------------------------------------- product
    s = deck.slide("04-product")
    header(s, 4, "The product", "A dispatch console that reads every post", size=32)
    card(s, 0.75, 1.65, 11.85, 5.15, fill=BG_ELEV, line=LINE2, adj=0.02, anim=True)
    rect(s, 0.76, 1.66, 11.83, 0.42, fill=PANEL)
    src = "labels: Rescue Radar predictions" if D.src == "ours" else "labels: human annotations (model predictions pending)"
    text(s, 0.95, 1.77, 11.4, 0.25, [[("● REPLAY   ", {"color": RED, "bold": True}), ("Hurricane Dorian 2019   ", {"color": TEXT, "bold": True}),
                                      (src, {"color": MUTED}), ("      " + SITE, {"color": DIM})]], size=10, font=MONO)
    lab_of = (lambda p: g(p, "ours", "label")) if D.src == "ours" else (lambda p: p.get("truth"))
    text(s, 0.95, 2.2, 3.4, 0.25, "INCOMING POSTS", size=9, color=DIM, font=MONO, bold=True)
    for i, p in enumerate(D.posts[6:10]):
        y = 2.5 + i * 1.06
        card(s, 0.9, y, 3.55, 0.96, fill=PANEL, line=LINE, adj=0.08)
        t = scrub(p["text"])
        text(s, 1.02, y + 0.07, 3.3, 0.55, (t[:92] + "…") if len(t) > 92 else t, size=9.5, color=TEXT)
        if lab_of(p):
            chip(s, 1.02, y + 0.66, lab_of(p), size=7.5)
    # map pane: equirectangular projection around the event center
    mx, my, mw, mh = 4.6, 2.15, 4.25, 4.55
    rect(s, mx, my, mw, mh, fill=BG, line=LINE)
    placed = [p for p in D.posts if isinstance(p.get("place"), dict) and f(p["place"].get("lat")) is not None]
    if placed:
        c = g(D.event, "center") or [sorted(p["place"]["lat"] for p in placed)[len(placed) // 2],
                                     sorted(p["place"]["lng"] for p in placed)[len(placed) // 2]]
        span = 360 * 600 / (256 * 2 ** f(g(D.event, "zoom"))) if f(g(D.event, "zoom")) else 16.0
        kx = mw / span
        ky = kx / math.cos(math.radians(c[0]))
        groups = {}
        for p in placed:
            k = (p["place"].get("name"), p["place"]["lat"], p["place"]["lng"])
            e = groups.setdefault(k, [0, 0, None])
            e[0] += 1
            if lab_of(p) in CRIT:
                e[1] += 1
                e[2] = e[2] or lab_of(p)
        labeled = 0
        for (name, lat, lng), (n_all, n_crit, lab) in sorted(groups.items(), key=lambda kv: kv[1][1]):
            x = mx + mw / 2 + (lng - c[1]) * kx
            y = my + mh / 2 - (lat - c[0]) * ky
            if not (mx + 0.1 < x < mx + mw - 0.1 and my + 0.1 < y < my + mh - 0.1):
                continue
            if n_crit:
                rr = 0.06 + min(0.1, math.sqrt(n_crit) * 0.025)
                oval(s, x, y, rr * 2.2, line=CAT.get(lab, RED), lw=1.0)
                oval(s, x, y, rr, fill=CAT.get(lab, RED), anim=True)
                if labeled < 4 and name:
                    text(s, x + rr + 0.06, y - 0.09, 1.9, 0.2, f"{name}" + (f" · {n_crit}" if n_crit > 1 else ""),
                         size=8, color=OPUS, font=MONO)
                    labeled += 1
            else:
                oval(s, x, y, 0.035, fill=BASE)
    else:
        text(s, mx + 0.3, my + mh / 2 - 0.2, mw - 0.6, 0.4, "Replay data pending: rescue pins render here", size=11,
             color=DIM, font=MONO, align="c")
    text(s, mx + 0.12, my + mh - 0.3, mw - 0.2, 0.22, "ember: rescue-critical places · grey: other located posts", size=8,
         color=DIM, font=MONO)
    text(s, 9.0, 2.2, 3.4, 0.25, "PRIORITY QUEUE", size=9, color=DIM, font=MONO, bold=True)
    for i, p in enumerate([p for p in D.posts if lab_of(p) in CRIT][:4]):
        y = 2.5 + i * 1.06
        card(s, 9.0, y, 3.45, 0.96, fill=CRIT_SOFT, line=CRIT_LINE, adj=0.08, anim=True)
        text(s, 9.1, y + 0.08, 0.3, 0.4, str(i + 1), size=18, bold=True, font=DISPLAY, color=RED)
        t = scrub(p["text"])
        text(s, 9.45, y + 0.07, 2.9, 0.55, (t[:80] + "…") if len(t) > 80 else t, size=9.5, color=TEXT)
        chip(s, 9.45, y + 0.66, lab_of(p), size=7.5)
    notes(s, "This is the dispatch console, replaying Hurricane Dorian. Posts stream in on the left, each one classified. "
             "Rescue-critical posts turn red, get a pin on the map, and jump into the priority queue on the right, "
             "with names, phone numbers and handles already redacted.\n"
             f"CUT TO LIVE DEMO here: the local console, http://localhost:8787 (live model calls work only there). Start the Dorian "
             "replay, then paste a fresh post into Head-to-Head to show Rescue Radar and the frontier model labelling it side by side. "
             f"Fallback if the local server is down: the static {SITE} tab and Head-to-Head's recorded race ('Run 20 random test posts').\n"
             "Transition back to the deck: push up.")
    add_transition_and_timing(s, "push")

    # 5 ---------------------------------------------------------------- how
    s = deck.slide("05-how")
    header(s, 5, "How it works", "One open model,\nfine-tuned for one job")
    nodes = [("Posts", "2019 replay, or paste / upload"), ("PII redaction", "Best effort, before a human reads it"),
             ("Classify", "Nemotron 3.5 Super + LoRA on Fireworks"), ("Locate", "Place names to map pins"),
             ("Prioritize", "Rescue-critical jumps the queue"), ("A human decides", "The model never sends a boat")]
    hline(s, 1.2, 2.85, 12.2, 2.85, color=LINE2, w=1.5, dash=True)
    for i, (h, b) in enumerate(nodes):
        x = 0.75 + i * 2.0
        hot, human = i == 2, i == 5
        oval(s, x + 0.45, 2.85, 0.42, fill=AMBER_SOFT if hot else PANEL, line=ACCENT if hot else (RED if human else LINE2),
             lw=1.5, anim=True)
        text(s, x + 0.03, 2.66, 0.84, 0.4, str(i + 1), size=18, bold=True, font=DISPLAY,
             color=ACCENT if hot else (RED if human else MUTED), align="c")
        text(s, x, 3.45, 1.85, 1.2, [[(h, {"size": 15, "bold": True})], [(b, {"size": 12, "color": MUTED})]], spacing=3,
             anim=True)
    card(s, 0.75, 4.95, 11.85, 1.75, fill=PANEL, line=LINE, anim=True)
    steps = [("TRAIN DATA", f"{num(D.ev.get('train_events'))} disasters", "HumAID, 2016 to 2018; look-alikes of test posts removed"),
             ("EXAMPLES", f"{num(train_examples(D.m))} posts", (f"Capped per class; the scored step-{ckpt_seen(D.m)[0]} checkpoint saw {num(ckpt_seen(D.m)[1])}"
              if ckpt_seen(D.m)[1] else "Capped per class so rare rescue categories count")),
             ("FINE-TUNE", "LoRA on Fireworks", "Serverless training on the open NVIDIA Nemotron 3.5 Super base"),
             ("SERVE", "Same code path", "Fireworks serverless sampling; the live server serves the scored checkpoint")]
    for i, (k, v, d_) in enumerate(steps):
        x = 1.0 + i * 2.93
        text(s, x, 5.12, 2.7, 0.25, k, size=10, color=ACCENT, font=MONO, bold=True)
        text(s, x, 5.42, 2.75, 0.45, v.upper(), size=16, bold=True, font=DISPLAY)
        text(s, x, 5.9, 2.7, 0.7, d_, size=12, color=MUTED)
    notes(s, "Under the hood: posts are PII-scrubbed, then classified into the 10 HumAID humanitarian categories by "
             "NVIDIA Nemotron 3.5 Super with our LoRA adapter, trained and served on Fireworks.\n"
             f"Training data: {num(D.ev.get('train_events'))} disasters from 2016 to 2018, "
             f"{num(train_examples(D.m))} labelled posts in the training file" + (f"; the scored step-{ckpt_seen(D.m)[0]} checkpoint saw {num(ckpt_seen(D.m)[1])} of them" if ckpt_seen(D.m)[1] else "") + ". The same SamplerClassifier code path serves the demo and the benchmark, "
             "and by default the live server serves exactly the checkpoint the benchmark scored (the console badge says 'scored'). "
             "A human always makes the dispatch call.\n"
             "Transition: fade.")
    add_transition_and_timing(s, "fade")

    # 6 ---------------------------------------------------------------- benchmark design
    s = deck.slide("06-benchmark")
    header(s, 6, "The benchmark", "Tested on disasters\nit has never seen")
    years = {"2016": ["Kaikoura earthquake", "Ecuador earthquake", "Canada wildfires", "Italy earthquake", "Hurricane Matthew"],
             "2017": ["Hurricane Harvey", "Hurricane Irma", "Hurricane Maria", "Puebla earthquake", "Sri Lanka floods"],
             "2018": ["Hurricane Florence", "Kerala floods", "Maryland floods", "Greece wildfires", "California wildfires"]}
    test = [("hurricane_dorian_2019", "Hurricane Dorian"), ("cyclone_idai_2019", "Cyclone Idai"),
            ("pakistan_earthquake_2019", "Pakistan earthquake"), ("midwestern_us_floods_2019", "Midwest floods")]
    hline(s, 0.75, 2.45, 9.1, 2.45, color=LINE2, w=2.5)
    hline(s, 9.1, 2.45, 12.6, 2.45, color=ORANGE, w=2.5)
    hline(s, 9.1, 1.95, 9.1, 4.85, color=ORANGE, w=1.25, dash=True)
    text(s, 9.25, 1.95, 3.3, 0.25, "NEVER SEEN IN TRAINING", size=10, color=ORANGE, font=MONO, bold=True)
    for i, (yr, evs) in enumerate(years.items()):
        cx = 1.9 + i * 2.65
        oval(s, cx, 2.45, 0.09, fill=BG, line=LINE2, lw=2)
        text(s, cx - 1.2, 2.62, 2.4, 0.5, yr, size=26, bold=True, font=DISPLAY, color=DIM, align="c", anim=True)
        text(s, cx - 1.25, 3.15, 2.5, 1.7, "\n".join(evs), size=10.5, color=MUTED, font=MONO, align="c", spacing=2, anim=True)
    oval(s, 10.85, 2.45, 0.1, fill=BG, line=ORANGE, lw=2.5)
    text(s, 9.65, 2.62, 2.4, 0.5, "2019", size=26, bold=True, font=DISPLAY, color=ORANGE, align="c", anim=True)
    text(s, 9.35, 3.15, 3.3, 1.7, [[(name + "  ", {"color": "FFB089"}), (f"{num(g(D.ev, 'events', k))} posts", {"color": TEXT, "bold": True})]
                                  for k, name in test], size=10.5, font=MONO, spacing=2, anim=True)
    tiles = [(num(D.ev.get("train_events")), "training disasters, 2016 to 2018", TEXT),
             (num(D.ev.get("test_events")), "unseen 2019 disasters held out", ORANGE),
             (num(D.ev.get("n")), "held-out posts; Claude answered fewer (spending cap)", TEXT)]
    for i, (v, lbl, col) in enumerate(tiles):
        x = 0.75 + i * 2.55
        card(s, x, 5.1, 2.35, 1.55, anim=True)
        text(s, x + 0.2, 5.2, 2.0, 0.7, v, size=34, bold=True, font=DISPLAY, color=col)
        text(s, x + 0.2, 5.95, 2.0, 0.6, lbl, size=12, color=MUTED)
    card(s, 8.45, 5.1, 4.15, 1.55, anim=True)
    text(s, 8.65, 5.22, 3.8, 1.35, [[("Same instructions and 10 labels; paired on posts both answered:", {"color": MUTED, "size": 12})],
                                   [("■ ", {"color": ACCENT}), ("Rescue Radar (ours)", {})],
                                   [("■ ", {"color": OPUS}), ("Claude Opus 5.5, 20-shot", {})],
                                   [("■ ", {"color": OPUS0}), ("Claude Opus 5.5, zero-shot", {})],
                                   [("■ ", {"color": BASE}), ("Nemotron base, no tuning", {})]], size=11, font=MONO, spacing=2)
    notes(s, f"The test is strict. We trained on {num(D.ev.get('train_events'))} disasters from 2016 to 2018 and tested on "
             f"{num(D.ev.get('test_events'))} disasters from 2019 that the model never saw: Hurricane Dorian, Cyclone Idai, "
             f"the Pakistan earthquake and the Midwest floods. {num(D.ev.get('n'))} held-out posts. Every system gets the same "
             "instructions and 10 labels; the 20-shot baselines also get 20 examples. Claude hit its API spending cap, so it answered "
             "fewer posts and every comparison is paired on the posts both systems answered. The protocol was pre-registered "
             "before any fine-tuned model was scored on the test set." + (" Deviation: the headline is the small-data run, which the pre-registration lists as an ablation; "
             "the pre-registered main system is not scored yet." if D.ours_key == "rescue_radar_quick" else "") + "\n"
             "Transition: push up.")
    add_transition_and_timing(s, "push")

    # 7 ---------------------------------------------------------------- results
    s = deck.slide("07-results")
    d_f1, d_rec = D.delta("macro_f1"), D.delta("critical_recall")
    # "beats" only when the macro-F1 interval excludes zero; a lead inside the noise is a match, not a win
    ci_f1, ci_rec = g(D.cmp, "macro_f1", "ci"), g(D.cmp, "critical_recall", "ci")
    f1_up, f1_down = bool(ci_f1) and ci_f1[0] > 0, bool(ci_f1) and ci_f1[1] < 0
    rec_up = bool(ci_rec) and ci_rec[0] > 0
    title7 = ("A fine-tuned open model\nbeats the frontier" if f1_up
              else "Matches the frontier,\nfinds more rescue requests" if not f1_down and rec_up
              else "A fine-tuned open model\nmatches the frontier" if not f1_down and ci_f1
              else "Fine-tuned open model\nvs the frontier")
    header(s, 7, f"Results vs {fname}", title7, size=32)
    text(s, 0.75, 2.2, 3.6, 0.9, pts(d_f1), size=50, bold=True, font=DISPLAY, color=ACCENT if (f(d_f1) or 0) >= 0 else OPUS, anim=True)
    text(s, 0.75, 3.05, 3.5, 0.6, f"macro-F1 gap vs {fname}, 4 unseen disasters", size=13, color=MUTED, anim=True)
    text(s, 0.75, 3.75, 3.6, 0.8, pts(d_rec), size=40, bold=True, font=DISPLAY, color=ACCENT if (f(d_rec) or 0) >= 0 else OPUS, anim=True)
    text(s, 0.75, 4.45, 3.5, 0.6, "rescue-critical recall gap: missing a rescue request is the costly error", size=13, color=MUTED, anim=True)
    rows = [("Rescue Radar", o, ACCENT)]
    for key, short in (("opus_few", "Opus 5.5, 20-shot"), ("opus_zero", "Opus 5.5, zero-shot"), ("base_zero", "Nemotron, base")):
        sd = D.systems.get(key) if key != D.ours_key else None
        if sd or key == D.front_key:
            rows.append((short, sd or {}, OPUS if key == D.front_key else (OPUS0 if key.startswith("opus") else BASE)))
    metrics = [("Macro-F1", lambda x: x.get("macro_f1"), lambda x: g(x, "ci95", "macro_f1"), TEXT),
               ("Accuracy", lambda x: x.get("accuracy"), lambda x: g(x, "ci95", "accuracy"), TEXT),
               ("Rescue-critical recall", lambda x: g(x, "critical", "recall"), lambda x: g(x, "ci95", "critical_recall"), RED2)]
    bx, bw, y = 6.35, 4.1, 2.15
    for title_, get_v, get_ci, col in metrics:
        text(s, 4.6, y, 4.0, 0.3, title_, size=14, bold=True, color=col)
        y += 0.32
        for short, sd, color in rows:
            v, ci = f(get_v(sd)), get_ci(sd)
            text(s, 4.6, y + 0.01, 1.7, 0.22, short, size=9.5, font=MONO, color=ACCENT if color == ACCENT else MUTED)
            rect(s, bx, y + 0.04, bw, 0.16, fill=PANEL2)
            if v is not None:
                rect(s, bx, y + 0.04, max(0.02, bw * max(0, min(1, v))), 0.16, fill=color, anim=True)
            if isinstance(ci, list) and len(ci) == 2 and f(ci[0]) is not None and f(ci[1]) is not None:
                x1, x2 = bx + bw * ci[0], bx + bw * ci[1]
                hline(s, x1, y + 0.12, x2, y + 0.12, color=TEXT, w=1.0)
                hline(s, x1, y + 0.02, x1, y + 0.22, color=TEXT, w=1.0)
                hline(s, x2, y + 0.02, x2, y + 0.22, color=TEXT, w=1.0)
            ci_txt = f"  {pct(ci[0])[:-1]}–{pct(ci[1])[:-1]}" if isinstance(ci, list) and len(ci) == 2 and None not in (f(ci[0]), f(ci[1])) else ""
            text(s, bx + bw + 0.12, y, 1.9, 0.22, [[(pct(v), {"bold": True, "color": TEXT if v is not None else DIM}),
                                                  (ci_txt, {"size": 8, "color": DIM})]], size=10, font=MONO)
            y += 0.27
        y += 0.12
    mc = g(D.cmp, "accuracy", "mcnemar") or {}
    if f(mc.get("a_only")) is not None and f(mc.get("b_only")) is not None:
        p_ = f(mc.get("p"))
        mc_txt = (f"Where exactly one system got a post right ({num(f(mc['a_only']) + f(mc['b_only']))} posts), Rescue Radar was right "
                  f"{num(mc['a_only'])} times and Opus {num(mc['b_only'])} times ({pval(p_)}). "
                  + ("A split that lopsided is very unlikely if the two were equally good." if p_ is not None and p_ < 0.05
                     else "That split is consistent with chance, so we claim no difference."))
    else:
        mc_txt = "McNemar head-to-head test: n/a until results/metrics.json has the comparison."
    parts = []
    for k, nm in (("macro_f1", "Macro-F1"), ("critical_recall", "Rescue-critical recall")):
        c_ = D.cmp.get(k) or {}
        if c_.get("ci"):
            lo, hi = c_["ci"]
            parts.append(f"{nm} {pts(c_.get('delta'))}, 95% CI {pts(lo)} to {pts(hi)}" +
                         ("; excludes zero." if lo > 0 or hi < 0 else "; includes zero, so no claim."))
    bs_txt = ("Bootstrap, test set re-drawn " + (num(g(D.cmp, 'macro_f1', 'n')) + " times: " if g(D.cmp, 'macro_f1', 'n') else ": ")
              + " ".join(parts)) if parts else "Bootstrap 95% intervals: n/a until results/metrics.json has the comparison."
    card(s, 0.75, 5.3, 3.6, 1.45, fill=PANEL, line=LINE, anim=True)
    text(s, 0.9, 5.4, 3.35, 1.3, [[("IS THE GAP REAL?", {"font": MONO, "size": 9, "bold": True, "color": ACCENT})],
                                  [(mc_txt, {"size": 10, "color": MUTED})]], spacing=3)
    text(s, 4.6, 6.62, 8.0, 0.6, bs_txt, size=9.5, color=DIM)
    raw7 = next((c for c in (D.m.get("comparisons") or []) if isinstance(c, dict) and c.get("a") == D.ours_key
                 and c.get("b") == D.front_key), {})
    sa7, sb7 = raw7.get("a_on_shared") or {}, raw7.get("b_on_shared") or {}

    def say_ci(ci):
        if not ci:
            return ""
        return "; the interval excludes zero" if ci[0] > 0 or ci[1] < 0 else f"; the interval includes zero, so level with {fname}"
    notes(s, f"The headline, paired on the {num(raw7.get('n'))} posts both systems answered on 4 disasters our fine-tune never saw: "
             f"Rescue Radar's macro-F1 is {pct(sa7.get('macro_f1'))} versus {pct(sb7.get('macro_f1'))} for {fname} "
             f"({pts(d_f1)}{say_ci(ci_f1)}). On rescue-critical recall, the error that costs lives, "
             f"it is {pct(sa7.get('critical_recall'))} versus {pct(sb7.get('critical_recall'))} ({pts(d_rec)}{say_ci(ci_rec)}).\n"
             f"Is it real? {mc_txt} {bs_txt}\n"
             "Say the direction exactly as the numbers show it; if a gap includes zero, say we cannot claim a difference.\n"
             + ("Disclose: these are the small-data run's numbers (pre-registered as an ablation); the pre-registered main "
                "system is not scored yet.\n" if D.ours_key == "rescue_radar_quick" else "") +
             "Transition: fade.")
    add_transition_and_timing(s, "fade")

    # 8 ---------------------------------------------------------------- eval functions: FN and FP
    s = deck.slide("07-results")
    header(s, 8, "The eval functions", "Two ways to be wrong,\ncounted post by post", accent="wrong", size=32)
    rb = D.m.get("rescue_binary") or {}
    rbs = rb.get("systems") or {}
    before, after, judge = rbs.get("base_zero") or {}, rbs.get(D.ours_key) or {}, rb.get("judge") or {}
    b_h, a_h, j_h = before.get("vs_human") or {}, after.get("vs_human") or {}, judge.get("vs_human") or {}
    supp = next((int(f(h["tp"]) + f(h["fn"])) for h in (a_h, j_h, b_h)
                 if f(h.get("tp")) is not None and f(h.get("fn")) is not None), None)
    defs = [("FALSE NEGATIVE", RED, "A real plea for help the system never flags. The error that costs lives.",
             b_h.get("fn"), a_h.get("fn"), f"missed of {num(supp)} real pleas"),
            ("FALSE POSITIVE", ORANGE, "A false alarm a dispatcher has to read and clear. The error that costs time.",
             b_h.get("fp"), a_h.get("fp"), "false alarms, all posts")]
    for i, (name, col, desc, vb, va, cap) in enumerate(defs):
        y = 2.3 + i * 2.25
        card(s, 0.75, y, 5.6, 2.05, fill=PANEL, line=col, anim=True)
        text(s, 1.0, y + 0.18, 5.1, 0.25, name, size=12, color=col, font=MONO, bold=True)
        text(s, 1.0, y + 0.5, 5.1, 0.6, desc, size=13, color=MUTED)
        text(s, 1.0, y + 1.1, 4.4, 0.8, [[(num(vb), {"color": DIM}), ("  →  ", {"color": DIM, "size": 24}),
                                          (num(va), {"color": col})]], size=40, bold=True, font=DISPLAY, anim=True)
        text(s, 1.0, y + 1.78, 5.1, 0.25, f"before fine-tuning  →  after · {cap}", size=10, color=DIM, font=MONO)
    rows8 = [("Nemotron base (before)", b_h, BASE), (f"Rescue Radar (after)", a_h, ACCENT), ("TypeSafe Jev judge", j_h, ORANGE)]
    vmax8 = max([f(r.get("fn")) or 0 for _, r, _ in rows8] + [f(r.get("fp")) or 0 for _, r, _ in rows8] + [1])
    y = 2.3
    for title8, kk in (("Missed pleas (false negatives)", "fn"), ("False alarms (false positives)", "fp")):
        text(s, 6.75, y, 5.8, 0.25, title8.upper(), size=10, color=ACCENT, font=MONO, bold=True)
        y += 0.3
        for nm, r, col in rows8:
            v = f(r.get(kk))
            text(s, 6.75, y + 0.01, 2.15, 0.22, nm, size=9, font=MONO, color=ACCENT if col == ACCENT else MUTED)
            rect(s, 8.95, y + 0.04, 2.6, 0.16, fill=PANEL2)
            if v is not None:
                rect(s, 8.95, y + 0.04, max(0.02, 2.6 * v / vmax8), 0.16, fill=col, anim=True)
            rate = r.get("fnr") if kk == "fn" else r.get("fpr")
            text(s, 11.65, y, 1.0, 0.22, [[(num(v), {"bold": True, "color": TEXT if v is not None else DIM}),
                                           (f"  {pct(rate)}" if f(rate) is not None else "", {"size": 8, "color": DIM})]],
                 size=10, font=MONO)
            y += 0.27
        y += 0.17
    card(s, 6.75, y + 0.05, 5.85, 6.75 - y, fill=PANEL, line=LINE, anim=True)
    agree_b, agree_a = g(before, "vs_jev", "agreement"), g(after, "vs_jev", "agreement")
    jq = (judge.get("question") or "does someone here need emergency assistance?")
    judge_txt = [[("SECOND OPINION: TYPESAFE (JEV) JUDGE", {"font": MONO, "size": 9, "bold": True, "color": ORANGE})],
                 [(f"An independent judgment-only model ({judge.get('model') or 'jev'}): one calibrated probability per post, "
                   f"no free text, {ms(g(judge, 'latency_ms', 'p50'))} median. Asked of every post: ", {"size": 10.5, "color": MUTED}),
                  ("“" + jq[:1].lower() + jq[1:] + "”", {"size": 10.5, "color": TEXT})],
                 [(f"It catches {pct(j_h.get('recall'))} of real pleas but raises {num(j_h.get('fp'))} false alarms "
                   f"({pct(j_h.get('precision'))} precision) — recall is cheap, precision is the hard part. "
                   f"Fine-tuning moves our agreement with Jev from {pct(agree_b)} to {pct(agree_a)}.", {"size": 10.5, "color": MUTED})]]
    text(s, 6.95, y + 0.17, 5.45, 6.5 - y, judge_txt, spacing=5)
    notes(s, "Our eval functions count the two ways a triage system can be wrong. A false negative is a real plea for help "
             "that is never flagged: the error that costs lives. A false positive is a false alarm a dispatcher must clear: "
             "the error that costs time.\n"
             f"Fine-tuning cuts missed pleas from {num(b_h.get('fn'))} to {num(a_h.get('fn'))} of {num(supp)} "
             f"({pct(b_h.get('fnr'))} to {pct(a_h.get('fnr'))} miss rate), and the price is more false alarms: "
             f"{num(b_h.get('fp'))} to {num(a_h.get('fp'))}. For a dispatch queue that trade is the right direction.\n"
             f"As a second opinion we also scored TypeSafe's Jev, an independent judgment-only model, on the same question. "
             f"It misses {num(j_h.get('fn'))} pleas and raises {num(j_h.get('fp'))} false alarms: high recall is easy, "
             "precision is what the fine-tune buys.\n"
             "Transition: fade.")
    add_transition_and_timing(s, "fade")

    # 9 ---------------------------------------------------------------- speed and cost
    s = deck.slide("08-speed")
    _o50, _f50 = f(g(D.ours, "latency_ms", "p50")), f(g(D.front, "latency_ms", "p50"))
    header(s, 9, "Speed and cost", ("Cheap enough for every post,\nslower per post for now"
                                    if _o50 is not None and _f50 is not None and _o50 > _f50
                                    else "Fast enough for a live feed,\ncheap enough for every post"))

    def tag(sd):
        if isinstance(sd.get("cost_measured"), bool):
            return "MEASURED" if sd["cost_measured"] else "ESTIMATED"
        note = str(sd.get("cost_note") or "").lower()
        return "ESTIMATED" if "estimat" in note else ("MEASURED" if "measur" in note else "PENDING")

    def panel(x, title_, tg, r, cap_good, cap_bad, items, fmt, note):
        card(s, x, 2.3, 5.75, 4.4, anim=True)
        text(s, x + 0.3, 2.5, 3.8, 0.4, title_, size=20, bold=True)
        tc = OK if tg == "MEASURED" else (ORANGE if tg == "ESTIMATED" else DIM)
        card(s, x + 4.2, 2.52, 1.3, 0.3, fill=PANEL2, line=tc, adj=0.15, lw=0.75)
        text(s, x + 4.2, 2.57, 1.3, 0.22, tg, size=9, bold=True, font=MONO, color=tc, align="c")
        if r is None:
            big, cap, col = NA, "fills in from results/metrics.json", DIM
        elif r >= 1:
            big, cap, col = f"{r:.1f}×", cap_good, ACCENT
        else:
            big, cap, col = f"{1 / r:.1f}×", cap_bad, OPUS
        text(s, x + 0.3, 2.95, 5.0, 0.95, big, size=48, bold=True, font=DISPLAY, color=col, anim=True)
        text(s, x + 0.3, 3.9, 5.2, 0.4, cap, size=14, color=MUTED)
        vmax = max([f(v) or 0 for _, v, _ in items] + [1e-9])
        for i, (lbl, v, color) in enumerate(items):
            yy = 4.45 + i * 0.36
            text(s, x + 0.3, yy, 1.9, 0.25, lbl, size=10, font=MONO, color=ACCENT if color == ACCENT else MUTED)
            rect(s, x + 2.15, yy + 0.05, 2.3, 0.16, fill=PANEL2)
            if f(v) is not None:
                rect(s, x + 2.15, yy + 0.05, max(0.02, 2.3 * f(v) / vmax), 0.16, fill=color, anim=True)
            text(s, x + 4.55, yy, 1.1, 0.25, fmt(v), size=10, bold=True, font=MONO, color=TEXT if f(v) is not None else DIM)
        text(s, x + 0.3, 5.95, 5.2, 0.7, note, size=9, color=DIM)

    lat_r = ratio(g(fr, "latency_ms", "p50"), g(o, "latency_ms", "p50"))
    fshort = "Opus 5.5, zero-shot" if D.front_key == "opus_zero" else "Opus 5.5, 20-shot"
    panel(0.75, "Latency per post", "MEASURED" if (o.get("latency_ms") or fr.get("latency_ms")) else "PENDING", lat_r,
          f"lower median latency than {fname}", f"higher median latency than {fname}",
          [("Rescue Radar p50", g(o, "latency_ms", "p50"), ACCENT), ("Opus 5.5 p50", g(fr, "latency_ms", "p50"), OPUS),
           ("Rescue Radar p95", g(o, "latency_ms", "p95"), ACCENT), ("Opus 5.5 p95", g(fr, "latency_ms", "p95"), OPUS)], ms,
          "Wall-clock time per post, measured on every benchmark call. Rescue Radar: Fireworks serverless sampling. "
          "32 parallel requests on shared capacity. Opus: Anthropic API, 24 parallel requests; same instructions plus 20 examples.")
    cost_r = ratio(fr.get("cost_per_1m_usd"), o.get("cost_per_1m_usd"))
    cnote = "  ".join(x for x in (f"Rescue Radar: {o['cost_note']}" if o.get("cost_note") else "",
                                  f"Opus: {fr['cost_note']}" if fr.get("cost_note") else "") if x) or \
        "Cost basis n/a: each figure is labelled measured or estimated when results land."
    if f(o.get("cost_per_1m_usd_undiscounted")) is not None:
        cnote += f" Rescue Radar undiscounted: {usd(o['cost_per_1m_usd_undiscounted'])} per 1M posts."
    panel(6.85, "Cost per 1M posts", tag(o) if o.get("cost_per_1m_usd") is not None else "PENDING", cost_r,
          f"cheaper per million posts than {fname}", f"more expensive per million posts than {fname}",
          [("Rescue Radar", o.get("cost_per_1m_usd"), ACCENT), (fshort, fr.get("cost_per_1m_usd"), OPUS)], usd, cnote if len(cnote) <= 480 else cnote[:477].rsplit(" ", 1)[0] + "…")
    notes(s, f"Speed: median latency per post is {ms(g(o, 'latency_ms', 'p50'))} for Rescue Radar versus "
             f"{ms(g(fr, 'latency_ms', 'p50'))} for {fname}; p95 {ms(g(o, 'latency_ms', 'p95'))} versus {ms(g(fr, 'latency_ms', 'p95'))}. "
             "Measured on every benchmark call.\n"
             f"Cost: {usd(o.get('cost_per_1m_usd'))} per million posts versus {usd(fr.get('cost_per_1m_usd'))}. "
             "Say whether each cost is measured or estimated, as labelled on the slide.\n"
             "Transition: push up.")
    add_transition_and_timing(s, "push")

    # 10 --------------------------------------------------------------- stack, responsible AI, limits
    s = deck.slide("09-stack")
    header(s, 10, "Stack, safeguards, limits", "Built to be trusted,\nhonest about where it fails")
    text(s, 0.75, 2.3, 4.0, 0.25, "SPONSOR STACK", size=11, color=ACCENT, font=MONO, bold=True)
    for i, (h, b) in enumerate([("FIREWORKS", "LoRA fine-tuning on serverless training, plus serving the checkpoint"),
                                ("NVIDIA", "Nemotron 3.5 Super: the open-weight base model we adapt"),
                                ("MICROSOFT", "Presidio PII redaction before human review; Foundry deployment is a next step, not built")]):
        y = 2.65 + i * 1.35
        card(s, 0.75, y, 3.85, 1.2, anim=True)
        text(s, 0.95, y + 0.12, 3.5, 1.0, [[(h, {"size": 20, "bold": True, "font": DISPLAY})], [(b, {"size": 12, "color": MUTED})]], spacing=3)
    rec = f(g(o, "critical", "recall"))
    pc = o.get("per_class") if isinstance(o.get("per_class"), dict) else {}
    weak = min(((k, f(v.get("f1"))) for k, v in pc.items() if isinstance(v, dict) and f(v.get("f1")) is not None),
               key=lambda kv: kv[1], default=None)
    cols = [("RESPONSIBLE AI", ACCENT, [("Human in the loop.", "The model ranks; a person dispatches."),
                                        ("Privacy first.", "Best-effort PII redaction before a dispatcher reads a post."),
                                        ("Open base model.", "The LoRA adapter could be exported for self-hosting (not done yet)."),
                                        ("Honest evaluation.", "Unseen disasters, one shared prompt, intervals and significance tests.")]),
            ("LIMITATIONS", ORANGE, [("It misses some.", (f"About {pct(round(1 - rec, 4) + 1e-9)} of rescue-critical posts on unseen disasters are not flagged, "
                                                          "so it runs beside 911, never instead of it.") if rec is not None else
                                      "Rescue-critical recall is n/a until results land; it runs beside 911, never instead of it."),
                                     ("Weakest category:", f"{label_name(weak[0])} (F1 {pct(weak[1])})." if weak else "n/a until results land."),
                                     ("English tweets, 2016 to 2019.", "Other languages and platforms are not yet tested."),
                                     ("Labels are crowd-annotated.", "Some ground truth is itself ambiguous.")])]
    for ci_, (h, col, items) in enumerate(cols):
        x = 4.95 + ci_ * 3.95
        text(s, x, 2.3, 3.6, 0.25, h, size=11, color=col, font=MONO, bold=True)
        text(s, x, 2.7, 3.65, 4.0, [[("○ ", {"color": col, "bold": True}), (a + " ", {"bold": True}), (b, {"color": MUTED})]
                                    for a, b in items], size=13.5, spacing=10, anim=True)
    notes(s, "Built on the sponsor stack: Fireworks for LoRA training and serving, NVIDIA Nemotron 3.5 Super as the open base, "
             "and Microsoft Presidio for best-effort PII redaction before a human reviews a post. Microsoft Foundry deployment is a next step, not built yet.\n"
             f"Limits, said plainly: it still misses {pct(1 - rec) if rec is not None else NA} of rescue-critical posts, "
             "it is tested on English tweets only, and it is a triage aid beside 911, never a replacement.\n"
             "Transition: fade.")
    add_transition_and_timing(s, "fade")

    # 11 --------------------------------------------------------------- the company, the ask, the close
    # Mirrors slide 10 of docs/deck/index.html. Qualitative company story; the only numbers are measured costs
    # from results/metrics.json. No prices, customers, partners or market sizes are claimed.
    s = deck.slide("10-next")
    header(s, 11, "The company", "Rescue Radar as a company", size=32)
    o_cost, f_cost = f(o.get("cost_per_1m_usd")), f(fr.get("cost_per_1m_usd"))
    o_full = f(o.get("cost_per_1m_usd_undiscounted"))
    basis = tag(o).lower() if o_cost is not None else "pending"
    cost_x = ratio(fr.get("cost_per_1m_usd"), o.get("cost_per_1m_usd"))
    fbrand = fname.split(",")[0]  # "Claude Opus 5.5, 20-shot" -> "Claude Opus 5.5"
    fsay = "Claude" if "Claude" in fname else fbrand
    GW, GAP, RH, TOP = 3.84, 0.155, 1.82, 1.62

    def cell(col, y, h, title_, w=GW, x=None, line=LINE):
        x = 0.75 + col * (GW + GAP) if x is None else x
        card(s, x, y, w, h, fill=PANEL, line=line, adj=0.05, anim=True)
        text(s, x + 0.22, y + 0.17, w - 0.44, 0.22, title_.upper(), size=9.5, color=ACCENT, bold=True, track=1.3)
        return x

    def items(x, y, rows, w=GW - 0.44, h=1.3, size=10.5):
        """rows: (bold lead, rest, dim). Real hanging bullets, calm grey dots as in the web deck."""
        paras = [([(lead, {"bold": True, "color": DIM if dim else TEXT})] if lead else []) +
                 ([(rest, {"color": DIM if dim else MUTED})] if rest else []) for lead, rest, dim in rows]
        text(s, x, y, w, h, paras, size=size, spacing=3.5, bullet=BASE)

    r1, r2 = TOP, TOP + RH + GAP
    x = cell(0, r1, RH, "Who pays")
    items(x + 0.22, r1 + 0.5, [("County and city emergency operations centers", "", False),
                               ("911 centers", " and state emergency management", False),
                               ("Humanitarian organizations", " that run response operations", False),
                               ("Dispatch-software vendors", " that embed the API", False)])
    x = cell(1, r1, RH, "Product surfaces")
    items(x + 0.22, r1 + 0.5, [("Dispatch console: ", "live feed, map and priority queue", False),
                               ("API ", "that screens posts for an agency's own tools", False),
                               ("Private deployment ", "in the agency's own cloud: planned, not built", False)])
    x = cell(2, r1, RH, "Pricing model")
    items(x + 0.22, r1 + 0.5, [("Annual subscription per agency, ", "budgeted before the storm", False),
                               ("Usage tier ", "for high-volume screening in a surge", False),
                               ("", "No price list yet: the pilots will set it", False)])
    x = cell(0, r2, RH, "Why it lasts", line=MOAT_LINE)
    text(s, x + 0.22, r2 + 0.44, 1.1, 0.42, usd(o_cost), size=22, font=MONO, color=TEXT if o_cost is not None else DIM,
         anim=True, name="Unit cost")
    text(s, x + 1.22, r2 + 0.45, GW - 1.4, 0.42,
         [[(f"per 1M posts, {basis}", {"color": MUTED})],
          [(f"{fbrand}: {usd(f_cost)}" + (f" ({cost_x:.0f}× more)" if cost_x else ""), {"color": DIM})]],
         size=8.5, spacing=1)
    items(x + 0.22, r2 + 0.92, [("Margin: ", (f"{usd(o_full)} per 1M even at full price" if o_full is not None
                                              else "screening every post is affordable"), False),
                                ("Data moat: ", "dispatcher actions become labels", False),
                                ("Open weights: ", "a path to running it privately", False)], h=0.82, size=10)
    x = cell(1, r2, RH, "Go-to-market")
    items(x + 0.22, r2 + 0.5, [("Pilots ", "with emergency operations centers: replay a past disaster, then shadow mode", False),
                               ("Expand ", "by region and language", False),
                               ("Partnerships with dispatch-software vendors ", "to reach agencies on their systems", False)])
    x = cell(2, r2, RH, "Next 90 days")
    items(x + 0.22, r2 + 0.5, [("", "Recruit pilot EOCs and one relief NGO", False),
                               ("", "Dedicated Fireworks deployment for surge latency", False),
                               ("", "Export the LoRA adapter for private deployment", False),
                               ("", "Multilingual evaluation", False)])
    r3 = r2 + RH + GAP
    fh = 6.94 - r3
    x = cell(0, r3, fh, "Team", w=5.45)
    text(s, x + 0.22, r3 + 0.45, 5.0, 0.4, [[("NarasingaMoorthy VeiluKanthaPerumal", {"bold": True}),
                                            ("  @vnmoorthy", {"font": MONO, "size": 9, "color": DIM})],
                                           [("TMLR papers on LLM downshifting and PAVO voice routing", {"size": 9.5, "color": MUTED})]],
         size=11, spacing=1)
    text(s, x + 0.22, r3 + 0.86, 5.0, 0.4, [[("Seth Caldwell", {"bold": True})],
                                           [("masky.ai", {"size": 9.5, "color": MUTED})]], size=11, spacing=1)
    x = cell(0, r3, fh, "The ask", w=GW * 3 + GAP * 2 - 5.45 - GAP, x=0.75 + 5.45 + GAP)
    text(s, x + 0.22, r3 + 0.45, 5.8, 0.62,
         [[(f"{i:02d}  ", {"font": MONO, "color": ACCENT, "size": 9.5}), (h_, {"bold": True}), (b_, {"color": MUTED})]
          for i, (h_, b_) in enumerate([("Pilot partners: ", "one EOC and one relief NGO for the next storm season"),
                                        ("Dedicated Fireworks capacity; ", "Microsoft Foundry for agencies"),
                                        ("Introductions ", "to dispatch and CAD software teams")], 1)], size=10.5, spacing=2.5, anim=True)
    text(s, x + 0.22, r3 + 1.06, 5.8, 0.2, [[("repo ", {"color": ACCENT}), (REPO, {}), ("   demo ", {"color": ACCENT}), (SITE, {})]],
         size=8.5, font=MONO)
    pitch = (f"As a company: emergency operations centers, 911 centers and relief NGOs pay an annual subscription, plus a usage "
             f"tier for surges. Screening a million posts costs {usd(o_cost)}, {basis}, against {usd(f_cost)} on {fsay}, "
             "leaving room for strong margins, and every dispatcher decision becomes training data. Go-to-market: pilots "
             "next hurricane season, then dispatch-software partners and new regions. We're asking for pilot partners. "
             "Thank you.")
    notes(s, "About 24 seconds, word for word (same script as guide/STORYBOARD.md, 2:36 to 3:00):\n" + pitch + "\n"
             "If asked: the product is the dispatch console and an API for an agency's own tools; private deployment is planned, not built. "
             "There is no price list yet; the pilots set it. "
             + (f"The {usd(o_cost)} includes Fireworks' limited-time 50% discount; at full price it is {usd(o_full)} per million "
                f"posts, still about {ratio(fr.get('cost_per_1m_usd'), o_full) or 0:.0f}x below {fbrand}. "
                if o_full is not None and ratio(fr.get('cost_per_1m_usd'), o_full) else "")
             + "Open weights mean an agency can run it privately; exporting the LoRA adapter is on the 90-day list. "
             "HumAID is licensed non-commercial, so a commercial product retrains on licensed or agency data. "
             "No customers, partners or contracts exist yet: pilots are the ask.\n"
             f"Team: NarasingaMoorthy VeiluKanthaPerumal and Seth Caldwell. Code: {REPO}. Demo: {SITE}.\n"
             "Transition: fade. Leave this slide up for questions.")
    add_transition_and_timing(s, "fade")

    apply_theme(deck.prs)
    deck.finish()

    out.parent.mkdir(parents=True, exist_ok=True)
    deck.prs.save(out)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "deck" / "RescueRadar.pptx"))
    a = ap.parse_args(argv)
    D = Data()
    out = build(D, Path(a.out))
    # sanity check: reopen with python-pptx and confirm every slide has notes, a transition and its animations
    prs = Presentation(str(out))
    for i, sl in enumerate(prs.slides, 1):
        x = sl._element
        assert sl.has_notes_slide and sl.notes_slide.notes_text_frame.text.strip(), f"slide {i} has no notes"
        assert x.find(qn("p:transition")) is not None, f"slide {i} has no transition"
    print(f"wrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}: {len(prs.slides)} slides, "
          f"results {'loaded' if D.systems else 'missing (n/a)'}, ours={'yes' if D.ours else 'n/a'}, "
          f"frontier={'yes' if D.front else 'n/a'}, replay posts={len(D.posts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
