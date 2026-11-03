# Pre-registered evaluation protocol

Written at 13:49 PT on 2026-11-02, before any fine-tuned model was scored on the test set.

## Test set
- 3,001 tweets sampled at random (seed 7, stratified by event) from the 4 HumAID disasters of 2019:
  Hurricane Dorian, Cyclone Idai, the Pakistan earthquake and the Midwestern US floods.
- No tweet from these 4 disasters is used for training, prompting examples or model selection.
- Training tweets whose normalized text also appears in the test disasters are removed (1 removed).

## Systems
- `opus_zero`: Claude Opus 5.5, zero-shot, adaptive thinking at effort `medium` (its API default), max_tokens 4096.
- `opus_few`: the same with 20 fixed examples (2 per category) drawn from the training disasters.
- `base_zero`: NVIDIA Nemotron 3.5 Super, no fine-tuning, same prompt.
- `rescue_radar`: Nemotron 3.5 Super + LoRA (rank 16, lr 1e-4, batch 32, 1 epoch) trained on 13,839 tweets from
  the 15 training disasters (capped at 1,500 per category).
- `rescue_radar_quick`: the same recipe on 3,939 tweets (400 per category; all 339 of the smallest category), reported as a data-size ablation.

Every system gets the identical system prompt and label definitions (`rr/labels.py`).

## Which checkpoint is the main system
The final checkpoint of the 13,839-example run. If that run has not finished by 14:55 PT, the main system is the
newest checkpoint of that run saved by 14:55 PT, chosen by step number. Test-set scores are never used to pick a
checkpoint.

## Metrics and tests
- Primary: macro-F1 over the 10 categories, and recall on rescue-critical posts (requests or urgent needs,
  injured or dead people, missing or found people), because a missed rescue request is the costly error.
- Secondary: accuracy, per-category F1, per-disaster scores, latency p50/p95, cost per 1M posts.
- Significance: exact McNemar test on per-tweet correctness, and a 5,000-sample bootstrap that resamples tweets
  within each disaster, giving 95% intervals for every metric and for every difference between systems.
- Measured numbers and estimates are labeled separately.

## Known invalid run, kept for transparency
A first frontier run used max_tokens 24. Claude Opus 5.5 always thinks before answering, so most answers were cut
off before the label and scored as wrong. That run is not used; its files are in `data/preds/_invalid/`.

## Corrections
- 14:40 PT: the quick run's training-set size was first written here as 3,839. The training log shows 3,939 (9 categories x 400 + all 339 `missing_or_found_people` examples). Nothing else in the protocol changed.
- 15:59 PT: the main run did not finish by the 14:55 cutoff, so, as pre-registered, the main system is its step-275 checkpoint (saved 14:50:36). At batch size 32 it saw 8,800 of the 13,839 training examples (about 64% of one shuffled pass). Earlier text describing it as trained on all 13,839 examples was wrong.
