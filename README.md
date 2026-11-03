<!-- Generated from README.template.md by scripts/render_docs.py. Edit the template, then re-run the script. -->
<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/hero.svg?v=sunrise-2">
  <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/hero-light.svg?v=sunrise-2">
  <img src="assets/hero.svg" alt="Rescue Radar: a radar sweep over a storm map lights up rescue requests among disaster posts" width="100%">
</picture>

### Find the people asking for rescue in the flood of disaster posts, in real time.

[![CI](https://github.com/vnmoorthy/rescue-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/vnmoorthy/rescue-radar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Fireworks AI](https://img.shields.io/badge/Fireworks%20AI-serverless%20LoRA%20%2B%20sampling-6720FF)](https://fireworks.ai/)
[![NVIDIA Nemotron](https://img.shields.io/badge/NVIDIA-Nemotron%203.5%20Super-76B900?logo=nvidia&logoColor=white)](https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/)
[![Microsoft](https://img.shields.io/badge/Microsoft-Presidio%20PII%20redaction-0078D4)](https://microsoft.github.io/presidio/)
[![HumAID](https://img.shields.io/badge/data-HumAID%20%28QCRI%29-F59E0B)](https://huggingface.co/datasets/QCRI/HumAID-events)
[![Hackathon](https://img.shields.io/badge/hackathon-Fireworks%3A%20Deploy%202026-E11D48)](#hackathon-disclosure)
[![macro-F1](https://img.shields.io/badge/macro--F1%20on%20unseen%20disasters-69.2%25-0E7490)](#results)

**[Live demo](https://vnmoorthy.github.io/rescue-radar/)** &nbsp;·&nbsp;
**[Slides](https://vnmoorthy.github.io/rescue-radar/deck/)** &nbsp;·&nbsp;
**[Pitch deck (.pptx)](https://github.com/vnmoorthy/rescue-radar/raw/main/deck/RescueRadar.pptx)** &nbsp;·&nbsp;
[Results](#results) &nbsp;·&nbsp; [How it works](#how-it-works) &nbsp;·&nbsp; [Quickstart](#quickstart) &nbsp;·&nbsp;
[Evaluation design](guide/EVALUATION.md)

</div>

---

**Rescue Radar reads every public post during a disaster, sorts it into the 10 HumAID humanitarian categories, and pushes the rescue-critical ones (people asking for help, people injured or killed, people missing or trapped) to the top of a dispatcher's queue.** The model is NVIDIA Nemotron 3.5 Super, fine-tuned with LoRA on Fireworks serverless training and served through Fireworks serverless sampling, and it is tested on 4 disasters from 2019 that it never saw during training.

> [!IMPORTANT]
> Paired on the **2,592** held-out posts from 4 unseen disasters that both systems answered, Rescue Radar catches **85.3%** of rescue-critical posts against **68.8%** for Claude Opus 5.5, 20-shot (**+16.5 pts**, 95% CI +11.2 to +21.9 pts, so the gain is not luck of the draw). Macro-F1 is 69.2% against 63.7% (+5.5 pts, 95% CI +2.6 to +8.5 pts). Rescue-critical precision is lower (60.2% vs 78.1%, each on the posts it answered).
>
> It costs **$171 per million posts** against $8,738 (51.1x cheaper at Fireworks' current rate, which includes a limited-time 50% discount; 25.5x at the undiscounted rate). It is slower per post: median latency 3.37 s against 1.31 s. Statistics, intervals and caveats are in [Results](#results).

<!-- growth-sections -->
## Pitch deck

[![Title slide](assets/screens/deck-1-light.png)](https://vnmoorthy.github.io/rescue-radar/deck/) [![Rescue Radar as a company](assets/screens/deck-10-dark.png)](https://vnmoorthy.github.io/rescue-radar/deck/#10)

Ten slides: the problem, the product, the held-out-disaster benchmark, results against Claude Opus 5.5 and GPT-6.1 Terra, speed and cost, limitations, and Rescue Radar as a company. **[Open the web deck](https://vnmoorthy.github.io/rescue-radar/deck/)** (light and dark, arrow keys to navigate) or **[download the PowerPoint](https://github.com/vnmoorthy/rescue-radar/raw/main/deck/RescueRadar.pptx)** ([source](deck/build_pptx.py), numbers filled from `results/metrics.json`).

## See it in 60 seconds

<p align="center">
  <img src="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/screens/replay.gif?v=sunrise-2" alt="Rescue Radar replaying real posts from a 2019 disaster: rescue-critical posts move to the priority queue while the rest fill the situational feed" width="100%">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/screens/replay-dark.png?v=sunrise-2">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/screens/replay-light.png?v=sunrise-2">
    <img src="assets/screens/replay-dark.png" alt="The Rescue Radar dispatch console: a map, the priority queue of rescue-critical posts, and the situational feed" width="100%">
  </picture>
</p>

1. Open the **[live demo](https://vnmoorthy.github.io/rescue-radar/)**. It runs in your browser: no account, no API key, no backend.
2. In **Live Replay**, pick one of the 4 held-out 2019 disasters and press <kbd>Space</kbd>. Real posts arrive in their original order; the ones the model marks rescue-critical go to the priority queue, with personal data redacted.
3. Open **Benchmark** to see how those labels score against Claude Opus 5.5, 20-shot on 3,001 posts the model never saw, then flip through the **[slides](https://vnmoorthy.github.io/rescue-radar/deck/)**.

<!-- ===================================================================== (b) Try it locally in 60 seconds -->

## Contents

[Why this matters](#why-this-matters) · [Results](#results) · [How it works](#how-it-works) · [Evaluation design](#evaluation-design-held-out-disasters) · [Quickstart](#quickstart) · [Reproduce the benchmark](#reproduce-the-benchmark) · [Repository layout](#repository-layout) · [Sponsor stack](#sponsor-stack) · [Responsible AI and limitations](#responsible-ai-and-limitations) · [From hackathon to company](#from-hackathon-to-company) · [Roadmap](#roadmap) · [Contributing](#contributing) · [Citation](#citation) · [Team](#team)

## Why this matters

When a hurricane or an earthquake hits, emergency lines saturate, and people turn to public social media to ask for help: an address, a trapped family, a missing child. Those posts are scattered among thousands of prayers, news links, donation drives and jokes. Responders have had to read them by hand.

The signal is rare. In the held-out evaluation set, only **8.5%** of posts (254 of 3,001) are rescue-critical. A dispatcher cannot read the other 91.5% fast enough. Rescue Radar reads all of them and puts the few that matter first, with personal data redacted, a location when the post names a known place, and a human making every decision.

Why a fine-tuned open model instead of a frontier API? What [Results](#results) measures against Claude Opus 5.5, 20-shot: significantly higher rescue-critical recall (+16.5 pts, at lower precision), macro-F1 +5.5 pts (95% CI +2.6 to +8.5 pts), and about 51.1x lower serving cost (25.5x at the undiscounted rate). It is slower per post on shared serverless capacity (3.37 s median against 1.31 s). The base model is open, so the small LoRA adapter could be exported for an agency to host itself instead of sending every post to a third-party API; that export is not built yet.

## Who is this for

| Who | What they get |
| --- | --- |
| **Emergency operations centers** | Replay a past disaster from your own area in the console (no integration needed), then run Rescue Radar in shadow mode beside your current process during an exercise. You get a priority queue of rescue-critical posts with personal data redacted, a map pin when a post names a known place, and a CSV export of the queue with each dispatcher's decision and notes. |
| **911 and emergency communications centers** | When phone lines saturate, people post publicly instead. Rescue Radar reads all of those posts and puts the 8.5% that are rescue-critical (in our test set) first, and `/api/classify` lets dispatch software call the same model. It is decision support: a person decides every item. Common Alerting Protocol export is planned, not built. |
| **Relief NGOs** | A situational-awareness feed sorted into the 10 HumAID categories (urgent needs, displaced people, infrastructure damage, donations and more), so a response team can see where needs cluster. The code is MIT; the HumAID-trained model inherits CC BY-NC-SA 4.0, so check that license against your use. |
| **Researchers in crisis informatics** | A held-out-disaster benchmark with a [pre-registration](guide/PREREGISTRATION.md), every system's per-post predictions in `data/preds/`, paired McNemar tests and stratified bootstrap intervals, per-disaster and per-category scores, and a script that re-renders every number in the docs. Add your model's predictions and compare on the same 3,001 posts. |

<!-- ===================================================================== (d) Rescue Radar vs a frontier API -->

### Rescue Radar vs a frontier API

Paired on the 2,592 held-out posts that both Rescue Radar and Claude Opus 5.5, 20-shot answered. Better value in bold.

| | Rescue Radar | Claude Opus 5.5, 20-shot |
| --- | --- | --- |
| Quality: macro-F1 over 10 categories | **69.2%** | 63.7% |
| Rescue-critical recall (a missed request is the costly error) | **85.3%** | 68.8% |
| Rescue-critical precision (lower means more false alarms) | 60.2% | **78.1%** |
| Cost per 1M posts (measured tokens x published price) | **$171** ($342 without Fireworks' limited-time 50% discount) | $8,738 |
| Can run privately | Partly: the base model is open-weight, so an agency could host it; exporting our adapter is not built yet | No: every post goes to a third-party API |
| Latency per post, p50 / p95, as measured in the benchmark run | 3.37 s / 8.42 s | **1.31 s / 2.71 s** |

<sub>Differences with 95% paired-bootstrap intervals: macro-F1 +5.5 pts (+2.6 to +8.5 pts), rescue-critical recall +16.5 pts (+11.2 to +21.9 pts). Cost: 51.1x cheaper at today's Fireworks rate, 25.5x at the undiscounted rate. The cheapest frontier setup we measured, GPT-6.1 Terra, zero-shot, costs $499 per 1M posts (2.9x ours), and Rescue Radar is +8.6 pts ahead of it on macro-F1 (+6.0 to +11.4 pts). Latency: Rescue Radar is slower; it ran with 32 parallel requests on shared Fireworks serverless capacity and Claude with 24 through the Anthropic API, so both numbers include load. A dedicated deployment is on the roadmap and not measured.</sub>

<!-- ===================================================================== (e) FAQ -->

## Results

Evaluated on **3,001** posts sampled from 4 disasters of 2019, none of which were in our fine-tuning data ([evaluation design](#evaluation-design-held-out-disasters)). Every system gets the same instructions and the same 10 category definitions; the 20-shot baselines also get 20 examples. **Not every system answered every post:** the Anthropic account hit its spending cap mid-run, so Claude Opus 5.5, 20-shot was scored on the 2,592 posts it answered (86%), Claude Opus 5.5, zero-shot was scored on the 1,920 posts it answered (64%). Each row's score is on its own posts; the comparisons below are paired on the posts both systems answered.

| System | Posts scored | Macro-F1 | Accuracy | Rescue-critical recall | p50 latency | Cost per 1M posts |
| --- | --- | --- | --- | --- | --- | --- |
| **Rescue Radar, main run (step 275 of 432: 8,800 of 13,839 examples seen)** | 3,001 | **69.2%**<br><sub>64.8% to 72.3%</sub> | 72.4%<br><sub>70.9% to 74.0%</sub> | 84.7%<br><sub>80.3% to 88.9%</sub> | 3.37 s | $171 |
| Claude Opus 5.5, 20-shot | 2,592 | 63.7%<br><sub>59.1% to 67.3%</sub> | 70.9%<br><sub>69.1% to 72.5%</sub> | 68.8%<br><sub>62.7% to 75.0%</sub> | 1.31 s | $8,738 |
| Claude Opus 5.5, zero-shot | 1,920 | 62.2%<br><sub>57.6% to 67.0%</sub> | 70.2%<br><sub>68.2% to 72.2%</sub> | 71.9%<br><sub>64.7% to 78.9%</sub> | 1.87 s | $3,412 |
| GPT-6.1 Terra, 20-shot | 3,001 | 60.6%<br><sub>56.7% to 63.9%</sub> | 67.8%<br><sub>66.2% to 69.5%</sub> | 70.9%<br><sub>65.4% to 76.3%</sub> | 1.28 s | $1,418 |
| GPT-6.1 Terra, zero-shot | 3,001 | 60.6%<br><sub>56.6% to 63.7%</sub> | 66.7%<br><sub>65.0% to 68.4%</sub> | 71.7%<br><sub>66.3% to 77.0%</sub> | 1.30 s | $499 |
| Nemotron 3.5 Super, no fine-tuning | 3,001 | 57.6%<br><sub>54.2% to 60.5%</sub> | 66.0%<br><sub>64.4% to 67.6%</sub> | 65.4%<br><sub>59.7% to 71.2%</sub> | 734 ms | $171 |
| Rescue Radar, small-data run (step 123 of 123: 3,936 of 3,939 examples seen) | 3,001 | 65.0%<br><sub>61.8% to 67.8%</sub> | 70.9%<br><sub>69.3% to 72.5%</sub> | 77.2%<br><sub>72.2% to 82.2%</sub> | 4.21 s | $171 |

<sub>Small numbers are 95% bootstrap intervals (5,000 paired resamples of tweets, stratified by disaster). Rescue-critical recall: the share of posts whose true label is one of `requests_or_urgent_needs`, `injured_or_dead_people`, `missing_or_found_people` that the system also labels as one of those three. Latency is wall-clock time per post as measured during the benchmark run (Rescue Radar and base Nemotron through Fireworks serverless sampling with 32 parallel requests on shared capacity, Claude through the Anthropic API with 24), so it reflects load as well as the model. Cost is measured tokens times published per-token prices:
<br>Rescue Radar, main run (step 275 of 432: 8,800 of 13,839 examples seen): measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it).
<br>Claude Opus 5.5, 20-shot: measured tokens x Anthropic list price ($4 in / $20 out per 1M tokens, thinking tokens included).
<br>Claude Opus 5.5, zero-shot: measured tokens x Anthropic list price ($4 in / $20 out per 1M tokens, thinking tokens included).
<br>GPT-6.1 Terra, 20-shot: measured tokens x OpenAI list price ($1 in / $5 out per 1M tokens, reasoning tokens included).
<br>GPT-6.1 Terra, zero-shot: measured tokens x OpenAI list price ($1 in / $5 out per 1M tokens, reasoning tokens included).
<br>Nemotron 3.5 Super, no fine-tuning: measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it).
<br>Rescue Radar, small-data run (step 123 of 123: 3,936 of 3,939 examples seen): measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it).
</sub>

### Is the difference real?

Both systems answered the same 2,592 of the 3,001 posts, so we compare them post by post on those: Rescue Radar 69.2% macro-F1 and 85.3% rescue-critical recall, Claude Opus 5.5, 20-shot 63.7% and 68.8%.

- **Paired exact test (McNemar).** Rescue Radar was right where Claude Opus 5.5, 20-shot was wrong on **291** posts, and the reverse happened on **233** posts. If both systems were equally accurate, a split at least this uneven would happen by chance with p = 0.013.
- **Paired bootstrap, stratified by disaster.** Resampling tweets within each disaster 5,000 times, the 95% interval for Rescue Radar minus Claude Opus 5.5, 20-shot is +2.6 to +8.5 pts for macro-F1, +0.5 to +4.0 pts for accuracy and +11.2 to +21.9 pts for rescue-critical recall. Rescue Radar has the higher macro-F1 in 4,997 of 5,000 resamples.
- **In plain words:** the macro-F1 advantage is not luck of the draw. The whole 95% interval is above zero.

<details>
<summary><b>Every pairwise comparison</b></summary>

| Rescue Radar vs | Macro-F1 difference (95% CI) | Accuracy difference (95% CI) | Rescue-critical recall difference (95% CI) | Ours right, theirs wrong / reverse | McNemar |
| --- | --- | --- | --- | --- | --- |
| Rescue Radar, small-data run (step 123 of 123: 3,936 of 3,939 examples seen) | +4.2 pts (+2.0 to +6.5 pts) | +1.5 pts (+0.3 to +2.7 pts) | +7.5 pts (+3.7 to +11.4 pts) | 197 / 151 | p = 0.016 |
| Nemotron 3.5 Super, no fine-tuning | +11.7 pts (+8.9 to +14.4 pts) | +6.5 pts (+4.8 to +8.1 pts) | +19.3 pts (+14.2 to +24.4 pts) | 429 / 235 | p < 0.001 |
| Claude Opus 5.5, 20-shot | +5.5 pts (+2.6 to +8.5 pts) | +2.2 pts (+0.5 to +4.0 pts) | +16.5 pts (+11.2 to +21.9 pts) | 291 / 233 | p = 0.013 |
| Claude Opus 5.5, zero-shot | +8.1 pts (+3.1 to +13.6 pts) | +3.3 pts (+1.1 to +5.4 pts) | +17.6 pts (+11.2 to +24.3 pts) | 251 / 188 | p = 0.003 |
| GPT-6.1 Terra, 20-shot | +8.6 pts (+5.5 to +12.2 pts) | +4.6 pts (+2.9 to +6.3 pts) | +13.8 pts (+9.1 to +18.7 pts) | 412 / 273 | p < 0.001 |
| GPT-6.1 Terra, zero-shot | +8.6 pts (+6.0 to +11.4 pts) | +5.7 pts (+4.0 to +7.5 pts) | +13.0 pts (+8.7 to +17.6 pts) | 431 / 259 | p < 0.001 |

</details>

<details>
<summary><b>Per disaster</b>: does it hold up on each unseen event?</summary>

| Disaster (2019) | Posts (rescue-critical) | Rescue Radar macro-F1 | Claude Opus 5.5, 20-shot macro-F1 (n) | Rescue Radar critical recall | Claude Opus 5.5, 20-shot critical recall (critical n) |
| --- | --- | --- | --- | --- | --- |
| Hurricane Dorian (2019) | 1,485 (52) | 60.4% | 53.5% (n = 1,279) | 59.6% | 21.7% (46) |
| Cyclone Idai (2019) | 767 (116) | 65.6% | 57.0% (n = 648) | 90.5% | 79.0% (95) |
| Pakistan Earthquake (2019) | 382 (81) | 54.0% | 53.6% (n = 346) | 93.8% | 89.0% (73) |
| Midwestern US Floods (2019) | 367 (5) | 48.6% | 43.7% (n = 319) | 60.0% | 0.0% (4) |

Claude Opus 5.5, 20-shot columns are scored on the posts it answered (n per row). Critical recall on a disaster with only a handful of rescue-critical posts rests on those few posts; read it as anecdotal, not as a result.

</details>

<details>
<summary><b>Rescue-critical categories</b>: precision, recall and F1 per class</summary>

| Category | Posts in eval set | Rescue Radar P / R / F1 | Claude Opus 5.5, 20-shot P / R / F1 (support on its answered posts) |
| --- | --- | --- | --- |
| Requests or urgent needs | 78 | 28.8% / 60.3% / 39.0% | 35.9% / 20.9% / 26.4% (67) |
| Injured or dead people | 172 | 88.0% / 94.2% / 91.0% | 92.3% / 89.2% / 90.7% (148) |
| Missing or found people | 4 | 40.0% / 100.0% / 57.1% | 30.0% / 100.0% / 46.2% (3) |

Small classes have wide intervals: read per-class numbers for categories with few posts as indicative only.

</details>

<sub>Results generated 2026-11-02T16:18:45 by `python -m rr.evaluate`. Full numbers, including confusion matrices: [`results/metrics.json`](results/metrics.json).</sub>

## How it works

1. **Ingest.** Posts arrive one by one. The demo replays the real 2019 disaster tweets in their original order (a tweet ID is a Twitter snowflake, so its post time is `(id >> 22) + 1288834974657` ms), or classifies text you paste or upload. Live stream ingestion is not built yet.
2. **Classify.** One instruction prompt with the 10 category definitions, one label out. The LoRA-tuned Nemotron runs on Fireworks serverless sampling at temperature 0; its reasoning block is closed in the prompt so it answers with the label alone.
3. **Prioritize.** Rescue-critical labels (`requests_or_urgent_needs`, `injured_or_dead_people`, `missing_or_found_people`) go to the priority queue. Everything else stays in the situational-awareness feed.
4. **Protect.** Before a person reads a post, `rr/scrub.py` replaces phone numbers, emails, handles, URLs and street addresses with placeholders, and people's names too when Microsoft Presidio is installed (a regex-only engine runs otherwise). This is best effort, and it applies to what the dispatcher sees: the raw post is what goes to the model providers.
5. **Locate.** `rr/geo.py` maps place names in the post to coordinates with a gazetteer of the affected areas. It never guesses a location for a post that names no known place.
6. **Decide.** A dispatcher works the queue: dispatch, resolve or dismiss, with notes, and exports it as CSV. The model ranks; a human decides.

The live console and the benchmark share the same code path, `rr.infer.SamplerClassifier`, with the same prompt from `rr/labels.py`. By default the server serves exactly the checkpoint the benchmark scored for the headline system (recorded in `data/preds/<system>.meta.json`), and the console's header badge says "scored". `RR_LIVE_MODEL=latest` serves the newest training checkpoint instead, and the badge then says it is not scored.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/architecture.svg?v=sunrise-2">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/vnmoorthy/rescue-radar/main/assets/architecture-light.svg?v=sunrise-2">
    <img src="assets/architecture.svg" alt="Architecture: offline training and evaluation lane, online triage lane, and ship lane" width="100%">
  </picture>
</p>

```mermaid
flowchart LR
  subgraph offline["Train and prove (offline)"]
    H[("HumAID tweets<br/>QCRI")] --> P["rr.prep<br/>split by disaster<br/>drop test duplicates"]
    P -->|"2016-2018 disasters"| T["rr.train<br/>LoRA on Fireworks<br/>serverless training"]
    T --> C[("LoRA checkpoints")]
    C --> R["rr.run_model<br/>Fireworks sampling"]
    B["rr.baseline<br/>Claude Opus 5.5"] --> E
    P -->|"unseen 2019 disasters"| E["rr.evaluate<br/>McNemar + bootstrap"]
    R --> E
    E --> M[("results/metrics.json")]
  end
  subgraph online["Triage in real time (online)"]
    S["Replay of 2019 posts<br/>or paste / upload"] --> API["rr.server<br/>FastAPI"]
    API --> I["rr.infer<br/>Nemotron 3.5 Super + LoRA"]
    I --> Q{"rescue-critical?"}
    Q -->|"yes"| PQ["Priority queue"]
    Q -->|"no"| FD["Situational feed"]
    API --> SC["rr.scrub<br/>PII redaction"]
    API --> G["rr.geo<br/>gazetteer"]
    PQ --> D["Dispatcher console<br/>a human decides"]
  end
  R -. "the scored checkpoint, same prompt" .-> I
  M --> D
```

More detail: [guide/ARCHITECTURE.md](guide/ARCHITECTURE.md) and the HTTP contract in [guide/API.md](guide/API.md).

## Evaluation design: held-out disasters

A model that has seen a disaster's tweets during training can look much better than it will be on the next disaster. So the split is by **event**, not by tweet:

| | Disasters | Years | Posts |
| --- | --- | --- | --- |
| Train | 15 HumAID events | 2016 to 2018 | 13,839 in the training file; the scored step-275 checkpoint (of 432 steps) saw 8,800 of them |
| Test | 4 unseen events: Cyclone Idai (2019), Hurricane Dorian (2019), Midwestern US Floods (2019), Pakistan Earthquake (2019) | 2019 | 15,384 in total; a seeded, event-stratified sample of 3,001 is the shared eval set |

- **No leakage by copy.** Training tweets whose normalized text also appears in the test events (retweets, copies) are removed: 1 of 61,100 training-event tweets.
- **Prompt parity.** Every system gets the same system prompt and category definitions (`rr/labels.py`). The 20-shot frontier baseline adds two fixed training examples per category.
- **Baselines.** Claude Opus 5.5 (zero-shot and 20-shot) as the strongest frontier reference, and the same Nemotron base model without fine-tuning, served through the same Fireworks path, so the gain from LoRA is isolated. GPT-6.1 Terra (zero-shot and 20-shot, through the OpenAI API) was added after pre-registration.
- **Statistics.** Exact McNemar test on per-post correctness, and a paired bootstrap resampled within each disaster for every interval.
- **Measured, not estimated.** Latency is measured per call; cost is measured token counts times published prices. The choice of the headline system and metrics was fixed before any fine-tuned model was scored on the test set ([`guide/PREREGISTRATION.md`](guide/PREREGISTRATION.md)).
The full method is in [guide/EVALUATION.md](guide/EVALUATION.md).

## Try it locally in 60 seconds

```bash
git clone https://github.com/vnmoorthy/rescue-radar.git && cd rescue-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m rr.server
```

Open **http://localhost:8787**.

- **No API keys needed for replay mode.** Live Replay streams the predictions committed in `data/preds/`, so the console works on a fresh clone with no `.env`.
- **Live classification needs `FIREWORKS_API_KEY`.** Classifying text you paste or upload calls the fine-tuned model on Fireworks serverless sampling. Put the key in a git-ignored `.env` file in the repo root (see [Quickstart](#quickstart)); the Head-to-Head view also needs `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` as the fallback).
- Python 3.12. The 60 seconds assume the dependencies are installed: the first `pip install` takes longer (Presidio, spaCy and the tokenizer libraries).

<!-- ===================================================================== (c) Who is this for -->

## Quickstart

Requirements: Python 3.12, a [Fireworks AI](https://fireworks.ai/) API key (training and serving), an [Anthropic](https://console.anthropic.com/) API key (frontier baseline and the Head-to-Head view), optionally an [OpenAI](https://platform.openai.com/) API key (the GPT-6.1 Terra baseline, and the Head-to-Head fallback when the Anthropic account is out of quota) and a [Hugging Face](https://huggingface.co/settings/tokens) token (the Nemotron tokenizer).

```bash
git clone https://github.com/vnmoorthy/rescue-radar.git
cd rescue-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root (it is git-ignored; never commit it):

```bash
FIREWORKS_API_KEY=...
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...      # optional: GPT-6.1 Terra baseline and Head-to-Head fallback
HF_TOKEN=...
```

Then build the data, train, evaluate and open the console:

```bash
python -m rr.prep        # download HumAID, build the held-out-disaster split
python -m rr.train       # LoRA fine-tune on Fireworks serverless training
python -m rr.evaluate    # score every system, write results/metrics.json
python -m rr.server      # dispatch console and API
```

Open **http://localhost:8787**. No keys at hand? The [live demo](https://vnmoorthy.github.io/rescue-radar/) replays the recorded predictions with no backend at all.

## Reproduce the benchmark

```bash
python -m rr.prep                                   # data/eval.jsonl, data/test_full.jsonl, data/train_sft.jsonl
RR_TAG=_full RR_PER_CLASS=1500 python -m rr.train   # headline run: every example in data/train_sft.jsonl
python -m rr.train                                  # small-data ablation run (default 400 per class)
python -m rr.run_model rescue_radar                 # fine-tuned model: the pre-registered checkpoint frozen at 14:55 PT (data/active_model.json)
python -m rr.run_model rescue_radar_quick           # ablation
python -m rr.run_model base_zero                    # Nemotron 3.5 Super without fine-tuning
python -m rr.baseline opus_zero                     # Claude Opus 5.5, zero-shot
python -m rr.baseline opus_few                      # Claude Opus 5.5, 20-shot
python -m rr.baseline gpt_zero                      # GPT-6.1 Terra, zero-shot (added after pre-registration)
python -m rr.baseline gpt_few                       # GPT-6.1 Terra, 20-shot (added after pre-registration)
python -m rr.evaluate                               # results/metrics.json
python scripts/render_docs.py                       # re-render README.md and the guides with the new numbers
```

Every prediction script is resumable: rows already in `data/preds/<system>.jsonl` are skipped. Training writes a sampler checkpoint every 25 steps, so the newest one can be evaluated even if a run is cut short. The scored headline checkpoint is step 275 of the 432-step run, frozen at 14:55 PT per the pre-registration; training continued afterwards and later checkpoints are not scored.
## Repository layout

```text
rescue-radar/
├── rr/                      Python package
│   ├── labels.py            the 10 HumAID categories, RESCUE_CRITICAL, the single prompt
│   ├── prep.py              held-out-disaster split and de-duplication
│   ├── train.py             LoRA fine-tune on Fireworks serverless training
│   ├── infer.py             the live model: Fireworks serverless sampling
│   ├── run_model.py         scores the open models on the eval set
│   ├── baseline.py          scores Claude Opus 5.5 and GPT-6.1 Terra (zero-shot, 20-shot)
│   ├── frontier.py          live Claude call for the Head-to-Head view
│   ├── evaluate.py          metrics, McNemar, stratified bootstrap -> results/metrics.json
│   ├── promote.py           promote a checkpoint to a permanent Fireworks model
│   ├── server.py            FastAPI app: /api/* and the console
│   ├── scrub.py             PII redaction before a human reads a post
│   ├── geo.py               gazetteer: place names -> coordinates
│   └── store.py             dispatcher queue (SQLite in state/)
├── web/                     dispatch console, no build step
├── docs/                    GitHub Pages: static console + slide deck
├── scripts/                 render_docs.py, export_static.py, make_dev_fixtures.py, check_secrets.py
├── data/                    eval set, predictions, training logs (generated)
├── results/metrics.json     benchmark results
├── guide/                   API contract, architecture, evaluation, deployment, demo runbook
├── assets/                  hero and architecture art
└── tests/                   pytest suite (runs without API keys)
```

## Sponsor stack

| Sponsor | What we use | Where in the code |
| --- | --- | --- |
| **Fireworks AI** | Serverless LoRA training (`create_lora_training_client`, cross-entropy on the label tokens, Adam steps, `save_weights_for_sampler` checkpoints) and serverless sampling of the trained adapter (`create_sampling_client`). The benchmark and the live console use the same sampling path. | `rr/train.py`, `rr/infer.py`, `rr/run_model.py`, `rr/promote.py` |
| **NVIDIA** | Nemotron 3.5 Super (`nvidia-nemotron-3p5-super-vl-120b-a12b-bf16` on Fireworks) is the base model we fine-tune; its tokenizer comes from Hugging Face. | `rr/train.py`, `rr/infer.py` |
| **Microsoft** | [Microsoft Presidio](https://microsoft.github.io/presidio/) (presidio-analyzer with spaCy, presidio-anonymizer) redacts personal data before a dispatcher reads a post, merged with regexes for handles, URLs and addresses; when Presidio is not installed, the regex engine runs alone. Deployment to Microsoft Foundry is a documented next step, not yet implemented: see [guide/DEPLOYMENT.md](guide/DEPLOYMENT.md). | `rr/scrub.py` |

Also used: **Anthropic** Claude Opus 5.5 as the frontier baseline (`rr/baseline.py`, `rr/frontier.py`), **OpenAI** GPT-6.1 Terra as a second frontier baseline added after pre-registration (`rr/baseline.py`), and **QCRI**'s HumAID dataset.

## Tech stack: what each piece made possible

| Technology | What it enabled |
| --- | --- |
| **Fireworks AI** serverless LoRA training and sampling | Fine-tuning a large open model in an afternoon with no GPUs to provision, a sampler checkpoint every 25 steps (which made the pre-registered 14:55 freeze possible), and serving the exact scored checkpoint to the live console through the same code path as the benchmark. |
| **NVIDIA Nemotron 3.5 Super** (open weights) | The base model we fine-tune. Open weights are what make private hosting by an agency possible later; the LoRA lifts it by +11.7 pts macro-F1 and +19.3 pts rescue-critical recall. |
| **HumAID** (QCRI) | Human-labeled tweets from 19 disasters, enough to train on 15 and test on 4 unseen ones. |
| **Microsoft Presidio** + spaCy | PII redaction before a dispatcher reads a post, merged with regexes for handles, URLs and addresses. |
| **FastAPI** + uvicorn, plain JavaScript | The dispatch console and HTTP API with no front-end build step; a static export of the same console runs on GitHub Pages with no backend. |
| **Claude Opus 5.5** and **GPT-6.1 Terra** | Frontier baselines, scored with the same prompt and category definitions. |
| NumPy, Jinja2, python-pptx | Exact McNemar tests and stratified bootstrap; docs rendered from `results/metrics.json` so no number is typed by hand; the PPTX deck. |

## Responsible AI and limitations

- **A human decides.** Rescue Radar ranks posts; it never dispatches anyone. Every queue item needs a dispatcher's action, and the model can be wrong, especially on a kind of disaster or a way of writing it has not seen.
- **Old data, one platform.** HumAID is English-language Twitter data from 2016 to 2019. Language, platforms and the way people ask for help have changed since; performance on today's platforms is untested.
- **The most important classes are the smallest.** In the eval set, `requests_or_urgent_needs` has 78 posts and `missing_or_found_people` has 4. Per-class numbers for them have wide intervals, and a high overall score does not guarantee every request is caught.
- **Uneven coverage.** Hurricane Dorian (2019) alone is 49.5% of the eval set; results are weighted toward that disaster (per-disaster numbers are reported separately).
- **Most posts have no location.** The gazetteer only resolves places it knows by name; posts without a named place have no coordinates and must be located by a person.
- **Redaction is best effort.** PII redaction reduces exposure; it does not guarantee that no personal data reaches a reader (the small spaCy model misses some names). It applies to what the dispatcher sees: raw posts are sent to the model providers (Fireworks, and Anthropic or OpenAI for the frontier comparison).
- **Not every baseline answered every post.** Claude Opus 5.5, 20-shot answered 2,592 posts (86%) before the Anthropic spending cap. Claude Opus 5.5, zero-shot answered 1,920 posts (64%) before the Anthropic spending cap. Comparisons are paired on the posts both systems answered.
- **Unseen by our fine-tune, not necessarily by every model.** The 2019 test disasters are absent from our fine-tuning data, but they are public tweets (and HumAID has been public since 2021), so we cannot rule out that any model saw them in pretraining.
- **Non-commercial data.** HumAID is licensed CC BY-NC-SA 4.0. The code in this repo is MIT, but models trained on HumAID and derived data inherit the non-commercial, share-alike terms.

## From hackathon to company

What exists today is a working dispatch console, an HTTP API and a held-out benchmark. This section is the plan for turning them into a company. It is a plan, not a track record: there are no customers, partners or prices yet.

**Who pays.** Organizations that must find people in trouble during a disaster, and today read public posts by hand or not at all:

- city, county and state emergency management agencies and their emergency operations centers;
- emergency communications and dispatch centers;
- humanitarian organizations that run response operations;
- vendors of dispatch and emergency-management software, who would embed the API in products agencies already use.

**Product surfaces.**

| Surface | What it is | Status |
| --- | --- | --- |
| Dispatch console | Map, priority queue, situational feed, dispatch / resolve / dismiss with notes, CSV export | Built (this repo) |
| Triage API | `/api/classify` and the queue endpoints, for dispatch and emergency-management software | Built; a product needs authentication, rate limits and an uptime commitment |
| Private deployment | The open-weight base model plus our adapter, run in the customer's own cloud or data center | Planned: adapter export is not built yet |
| Standard alert export | Queue items as Common Alerting Protocol (CAP) messages for dispatch systems | Planned |

**Pricing model.** No prices are set. The model we would test: an annual subscription per agency for the console (seats plus a baseline volume of posts), usage-based pricing per post for software vendors on the API, surge capacity during declared disasters, and a separate license for private deployments. Pilots come first.

**Why margins can be strong.** The main variable cost is the model call, and it is measured, not estimated: $171 per million posts on Fireworks serverless ($342 at the undiscounted rate), against $8,738 for the frontier baseline (Claude Opus 5.5, 20-shot) and $499 for the cheapest frontier configuration we measured (GPT-6.1 Terra, zero-shot), which also scored lower macro-F1 in the paired comparison (Rescue Radar +8.6 pts, 95% CI +6.0 to +11.4 pts). Per-token pricing keeps the cost per post flat as volume grows, and because the base model is open-weight, serving is not tied to one frontier provider's price list: the same adapter could run on a dedicated Fireworks deployment or, once export is built, on a customer's own hardware. A subscription priced on the value of finding requests, on top of that cost, leaves room for healthy gross margins.

**A data moat from dispatcher feedback.** Every dispatcher action is a label: a dispatched, resolved or dismissed item says whether the model ranked that post well. With each customer's consent, those labels become training data for the next adapter (see [Roadmap](#roadmap)), so the model keeps learning the platforms, languages and kinds of disaster that customers actually see. A new adapter would ship only if it beats the current one on held-out disasters, with the same paired statistics as this benchmark. This matters for licensing too: the current adapter is trained on HumAID, which is non-commercial (CC BY-NC-SA 4.0), so a commercial product needs commercially licensed training data, from a license with the dataset's authors or from customers' own labels.

**Open weights, run privately.** Nemotron 3.5 Super is an open-weight model. An agency that cannot send posts to a third-party API could run the base model and our adapter inside its own environment, and personal data is already redacted before a dispatcher reads a post.

**Go to market.**

1. **Pilots with emergency operations centers.** Replay a past disaster from the agency's own area through the console (the replay mode exists today), then run Rescue Radar in shadow mode next to the current process during an exercise or a live activation, and measure what it catches and what it misses.
2. **Partnerships with dispatch-software vendors.** Agencies get Rescue Radar inside tools they already bought, through procurement they have already done; the vendor gets a measured triage model without building one.
3. **Expand by region and language.** Each new deployment adds feedback labels; multilingual evaluation is on the roadmap.

**Risks, and how the product handles them.**

| Risk | How Rescue Radar handles it |
| --- | --- |
| Liability for a missed or wrong call | It is decision support: the model ranks, and a dispatcher decides every queue item. It never drops a post: anything not marked rescue-critical stays in the situational feed for a person to read. Recall and precision on unseen disasters are published with intervals, including the weak side: rescue-critical precision is 60.2% against 78.1% for Claude Opus 5.5, 20-shot, so dispatchers see more false alarms in exchange for fewer missed requests. |
| Long public-sector procurement cycles | Start with pilots that replay past events (no integration needed), and sell through software vendors that agencies already buy from. |
| Platform data access | Social platforms restrict and charge for API access, and their terms change. The model classifies any text, by paste, upload or API, so customers connect the sources they are licensed to use; voice intake is on the roadmap. Live stream ingestion is not built yet. |
| Drift to new platforms, languages and disasters | Retrain from dispatcher feedback, and gate every new adapter on held-out disasters before it ships. |
| Privacy | PII is redacted before human review (best effort, see [limitations](#responsible-ai-and-limitations)), and private deployment keeps posts inside the agency. |

## FAQ

<details>
<summary><b>The data is from 2016 to 2019. Does this work on today's posts?</b></summary>

We do not know yet, and we say so. HumAID is English-language Twitter data; the test disasters are from 2019 and none of them were in training. Platforms and the way people ask for help have changed since, so performance on today's platforms is untested. Results also vary by disaster: rescue-critical recall is 90.5% on Cyclone Idai but 59.6% on Hurricane Dorian. Newer and multilingual evaluation is on the roadmap.
</details>

<details>
<summary><b>Who is liable if it misses someone?</b></summary>

Rescue Radar is decision support, not a dispatcher. The model ranks posts; a person decides every queue item, and nothing is dropped: posts not marked rescue-critical stay in the situational feed for a person to read. We publish the weak side next to the strong side, with intervals, so an agency can judge the risk before a pilot.
</details>

<details>
<summary><b>How many false alarms does it raise?</b></summary>

More than the frontier model. Rescue-critical precision is 60.2% against 78.1% for Claude Opus 5.5, 20-shot, so about 40% of the posts it flags are not rescue-critical. That is the trade we chose: the pre-registered primary metric is recall on rescue-critical posts (84.7%), because a missed rescue request costs more than a dispatcher dismissing a false alarm. The weakest category is `requests_or_urgent_needs` (precision 28.8%, recall 60.3%; only 78 test posts carry that label), where most false alarms are donation and volunteering posts.
</details>

<details>
<summary><b>How fast is it?</b></summary>

Slower than a frontier API today: 3.37 s median and 8.42 s p95 per post during the benchmark, against 1.31 s median for Claude Opus 5.5, 20-shot. Rescue Radar ran on shared Fireworks serverless capacity with 32 parallel requests, so these numbers include load. A dedicated Fireworks deployment for steady latency is the first roadmap item; we have not measured it.
</details>

<details>
<summary><b>What happens to personal data?</b></summary>

Before a dispatcher reads a post, `rr/scrub.py` replaces phone numbers, emails, handles, URLs and street addresses with placeholders, and names too when Microsoft Presidio is installed. Redaction is best effort and applies to what the dispatcher sees: the raw post is what the model provider (Fireworks) classifies. Because the base model is open-weight, posts could stay inside an agency's own environment once adapter export is built; it is not built yet.
</details>

<details>
<summary><b>What is the license?</b></summary>

The code is [MIT](LICENSE). The data is not: HumAID is CC BY-NC-SA 4.0, so the fine-tuned model and files derived from HumAID inherit its non-commercial, share-alike terms ([DATA_LICENSE.md](DATA_LICENSE.md)). A commercial product would need commercially licensed training data.
</details>

<details>
<summary><b>Can I reproduce the benchmark?</b></summary>

Yes. The per-post predictions of every system are committed in `data/preds/`, so `python -m rr.evaluate` recomputes every number in `results/metrics.json` (McNemar tests, 5,000-sample stratified bootstrap) without any API key. To regenerate the predictions themselves, follow [Reproduce the benchmark](#reproduce-the-benchmark); that needs Fireworks and Anthropic keys and costs money. The test set, systems, metrics and checkpoint rule were fixed in the [pre-registration](guide/PREREGISTRATION.md) before any fine-tuned model was scored, and its one correction is logged in it.
</details>

<details>
<summary><b>Why not just prompt a frontier model?</b></summary>

We tried, and measured it. On the 2,592 posts both answered, Claude Opus 5.5, 20-shot caught 68.8% of rescue-critical posts against 85.3% for Rescue Radar (+16.5 pts, 95% CI +11.2 to +21.9 pts), at 51.1x the cost per post. Fine-tuning on 15 earlier disasters teaches the model where the HumAID category boundaries are. The frontier model still has real advantages: higher rescue-critical precision, lower latency, and no training step. The same LoRA also lifts the untuned base model by +11.7 pts macro-F1.
</details>

<!-- ===================================================================== (f) Star and share, How to cite -->

## Roadmap

- [ ] Dedicated Fireworks deployment of the promoted model for steady latency at disaster-time volume
- [ ] Microsoft Foundry deployment path for agencies that run on Azure
- [ ] Learn from dispatcher actions: dispatched and dismissed items become new training labels
- [ ] Cluster near-duplicate requests so one address is not dispatched five times
- [ ] Location extraction beyond the gazetteer (named-entity recognition plus a geocoder) with uncertainty shown on the map
- [ ] Multilingual evaluation and newer events from other crisis datasets
- [ ] Calibrated confidence and an "unsure, send to a human" path, then confidence-aware escalation of uncertain posts to a frontier model (the policy the downshifting paper by a team member recommends testing)
- [ ] Voice intake for people who cannot reach 911: a talking [masky.ai](https://masky.ai/) avatar line that answers the call, PAVO-style routing across the speech-to-LLM pipeline, and Rescue Radar triage of the transcript
- [ ] Export queue items as Common Alerting Protocol (CAP) messages for dispatch systems

## Star and share

If Rescue Radar is useful to you, **star the repo** so people in emergency management and crisis informatics can find it, and share the **[live demo](https://vnmoorthy.github.io/rescue-radar/)**: it runs in any browser with no install. Found a post it gets wrong? [Open an issue](https://github.com/vnmoorthy/rescue-radar/issues/new/choose) with the text (remove personal data first). Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).

**How to cite.** Use GitHub's **Cite this repository** button (it reads [CITATION.cff](CITATION.cff)) or the BibTeX under [Citation](#citation), and please cite the HumAID dataset (Alam et al., ICWSM 2021) too.

<!-- ===================================================================== (g) Built in one afternoon -->

## Contributing

Contributions are welcome: bug reports, evaluation ideas, new disasters, better redaction. Read [CONTRIBUTING.md](CONTRIBUTING.md) and our [Code of Conduct](CODE_OF_CONDUCT.md). Please report security issues privately as described in [SECURITY.md](SECURITY.md).

## Citation

If you use Rescue Radar, please cite this repository and the HumAID dataset ([CITATION.cff](CITATION.cff)):

```bibtex
@software{rescue_radar_2026,
  title  = {Rescue Radar: real-time triage of disaster posts with a LoRA-tuned open model},
  author = {vnmoorthy and Caldwell, Seth},
  year   = {2026},
  url    = {https://github.com/vnmoorthy/rescue-radar},
  note   = {Built at the Fireworks: Deploy hackathon, San Francisco}
}

@inproceedings{alam2021humaid,
  title     = {HumAID: Human-Annotated Disaster Incidents Data from Twitter with Deep Learning Benchmarks},
  author    = {Alam, Firoj and Qazi, Umair and Imran, Muhammad and Ofli, Ferda},
  booktitle = {Proceedings of the International AAAI Conference on Web and Social Media (ICWSM)},
  year      = {2021}
}
```

## Acknowledgments

- [QCRI](https://www.hbku.edu.qa/en/qcri) for HumAID, the human-annotated disaster tweets this work is built on.
- [Fireworks AI](https://fireworks.ai/) for serverless LoRA training and sampling, and for hosting Fireworks: Deploy.
- [NVIDIA](https://www.nvidia.com/) for the Nemotron 3.5 Super open model.
- [Microsoft](https://microsoft.github.io/presidio/) for Presidio, used for PII redaction.
- [Anthropic](https://www.anthropic.com/) for Claude Opus 5.5, our frontier baseline.
- [OpenAI](https://openai.com/) for GPT-6.1 Terra, a second frontier baseline (added after pre-registration) and the Head-to-Head fallback.
- The responders and volunteers who read disaster feeds by hand, whose work inspired this project.

## Team

| | |
| --- | --- |
| **NarasingaMoorthy VeiluKanthaPerumal** | [@vnmoorthy](https://github.com/vnmoorthy) · [Google Scholar](https://scholar.google.com/citations?user=s7C14hwAAAAJ&hl=en) |
| **Seth Caldwell** | [masky.ai](https://masky.ai/) |

### Prior research by a team member

Rescue Radar is a downshifting decision: replacing a frontier model with a smaller open one. Before this hackathon, a member
of this team published on exactly that question in *How Much Quality Survives LLM Downshifting?* (TMLR, 08/2026,
[OpenReview](https://openreview.net/forum?id=6ccINAFoJi)), which shows that LLM-judged "quality preserved" figures swing
from 61% to 97% depending on the judge, and on routing inference across speech pipelines in *PAVO* (TMLR, 08/2026,
[OpenReview](https://openreview.net/forum?id=zrneoIxlFx)). Our evaluation follows the first paper's advice: human labels
instead of an LLM judge, intervals on every number, two prompting protocols per frontier model, real disaster posts.
PAVO is the blueprint for the voice-intake item on our roadmap. The Rescue Radar code, data split, fine-tune and benchmark
were built during the event. Full citations: [guide/REFERENCES.md](guide/REFERENCES.md).

## Built in one afternoon

Everything here was built on **November 2, 2026** at Fireworks: Deploy. Times are Pacific, taken from the files named in the right column.

| Time (PT) | Step | Evidence |
| --- | --- | --- |
| by 13:29 | **Data split.** HumAID split by disaster: 13,839 training examples from 15 disasters (2016 to 2018), and 3,001 test posts from 4 unseen disasters of 2019 | file time of `data/eval.jsonl` |
| 13:38 | **Training starts.** The small-data run (3,939 examples) at 13:38 and the main run (13,839 examples, 432 planned steps) at 13:40, both LoRA on Fireworks serverless training | `data/train_log.jsonl`, `data/train_log_full.jsonl` |
| 13:47 to 13:58 | **Baselines.** Untuned Nemotron 3.5 Super, Claude Opus 5.5 zero-shot and 20-shot (stopped early by the API spending cap), GPT-6.1 Terra zero-shot and 20-shot (added after pre-registration) | file times in `data/preds/` |
| 13:49 | **Pre-registration** of the test set, systems, metrics, statistics and the checkpoint rule, before any fine-tuned model was scored | [`guide/PREREGISTRATION.md`](guide/PREREGISTRATION.md) |
| 14:06 | Small-data run finishes (123 steps); it becomes the data-size ablation | `data/train_log.jsonl` |
| 14:40 | Correction logged in the pre-registration (the small run's size, 3,839 to 3,939); nothing else changed | [`guide/PREREGISTRATION.md`](guide/PREREGISTRATION.md) |
| 14:55 | **Freeze.** By the pre-registered rule, the main run's newest checkpoint saved by 14:55, step 275 (saved 14:50:36), is frozen as the main system at 14:55:04. The run was still training; later checkpoints are not scored, because test scores never pick a checkpoint. | [`data/active_model.json`](data/active_model.json) |
| about 15:02 | Frozen checkpoint scored on all 3,001 test posts | file time of `data/preds/rescue_radar.jsonl` |
| 15:05 | **Product.** First public commit: dispatch console, HTTP API, static demo on GitHub Pages, slide deck and docs | `git log` |
| 16:18 | `results/metrics.json` generated with paired statistics for every system | `results/metrics.json` |
| 15:26 onward | **QA.** Light and dark themes across console, site, deck and README art (15:26), cache-busted assets (15:33), then a QA pass over the console, site, deck and docs | `git log` |

<!-- ===================================================================== (h) Tech stack, optional -->

## Hackathon disclosure

Rescue Radar was built during **Fireworks: Deploy** in San Francisco on **November 2, 2026**. AI coding assistants were used while writing the code and documentation. The dataset is HumAID by QCRI; we did not collect or label any data. Frontier-baseline predictions come from Claude Opus 5.5 through the Anthropic API and GPT-6.1 Terra through the OpenAI API. The live Head-to-Head calls Claude Opus 5.5 and switches to GPT-6.1 Terra when the Anthropic account is out of quota; each result names the model that answered.

## License

Code: [MIT](LICENSE). Data: HumAID is CC BY-NC-SA 4.0 (non-commercial, share-alike); it is downloaded from its source by `rr.prep`, and files derived from it in `data/` keep that license.
