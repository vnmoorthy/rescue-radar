"""Live frontier baseline for the Head-to-Head view, with the same prompt and 20 examples as the benchmark.

Provider is chosen by RR_FRONTIER: "claude" (Claude Opus 5.5), "gpt" (GPT-6.1 Terra) or "auto" (default:
Claude, switching to GPT-6.1 Terra if the Anthropic account is out of quota). Every result names the model that
actually answered, so the console never mislabels a comparison.
"""
import threading, time
from functools import lru_cache

from rr.env import load_env
from rr.labels import SYSTEM, parse_label

env = load_env()
CLAUDE_MODEL = env.get("BASELINE_MODEL", "claude-opus-5-5")
GPT_MODEL = "gpt-6.1-terra"
CLAUDE_NAME, GPT_NAME = "Claude Opus 5.5 (20-shot)", "GPT-6.1 Terra (20-shot)"
# USD per million tokens, list prices: Claude Opus 5.5 $4 in / $20 out; GPT-6.1 Terra $1 in / $5 out.
PRICE_IN, PRICE_OUT = 4.0, 20.0
GPT_PRICE_IN, GPT_PRICE_OUT = 1.0, 5.0
_state = {"claude_blocked": False, "probed": False}
_lock = threading.Lock()


def _is_quota_error(e):
    msg = str(e).lower()
    return "usage limit" in msg or "credit balance" in msg


def _probe_claude():
    """One tiny request: if the Anthropic account is out of quota it fails at once and costs nothing."""
    try:
        _claude().messages.create(model=CLAUDE_MODEL, max_tokens=16, messages=[{"role": "user", "content": "ok"}])
    except Exception as e:
        if _is_quota_error(e):
            with _lock:
                _state["claude_blocked"] = True


def frontier_name():
    mode = env.get("RR_FRONTIER", "auto")
    if mode == "auto" and not _state["probed"] and env.get("ANTHROPIC_API_KEY"):
        _state["probed"] = True
        threading.Thread(target=_probe_claude, daemon=True).start()
    if mode == "gpt" or (mode == "auto" and _state["claude_blocked"]):
        return GPT_NAME
    return CLAUDE_NAME


FRONTIER_NAME = CLAUDE_NAME  # kept for imports; use frontier_name() for the live value


@lru_cache(maxsize=1)
def _claude():
    import anthropic
    if not env.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=env["ANTHROPIC_API_KEY"], max_retries=2)


@lru_cache(maxsize=1)
def _openai():
    from openai import OpenAI
    if not env.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set.")
    return OpenAI(api_key=env["OPENAI_API_KEY"], max_retries=2)


@lru_cache(maxsize=1)
def _shot_messages():
    from rr.baseline import few_shots
    msgs = []
    for s in few_shots():
        msgs += [{"role": "user", "content": f"Post: {s['text']}"}, {"role": "assistant", "content": s["label"]}]
    return msgs


def cost_usd(in_tok, out_tok, gpt=False):
    pin, pout = (GPT_PRICE_IN, GPT_PRICE_OUT) if gpt else (PRICE_IN, PRICE_OUT)
    return (in_tok * pin + out_tok * pout) / 1e6


def _ask_claude(text):
    t0 = time.time()
    resp = _claude().messages.create(model=CLAUDE_MODEL, max_tokens=4096, system=SYSTEM, thinking={"type": "adaptive"},
                                     output_config={"effort": "medium"},
                                     messages=_shot_messages() + [{"role": "user", "content": f"Post: {text}"}])
    raw = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    if resp.stop_reason == "refusal" or not raw.strip():
        raise RuntimeError(f"Claude Opus 5.5 returned no label (stop_reason={resp.stop_reason}).")
    return {"label": parse_label(raw), "latency_ms": round((time.time() - t0) * 1000, 1), "in_tok": resp.usage.input_tokens,
            "out_tok": resp.usage.output_tokens, "cost_usd": cost_usd(resp.usage.input_tokens, resp.usage.output_tokens),
            "model": CLAUDE_NAME, "raw": raw[:80]}


def _ask_gpt(text):
    t0 = time.time()
    resp = _openai().chat.completions.create(model=GPT_MODEL, max_completion_tokens=4096,
                                             messages=[{"role": "system", "content": SYSTEM}] + _shot_messages()
                                             + [{"role": "user", "content": f"Post: {text}"}])
    raw = resp.choices[0].message.content or ""
    if not raw.strip():
        raise RuntimeError("GPT-6.1 Terra returned no label.")
    u = resp.usage
    return {"label": parse_label(raw), "latency_ms": round((time.time() - t0) * 1000, 1), "in_tok": u.prompt_tokens,
            "out_tok": u.completion_tokens, "cost_usd": cost_usd(u.prompt_tokens, u.completion_tokens, gpt=True),
            "model": GPT_NAME, "raw": raw[:80]}


def classify_frontier(text):
    mode = env.get("RR_FRONTIER", "auto")
    try:
        if mode == "gpt" or (mode == "auto" and _state["claude_blocked"]):
            return _ask_gpt(text)
        try:
            return _ask_claude(text)
        except Exception as e:
            if mode == "auto" and _is_quota_error(e):
                with _lock:
                    _state["claude_blocked"] = True
                return _ask_gpt(text)
            raise
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Frontier call failed: {type(e).__name__}") from e
