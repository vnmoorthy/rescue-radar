# Rescue Radar v1.0.0

**Find the people asking for rescue in the flood of disaster posts.** Rescue Radar sorts every public post written during a disaster into the 10 HumAID humanitarian categories and puts the rescue-critical ones (requests or urgent needs, injured or dead people, missing or found people) at the top of a dispatcher's queue. It is NVIDIA Nemotron 3.5 Super fine-tuned with LoRA on Fireworks serverless training, served through Fireworks serverless sampling, and tested on 4 disasters from 2019 that it never saw in training.

Built on November 2, 2026 at Fireworks: Deploy in San Francisco.

- Live demo (no install, no key): https://vnmoorthy.github.io/rescue-radar/
- Slides: https://vnmoorthy.github.io/rescue-radar/deck/ (PowerPoint: `deck/RescueRadar.pptx`, attached to this release)
- Repository: https://github.com/vnmoorthy/rescue-radar

## Headline results

All numbers are from `results/metrics.json` (generated 2026-11-02 15:26 PT). Test set: 3,001 posts sampled from 4 unseen 2019 disasters (Hurricane Dorian 1,485, Cyclone Idai 767, Pakistan earthquake 382, Midwestern US floods 367), of which 254 are rescue-critical. Training: a class-capped pool of 13,839 examples from 15 disasters of 2016 to 2018; the pre-registered main checkpoint (step 275 of 432) saw 8,800 of them. Intervals are 95% bootstrap intervals (5,000 resamples, stratified by disaster).

**Rescue Radar on all 3,001 posts:** macro-F1 69.2% (64.8% to 72.2%), accuracy 72.4% (70.9% to 74.0%), rescue-critical recall 84.7% (80.2% to 88.9%), rescue-critical precision 60.2%.

**Against Claude Opus 5.5 with 20 examples**, paired on the 2,592 posts both systems answered:

| | Rescue Radar | Claude Opus 5.5, 20-shot | Difference (95% CI) |
| --- | --- | --- | --- |
| Rescue-critical recall | **85.3%** | 68.8% | +16.5 pts (+11.2 to +21.9) |
| Macro-F1 | **69.2%** | 63.7% | +5.5 pts (+2.6 to +8.5) |
| Accuracy | **73.1%** | 70.9% | +2.2 pts (+0.5 to +4.0); McNemar p = 0.013 |
| Rescue-critical precision | 60.2% | **78.1%** | lower: more false alarms |
| Cost per 1M posts | **$171** ($342 undiscounted) | $8,738 | 51.1x cheaper (25.5x undiscounted) |
| Latency per post, p50 / p95 | 3.37 s / 8.42 s | **1.31 s / 2.71 s** | slower |

**Other comparisons** (Rescue Radar minus the other system, 95% CI):

| Against | Posts | Macro-F1 | Rescue-critical recall | Their cost per 1M posts |
| --- | --- | --- | --- | --- |
| Nemotron 3.5 Super, no fine-tuning | 3,001 | +11.7 pts (+8.9 to +14.4) | +19.3 pts (+14.2 to +24.4) | $171 |
| Claude Opus 5.5, zero-shot | 1,920 | +8.1 pts (+3.1 to +13.6) | +17.6 pts (+11.2 to +24.3) | $3,412 |
| GPT-6.1 Terra, 20-shot | 3,001 | +8.6 pts (+5.5 to +12.2) | +13.8 pts (+9.1 to +18.7) | $1,418 |
| GPT-6.1 Terra, zero-shot | 3,001 | +8.6 pts (+6.0 to +11.4) | +13.0 pts (+8.7 to +17.6) | $499 |
| Small-data ablation (3,939 training examples) | 3,001 | +4.2 pts (+2.0 to +6.5) | +7.5 pts (+3.7 to +11.4) | $171 |

Cost is measured tokens times published prices. The Fireworks rate for Nemotron 3.5 Super ($0.57 per 1M prefill tokens, $1.44 per 1M sampled tokens) includes a limited-time 50% discount; the undiscounted cost is $342 per 1M posts. Latency was measured during the benchmark run with 32 parallel requests on shared Fireworks serverless capacity (Claude: 24 through the Anthropic API), so it reflects load as well as the model.

## What is in this release

- **The fine-tuned model**, promoted to permanent models in the team's Fireworks account (base model `accounts/fireworks/models/nvidia-nemotron-3p5-super-vl-120b-a12b-bf16`, LoRA rank 16, lr 1e-4, batch 32, 1 epoch planned):
  - `accounts/vnmoorthy/models/rescue-radar-nemotron`: the headline system, from step 275 (8,800 examples seen) of the 13,839-example run (training session `ts-19e3a2b722a94b0fba11ba569f8457f9`), state READY.
  - `accounts/vnmoorthy/models/rescue-radar-nemotron-quick`: the small-data ablation, from step 123 of the 3,939-example run (training session `ts-b3b9dd825f194d349e5d117fc5e98411`), state READY.
- **Dispatch console** (`python -m rr.server`, http://localhost:8787): Live Replay of the 2019 disasters in their original order, Triage Desk with a priority queue and situational feed, dispatch / resolve / dismiss with notes, CSV export, map pins from a gazetteer, Head-to-Head against a frontier model, Benchmark and How it works views, light and dark themes.
- **HTTP API** (`/api/classify` and the queue endpoints), documented in `guide/API.md`.
- **Static demo** on GitHub Pages that replays the recorded predictions with no backend.
- **PII redaction** before a person reads a post: Microsoft Presidio with spaCy plus regexes for phone numbers, emails, handles, URLs and street addresses (`rr/scrub.py`).
- **The benchmark**: held-out-disaster split (`rr/prep.py`), per-post predictions of all 7 systems in `data/preds/`, metrics with exact McNemar tests and stratified bootstrap (`rr/evaluate.py`, `results/metrics.json`), and the pre-registration written before any fine-tuned model was scored (`guide/PREREGISTRATION.md`).
- **Slide deck**: `deck/RescueRadar.pptx` (built by `deck/build_pptx.py`) and the web version at https://vnmoorthy.github.io/rescue-radar/deck/.
- **Docs**: README and guides rendered from `results/metrics.json` by `scripts/render_docs.py`, so no number in them is typed by hand; architecture, API, evaluation, deployment and demo runbook in `guide/`.

## How to run

```bash
git clone https://github.com/vnmoorthy/rescue-radar.git && cd rescue-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m rr.server          # open http://localhost:8787
```

Live Replay works on a fresh clone with no API key. Classifying new text needs `FIREWORKS_API_KEY` in a git-ignored `.env`; the Head-to-Head view also needs `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` as the fallback). Requires Python 3.12.

To recompute every number from the committed predictions, with no API key: `python -m rr.evaluate`. To rerun training and every system from scratch, follow "Reproduce the benchmark" in the README (needs Fireworks and Anthropic keys and costs money).

## Known limitations

- **A human decides.** Rescue Radar ranks posts; it never dispatches anyone, and it can be wrong.
- **More false alarms than the frontier model.** Rescue-critical precision is 60.2% (Claude Opus 5.5 20-shot: 78.1%), so about 40% of flagged posts are not rescue-critical. The weakest category, `requests_or_urgent_needs`, has precision 28.8% and recall 60.3%, and only 78 test posts carry that label.
- **Uneven across disasters.** Rescue-critical recall is 93.8% on the Pakistan earthquake and 90.5% on Cyclone Idai, but 59.6% on Hurricane Dorian (52 rescue-critical posts) and 60.0% on the Midwestern US floods (only 5).
- **Slower per post.** 3.37 s median and 8.42 s p95 on shared serverless capacity. A dedicated deployment is planned and not measured.
- **The main training run was frozen early.** By the pre-registered rule, the headline system is the newest checkpoint saved by 14:55 PT: step 275 of 432 planned steps. Later checkpoints are not scored, because test scores never pick a checkpoint.
- **Old data, one platform, one language.** HumAID is English-language Twitter data from 2016 to 2019; performance on today's platforms is untested. The test disasters are absent from our fine-tuning data, but they are public posts, so we cannot rule out that any model saw them in pretraining.
- **Incomplete frontier coverage.** The Anthropic account hit its spending cap: Claude Opus 5.5 answered 2,592 posts with 20 examples (86%) and 1,920 zero-shot (64%). Comparisons are paired on the posts both systems answered.
- **Redaction is best effort.** It applies to what the dispatcher sees; raw posts go to Fireworks (and to Anthropic or OpenAI in the Head-to-Head view).
- **Not built yet:** live stream ingestion (the demo replays recorded posts or classifies pasted and uploaded text), adapter export for private hosting, Microsoft Foundry deployment, Common Alerting Protocol export. Locations come only from a gazetteer of the affected areas, so most posts have no map pin.
- **License.** Code: MIT. HumAID is CC BY-NC-SA 4.0, so the fine-tuned models and files derived from HumAID are non-commercial and share-alike.

## Citation

Use GitHub's "Cite this repository" button (from `CITATION.cff`) and please also cite HumAID: Alam, Qazi, Imran and Ofli, "HumAID: Human-Annotated Disaster Incidents Data from Twitter with Deep Learning Benchmarks", ICWSM 2021.
