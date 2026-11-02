{#- Rendered to README.md by scripts/render_docs.py. Every number below comes from results/metrics.json or data/ at
    render time; anything missing prints as "n/a". Never type a benchmark number into this file. -#}
{% set run = ours_run %}
{% set sh_a = cmp.a_on_shared or {} %}{% set sh_b = cmp.b_on_shared or {} %}
{% set bs = cmp.bootstrap or {} %}
{% set mf_side = ci_side(bs.macro_f1_delta_ci95) %}{% set cr_side = ci_side(bs.critical_recall_delta_ci95) %}{% set acc_side = ci_side(bs.delta_ci95) %}
{% set test_events = m.eval.test_events or d.test_events_n %}
{% set train_events = m.eval.train_events or d.train_events_n %}
{% set eval_n = m.eval.n or d.eval_n %}
{% set of1 = f(ours.macro_f1) %}{% set ff1 = f(frontier.macro_f1) %}
{% set oc = f(ours.cost_per_1m_usd) %}{% set fc = f(frontier.cost_per_1m_usd) %}
{% set ol = f(ours.latency_ms.p50) %}{% set fl = f(frontier.latency_ms.p50) %}
<div align="center">

<img src="assets/hero.svg" alt="Rescue Radar: a radar sweep over a storm map lights up rescue requests among disaster posts" width="100%">

### Find the people asking for rescue in the flood of disaster posts, in real time.

[![CI](https://github.com/vnmoorthy/rescue-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/vnmoorthy/rescue-radar/actions/workflows/ci.yml)
[![License: MIT]({{ shield("license", "MIT", "2ea44f") }})](LICENSE)
[![Python 3.12]({{ shield("python", "3.12", "3776AB", logo="python") }})](https://www.python.org/)
[![Fireworks AI]({{ shield("Fireworks AI", "serverless LoRA + sampling", "6720FF") }})](https://fireworks.ai/)
[![NVIDIA Nemotron]({{ shield("NVIDIA", "Nemotron 3.5 Super", "76B900", logo="nvidia") }})](https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/)
{% if integ.presidio %}
[![Microsoft]({{ shield("Microsoft", "Presidio PII redaction", "0078D4") }})](https://microsoft.github.io/presidio/)
{% else %}
[![Microsoft]({{ shield("Microsoft", "Foundry deployment path", "0078D4") }})](guide/DEPLOYMENT.md)
{% endif %}
[![HumAID]({{ shield("data", "HumAID (QCRI)", "F59E0B") }})](https://huggingface.co/datasets/QCRI/HumAID-events)
[![Hackathon]({{ shield("hackathon", "Fireworks: Deploy 2026", "E11D48") }})](#hackathon-disclosure)
{% if of1 is not none %}
[![macro-F1]({{ shield("macro-F1 on unseen disasters" ~ (" (small-data run)" if headline_ablation else ""), pct(of1), "0E7490") }})](#results)
{% endif %}

**[Live demo](https://vnmoorthy.github.io/rescue-radar/)** &nbsp;·&nbsp;
**[Slides](https://vnmoorthy.github.io/rescue-radar/deck/)** &nbsp;·&nbsp;
[Results](#results) &nbsp;·&nbsp; [How it works](#how-it-works) &nbsp;·&nbsp; [Quickstart](#quickstart) &nbsp;·&nbsp;
[Evaluation design](guide/EVALUATION.md)

</div>

---

**Rescue Radar reads every public post during a disaster, sorts it into the {{ num(d.labels_n) }} HumAID humanitarian categories, and pushes the rescue-critical ones (people asking for help, people injured or killed, people missing or trapped) to the top of a dispatcher's queue.** The model is NVIDIA Nemotron 3.5 Super, fine-tuned with LoRA on Fireworks serverless training and served through Fireworks serverless sampling, and it is tested on {{ num(test_events) }} disasters from 2019 that it never saw during training.

{% if of1 is not none and ff1 is not none and cmp.mcnemar is mapping %}
> [!IMPORTANT]
{% if headline_ablation %}
> **These are the small-data run's numbers** ({{ num(ours_train.examples) }} training examples{% if ours.checkpoint_step %}, step {{ ours.checkpoint_step }}{% endif %}). The [pre-registration](guide/PREREGISTRATION.md) lists that run as a data-size ablation; the pre-registered main system is not scored yet.
>
{% endif %}
> Paired on the **{{ num(cmp.n) }}** held-out posts from {{ num(test_events) }} unseen disasters that both systems answered, Rescue Radar catches **{{ pct(sh_a.critical_recall) }}** of rescue-critical posts against **{{ pct(sh_b.critical_recall) }}** for {{ frontier_name }} (**{{ pts(cmp.delta_critical_recall) }}**, 95% CI {{ ci_pts(bs.critical_recall_delta_ci95) }}{{ ", so the gain is not luck of the draw" if cr_side == "above" else "" }}). Macro-F1 is {{ pct(sh_a.macro_f1) }} against {{ pct(sh_b.macro_f1) }} ({{ pts(cmp.delta_macro_f1) }}, 95% CI {{ ci_pts(bs.macro_f1_delta_ci95) }}){% if mf_side == "spans" %}: within noise, so we do not claim a macro-F1 win{% elif mf_side == "below" %}: {{ frontier_name }} is ahead{% endif %}. Rescue-critical precision is lower ({{ pct(ours.critical.precision) }} vs {{ pct(frontier.critical.precision) }}, each on the posts it answered).
{% if oc is not none and fc is not none and oc > 0 and fc > 0 %}
>
> It costs **{{ usd(oc) }} per million posts** against {{ usd(fc) }} ({{ ratio(fc, oc) if fc >= oc else ratio(oc, fc) }} {{ "cheaper" if fc >= oc else "more expensive" }} at Fireworks' current rate, which includes a limited-time 50% discount{% if ours.cost_per_1m_usd_undiscounted is number %}; {{ ratio(fc, ours.cost_per_1m_usd_undiscounted) }} at the undiscounted rate{% endif %}){% if ol is not none and fl is not none %}. It is {{ "slower" if ol > fl else "faster" }} per post: median latency {{ ms(ol) }} against {{ ms(fl) }}{% endif %}. Statistics, intervals and caveats are in [Results](#results).
{% endif %}
{% else %}
> [!NOTE]
> Benchmark results are **pending**: they appear here automatically when `python -m rr.evaluate` writes `results/metrics.json` and `python scripts/render_docs.py` re-renders this page.{% if base.macro_f1 is number %} So far: the untuned base model, {{ base.name }}, scores {{ pct(base.macro_f1) }} macro-F1 on the {{ num(eval_n) }}-post held-out set.{% endif %}

{% endif %}

## Contents

[Why this matters](#why-this-matters) · [Results](#results) · [How it works](#how-it-works) · [Evaluation design](#evaluation-design-held-out-disasters) · [Quickstart](#quickstart) · [Reproduce the benchmark](#reproduce-the-benchmark) · [Repository layout](#repository-layout) · [Sponsor stack](#sponsor-stack) · [Responsible AI and limitations](#responsible-ai-and-limitations) · [Roadmap](#roadmap) · [Contributing](#contributing) · [Citation](#citation) · [Team](#team)

## Why this matters

When a hurricane or an earthquake hits, emergency lines saturate, and people turn to public social media to ask for help: an address, a trapped family, a missing child. Those posts are scattered among thousands of prayers, news links, donation drives and jokes. Responders have had to read them by hand.

The signal is rare. In the held-out evaluation set, only **{{ pct(d.eval_critical_share) }}** of posts ({{ num(d.eval_critical_n) }} of {{ num(d.eval_n) }}) are rescue-critical. A dispatcher cannot read the other {{ pct(1 - d.eval_critical_share if d.eval_critical_share is number else none) }} fast enough. Rescue Radar reads all of them and puts the few that matter first, with personal data redacted, a location when the post names a known place, and a human making every decision.

Why a fine-tuned open model instead of a frontier API? What [Results](#results) measures against {{ frontier_name }}:{% if cr_side == "above" %} significantly higher rescue-critical recall ({{ pts(cmp.delta_critical_recall) }}, at lower precision){% elif cr_side %} rescue-critical recall {{ pts(cmp.delta_critical_recall) }} (95% CI {{ ci_pts(bs.critical_recall_delta_ci95) }}){% endif %}{% if mf_side == "spans" and acc_side == "spans" %}, macro-F1 and accuracy statistically level{% elif mf_side %}, macro-F1 {{ pts(cmp.delta_macro_f1) }} (95% CI {{ ci_pts(bs.macro_f1_delta_ci95) }}){% endif %}{% if oc is not none and fc is not none and oc > 0 and fc > 0 %}, and about {{ ratio(fc, oc) }} lower serving cost ({{ ratio(fc, ours.cost_per_1m_usd_undiscounted) }} at the undiscounted rate){% endif %}{% if ol is not none and fl is not none and ol > fl %}. It is slower per post on shared serverless capacity ({{ ms(ol) }} median against {{ ms(fl) }}){% endif %}. The base model is open, so the small LoRA adapter could be exported for an agency to host itself instead of sending every post to a third-party API; that export is not built yet.

## Results

Evaluated on **{{ num(eval_n) }}** posts sampled from {{ num(test_events) }} disasters of 2019, none of which were in our fine-tuning data ([evaluation design](#evaluation-design-held-out-disasters)). Every system gets the same instructions and the same {{ num(d.labels_n) }} category definitions; the 20-shot baselines also get 20 examples.{% for r in rows if r.s.coverage is number and r.s.coverage < 1 %}{% if loop.first %} **Not every system answered every post:** the Anthropic account hit its spending cap mid-run, so{% endif %} {{ r.name }} was scored on the {{ num(r.s.n) }} posts it answered ({{ pct(r.s.coverage, 0) }}){{ "," if not loop.last else "." }}{% if loop.last %} Each row's score is on its own posts; the comparisons below are paired on the posts both systems answered.{% endif %}{% endfor %}


| System | Posts scored | Macro-F1 | Accuracy | Rescue-critical recall | p50 latency | Cost per 1M posts |
| --- | --- | --- | --- | --- | --- | --- |
{% for r in rows %}
| {{ "**" ~ ("Rescue Radar (small-data run)" if headline_ablation else r.name) ~ "**" if r.ours else r.name }} | {{ num(r.s.n) }} | {{ "**" ~ pct(r.s.macro_f1) ~ "**" if r.ours else pct(r.s.macro_f1) }}<br><sub>{{ ci(r.s.ci95.macro_f1) }}</sub> | {{ pct(r.s.accuracy) }}<br><sub>{{ ci(r.s.ci95.accuracy) }}</sub> | {{ pct(r.s.critical.recall) }}<br><sub>{{ ci(r.s.ci95.critical_recall) }}</sub> | {{ ms(r.s.latency_ms.p50) }} | {{ usd(r.s.cost_per_1m_usd) }} |
{% endfor %}

<sub>Small numbers are 95% bootstrap intervals ({{ num(m.eval.bootstrap_resamples) }} paired resamples of tweets, stratified by disaster). Rescue-critical recall: the share of posts whose true label is one of {% for k in d.critical_labels %}`{{ k }}`{{ ", " if not loop.last }}{% endfor %} that the system also labels as one of those three. Latency is wall-clock time per post as measured during the benchmark run (Rescue Radar and base Nemotron through Fireworks serverless sampling with 32 parallel requests on shared capacity, Claude through the Anthropic API with 24), so it reflects load as well as the model. Cost is measured tokens times published per-token prices:
{% for r in rows if r.s.cost_note %}
<br>{{ r.name }}: {{ r.s.cost_note }}.
{% endfor %}
</sub>

### Is the difference real?

{% if cmp.mcnemar is mapping %}
Both systems answered the same {{ num(cmp.n) }} of the {{ num(eval_n) }} posts, so we compare them post by post on those: Rescue Radar {{ pct(sh_a.macro_f1) }} macro-F1 and {{ pct(sh_a.critical_recall) }} rescue-critical recall, {{ frontier_name }} {{ pct(sh_b.macro_f1) }} and {{ pct(sh_b.critical_recall) }}.

- **Paired exact test (McNemar).** Rescue Radar was right where {{ frontier_name }} was wrong on **{{ num(cmp.mcnemar.a_only) }}** posts, and the reverse happened on **{{ num(cmp.mcnemar.b_only) }}** posts. If both systems were equally accurate, a split at least this uneven would happen by chance with {{ pval(cmp.mcnemar.p) }}{% if cmp.mcnemar.log10_p is number and cmp.mcnemar.p is number and cmp.mcnemar.p < 0.001 %} (log10 p = {{ num(cmp.mcnemar.log10_p) }}){% endif %}.
- **Paired bootstrap, stratified by disaster.** Resampling tweets within each disaster {{ num(cmp.bootstrap.n) }} times, the 95% interval for Rescue Radar minus {{ frontier_name }} is {{ ci_pts(cmp.bootstrap.macro_f1_delta_ci95) }} for macro-F1, {{ ci_pts(cmp.bootstrap.delta_ci95) }} for accuracy and {{ ci_pts(cmp.bootstrap.critical_recall_delta_ci95) }} for rescue-critical recall. Rescue Radar has the higher macro-F1 in {{ num(cmp.bootstrap.a_wins) }} of {{ num(cmp.bootstrap.n) }} resamples.
{% set side = ci_side(cmp.bootstrap.macro_f1_delta_ci95) %}
{% if side == "above" %}
- **In plain words:** the macro-F1 advantage is not luck of the draw. The whole 95% interval is above zero.
{% elif side == "below" %}
- **In plain words:** {{ frontier_name }} is ahead on macro-F1, and the whole 95% interval of the difference is below zero.
{% elif side == "spans" %}
- **In plain words:** the macro-F1 difference is within noise. The 95% interval includes zero, so we do not claim either system is better on that metric.
{% endif %}
{% else %}
Statistics are **pending** until `results/metrics.json` contains the comparison between Rescue Radar and the frontier baseline.
{% endif %}

{% if cmps %}
<details>
<summary><b>Every pairwise comparison</b></summary>

| Rescue Radar vs | Macro-F1 difference (95% CI) | Accuracy difference (95% CI) | Rescue-critical recall difference (95% CI) | Ours right, theirs wrong / reverse | McNemar |
| --- | --- | --- | --- | --- | --- |
{% for c in cmps %}
| {{ (systems.get(c.b) or {}).get('name') or c.b }} | {{ pts(c.delta_macro_f1) }} ({{ ci_pts(c.bootstrap.macro_f1_delta_ci95) }}) | {{ pts(c.delta) }} ({{ ci_pts(c.bootstrap.delta_ci95) }}) | {{ pts(c.delta_critical_recall) }} ({{ ci_pts(c.bootstrap.critical_recall_delta_ci95) }}) | {{ num(c.mcnemar.a_only) }} / {{ num(c.mcnemar.b_only) }} | {{ pval(c.mcnemar.p) }} |
{% endfor %}

</details>
{% endif %}

<details>
<summary><b>Per disaster</b>: does it hold up on each unseen event?</summary>

| Disaster (2019) | Posts | Rescue Radar macro-F1 | {{ frontier_name }} macro-F1 | Rescue Radar critical recall | {{ frontier_name }} critical recall |
| --- | --- | --- | --- | --- | --- |
{% for e, n in (m.eval.events or d.eval_events or {}) | dictsort(by='value', reverse=true) %}
| {{ event_name(e) }} | {{ num(n) }} | {{ pct(ours.per_event[e].macro_f1) }} | {{ pct(frontier.per_event[e].macro_f1) }} | {{ pct(ours.per_event[e].critical_recall) }} | {{ pct(frontier.per_event[e].critical_recall) }} |
{% endfor %}

</details>

<details>
<summary><b>Rescue-critical categories</b>: precision, recall and F1 per class</summary>

| Category | Posts in eval set | Rescue Radar P / R / F1 | {{ frontier_name }} P / R / F1 |
| --- | --- | --- | --- |
{% for k in d.critical_labels %}
| {{ label_name(k) }} | {{ num(d.eval_labels[k]) }} | {{ pct(ours.per_class[k].precision) }} / {{ pct(ours.per_class[k].recall) }} / {{ pct(ours.per_class[k].f1) }} | {{ pct(frontier.per_class[k].precision) }} / {{ pct(frontier.per_class[k].recall) }} / {{ pct(frontier.per_class[k].f1) }} |
{% endfor %}

Small classes have wide intervals: read per-class numbers for categories with few posts as indicative only.

</details>

{% if m.generated_at %}
<sub>Results generated {{ m.generated_at }} by `python -m rr.evaluate`. Full numbers, including confusion matrices: [`results/metrics.json`](results/metrics.json).</sub>
{% endif %}

## How it works

1. **Ingest.** Posts arrive one by one. The demo replays the real 2019 disaster tweets in their original order (a tweet ID is a Twitter snowflake, so its post time is `(id >> 22) + 1288834974657` ms), or classifies text you paste or upload. Live stream ingestion is not built yet.
2. **Classify.** One instruction prompt with the {{ num(d.labels_n) }} category definitions, one label out. The LoRA-tuned Nemotron runs on Fireworks serverless sampling at temperature 0; its reasoning block is closed in the prompt so it answers with the label alone.
3. **Prioritize.** Rescue-critical labels (`requests_or_urgent_needs`, `injured_or_dead_people`, `missing_or_found_people`) go to the priority queue. Everything else stays in the situational-awareness feed.
4. **Protect.** Before a person reads a post, `rr/scrub.py` replaces phone numbers, emails, handles, URLs and street addresses with placeholders{% if integ.presidio %}, and people's names too when Microsoft Presidio is installed (a regex-only engine runs otherwise){% endif %}. This is best effort, and it applies to what the dispatcher sees: the raw post is what goes to the model providers.
5. **Locate.** `rr/geo.py` maps place names in the post to coordinates with a gazetteer of the affected areas. It never guesses a location for a post that names no known place.
6. **Decide.** A dispatcher works the queue: dispatch, resolve or dismiss, with notes, and exports it as CSV. The model ranks; a human decides.

The live console and the benchmark share the same code path, `rr.infer.SamplerClassifier`, with the same prompt from `rr/labels.py`. By default the server serves exactly the checkpoint the benchmark scored for the headline system (recorded in `data/preds/<system>.meta.json`), and the console's header badge says "scored". `RR_LIVE_MODEL=latest` serves the newest training checkpoint instead, and the badge then says it is not scored.

<p align="center">
  <img src="assets/architecture.svg" alt="Architecture: offline training and evaluation lane, online triage lane, and ship lane" width="100%">
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
| Train | {{ num(train_events) }} HumAID events | 2016 to 2018 | {{ num(d.train_sft_n) }} in the training file{% if ours_train.examples is number %}, {{ num(ours_train.examples) }} used by the headline model{% endif %} |
| Test | {{ num(test_events) }} unseen events: {% for e in (m.eval.events or d.eval_events or {}) | sort %}{{ event_name(e) }}{{ ", " if not loop.last }}{% endfor %} | 2019 | {{ num(d.test_full_n) }} in total; a seeded, event-stratified sample of {{ num(eval_n) }} is the shared eval set |

- **No leakage by copy.** Training tweets whose normalized text also appears in the test events (retweets, copies) are removed{% if d.dedup_removed is number %}: {{ num(d.dedup_removed) }} of {{ num(d.raw_train_n) }} training-event tweets{% endif %}.
- **Prompt parity.** Every system gets the same system prompt and category definitions (`rr/labels.py`). The 20-shot frontier baseline adds two fixed training examples per category.
- **Baselines.** {{ frontier_name }} as the strongest frontier reference (zero-shot and 20-shot), and the same Nemotron base model without fine-tuning, served through the same Fireworks path, so the gain from LoRA is isolated. GPT-6.1 Terra (zero-shot and 20-shot, through the OpenAI API) was added after pre-registration.
- **Statistics.** Exact McNemar test on per-post correctness, and a paired bootstrap resampled within each disaster for every interval.
- **Measured, not estimated.** Latency is measured per call; cost is measured token counts times published prices.{% if m.eval.preregistration %} The choice of the headline system and metrics was fixed before test-set scoring ([`{{ m.eval.preregistration }}`]({{ m.eval.preregistration }})).{% endif %}{% if headline_ablation %} **Deviation:** the pre-registered main system (the larger run's checkpoint frozen at 14:55) has not been scored yet, so the headline numbers on this page come from the small-data run that the pre-registration lists as an ablation.{% endif %}

The full method is in [guide/EVALUATION.md](guide/EVALUATION.md).

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
python -m rr.run_model rescue_radar                 # fine-tuned model, final checkpoint of the headline run
python -m rr.run_model rescue_radar_quick           # ablation
python -m rr.run_model base_zero                    # Nemotron 3.5 Super without fine-tuning
python -m rr.baseline opus_zero                     # Claude Opus 5.5, zero-shot
python -m rr.baseline opus_few                      # Claude Opus 5.5, 20-shot
python -m rr.evaluate                               # results/metrics.json
python scripts/render_docs.py                       # re-render README.md and the guides with the new numbers
```

Every prediction script is resumable: rows already in `data/preds/<system>.jsonl` are skipped. Training writes a sampler checkpoint every 25 steps, so the newest one can be evaluated even if a run is cut short.{% if run.steps %} The headline training run logged {{ num(run.steps) }}{% if ours_train.steps and run.steps < ours_train.steps %} of {{ num(ours_train.steps) }} steps so far (still training){% else %} steps{% endif %} in {{ num(run.train_minutes, 0) }} minutes of training time on Fireworks serverless.{% endif %}

## Repository layout

```text
rescue-radar/
├── rr/                      Python package
│   ├── labels.py            the 10 HumAID categories, RESCUE_CRITICAL, the single prompt
│   ├── prep.py              held-out-disaster split and de-duplication
│   ├── train.py             LoRA fine-tune on Fireworks serverless training
│   ├── infer.py             the live model: Fireworks serverless sampling
│   ├── run_model.py         scores the open models on the eval set
│   ├── baseline.py          scores Claude Opus 5.5 (zero-shot, 20-shot)
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
| **Microsoft** | {% if integ.presidio %}[Microsoft Presidio](https://microsoft.github.io/presidio/) (presidio-analyzer with spaCy, presidio-anonymizer) redacts personal data before a dispatcher reads a post, merged with regexes for handles, URLs and addresses; when Presidio is not installed, the regex engine runs alone.{% else %}PII redaction before human review (`rr/scrub.py`).{% endif %} Deployment to Microsoft Foundry is a documented next step, not yet implemented: see [guide/DEPLOYMENT.md](guide/DEPLOYMENT.md). | `rr/scrub.py` |

Also used: **Anthropic** Claude Opus 5.5 as the frontier baseline (`rr/baseline.py`, `rr/frontier.py`), and **QCRI**'s HumAID dataset.

## Responsible AI and limitations

- **A human decides.** Rescue Radar ranks posts; it never dispatches anyone. Every queue item needs a dispatcher's action, and the model can be wrong, especially on a kind of disaster or a way of writing it has not seen.
- **Old data, one platform.** HumAID is English-language Twitter data from 2016 to 2019. Language, platforms and the way people ask for help have changed since; performance on today's platforms is untested.
- **The most important classes are the smallest.** In the eval set, `requests_or_urgent_needs` has {{ num(d.eval_labels.requests_or_urgent_needs) }} posts and `missing_or_found_people` has {{ num(d.eval_labels.missing_or_found_people) }}. Per-class numbers for them have wide intervals, and a high overall score does not guarantee every request is caught.
- **Uneven coverage.** {{ event_name(d.eval_top_event) }} alone is {{ pct(d.eval_top_event_share) }} of the eval set; results are weighted toward that disaster (per-disaster numbers are reported separately).
- **Most posts have no location.** The gazetteer only resolves places it knows by name; posts without a named place have no coordinates and must be located by a person.
- **Redaction is best effort.** PII redaction reduces exposure; it does not guarantee that no personal data reaches a reader (the small spaCy model misses some names). It applies to what the dispatcher sees: raw posts are sent to the model providers (Fireworks, and Anthropic or OpenAI for the frontier comparison).
- **Not every baseline answered every post.**{% for r in rows if r.s.coverage is number and r.s.coverage < 1 %} {{ r.name }} answered {{ num(r.s.n) }} posts ({{ pct(r.s.coverage, 0) }}) before the Anthropic spending cap.{% endfor %} Comparisons are paired on the posts both systems answered.
- **Unseen by our fine-tune, not necessarily by every model.** The 2019 test disasters are absent from our fine-tuning data, but they are public tweets (and HumAID has been public since 2021), so we cannot rule out that any model saw them in pretraining.
- **Non-commercial data.** HumAID is licensed CC BY-NC-SA 4.0. The code in this repo is MIT, but models trained on HumAID and derived data inherit the non-commercial, share-alike terms.

## Roadmap

- [ ] Dedicated Fireworks deployment of the promoted model for steady latency at disaster-time volume
- [ ] Microsoft Foundry deployment path for agencies that run on Azure
- [ ] Learn from dispatcher actions: dispatched and dismissed items become new training labels
- [ ] Cluster near-duplicate requests so one address is not dispatched five times
- [ ] Location extraction beyond the gazetteer (named-entity recognition plus a geocoder) with uncertainty shown on the map
- [ ] Multilingual evaluation and newer events from other crisis datasets
- [ ] Calibrated confidence and an "unsure, send to a human" path, then confidence-aware escalation of uncertain posts to a frontier model (the policy our team's downshifting paper recommends testing)
- [ ] Voice intake for people who cannot reach 911: a talking [masky.ai](https://masky.ai/) avatar line that answers the call, PAVO-style routing across the speech-to-LLM pipeline, and Rescue Radar triage of the transcript
- [ ] Export queue items as Common Alerting Protocol (CAP) messages for dispatch systems

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

### Prior research by the team

Rescue Radar is a downshifting decision: replacing a frontier model with a smaller open one. Before this hackathon, a member
of this team published on exactly that question in *How Much Quality Survives LLM Downshifting?* (TMLR, 08/2026,
[OpenReview](https://openreview.net/forum?id=6ccINAFoJi)), which shows that LLM-judged "quality preserved" figures swing
from 61% to 97% depending on the judge, and on routing inference across speech pipelines in *PAVO* (TMLR, 08/2026,
[OpenReview](https://openreview.net/forum?id=zrneoIxlFx)). Our evaluation follows the first paper's advice: human labels
instead of an LLM judge, intervals on every number, two prompting protocols per frontier model, real disaster posts.
PAVO is the blueprint for the voice-intake item on our roadmap. The Rescue Radar code, data split, fine-tune and benchmark
were built during the event. Full citations: [guide/REFERENCES.md](guide/REFERENCES.md).

## Hackathon disclosure

Rescue Radar was built during **Fireworks: Deploy** in San Francisco on **November 2, 2026**. AI coding assistants were used while writing the code and documentation. The dataset is HumAID by QCRI; we did not collect or label any data. Frontier-baseline predictions come from Claude Opus 5.5 through the Anthropic API and GPT-6.1 Terra through the OpenAI API. The live Head-to-Head calls Claude Opus 5.5 and switches to GPT-6.1 Terra when the Anthropic account is out of quota; each result names the model that answered.

## License

Code: [MIT](LICENSE). Data: HumAID is CC BY-NC-SA 4.0 (non-commercial, share-alike); it is downloaded from its source by `rr.prep`, and files derived from it in `data/` keep that license.
