# Deployment

Three ways to run Rescue Radar today, and two production paths that are next steps.

| Path | Status | Needs keys | What you get |
| --- | --- | --- | --- |
| Local server | Works | Yes for live classification | Full console, live model, Head-to-Head, queue |
| GitHub Pages static demo | Works | No | Console replaying recorded predictions, Benchmark view, deck |
| Fireworks serverless sampling | Works (this is what the local server uses) | `FIREWORKS_API_KEY` | The fine-tuned adapter served on shared capacity |
| Fireworks dedicated deployment | Next step | `FIREWORKS_API_KEY`, `FIREWORKS_ACCOUNT_ID` | Reserved capacity, steady latency |
| Microsoft Foundry | Next step, not implemented | Azure subscription | Deployment inside an agency's Azure tenancy |

## 1. Local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# .env in the repo root (git-ignored): FIREWORKS_API_KEY, ANTHROPIC_API_KEY, HF_TOKEN
python -m rr.server                 # http://localhost:8787
```

Settings (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `RR_HOST` | `127.0.0.1` | Bind address. Keep it local unless you add authentication in front. |
| `RR_PORT` | `8787` | Port |
| `RR_MODE` | unset | `base` serves the untuned base model through the same path |
| `RR_SCRUBBER` | auto | `regex` forces the regex redaction engine instead of Microsoft Presidio |
| `RR_STATE_DIR` | `state/` | Where the queue database lives |

Without keys the server still starts: recorded replays, the queue and the Benchmark view work, and live
classification answers HTTP 503 with a readable message.

## 2. GitHub Pages static demo

The static demo needs no backend and no keys: it replays the recorded predictions in `data/preds/` and reads the
benchmark from `results/metrics.json`.

```bash
python scripts/render_docs.py        # README and guides with current numbers
python scripts/export_static.py      # writes docs/ (console in static mode + deck)
git add docs README.md guide && git commit -m "Update static demo"
```

In the repository settings, set **Pages** to deploy from the `main` branch, `/docs` folder. The site is served at
<https://vnmoorthy.github.io/rescue-radar/> and the deck at <https://vnmoorthy.github.io/rescue-radar/deck/>.

## 3. Fireworks serverless sampling (current serving path)

`rr/infer.py` (`SamplerClassifier`) creates a Fireworks serverless sampling client for a LoRA checkpoint saved during
training. The live server (`rr/server.py`) serves, by default, exactly the checkpoint the benchmark scored for the
headline system (`data/preds/<system>.meta.json`); `RR_LIVE_MODEL=latest` falls back to `rr.infer.get_classifier()`
(`data/active_model.json`, or the newest entry in `data/checkpoints*.json`), which may be an unscored training
checkpoint. The benchmark used the same code path, so the README's latency and cost apply to it (measured with 32
parallel requests on shared capacity). Sampler checkpoints are tied to the training
session that produced them.

## 4. Next step: Fireworks dedicated deployment

1. Promote the checkpoint to a permanent model in your Fireworks account:
   ```bash
   python -m rr.promote _full rescue-radar-nemotron
   ```
2. Create a dedicated deployment of that model in Fireworks (console or `firectl`), sized for the expected
   posts per second.
3. Point the classifier at the deployment. This needs a small change in `rr/infer.py` (an
   OpenAI-compatible chat call with the same prompt), and a re-run of `python -m rr.run_model rescue_radar` and
   `python -m rr.evaluate` so the published latency and cost describe the new path.

## 5. Next step: Microsoft Foundry

For agencies that must keep data inside their Azure tenancy, the plan is to deploy the promoted model through
Microsoft Foundry and keep PII redaction (Microsoft Presidio, already in `rr/scrub.py`) in front of every human
reader. None of the Foundry integration is implemented in this repository yet: there is no Azure SDK
dependency and no Foundry client in `rr/`. Steps we expect:

1. Export the promoted model (base model plus LoRA adapter) from Fireworks.
2. Register and deploy it as a managed online endpoint in a Foundry project.
3. Add a Foundry client to `rr/infer.py` behind a setting, keeping the prompt and `parse_label()` unchanged.
4. Re-run the benchmark on the new endpoint before using it, and publish the new latency and cost.

## Production checklist

- [ ] Authentication in front of the API and console (the prototype has none)
- [ ] TLS, and `RR_HOST` bound to a private interface
- [ ] Retention policy for the queue database and logs; posts can contain personal data
- [ ] A human dispatcher reviews every queue item; the model never dispatches on its own
- [ ] Monitoring of model availability (HTTP 503 rate) and queue latency
- [ ] Re-evaluate on a recent, local disaster before relying on the scores
- [ ] Respect the CC BY-NC-SA 4.0 terms of HumAID (non-commercial) or retrain on data you may use
