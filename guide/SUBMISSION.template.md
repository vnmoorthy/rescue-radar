{% set qname = ("Rescue Radar, small-data run (" ~ num(ours_train.examples) ~ " examples)") if headline_ablation else (ours.name or "Rescue Radar") %}
{% set bs = cmp.bootstrap or {} %}
# HackerSquad submission: copy and paste

**Project name:** Rescue Radar

**One line:** Finds the people asking to be rescued inside the flood of disaster posts, in real time, at a fraction of frontier-model cost.

**Team:** NarasingaMoorthy VeiluKanthaPerumal ([@vnmoorthy](https://github.com/vnmoorthy)), Seth Caldwell

**Repository:** https://github.com/vnmoorthy/rescue-radar (commit: paste the output of `git rev-parse HEAD`)

**Live demo:** https://vnmoorthy.github.io/rescue-radar/ · **Slides:** https://vnmoorthy.github.io/rescue-radar/deck/

**Sponsor prizes entered:** Overall placement (Fireworks), NVIDIA Best-Use Award.

## Project overview

**Who benefits.** Emergency dispatchers, emergency operations centers and relief NGOs. In large disasters 911 lines saturate and people post rescue requests publicly: during Hurricane Harvey, Rice University's Kinder Institute found about 5,200 rescue requests in over a million tweets, and FEMA missed 46% of them.

**The task.** Read every disaster-time post and classify it into the 10 HumAID humanitarian categories, pushing the rescue-critical ones (urgent needs, injured or dead, missing or found people) into a dispatcher's priority queue with a map pin.

**Approach.** NVIDIA Nemotron 3.5 Super fine-tuned with LoRA (rank 16) on Fireworks serverless training, served through Fireworks serverless sampling, behind a FastAPI backend and a dispatch console. Microsoft Presidio redacts personal data before any human sees a post.

**Business value.** The model labels posts for {{ usd(ours.cost_per_1m_usd) }} per million, against {{ usd(systems.opus_few.cost_per_1m_usd) }} for Claude Opus 5.5 (20-shot) and {{ usd(systems.gpt_few.cost_per_1m_usd) }} for GPT-6.1 Terra (20-shot), {% set mf_side = ci_side(bs.macro_f1_delta_ci95) %}{% set acc_side = ci_side(bs.delta_ci95) %}with macro-F1 {{ "statistically level with" if mf_side == "spans" else ("above" if mf_side == "above" else ("below" if mf_side == "below" else "n/a against")) }} Claude Opus 5.5 (20-shot) ({{ pts(cmp.delta_macro_f1) }}, 95% CI {{ ci_pts(bs.macro_f1_delta_ci95) }}), accuracy {{ "statistically level" if acc_side == "spans" else ("higher" if acc_side == "above" else ("lower" if acc_side == "below" else "n/a")) }} ({{ pts(cmp.delta) }}, 95% CI {{ ci_pts(bs.delta_ci95) }}), and rescue-critical recall {{ pts(cmp.delta_critical_recall) }} (95% CI {{ ci_pts(bs.critical_recall_delta_ci95) }}) at lower precision, paired on the {{ num(cmp.n) }} posts both answered, on disasters our fine-tune never saw (see the statistics below for where it is ahead, tied or behind).{% if headline_ablation %} These are the small-data run's numbers: the pre-registration lists that run as an ablation, and the pre-registered main system is not scored yet.{% endif %} At that price an agency can screen every post of a disaster instead of sampling a few.

## Evaluation evidence

**Design.** Train on 15 HumAID disasters from 2016-2018; test on {{ num(m.eval.n) }} tweets sampled from 4 disasters from 2019 that are outside our fine-tuning data and every prompt (the frontier models' and the Nemotron base model's pretraining data is not public) (Hurricane Dorian, Cyclone Idai, Pakistan earthquake, Midwest floods), {{ num(m.eval.critical_support) }} of them rescue-critical. Every system gets the same instructions and label definitions (the 20-shot baselines also get 20 examples); the frontier models were scored on the tweets they answered (see limitations), and every comparison is paired on shared tweets. Protocol pre-registered at 13:49 PT before any fine-tuned score existed (`guide/PREREGISTRATION.md`). Deviations: the GPT-6.1 Terra baselines were added after pre-registration{% if headline_ablation %}, and the headline is the small-data run (pre-registered as an ablation) because the pre-registered main system is not scored yet{% endif %}.

**Dataset.** HumAID (Alam et al., ICWSM 2021), human-labeled, CC BY-NC-SA 4.0. Training set: {{ num(ours_train.examples) }} tweets capped per category (from the training log, `{{ ours_train.source or "data/train.out" }}`).

| System | Tweets scored | Macro-F1 (95% CI) | Accuracy | Rescue-critical recall (95% CI) | Critical precision | Cost per 1M posts |
| --- | --- | --- | --- | --- | --- | --- |
{% for k in ['rescue_radar', 'rescue_radar_quick', 'base_zero', 'opus_few', 'opus_zero', 'gpt_few', 'gpt_zero'] if k in systems -%}
| {{ qname if k == ours_key else systems[k].name }} | {{ num(systems[k].n) }} | {{ pct(systems[k].macro_f1) }} ({{ ci(systems[k].ci95.macro_f1) }}) | {{ pct(systems[k].accuracy) }} | {{ pct(systems[k].critical.recall) }} ({{ ci(systems[k].ci95.critical_recall) }}) | {{ pct(systems[k].critical.precision) }} | {{ usd(systems[k].cost_per_1m_usd) }} |
{% endfor %}

**Statistics: {{ qname }} against each system, paired on the tweets both answered.**

| Against | Shared tweets | Macro-F1 difference (95% CI) | Rescue-critical recall difference (95% CI) | Accuracy difference | McNemar |
| --- | --- | --- | --- | --- | --- |
{% for c in cmps -%}
| {{ systems[c.b].name }} | {{ num(c.n) }} | {{ pts(c.delta_macro_f1) }} ({{ ci_pts(c.bootstrap.macro_f1_delta_ci95) }}) | {{ pts(c.delta_critical_recall) }} ({{ ci_pts(c.bootstrap.critical_recall_delta_ci95) }}) | {{ pts(c.delta) }} ({{ ci_pts(c.bootstrap.delta_ci95) }}) | {{ pval(c.mcnemar.p) }} |
{% endfor %}

Intervals come from 5,000 bootstrap resamples of tweets within each disaster; McNemar is the exact test on per-tweet correctness.

**Limitations and disclosures.**
- Claude Opus 5.5 hit the account's API spending cap mid-run, so it is scored on the {{ num(systems.opus_few.n) }} (20-shot) and {{ num(systems.opus_zero.n) }} (zero-shot) tweets it answered, a random subset of the shuffled test set; every comparison with it is paired on exactly those tweets. GPT-6.1 Terra answered all {{ num(m.eval.n) }}.
- A first Claude run used a 24-token output cap; Opus 5.5 always thinks first, so most answers were cut off. We discarded it (kept in `data/preds/_invalid/`) and reran with room to finish.
- Personal-data redaction (Presidio plus rules) is best-effort: some first names and payment handles can slip through, and the raw post is sent to the model before the redacted copy is shown to a human.
- Our model flags more posts as rescue-critical than Claude does (precision {{ pct(ours.critical.precision) }} vs {{ pct(systems.opus_few.critical.precision) }}): it trades some false alarms for fewer missed requests.
- Latency is a measured weakness today: under 16-32 parallel requests, median {{ ms(ours.latency_ms.p50) }} per post for our model on Fireworks' shared training-sampler pool vs {{ ms(systems.opus_few.latency_ms.p50) }} for Claude and {{ ms(systems.gpt_few.latency_ms.p50) }} for GPT-6.1 Terra through their APIs. A dispatcher queue tolerates seconds; a dedicated Fireworks deployment is the next step, and we did not deploy one today.
- Fireworks cost uses its published sampling rate, which includes a limited-time 50% discount (about 2x without it, still {{ ratio(systems.opus_few.cost_per_1m_usd, ours.cost_per_1m_usd_undiscounted) }} cheaper than Claude 20-shot).
- Data is 2016-2019 Twitter; the urgent category is small; dataset is non-commercial (CC BY-NC-SA 4.0).

## Sponsor technology

- **Fireworks:** serverless LoRA training (Training API), serverless sampling for live inference and the benchmark, and checkpoint promotion to a permanent model (`accounts/vnmoorthy/models/rescue-radar-nemotron-quick`).
- **NVIDIA:** Nemotron 3.5 Super (120B total, 12B active) is the base model we fine-tune; untuned Nemotron is our "before" baseline.
- **Microsoft:** Presidio redacts personal data before review in the API and console.

## What we built today, and AI assistance

Everything in the repository was built during the event on Nov 2, 2026: data split, training, evaluation, backend, console, docs and deck. We used AI coding assistants (Claude Code) heavily and can explain every part. HumAID is by QCRI; the base model is NVIDIA's.

## Demo video (under 120 seconds)

1. 0:00 the Harvey statistic and one real Dorian rescue post.
2. 0:15 Live Replay of Hurricane Dorian at 100x: rescue requests land in the queue and on the map, cost meter beside the frontier model's.
3. 0:55 Head-to-Head on one post, then Triage Desk with redaction.
4. 1:20 Benchmark tab: macro-F1 and rescue-critical recall with intervals, and the cost per million posts.
5. 1:45 Close: open source, link to the repo.
