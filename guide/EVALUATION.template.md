{#- Rendered to guide/EVALUATION.md by scripts/render_docs.py. Numbers come from results/metrics.json and data/. -#}
{% set test_events = m.eval.test_events or d.test_events_n %}
{% set train_events = m.eval.train_events or d.train_events_n %}
{% set eval_n = m.eval.n or d.eval_n %}
# Evaluation method

The question we answer: **on a disaster the model has never seen, how well does it find the posts that need a
rescuer, compared with a frontier model and with the same open model before fine-tuning?**

Results: [README](../README.md#results) and [`results/metrics.json`](../results/metrics.json). Code:
`rr/prep.py`, `rr/run_model.py`, `rr/baseline.py`, `rr/evaluate.py`.

## 1. Split by disaster, not by tweet

Tweets about one disaster share places, names, hashtags and phrasing. A random tweet-level split would reward
memorizing the event. We hold out whole events instead:

| | Events | Years | Size |
| --- | --- | --- | --- |
| Train | {{ num(train_events) }} HumAID events | 2016 to 2018 | {{ num(d.train_sft_n) }} examples in `data/train_sft.jsonl` (at most 1,500 per class) |
| Test | {{ num(test_events) }} HumAID events | 2019 | {{ num(d.test_full_n) }} tweets in `data/test_full.jsonl` |
| Eval set | the same {{ num(test_events) }} events | 2019 | {{ num(eval_n) }} tweets in `data/eval.jsonl`, sampled with a fixed seed in proportion to each event's size |

Eval set by event:

| Event | Tweets | Share |
| --- | --- | --- |
{% for e, n in (d.eval_events or {}) | dictsort(by='value', reverse=true) %}
| {{ event_name(e) }} | {{ num(n) }} | {{ pct(n / d.eval_n) }} |
{% endfor %}

Eval set by category (rescue-critical in bold):

| Category | Tweets |
| --- | --- |
{% for l in d.labels %}
| {{ "**" ~ l.name ~ "**" if l.critical else l.name }} | {{ num(d.eval_labels[l.id]) }} |
{% endfor %}

Rescue-critical posts are {{ pct(d.eval_critical_share) }} of the eval set ({{ num(d.eval_critical_n) }} tweets).

## 2. De-duplication

Retweets and copied text cross event boundaries. `rr/prep.py` normalizes text (lowercase, strip the retweet
prefix, URLs, mentions, `#` and punctuation) and drops every training tweet whose normalized text also appears in
any test event{% if d.dedup_removed is number %}: {{ num(d.dedup_removed) }} of {{ num(d.raw_train_n) }} training-event tweets were removed{% endif %}.

## 3. Prompt parity

- Every system gets the same system prompt: the task, the {{ num(d.labels_n) }} category names and their one-line
  definitions (`rr/labels.py`), and the post as `Post: <text>`.
- The **20-shot** frontier baseline adds two fixed training examples per category (seeded), the same 20 for every
  post; the live Head-to-Head view uses the same 20.
- Answers are mapped to a category by `parse_label()`: the first category name found in the output, then a
  first-word match, otherwise `other_relevant_information`. The same parser is used for every system.
- For Nemotron, the chat template's reasoning block is closed in the prompt so the model answers with the label
  directly (training and inference use the identical prompt). Decoding is greedy (temperature 0).

## 4. Systems

| Key | System | Why it is here |
| --- | --- | --- |
| `rescue_radar` | Nemotron 3.5 Super + LoRA on `data/train_sft.jsonl`{% if ours_train.seen is number %} ({{ num(ours_train.examples) }} examples; the scored step-{{ ours_train.step }} checkpoint of the {{ num(ours_train.steps) }}-step run saw {{ num(ours_train.seen) }} of them){% endif %} | The pre-registered main system: the newest checkpoint saved by 14:55 PT was fixed as the headline before any fine-tuned model was scored on the test set{% if headline_ablation %} (**not scored yet**; see the deviation note below){% endif %} |
| `rescue_radar_quick` | The same recipe on a smaller, class-balanced subset | Ablation: how much does more data help? |
| `base_zero` | Nemotron 3.5 Super without fine-tuning, same prompt, same serving path | Isolates the effect of LoRA |
| `opus_zero` | Claude Opus 5.5, zero-shot | Frontier reference |
| `opus_few` | Claude Opus 5.5, 20-shot | Stronger frontier reference |
| `gpt_zero`, `gpt_few` | GPT-6.1 Terra (OpenAI API), zero-shot and 20-shot | Second frontier reference, **added after pre-registration** (not part of the pre-registered protocol) |

{% if m.eval.preregistration %}
The headline system, metrics and tests were written down before any fine-tuned model was scored on the test set in [`{{ m.eval.preregistration }}`](../{{ m.eval.preregistration }}).
{% endif %}
{% if headline_ablation %}

**Deviation from the pre-registration.** `results/metrics.json` currently names `rescue_radar_quick` as the headline
(`headline.ours`) because the main run has no complete predictions file yet. Every headline number in the README, the
console, the deck and the submission is therefore the small-data run's ({{ num(ours_train.examples) }} training
examples, from `{{ ours_train.source or "data/train.out" }}`), which the pre-registration lists as an ablation. The
pre-registered main system will replace it once its frozen checkpoint is scored.
{% endif %}

## 5. Metrics

- **Macro-F1** over the {{ num(d.labels_n) }} categories (each category counts equally, so rare categories matter).
- **Accuracy** (exact category).
- **Rescue-critical precision, recall and F1**, treating the three rescue-critical categories as one positive
  class. Recall is the dispatcher's main concern: how many posts that needed a rescuer reached the queue.
- **Per event** and **per class** scores, and full confusion matrices, in `results/metrics.json`.
- **Latency**: wall-clock time per post, p50 / p95 / mean, measured during the benchmark run.
- **Cost per 1M posts**: measured input and output tokens per post, times published per-token prices.

## 6. Statistics

- **Exact McNemar test** on per-post correctness for each pair of systems: only the posts where exactly one system
  is right carry information. The p-value is the two-sided exact binomial probability of a split at least that
  uneven if both systems were equally accurate.
- **Paired bootstrap, stratified by disaster**: {{ num(m.eval.bootstrap_resamples) }} resamples; each resample draws
  tweets with replacement within each event (keeping each event's size), and every system is scored on the same
  resample. 95% percentile intervals are reported for every metric and for every difference between systems,
  together with how many resamples the headline system wins on macro-F1.

## 7. Measured vs estimated

| Quantity | Status | Source |
| --- | --- | --- |
| Accuracy, macro-F1, recall | Measured | Predictions in `data/preds/*.jsonl` against HumAID labels |
| Latency | Measured | Per-call wall-clock time, including network, recorded in each prediction row |
| Tokens per post | Measured | API usage for Claude; tokenizer counts for the open models |
| Cost per post | Computed | Measured tokens times the published price stated in each system's `cost_note` |

Current cost notes:
{% for k, s in systems | dictsort %}
- **{{ s.name or k }}**: {{ s.cost_note or "n/a" }}{% if s.cost_per_1m_usd_undiscounted is number and s.cost_per_1m_usd_undiscounted != s.cost_per_1m_usd %} (without the discount: {{ usd(s.cost_per_1m_usd_undiscounted) }} per 1M posts){% endif %}.
{% else %}
- n/a (results pending)
{% endfor %}

Latency depends on load and concurrency: open models were called through shared Fireworks serverless capacity
with parallel workers, Claude through the public Anthropic API. A dedicated deployment would change both latency
and cost; see [DEPLOYMENT.md](DEPLOYMENT.md).

## 8. Threats to validity

- **Label noise.** HumAID labels come from crowd annotation; some categories overlap (for example
  `requests_or_urgent_needs` and `rescue_volunteering_or_donation_effort`).
- **Small critical classes.** `requests_or_urgent_needs` has {{ num(d.eval_labels.requests_or_urgent_needs) }} eval
  tweets and `missing_or_found_people` has {{ num(d.eval_labels.missing_or_found_people) }}; their per-class
  numbers have wide intervals.
- **Event imbalance.** {{ event_name(d.eval_top_event) }} is {{ pct(d.eval_top_event_share) }} of the eval set, so
  pooled numbers lean toward it; per-event numbers are reported separately.
- **Time and platform.** All data is English Twitter from 2016 to 2019; newer platforms and language are untested.
- **Frontier prompting.** We gave Claude the same instructions and up to 20 examples, not a tuned prompt; a
  different prompt could score differently.
- **Partial frontier coverage.** The Anthropic account hit its API spending cap mid-run{% for k in ("opus_few", "opus_zero") if (systems.get(k) or {}).get("n") is number %}; {{ systems[k].name }} answered {{ num(systems[k].n) }} of {{ num(m.eval.n) }} posts ({{ pct(systems[k].coverage, 0) }}){% endfor %}. Each system's own score is on the posts it answered, and every comparison is paired on the posts both systems answered.
- **Pretraining exposure.** The test disasters are absent from our fine-tuning data, but the tweets are public (and
  HumAID has been public since 2021), so we cannot rule out that any model, including the Nemotron base, saw them in
  pretraining.
