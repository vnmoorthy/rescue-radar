"""Upload the SFT dataset and launch a LoRA fine-tuning job on Fireworks.

usage: python3 -m rr.finetune launch [base_model]   |   python3 -m rr.finetune status <job_name>
"""
import json, sys, time, urllib.error, urllib.request
from pathlib import Path

from rr.env import load_env

ROOT = Path(__file__).resolve().parent.parent
env = load_env()
ACCT = env["FIREWORKS_ACCOUNT_ID"]
API = f"https://api.fireworks.ai/v1/accounts/{ACCT}"
AUTH = {"Authorization": f"Bearer {env['FIREWORKS_API_KEY']}"}


def call(method, url, body=None, files=None):
    if files:
        boundary = "rrboundary7"
        name, path = files
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{Path(path).name}\"\r\n"
                f"Content-Type: application/jsonl\r\n\r\n").encode() + Path(path).read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        headers = {**AUTH, "Content-Type": f"multipart/form-data; boundary={boundary}"}
    else:
        data = json.dumps(body).encode() if body is not None else None
        headers = {**AUTH, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            txt = r.read()
            return r.status, json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600]


def launch(base_model):
    stamp = time.strftime("%H%M")
    ds_id = f"humaid-sft-{stamp}"
    path = ROOT / "data" / "train_sft.jsonl"
    n = sum(1 for _ in open(path))
    print("create dataset", call("POST", f"{API}/datasets", {"datasetId": ds_id, "dataset": {"userUploaded": {}, "exampleCount": str(n)}}))
    print("upload", call("POST", f"{API}/datasets/{ds_id}:upload", files=("file", path)))
    for _ in range(30):
        s, d = call("GET", f"{API}/datasets/{ds_id}")
        state = d.get("state") if isinstance(d, dict) else d
        print("dataset state", state)
        if state == "READY":
            break
        time.sleep(5)
    job = {"baseModel": base_model, "dataset": f"accounts/{ACCT}/datasets/{ds_id}",
           "outputModel": f"accounts/{ACCT}/models/rescue-radar-{stamp}", "epochs": 1, "learningRate": 0.0001,
           "loraRank": 16, "maxContextLength": 1024, "displayName": f"rescue-radar-{stamp}"}
    s, d = call("POST", f"{API}/supervisedFineTuningJobs", job)
    print("create job", s, d)
    if s == 200:
        (ROOT / "data" / "job.json").write_text(json.dumps(d, indent=1))


def status(name):
    s, d = call("GET", f"https://api.fireworks.ai/v1/{name}")
    print(s, json.dumps({k: d.get(k) for k in ("name", "state", "status", "outputModel", "createTime", "updateTime", "jobProgress")}, indent=1) if s == 200 else d)


if __name__ == "__main__":
    if sys.argv[1] == "launch":
        launch(sys.argv[2] if len(sys.argv) > 2 else env["BASE_MODEL"])
    else:
        status(sys.argv[2])
