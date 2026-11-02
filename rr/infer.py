"""The live Rescue Radar model.

Serves the fine-tuned LoRA checkpoint through Fireworks serverless sampling. The same code path is used for
the benchmark and for the live console, so what the demo shows is what was scored.

Which weights: data/active_model.json ({"base_model", "path", "name"}) if present, written by rr.evaluate
when it picks the best checkpoint; otherwise the newest checkpoint in data/checkpoints*.json.
RR_MODE=base serves the untuned base model through the same path (the "before" baseline).
"""
import json, os, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rr.env import load_env
from rr.labels import build_messages, parse_label

env = load_env()
ROOT = Path(__file__).resolve().parent.parent
SERVERLESS = "https://api.fireworks.ai/training/v1/serverless"
TOKENIZERS = {
    "accounts/fireworks/models/nvidia-nemotron-3p5-super-vl-120b-a12b-bf16": "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16",
    "accounts/fireworks/models/glm-5p3-flash": "zai-org/GLM-5.3-Flash",
}
DEFAULT_BASE = "accounts/fireworks/models/nvidia-nemotron-3p5-super-vl-120b-a12b-bf16"
SHORT = {DEFAULT_BASE: "Nemotron 3.5 Super", "accounts/fireworks/models/glm-5p3-flash": "GLM 5.3 Flash"}


def latest_checkpoint():
    active = ROOT / "data" / "active_model.json"
    if active.exists():
        return json.loads(active.read_text())
    best = None
    for p in sorted((ROOT / "data").glob("checkpoints*.json")):
        d = json.loads(p.read_text())
        if d.get("checkpoints"):
            c = d["checkpoints"][-1]
            if best is None or c["at"] > best["at"]:
                best = {"base_model": d["base_model"], "path": c["path"], "at": c["at"], "step": c["step"],
                        "name": f"Rescue Radar: {SHORT.get(d['base_model'], 'open model')} + LoRA (step {c['step']})"}
    return best


class SamplerClassifier:
    def __init__(self, base_model, path=None, name=None):
        from fireworks.training.sdk import FiretitanServiceClient, types
        from transformers import AutoTokenizer
        if not env.get("FIREWORKS_API_KEY"):
            raise RuntimeError("FIREWORKS_API_KEY is not set, so the Rescue Radar model is unavailable.")
        self.types = types
        self.base_model, self.path = base_model, path
        self.kind = "finetuned" if path else "base"
        self.name = name or (f"{SHORT.get(base_model, base_model)} (base, no fine-tuning)")
        self.tok = AutoTokenizer.from_pretrained(TOKENIZERS[base_model], token=env.get("HF_TOKEN"))
        svc = FiretitanServiceClient(api_key=env["FIREWORKS_API_KEY"], base_url=SERVERLESS)
        self.sampler = (svc.create_sampling_client(model_path=path, tokenizer=self.tok) if path
                        else svc.create_sampling_client(base_model=base_model, tokenizer=self.tok))
        self.params = types.SamplingParams(max_tokens=16, temperature=0.0)
        self.lock = threading.Lock()

    def _prompt(self, text):
        # Reasoning models open a <think> block; closing it makes the model answer with the label only.
        s = self.tok.apply_chat_template(build_messages(text), add_generation_prompt=True, tokenize=False) + "</think>"
        return self.types.ModelInput.from_ints(self.tok.encode(s, add_special_tokens=False))

    def classify(self, texts, workers=32):
        out = [None] * len(texts)

        def one(i):
            t0 = time.time()
            res = self.sampler.sample(prompt=self._prompt(texts[i]), num_samples=1, sampling_params=self.params).result()
            raw = self.tok.decode(res.sequences[0].tokens, skip_special_tokens=True)
            out[i] = {"label": parse_label(raw), "latency_ms": round((time.time() - t0) * 1000, 1), "raw": raw.strip()[:80]}

        try:
            with ThreadPoolExecutor(max(1, min(workers, len(texts)))) as ex:
                list(ex.map(one, range(len(texts))))
        except Exception as e:
            raise RuntimeError(f"Rescue Radar model call failed: {type(e).__name__}: {str(e)[:200]}") from e
        return out


_clf, _clf_lock = None, threading.Lock()


def get_classifier():
    global _clf
    with _clf_lock:
        if _clf is None:
            if os.environ.get("RR_MODE") == "base":
                _clf = SamplerClassifier(os.environ.get("RR_BASE", DEFAULT_BASE))
            else:
                ck = latest_checkpoint()
                if not ck:
                    raise RuntimeError("No fine-tuned checkpoint found yet. Run python -m rr.train first.")
                _clf = SamplerClassifier(ck["base_model"], ck["path"], ck.get("name"))
        return _clf
