"""Build the held-out-disaster split for Rescue Radar.

Train: every HumAID disaster from 2016-2018. Test: the four 2019 disasters, never seen in training.
Tweets whose normalized text also appears in test are dropped from training (retweets, copies).
Outputs (data/):
  test_full.jsonl   all test tweets (15k)
  eval.jsonl        seeded random sample of test tweets, the shared eval set for every system
  train_sft.jsonl   capped-per-class training set in Fireworks chat format
"""
import json, random, re, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from rr.labels import LABELS, build_messages

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"
HF = "https://huggingface.co/datasets/QCRI/HumAID-events/resolve/main"
EVENTS = ["hurricane_florence_2018", "kaikoura_earthquake_2016", "kerala_floods_2018", "hurricane_harvey_2017",
          "hurricane_maria_2017", "midwestern_us_floods_2019", "puebla_mexico_earthquake_2017", "maryland_floods_2018",
          "hurricane_irma_2017", "ecuador_earthquake_2016", "cyclone_idai_2019", "canada_wildfires_2016",
          "italy_earthquake_aug_2016", "greece_wildfires_2018", "hurricane_dorian_2019", "california_wildfires_2018",
          "pakistan_earthquake_2019", "hurricane_matthew_2016", "srilanka_floods_2017"]
TEST_EVENTS = {e for e in EVENTS if e.endswith("2019")}
EVAL_N = 3000
CAP_PER_CLASS = 1500
SEED = 7


def norm(t):
    t = t.lower()
    t = re.sub(r"^rt @\w+:?", "", t)
    t = re.sub(r"https?://\S+|@\w+|#", " ", t)
    return re.sub(r"[^a-z0-9 ]+", " ", re.sub(r"\s+", " ", t)).strip()


def load_event(e):
    rows = []
    for split in ("train", "dev", "test"):
        p = RAW / e / f"{split}.json"
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(f"{HF}/{e}/{split}.json", p)
        rows += json.load(open(p))
    return [{"id": str(r["tweet_id"]), "event": e, "text": r["tweet_text"], "label": r["class_label"]} for r in rows]


def main():
    train, test = [], []
    for e in EVENTS:
        (test if e in TEST_EVENTS else train).extend(load_event(e))
    test_keys = {norm(r["text"]) for r in test}
    before = len(train)
    train = [r for r in train if norm(r["text"]) not in test_keys and r["label"] in LABELS]
    test = [r for r in test if r["label"] in LABELS]
    print(f"train {before} -> {len(train)} after removing {before - len(train)} test-overlap tweets; test {len(test)}")

    rng = random.Random(SEED)
    by_event = defaultdict(list)
    for r in test:
        by_event[r["event"]].append(r)
    eval_rows = []
    for e, rows in sorted(by_event.items()):
        k = round(EVAL_N * len(rows) / len(test))
        eval_rows += rng.sample(rows, k)
    rng.shuffle(eval_rows)

    by_label = defaultdict(list)
    for r in train:
        by_label[r["label"]].append(r)
    sft = []
    for lab, rows in sorted(by_label.items()):
        rng.shuffle(rows)
        sft += rows[:CAP_PER_CLASS]
    rng.shuffle(sft)

    OUT.mkdir(exist_ok=True)
    with open(OUT / "test_full.jsonl", "w") as f:
        for r in test:
            f.write(json.dumps(r) + "\n")
    with open(OUT / "eval.jsonl", "w") as f:
        for r in eval_rows:
            f.write(json.dumps(r) + "\n")
    with open(OUT / "train_sft.jsonl", "w") as f:
        for r in sft:
            msgs = build_messages(r["text"]) + [{"role": "assistant", "content": r["label"]}]
            f.write(json.dumps({"messages": msgs}) + "\n")
    print("eval", len(eval_rows), Counter(r["event"] for r in eval_rows))
    print("eval labels", Counter(r["label"] for r in eval_rows).most_common())
    print("sft", len(sft), Counter(r["label"] for r in sft).most_common())


if __name__ == "__main__":
    main()
