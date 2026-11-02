"""Promote the newest sampler checkpoint of a training run to a permanent Fireworks model.

The promoted model (accounts/<account>/models/<id>) outlives the training session, so it can be served from a
dedicated Fireworks deployment or deployed to Microsoft Foundry.
usage: python -m rr.promote <tag> <output_model_id>     e.g. python -m rr.promote _full rescue-radar-nemotron
"""
import json, sys
from pathlib import Path

from rr.env import load_env

env = load_env()
from fireworks.training.sdk import FireworksClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(tag, model_id):
    ck = json.loads((ROOT / "data" / f"checkpoints{tag}.json").read_text())
    acct = env["FIREWORKS_ACCOUNT_ID"]
    session = f"accounts/{acct}/trainingSessions/{ck['session']}"
    fc = FireworksClient(api_key=env["FIREWORKS_API_KEY"])
    cks = [c for c in fc.list_training_session_checkpoints(session) if c.get("promotable")]
    if not cks:
        sys.exit(f"no promotable checkpoints in {session}")
    active = ROOT / "data" / "active_model.json"
    chosen = json.loads(active.read_text()) if (tag == "_full" and active.exists()) else ck["checkpoints"][-1]
    want = chosen["path"].rsplit("/", 1)[-1]
    match = [c for c in cks if c["name"].endswith(want)] or sorted(cks, key=lambda c: c.get("createTime", ""))[-1:]
    target = match[0]
    print("promoting", target["name"], target.get("checkpointType"))
    model = fc.promote_session_checkpoint(name=target["name"], output_model_id=model_id, base_model=ck["base_model"])
    out = {"model": model.get("name"), "from_checkpoint": target["name"], "step": chosen["step"],
           "base_model": ck["base_model"], "state": model.get("state")}
    (ROOT / "data" / f"promoted{tag}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
