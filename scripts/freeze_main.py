"""Pre-registered freeze (guide/PREREGISTRATION.md): at 14:55 PT pick the newest checkpoint of the main run saved
by then, by step number, and record it in data/active_model.json. Test scores play no part in the choice."""
import json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUTOFF = "14:55:00"
d = json.loads((ROOT / "data" / "checkpoints_full.json").read_text())
ok = [c for c in d["checkpoints"] if c["at"] <= CUTOFF]
c = max(ok, key=lambda c: c["step"])
out = {"base_model": d["base_model"], "path": c["path"], "step": c["step"], "at": c["at"],
       "name": f"Rescue Radar: Nemotron 3.5 Super + LoRA (main run, step {c['step']})",
       "rule": f"newest checkpoint of the 13,839-example run saved by {CUTOFF} PT, chosen by step number",
       "frozen_at": time.strftime("%H:%M:%S"), "run_finished": any(x.get("step") == 432 for x in d["checkpoints"])}
(ROOT / "data" / "active_model.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
