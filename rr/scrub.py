"""PII redaction before a human dispatcher sees a post.

scrub(text) -> (redacted_text, redactions) where each redaction is {"type", "start", "end", "orig_start", "orig_end"}:
start/end index the placeholder inside redacted_text (so the console can highlight it), orig_start/orig_end index the
removed span in the original text. Placeholders: [PERSON] [PHONE] [EMAIL] [HANDLE] [URL] [ADDRESS].

Two engines:
  presidio  Microsoft Presidio (presidio-analyzer with spaCy en_core_web_sm) finds PERSON, PHONE and EMAIL, merged
            with the regexes below for HANDLE, URL, ADDRESS and non-US phone formats; presidio-anonymizer applies it.
  regex     the regexes alone (PHONE, EMAIL, HANDLE, URL, ADDRESS; no PERSON). Used when Presidio or the spaCy
            model is not installed, fails to load, or RR_SCRUBBER=regex.
mode() says which one is active. Presidio loads lazily (about 10 s) on the first scrub.
"""
import importlib.util
import os
import re
import threading

TYPES = ("PERSON", "PHONE", "EMAIL", "HANDLE", "URL", "ADDRESS")
# Lower wins when two detections overlap.
PRIORITY = {"EMAIL": 0, "URL": 1, "HANDLE": 2, "ADDRESS": 3, "PHONE": 4, "PERSON": 5}

EMAIL_RE = re.compile(r"(?<![\w.+%-])[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
URL_RE = re.compile(
    r"(?:\b(?:https?://|www\.)[^\s<>\"']+)"
    r"|(?:\b(?:[A-Za-z0-9-]+\.)+(?:com|org|net|gov|edu|int|io|ly|co|me|info|news|tv|pk|zw|mz|mw|bs|us|uk|ca|in)"
    r"(?:/[^\s<>\"']*)?(?![\w@.-]))", re.IGNORECASE)
HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]{1,30}")
PHONE_RE = re.compile(r"(?<![\w/.,+])\+?\(?\d[\d().\s-]{5,20}\d(?![\w/])")
_SUFFIX = (r"(?:[Ss]treet|St|[Aa]venue|Ave|[Rr]oad|Rd|[Bb]oulevard|Blvd|[Ll]ane|Ln|[Dd]rive|Dr|[Cc]ourt|Ct|[Hh]ighway|Hwy|"
           r"[Pp]lace|Pl|[Tt]errace|Ter|[Cc]ircle|Cir|[Pp]arkway|Pkwy|[Tt]rail|Trl|[Ss]quare|Sq|[Ww]ay)")
ADDRESS_RE = re.compile(r"\b\d{1,6}[A-Za-z]?\s+(?:(?:[NSEW]\.?|North|South|East|West)\s+)?"
                        r"(?:(?:[A-Z][A-Za-z'.-]*|\d+(?:st|nd|rd|th))\s+){1,4}" + _SUFFIX + r"\b\.?")
_PLACEHOLDER = re.compile(r"\[(?:%s)\]" % "|".join(TYPES))

# Bump when the redaction rules change: rr.server keys its replay scrub cache on it, so old results are not reused.
RULES_VERSION = 2

# Storm names that are also common first names: a PERSON detection made only of these (plus storm words) is skipped
# only when it is used as a storm name ("Hurricane Maria", "#Florence"), never because one word of a person's
# full name matches ("Michael Brown", "Florence Smith", "Call Maria at ...").
_NAME_STORMS = {"maria", "michael", "andrew", "florence", "matthew", "harvey", "irma", "katrina", "sandy", "kenneth"}
_STORM_WORDS = {"hurricane", "cyclone", "typhoon", "storm", "tropical", "ts", "tc"}
_STORM_BEFORE = re.compile(r"(?:hurricane|cyclone|typhoon|storm|ts|tc)[\s#]*$", re.IGNORECASE)
# Words spaCy's small model tends to tag as PERSON in disaster posts that are not private people.
_NOT_PEOPLE = {
    "dorian", "idai", "humberto", "lorenzo", "allah", "god", "jesus", "christ", "lord", "ameen", "amen", "hurricane",
    "cyclone", "storm", "earthquake", "flood", "floods", "red cross", "fema", "unicef", "wfp", "ndma", "ispr", "nhc",
    "breaking", "update", "rip", "prayers", "pray", "ya allah", "insha allah", "inshallah", "mashallah", "mar", "lago",
    "zim", "moz", "kashmiris", "pakistanis", "zimbabweans", "nebraskans", "floridians", "bahamians", "info",
    # public officials named in the posts are not private individuals
    "trump", "donald trump", "trumps", "desantis", "ron desantis", "mcmaster", "henry mcmaster", "roy cooper", "kemp",
    "brian kemp", "imran khan", "erdogan", "mnangagwa", "nyusi", "filipe nyusi", "ricketts", "pete ricketts",
    "ben sasse", "sasse", "kim reynolds", "modi", "firdous ashiq awan", "obama", "pence", "mike pence",
}
_LEAD_WORDS = {"call", "contact", "dm", "ask", "tell", "dear", "pray", "praying", "thank", "thanks", "please", "help",
               "rescue", "find", "missing", "rip", "breaking", "update", "via", "cc", "sir", "madam", "mr", "mrs", "ms"}


def _regex_spans(text):
    spans = []
    for typ, rx in (("EMAIL", EMAIL_RE), ("URL", URL_RE), ("HANDLE", HANDLE_RE), ("ADDRESS", ADDRESS_RE)):
        for m in rx.finditer(text):
            s, e = m.start(), m.end()
            if typ == "URL":
                while e > s and text[e - 1] in ".,;:!?)]}'\"":
                    e -= 1
            spans.append((s, e, typ))
    for m in PHONE_RE.finditer(text):
        s, e = m.start(), m.end()
        cand = text[s:e]
        if cand.startswith("(") and ")" not in cand:  # "(1935" style
            s += 1
            cand = cand[1:]
        while cand and cand[-1] in ")-. ":
            cand = cand[:-1]
            e -= 1
        digits = re.sub(r"\D", "", cand)
        if not 7 <= len(digits) <= 15:
            continue
        if re.search(r"\s[-.]\s|\s{2,}", cand):  # "1935 - 84", score lines
            continue
        if re.fullmatch(r"(?:19|20)\d\d\s*[-/]\s*(?:19|20)?\d\d(?:\s*[-/]\s*\d\d)?", cand):  # years, dates
            continue
        if re.fullmatch(r"\d+", cand) and len(digits) < 10:  # bare short numbers are counts, not phones
            continue
        spans.append((s, e, "PHONE"))
    return spans


def _resolve(spans):
    """Drop overlaps: higher priority type first, then the longer span."""
    keep = []
    for s, e, t in sorted(set(spans), key=lambda x: (PRIORITY[x[2]], -(x[1] - x[0]), x[0])):
        if s < e and all(e <= ks or s >= ke for ks, ke, _ in keep):
            keep.append((s, e, t))
    return sorted(keep)


def _apply(text, spans):
    out, reds, pos = [], [], 0
    for s, e, t in spans:
        out.append(text[pos:s])
        start = sum(len(x) for x in out)
        ph = f"[{t}]"
        out.append(ph)
        reds.append({"type": t, "start": start, "end": start + len(ph), "orig_start": s, "orig_end": e})
        pos = e
    out.append(text[pos:])
    return "".join(out), reds


_LEAD_RE = re.compile(r"(?:(?:%s)\b[\s.,:;!]*)+" % "|".join(sorted(_LEAD_WORDS, key=len, reverse=True)), re.IGNORECASE)


def _person_ok(text, s, e):
    """Keep a PERSON detection only if it plausibly names a private person (not a storm, deity or place)."""
    from rr.geo import all_names
    m = _LEAD_RE.match(text, s, e)
    if m:
        s = m.end()
    span = text[s:e].strip()
    if (not span or any(c.isdigit() for c in span) or span[:1] in "#@[" or not span[:1].isupper()
            or (s > 0 and text[s - 1] in "#@") or _PLACEHOLDER.search(span)):
        return None
    s = text.index(span, s)
    e = s + len(span)
    words = [w.strip(".,:;!?'\"()").lower() for w in span.split()]
    low = " ".join(words)
    places = all_names()
    if low in _NOT_PEOPLE or low in places or span.isupper() or any(w in _NOT_PEOPLE for w in words):
        return None
    if (words and all(w in _NAME_STORMS or w in _STORM_WORDS for w in words)
            and (any(w in _STORM_WORDS for w in words) or _STORM_BEFORE.search(text[max(0, s - 24):s]))):
        return None  # "Hurricane Maria", "Cyclone Kenneth": a storm, not a person
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            if " ".join(words[i:i + n]) in places:
                return None
    return (s, e, "PERSON")


class _Presidio:
    def __init__(self):
        from presidio_analyzer import AnalyzerEngine, BatchAnalyzerEngine
        from presidio_analyzer.nlp_engine import NlpEngineProvider
        from presidio_anonymizer import AnonymizerEngine
        from presidio_anonymizer.entities import OperatorConfig
        provider = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}]})
        self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine(), supported_languages=["en"])
        self.batch = BatchAnalyzerEngine(analyzer_engine=self.analyzer)
        self.anonymizer = AnonymizerEngine()
        self.ops = {t: OperatorConfig("replace", {"new_value": f"[{t}]"}) for t in TYPES}
        self.lock = threading.Lock()
        self.entities = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS"]
        self.map = {"PERSON": "PERSON", "PHONE_NUMBER": "PHONE", "EMAIL_ADDRESS": "EMAIL"}

    def spans(self, texts):
        with self.lock:
            if len(texts) == 1:
                results = [self.analyzer.analyze(text=texts[0], language="en", entities=self.entities)]
            else:
                results = self.batch.analyze_iterator(texts, language="en", batch_size=64, entities=self.entities)
        out = []
        for text, res in zip(texts, results):
            sp = []
            for r in res:
                t = self.map.get(r.entity_type)
                if t == "PERSON":
                    if r.score < 0.6:
                        continue
                    ok = _person_ok(text, r.start, r.end)
                    if ok:
                        sp.append(ok)
                elif t and r.score >= 0.4:
                    sp.append((r.start, r.end, t))
            out.append(sp)
        return out

    def apply(self, text, spans):
        from presidio_anonymizer.entities import RecognizerResult
        if not spans:
            return text, []
        res = self.anonymizer.anonymize(
            text=text, operators=self.ops,
            analyzer_results=[RecognizerResult(entity_type=t, start=s, end=e, score=1.0) for s, e, t in spans])
        items = sorted(res.items, key=lambda i: i.start)
        mine = _apply(text, spans)
        if len(items) != len(spans) or res.text != mine[0]:  # anonymizer merged neighbours: keep exact spans
            return mine
        reds = [{"type": i.entity_type, "start": i.start, "end": i.end, "orig_start": s, "orig_end": e}
                for i, (s, e, _) in zip(items, spans)]
        return res.text, reds


_engine, _mode, _error, _lock = None, None, None, threading.Lock()


def available():
    """Presidio and the small spaCy model are installed (does not load them)."""
    return all(importlib.util.find_spec(m) is not None for m in ("presidio_analyzer", "presidio_anonymizer",
                                                                  "en_core_web_sm"))


def mode():
    """'presidio' or 'regex': the engine scrub() uses (decided without loading Presidio if not loaded yet)."""
    if _mode:
        return _mode
    if os.environ.get("RR_SCRUBBER", "").lower() == "regex" or not available():
        return "regex"
    return "presidio"


def status():
    return {"engine": mode(), "loaded": _mode is not None, "error": _error}


def _get():
    global _engine, _mode, _error
    if _mode:
        return _engine
    with _lock:
        if _mode:
            return _engine
        if mode() == "presidio":
            try:
                _engine = _Presidio()
                _mode = "presidio"
                return _engine
            except Exception as e:  # missing model, version clash: fall back, but say so in /api/health
                _error = f"Presidio failed to load, using regex: {type(e).__name__}: {str(e)[:160]}"
        _engine, _mode = None, "regex"
        return None


def scrub_many(texts):
    """Redact a list of posts. Returns [(redacted_text, redactions)] in order."""
    texts = [t or "" for t in texts]
    eng = _get()
    if not texts:
        return []
    extra = eng.spans(texts) if eng else [[] for _ in texts]
    out = []
    for text, sp in zip(texts, extra):
        protected = [(m.start(), m.end()) for m in _PLACEHOLDER.finditer(text)]
        spans = [x for x in _resolve(_regex_spans(text) + sp)
                 if all(x[1] <= ps or x[0] >= pe for ps, pe in protected)]
        out.append(eng.apply(text, spans) if eng else _apply(text, spans))
    return out


def scrub(text):
    """(redacted_text, redactions) for one post."""
    return scrub_many([text])[0]
