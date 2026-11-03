<!-- Generated from guide/EVALUATION.template.md by scripts/render_docs.py. Edit the template, then re-run the script. -->
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
| Train | 15 HumAID events | 2016 to 2018 | 13,839 examples in `data/train_sft.jsonl` (at most 1,500 per class) |
| Test | 4 HumAID events | 2019 | 15,384 tweets in `data/test_full.jsonl` |
| Eval set | the same 4 events | 2019 | 3,001 tweets in `data/eval.jsonl`, sampled with a fixed seed in proportion to each event's size |

Eval set by event:

| Event | Tweets | Share |
| --- | --- | --- |
| Hurricane Dorian (2019) | 1,485 | 49.5% |
| Cyclone Idai (2019) | 767 | 25.6% |
| Pakistan Earthquake (2019) | 382 | 12.7% |
| Midwestern US Floods (2019) | 367 | 12.2% |

Eval set by category (rescue-critical in bold):

| Category | Tweets |
| --- | --- |
| **Requests or urgent needs** | 78 |
| **Injured or dead people** | 172 |
| **Missing or found people** | 4 |
| Displaced people and evacuations | 180 |
| Infrastructure and utility damage | 309 |
| Caution and advice | 302 |
| Rescue volunteering or donation effort | 743 |
| Sympathy and support | 481 |
| Other relevant information | 435 |
| Not humanitarian | 297 |

Rescue-critical posts are 8.5% of the eval set (254 tweets).

## 2. De-duplication

Retweets and copied text cross event boundaries. `rr/prep.py` normalizes text (lowercase, strip the retweet
prefix, URLs, mentions, `#` and punctuation) and drops every training tweet whose normalized text also appears in
any test event: 1 of 61,100 training-event tweets were removed.

## 3. Prompt parity

- Every system gets the same system prompt: the task, the 10 category names and their one-line
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
| `rescue_radar` | Nemotron 3.5 Super + LoRA on `data/train_sft.jsonl` (13,839 examples; the scored step-275 checkpoint of the 432-step run saw 8,800 of them) | The pre-registered main system: the newest checkpoint saved by 14:55 PT was fixed as the headline before any fine-tuned model was scored on the test set |
| `rescue_radar_quick` | The same recipe on a smaller, class-balanced subset | Ablation: how much does more data help? |
| `base_zero` | Nemotron 3.5 Super without fine-tuning, same prompt, same serving path | Isolates the effect of LoRA |
| `opus_zero` | Claude Opus 5.5, zero-shot | Frontier reference |
| `opus_few` | Claude Opus 5.5, 20-shot | Stronger frontier reference |
| `gpt_zero`, `gpt_few` | GPT-6.1 Terra (OpenAI API), zero-shot and 20-shot | Second frontier reference, **added after pre-registration** (not part of the pre-registered protocol) |

The headline system, metrics and tests were written down before any fine-tuned model was scored on the test set in [`guide/PREREGISTRATION.md`](../guide/PREREGISTRATION.md).

## 5. Metrics

- **Macro-F1** over the 10 categories (each category counts equally, so rare categories matter).
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
- **Paired bootstrap, stratified by disaster**: 5,000 resamples; each resample draws
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
- **Nemotron 3.5 Super, no fine-tuning**: measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it) (without the discount: $343 per 1M posts).
- **GPT-6.1 Terra, 20-shot**: measured tokens x OpenAI list price ($1 in / $5 out per 1M tokens, reasoning tokens included).
- **GPT-6.1 Terra, zero-shot**: measured tokens x OpenAI list price ($1 in / $5 out per 1M tokens, reasoning tokens included).
- **Claude Opus 5.5, 20-shot**: measured tokens x Anthropic list price ($4 in / $20 out per 1M tokens, thinking tokens included).
- **Claude Opus 5.5, zero-shot**: measured tokens x Anthropic list price ($4 in / $20 out per 1M tokens, thinking tokens included).
- **Rescue Radar, main run (step 275 of 432: 8,800 of 13,839 examples seen)**: measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it) (without the discount: $342 per 1M posts).
- **Rescue Radar, small-data run (step 123 of 123: 3,936 of 3,939 examples seen)**: measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it) (without the discount: $342 per 1M posts).

Latency depends on load and concurrency: open models were called through shared Fireworks serverless capacity
with parallel workers, Claude through the public Anthropic API. A dedicated deployment would change both latency
and cost; see [DEPLOYMENT.md](DEPLOYMENT.md).

## 8. Threats to validity

- **Label noise.** HumAID labels come from crowd annotation; some categories overlap (for example
  `requests_or_urgent_needs` and `rescue_volunteering_or_donation_effort`).
- **Small critical classes.** `requests_or_urgent_needs` has 78 eval
  tweets and `missing_or_found_people` has 4; their per-class
  numbers have wide intervals.
- **Event imbalance.** Hurricane Dorian (2019) is 49.5% of the eval set, so
  pooled numbers lean toward it; per-event numbers are reported separately.
- **Time and platform.** All data is English Twitter from 2016 to 2019; newer platforms and language are untested.
- **Frontier prompting.** We gave Claude the same instructions and up to 20 examples, not a tuned prompt; a
  different prompt could score differently.
- **Partial frontier coverage.** The Anthropic account hit its API spending cap mid-run; Claude Opus 5.5, 20-shot answered 2,592 of 3,001 posts (86%); Claude Opus 5.5, zero-shot answered 1,920 of 3,001 posts (64%). Each system's own score is on the posts it answered, and every comparison is paired on the posts both systems answered.
- **Pretraining exposure.** The test disasters are absent from our fine-tuning data, but the tweets are public (and
  HumAID has been public since 2021), so we cannot rule out that any model, including the Nemotron base, saw them in
  pretraining.
