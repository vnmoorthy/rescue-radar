{#- README_ADDITIONS.md: ready-to-paste blocks for README.template.md. This is a staging file, not a template:
    scripts/render_docs.py only renders *.template.md, so the Jinja below stays raw until a block is pasted into
    README.template.md. Every benchmark number is a placeholder rendered from results/metrics.json; never type one in.

    Before merging block (a): assets/screens/ does not exist yet (not on disk, not on main). Add these three files first:
      assets/screens/replay.gif          a short capture of Live Replay with the priority queue filling
      assets/screens/replay-dark.png    the console in the dark theme
      assets/screens/replay-light.png   the same view in the light theme
    Suggested section order in the README: (a) after the hero, (b) at the top of Quickstart, (c) after "Why this matters",
    (d) at the end of Results, (e) before Contributing, (f) next to Citation, (g) before "Hackathon disclosure",
    (h) next to "Sponsor stack" or in place of it. -#}
{#- Same cache-buster as the top of README.template.md; these only apply if a block is pasted somewhere they are unset. -#}
{% if raw is not defined %}{% set raw = repo | replace("https://github.com/", "https://raw.githubusercontent.com/") ~ "/main/" %}{% endif %}
{% if v is not defined %}{% set v = "?v=sunrise-2" %}{% endif %}

<!-- ===================================================================== (a) See it in 60 seconds -->

## See it in 60 seconds

<p align="center">
  <img src="{{ raw }}assets/screens/replay.gif{{ v }}" alt="Rescue Radar replaying real posts from a 2019 disaster: rescue-critical posts move to the priority queue while the rest fill the situational feed" width="100%">
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="{{ raw }}assets/screens/replay-dark.png{{ v }}">
    <source media="(prefers-color-scheme: light)" srcset="{{ raw }}assets/screens/replay-light.png{{ v }}">
    <img src="assets/screens/replay-dark.png" alt="The Rescue Radar dispatch console: a map, the priority queue of rescue-critical posts, and the situational feed" width="100%">
  </picture>
</p>

1. Open the **[live demo](https://vnmoorthy.github.io/rescue-radar/)**. It runs in your browser: no account, no API key, no backend.
2. In **Live Replay**, pick one of the {{ num(m.eval.test_events) }} held-out 2019 disasters and press <kbd>Space</kbd>. Real posts arrive in their original order; the ones the model marks rescue-critical go to the priority queue, with personal data redacted.
3. Open **Benchmark** to see how those labels score against {{ frontier_name }} on {{ num(m.eval.n) }} posts the model never saw, then flip through the **[slides](https://vnmoorthy.github.io/rescue-radar/deck/)**.

<!-- ===================================================================== (b) Try it locally in 60 seconds -->

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

## Who is this for

| Who | What they get |
| --- | --- |
| **Emergency operations centers** | Replay a past disaster from your own area in the console (no integration needed), then run Rescue Radar in shadow mode beside your current process during an exercise. You get a priority queue of rescue-critical posts with personal data redacted, a map pin when a post names a known place, and a CSV export of the queue with each dispatcher's decision and notes. |
| **911 and emergency communications centers** | When phone lines saturate, people post publicly instead. Rescue Radar reads all of those posts and puts the {{ pct(d.eval_critical_share) }} that are rescue-critical (in our test set) first, and `/api/classify` lets dispatch software call the same model. It is decision support: a person decides every item. Common Alerting Protocol export is planned, not built. |
| **Relief NGOs** | A situational-awareness feed sorted into the {{ num(d.labels_n) }} HumAID categories (urgent needs, displaced people, infrastructure damage, donations and more), so a response team can see where needs cluster. The code is MIT; the HumAID-trained model inherits CC BY-NC-SA 4.0, so check that license against your use. |
| **Researchers in crisis informatics** | A held-out-disaster benchmark with a [pre-registration](guide/PREREGISTRATION.md), every system's per-post predictions in `data/preds/`, paired McNemar tests and stratified bootstrap intervals, per-disaster and per-category scores, and a script that re-renders every number in the docs. Add your model's predictions and compare on the same {{ num(m.eval.n) }} posts. |

<!-- ===================================================================== (d) Rescue Radar vs a frontier API -->

### Rescue Radar vs a frontier API

Paired on the {{ num(cmp.n) }} held-out posts that both Rescue Radar and {{ frontier_name }} answered. Better value in bold.

| | Rescue Radar | {{ frontier_name }} |
| --- | --- | --- |
| Quality: macro-F1 over {{ num(d.labels_n) }} categories | **{{ pct(cmp.a_on_shared.macro_f1) }}** | {{ pct(cmp.b_on_shared.macro_f1) }} |
| Rescue-critical recall (a missed request is the costly error) | **{{ pct(cmp.a_on_shared.critical_recall) }}** | {{ pct(cmp.b_on_shared.critical_recall) }} |
| Rescue-critical precision (lower means more false alarms) | {{ pct(ours.critical.precision) }} | **{{ pct(frontier.critical.precision) }}** |
| Cost per 1M posts (measured tokens x published price) | **{{ usd(ours.cost_per_1m_usd) }}** ({{ usd(ours.cost_per_1m_usd_undiscounted) }} without Fireworks' limited-time 50% discount) | {{ usd(frontier.cost_per_1m_usd) }} |
| Can run privately | Partly: the base model is open-weight, so an agency could host it; exporting our adapter is not built yet | No: every post goes to a third-party API |
| Latency per post, p50 / p95, as measured in the benchmark run | {{ ms(ours.latency_ms.p50) }} / {{ ms(ours.latency_ms.p95) }} | **{{ ms(frontier.latency_ms.p50) }} / {{ ms(frontier.latency_ms.p95) }}** |

<sub>Differences with 95% paired-bootstrap intervals: macro-F1 {{ pts(cmp.delta_macro_f1) }} ({{ ci_pts(cmp.bootstrap.macro_f1_delta_ci95) }}), rescue-critical recall {{ pts(cmp.delta_critical_recall) }} ({{ ci_pts(cmp.bootstrap.critical_recall_delta_ci95) }}). Cost: {{ ratio(frontier.cost_per_1m_usd, ours.cost_per_1m_usd) }} cheaper at today's Fireworks rate, {{ ratio(frontier.cost_per_1m_usd, ours.cost_per_1m_usd_undiscounted) }} at the undiscounted rate. The cheapest frontier setup we measured, {{ systems.gpt_zero.name }}, costs {{ usd(systems.gpt_zero.cost_per_1m_usd) }} per 1M posts ({{ ratio(systems.gpt_zero.cost_per_1m_usd, ours.cost_per_1m_usd) }} ours), and Rescue Radar is {{ pts(cmp_by_b.gpt_zero.delta_macro_f1) }} ahead of it on macro-F1 ({{ ci_pts(cmp_by_b.gpt_zero.bootstrap.macro_f1_delta_ci95) }}). Latency: Rescue Radar is slower; it ran with 32 parallel requests on shared Fireworks serverless capacity and Claude with 24 through the Anthropic API, so both numbers include load. A dedicated deployment is on the roadmap and not measured.</sub>

<!-- ===================================================================== (e) FAQ -->

## FAQ

<details>
<summary><b>The data is from 2016 to 2019. Does this work on today's posts?</b></summary>

We do not know yet, and we say so. HumAID is English-language Twitter data; the test disasters are from 2019 and none of them were in training. Platforms and the way people ask for help have changed since, so performance on today's platforms is untested. Results also vary by disaster: rescue-critical recall is {{ pct(ours.per_event.cyclone_idai_2019.critical_recall) }} on Cyclone Idai but {{ pct(ours.per_event.hurricane_dorian_2019.critical_recall) }} on Hurricane Dorian. Newer and multilingual evaluation is on the roadmap.
</details>

<details>
<summary><b>Who is liable if it misses someone?</b></summary>

Rescue Radar is decision support, not a dispatcher. The model ranks posts; a person decides every queue item, and nothing is dropped: posts not marked rescue-critical stay in the situational feed for a person to read. We publish the weak side next to the strong side, with intervals, so an agency can judge the risk before a pilot.
</details>

<details>
<summary><b>How many false alarms does it raise?</b></summary>

More than the frontier model. Rescue-critical precision is {{ pct(ours.critical.precision) }} against {{ pct(frontier.critical.precision) }} for {{ frontier_name }}, so about {{ pct(1 - ours.critical.precision if ours.critical.precision is number else none, 0) }} of the posts it flags are not rescue-critical. That is the trade we chose: the pre-registered primary metric is recall on rescue-critical posts ({{ pct(ours.critical.recall) }}), because a missed rescue request costs more than a dispatcher dismissing a false alarm. The weakest category is `requests_or_urgent_needs` (precision {{ pct(ours.per_class.requests_or_urgent_needs.precision) }}, recall {{ pct(ours.per_class.requests_or_urgent_needs.recall) }}; only {{ num(ours.per_class.requests_or_urgent_needs.support) }} test posts carry that label), where most false alarms are donation and volunteering posts.
</details>

<details>
<summary><b>How fast is it?</b></summary>

Slower than a frontier API today: {{ ms(ours.latency_ms.p50) }} median and {{ ms(ours.latency_ms.p95) }} p95 per post during the benchmark, against {{ ms(frontier.latency_ms.p50) }} median for {{ frontier_name }}. Rescue Radar ran on shared Fireworks serverless capacity with 32 parallel requests, so these numbers include load. A dedicated Fireworks deployment for steady latency is the first roadmap item; we have not measured it.
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

Yes. The per-post predictions of every system are committed in `data/preds/`, so `python -m rr.evaluate` recomputes every number in `results/metrics.json` (McNemar tests, {{ num(m.eval.bootstrap_resamples) }}-sample stratified bootstrap) without any API key. To regenerate the predictions themselves, follow [Reproduce the benchmark](#reproduce-the-benchmark); that needs Fireworks and Anthropic keys and costs money. The test set, systems, metrics and checkpoint rule were fixed in the [pre-registration](guide/PREREGISTRATION.md) before any fine-tuned model was scored, and its one correction is logged in it.
</details>

<details>
<summary><b>Why not just prompt a frontier model?</b></summary>

We tried, and measured it. On the {{ num(cmp.n) }} posts both answered, {{ frontier_name }} caught {{ pct(cmp.b_on_shared.critical_recall) }} of rescue-critical posts against {{ pct(cmp.a_on_shared.critical_recall) }} for Rescue Radar ({{ pts(cmp.delta_critical_recall) }}, 95% CI {{ ci_pts(cmp.bootstrap.critical_recall_delta_ci95) }}), at {{ ratio(frontier.cost_per_1m_usd, ours.cost_per_1m_usd) }} the cost per post. Fine-tuning on {{ num(m.eval.train_events) }} earlier disasters teaches the model where the HumAID category boundaries are. The frontier model still has real advantages: higher rescue-critical precision, lower latency, and no training step. The same LoRA also lifts the untuned base model by {{ pts(cmp_by_b.base_zero.delta_macro_f1) }} macro-F1.
</details>

<!-- ===================================================================== (f) Star and share, How to cite -->

## Star and share

If Rescue Radar is useful to you, **star the repo** so people in emergency management and crisis informatics can find it, and share the **[live demo](https://vnmoorthy.github.io/rescue-radar/)**: it runs in any browser with no install. Found a post it gets wrong? [Open an issue](https://github.com/vnmoorthy/rescue-radar/issues/new/choose) with the text (remove personal data first). Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).

**How to cite.** Use GitHub's **Cite this repository** button (it reads [CITATION.cff](CITATION.cff)) or the BibTeX under [Citation](#citation), and please cite the HumAID dataset (Alam et al., ICWSM 2021) too.

<!-- ===================================================================== (g) Built in one afternoon -->

## Built in one afternoon

Everything here was built on **November 2, 2026** at Fireworks: Deploy. Times are Pacific, taken from the files named in the right column.

| Time (PT) | Step | Evidence |
| --- | --- | --- |
| by 13:29 | **Data split.** HumAID split by disaster: {{ num(ours_train.examples) }} training examples from {{ num(m.eval.train_events) }} disasters (2016 to 2018), and {{ num(m.eval.n) }} test posts from {{ num(m.eval.test_events) }} unseen disasters of 2019 | file time of `data/eval.jsonl` |
| {{ d.runs.quick.started[:5] }} | **Training starts.** The small-data run (3,939 examples) at {{ d.runs.quick.started[:5] }} and the main run ({{ num(ours_train.examples) }} examples, {{ num(ours_train.steps) }} planned steps) at {{ ours_run.started[:5] }}, both LoRA on Fireworks serverless training | `data/train_log.jsonl`, `data/train_log_full.jsonl` |
| 13:47 to 13:58 | **Baselines.** Untuned Nemotron 3.5 Super, Claude Opus 5.5 zero-shot and 20-shot (stopped early by the API spending cap), GPT-6.1 Terra zero-shot and 20-shot (added after pre-registration) | file times in `data/preds/` |
| 13:49 | **Pre-registration** of the test set, systems, metrics, statistics and the checkpoint rule, before any fine-tuned model was scored | [`guide/PREREGISTRATION.md`](guide/PREREGISTRATION.md) |
| {{ d.runs.quick.finished[:5] }} | Small-data run finishes ({{ num(d.runs.quick.steps) }} steps); it becomes the data-size ablation | `data/train_log.jsonl` |
| 14:40 | Correction logged in the pre-registration (the small run's size, 3,839 to 3,939); nothing else changed | [`guide/PREREGISTRATION.md`](guide/PREREGISTRATION.md) |
| {{ d.active_model.frozen_at[:5] }} | **Freeze.** By the pre-registered rule, the main run's newest checkpoint saved by 14:55, step {{ d.active_model.step }} (saved {{ d.active_model.at }}), is frozen as the main system at {{ d.active_model.frozen_at }}.{{ " The run was still training; later checkpoints are not scored, because test scores never pick a checkpoint." if d.active_model.run_finished == false else "" }} | [`data/active_model.json`](data/active_model.json) |
| about 15:02 | Frozen checkpoint scored on all {{ num(m.eval.n) }} test posts | file time of `data/preds/rescue_radar.jsonl` |
| 15:05 | **Product.** First public commit: dispatch console, HTTP API, static demo on GitHub Pages, slide deck and docs | `git log` |
| {{ m.generated_at[11:16] }} | `results/metrics.json` generated with paired statistics for every system | `results/metrics.json` |
| 15:26 onward | **QA.** Light and dark themes across console, site, deck and README art (15:26), cache-busted assets (15:33), then a QA pass over the console, site, deck and docs | `git log` |

<!-- ===================================================================== (h) Tech stack, optional -->

## Tech stack: what each piece made possible

| Technology | What it enabled |
| --- | --- |
| **Fireworks AI** serverless LoRA training and sampling | Fine-tuning a large open model in an afternoon with no GPUs to provision, a sampler checkpoint every 25 steps (which made the pre-registered 14:55 freeze possible), and serving the exact scored checkpoint to the live console through the same code path as the benchmark. |
| **NVIDIA Nemotron 3.5 Super** (open weights) | The base model we fine-tune. Open weights are what make private hosting by an agency possible later; the LoRA lifts it by {{ pts(cmp_by_b.base_zero.delta_macro_f1) }} macro-F1 and {{ pts(cmp_by_b.base_zero.delta_critical_recall) }} rescue-critical recall. |
| **HumAID** (QCRI) | Human-labeled tweets from {{ num(d.all_events_n) }} disasters, enough to train on {{ num(m.eval.train_events) }} and test on {{ num(m.eval.test_events) }} unseen ones. |
| **Microsoft Presidio** + spaCy | PII redaction before a dispatcher reads a post, merged with regexes for handles, URLs and addresses. |
| **FastAPI** + uvicorn, plain JavaScript | The dispatch console and HTTP API with no front-end build step; a static export of the same console runs on GitHub Pages with no backend. |
| **Claude Opus 5.5** and **GPT-6.1 Terra** | Frontier baselines, scored with the same prompt and category definitions. |
| NumPy, Jinja2, python-pptx | Exact McNemar tests and stratified bootstrap; docs rendered from `results/metrics.json` so no number is typed by hand; the PPTX deck. |
