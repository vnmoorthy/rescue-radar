"""LoRA fine-tune on Fireworks serverless training.

Supervised cross-entropy on the label tokens only. Saves a sampler checkpoint every SAVE_EVERY steps so the
latest one can be evaluated even if the deadline arrives mid-run.
usage: python -m rr.train [base_model ...]   (tries each base model in order until one starts)
"""
import json, os, random, sys, time
from collections import defaultdict
from pathlib import Path

from rr.env import load_env
from rr.labels import build_messages

load_env()
from fireworks.training.sdk import AdamParams, FiretitanServiceClient, types  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TAG = os.environ.get("RR_TAG", "")
LOG = ROOT / "data" / f"train_log{TAG}.jsonl"
CKPTS = ROOT / "data" / f"checkpoints{TAG}.json"
PER_CLASS = int(os.environ.get("RR_PER_CLASS", 400))
BATCH = int(os.environ.get("RR_BATCH", 32))
LR = float(os.environ.get("RR_LR", 1e-4))
RANK = 16
SAVE_EVERY = 25
TOKENIZERS = {"accounts/fireworks/models/nvidia-nemotron-3p5-super-vl-120b-a12b-bf16": "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16",
              "accounts/fireworks/models/glm-5p3-flash": "zai-org/GLM-5.3-Flash"}
DEFAULT_BASES = ["accounts/fireworks/models/nvidia-nemotron-3p5-super-vl-120b-a12b-bf16",
                 "accounts/fireworks/models/glm-5p3-flash"]


def prompt_tokens(tok, text):
    # Reasoning models open a <think> block; closing it in the prompt makes the model answer with the label only.
    s = tok.apply_chat_template(build_messages(text), add_generation_prompt=True, tokenize=False) + "</think>"
    return tok.encode(s, add_special_tokens=False)


def load_tokenizer(base):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained(TOKENIZERS[base], token=os.environ.get("HF_TOKEN"))


def make_datum(tok, text, label):
    p = list(prompt_tokens(tok, text))
    c = tok.encode(label, add_special_tokens=False) + ([tok.eos_token_id] if tok.eos_token_id is not None else [])
    toks = p + c
    weights = [0.0] * (len(p) - 1) + [1.0] * len(c)
    return types.Datum(model_input=types.ModelInput.from_ints(toks[:-1]),
                       loss_fn_inputs={"target_tokens": toks[1:], "weights": weights})


def load_rows():
    rows = [json.loads(l) for l in open(ROOT / "data" / "train_sft.jsonl")]
    by = defaultdict(list)
    for r in rows:
        by[r["messages"][-1]["content"]].append(r["messages"][-2]["content"].removeprefix("Post: "))
    rng = random.Random(11)
    out = []
    for lab, texts in sorted(by.items()):
        rng.shuffle(texts)
        out += [(t, lab) for t in texts[:PER_CLASS]]
    rng.shuffle(out)
    return out


def main(bases):
    tc = base = svc = None
    for b in bases:
        try:
            svc = FiretitanServiceClient(api_key=os.environ["FIREWORKS_API_KEY"],
                                         base_url="https://api.fireworks.ai/training/v1/serverless")
            tc = svc.create_lora_training_client(base_model=b, rank=RANK)
            base = b
            break
        except Exception as e:
            print(f"cannot start on {b}: {type(e).__name__}: {str(e)[:300]}", flush=True)
    if tc is None:
        sys.exit("no base model could start")
    print(f"training on {base} session={svc.training_session_id} run={tc.run_id}", flush=True)
    tok = load_tokenizer(base)
    rows = load_rows()
    datums = [make_datum(tok, t, l) for t, l in rows]
    print(f"{len(datums)} examples, batch {BATCH}, {len(datums) // BATCH} steps", flush=True)
    ckpts = {"base_model": base, "session": svc.training_session_id, "run": tc.run_id, "checkpoints": []}
    adam = AdamParams(learning_rate=LR, beta1=0.9, beta2=0.95, eps=1e-8, weight_decay=0.0)
    steps = len(datums) // BATCH
    for step in range(steps):
        t0 = time.time()
        batch = datums[step * BATCH:(step + 1) * BATCH]
        out = tc.forward_backward(batch, "cross_entropy").result()
        tc.optim_step(adam).result()
        loss = None
        try:
            m = getattr(out, "metrics", {}) or {}
            loss = next((v for k, v in m.items() if "loss" in k), None)
        except Exception:
            pass
        rec = {"step": step + 1, "loss": loss, "secs": round(time.time() - t0, 2), "at": time.strftime("%H:%M:%S")}
        with open(LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(rec, flush=True)
        if (step + 1) % SAVE_EVERY == 0 or step + 1 == steps:
            path = tc.save_weights_for_sampler(f"rr{TAG[-3:]}-s{step + 1:04d}").result().path
            ckpts["checkpoints"].append({"step": step + 1, "path": path, "at": rec["at"]})
            CKPTS.write_text(json.dumps(ckpts, indent=1))
            print("saved", path, flush=True)
    print("done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_BASES)
