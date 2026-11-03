<!-- Generated from guide/SUBMISSION.template.md by scripts/render_docs.py. Edit the template, then re-run the script. -->
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

**Business value.** The model labels posts for $171 per million, against $8,738 for Claude Opus 5.5 (20-shot) and $1,418 for GPT-6.1 Terra (20-shot), with macro-F1 above Claude Opus 5.5 (20-shot) (+5.5 pts, 95% CI +2.6 to +8.5 pts), accuracy higher (+2.2 pts, 95% CI +0.5 to +4.0 pts), and rescue-critical recall +16.5 pts (95% CI +11.2 to +21.9 pts) at lower precision, paired on the 2,592 posts both answered, on disasters our fine-tune never saw (see the statistics below for where it is ahead, tied or behind). At that price an agency can screen every post of a disaster instead of sampling a few.

**As a company.** The customers who pay are the organizations that must find people in trouble during a disaster: emergency management agencies and their emergency operations centers, dispatch centers, humanitarian organizations, and the dispatch-software vendors that would embed the API. The plan is pilots first (replay a past local disaster through the console, then shadow mode during an exercise), then distribution through those vendors. Pricing would be an annual agency subscription, usage-based API pricing for vendors and a license for private deployment on the open-weight model; no prices are set. Margins rest on the measured serving cost above, and dispatcher actions (dispatch, resolve, dismiss) become labels for the next adapter, which ships only if it beats the current one on held-out disasters. Liability is handled by design: a human decides every queue item and no post is dropped. The current adapter is trained on non-commercial HumAID data, so a commercial version needs licensed or customer-generated labels. Details: "From hackathon to company" in the README.

## Evaluation evidence

**Design.** Train on 15 HumAID disasters from 2016-2018; test on 3,001 tweets sampled from 4 disasters from 2019 that are outside our fine-tuning data and every prompt (the frontier models' and the Nemotron base model's pretraining data is not public) (Hurricane Dorian, Cyclone Idai, Pakistan earthquake, Midwest floods), 254 of them rescue-critical. Every system gets the same instructions and label definitions (the 20-shot baselines also get 20 examples); the frontier models were scored on the tweets they answered (see limitations), and every comparison is paired on shared tweets. Protocol pre-registered at 13:49 PT before any fine-tuned score existed (`guide/PREREGISTRATION.md`). Deviations: the GPT-6.1 Terra baselines were added after pre-registration.

**Dataset.** HumAID (Alam et al., ICWSM 2021), human-labeled, CC BY-NC-SA 4.0. Training set: 13,839 tweets capped per category (from the training log, `data/train_full.out`); the scored step-275 checkpoint saw 8,800 of them.

| System | Tweets scored | Macro-F1 (95% CI) | Accuracy | Rescue-critical recall (95% CI) | Critical precision | Cost per 1M posts |
| --- | --- | --- | --- | --- | --- | --- |
| Rescue Radar, main run (step 275 of 432: 8,800 of 13,839 examples seen) | 3,001 | 69.2% (64.8% to 72.3%) | 72.4% | 84.7% (80.3% to 88.9%) | 60.2% | $171 |
| Rescue Radar, small-data run (step 123 of 123: 3,936 of 3,939 examples seen) | 3,001 | 65.0% (61.8% to 67.8%) | 70.9% | 77.2% (72.2% to 82.2%) | 66.9% | $171 |
| Nemotron 3.5 Super, no fine-tuning | 3,001 | 57.6% (54.2% to 60.5%) | 66.0% | 65.4% (59.7% to 71.2%) | 76.5% | $171 |
| Claude Opus 5.5, 20-shot | 2,592 | 63.7% (59.1% to 67.3%) | 70.9% | 68.8% (62.7% to 75.0%) | 78.1% | $8,738 |
| Claude Opus 5.5, zero-shot | 1,920 | 62.2% (57.6% to 67.0%) | 70.2% | 71.9% (64.7% to 78.9%) | 79.1% | $3,412 |
| GPT-6.1 Terra, 20-shot | 3,001 | 60.6% (56.7% to 63.9%) | 67.8% | 70.9% (65.4% to 76.3%) | 65.5% | $1,418 |
| GPT-6.1 Terra, zero-shot | 3,001 | 60.6% (56.6% to 63.7%) | 66.7% | 71.7% (66.3% to 77.0%) | 64.1% | $499 |

**Statistics: Rescue Radar, main run (step 275 of 432: 8,800 of 13,839 examples seen) against each system, paired on the tweets both answered.**

| Against | Shared tweets | Macro-F1 difference (95% CI) | Rescue-critical recall difference (95% CI) | Accuracy difference | McNemar |
| --- | --- | --- | --- | --- | --- |
| Rescue Radar, small-data run (step 123 of 123: 3,936 of 3,939 examples seen) | 3,001 | +4.2 pts (+2.0 to +6.5 pts) | +7.5 pts (+3.7 to +11.4 pts) | +1.5 pts (+0.3 to +2.7 pts) | p = 0.016 |
| Nemotron 3.5 Super, no fine-tuning | 3,001 | +11.7 pts (+8.9 to +14.4 pts) | +19.3 pts (+14.2 to +24.4 pts) | +6.5 pts (+4.8 to +8.1 pts) | p < 0.001 |
| Claude Opus 5.5, 20-shot | 2,592 | +5.5 pts (+2.6 to +8.5 pts) | +16.5 pts (+11.2 to +21.9 pts) | +2.2 pts (+0.5 to +4.0 pts) | p = 0.013 |
| Claude Opus 5.5, zero-shot | 1,920 | +8.1 pts (+3.1 to +13.6 pts) | +17.6 pts (+11.2 to +24.3 pts) | +3.3 pts (+1.1 to +5.4 pts) | p = 0.003 |
| GPT-6.1 Terra, 20-shot | 3,001 | +8.6 pts (+5.5 to +12.2 pts) | +13.8 pts (+9.1 to +18.7 pts) | +4.6 pts (+2.9 to +6.3 pts) | p < 0.001 |
| GPT-6.1 Terra, zero-shot | 3,001 | +8.6 pts (+6.0 to +11.4 pts) | +13.0 pts (+8.7 to +17.6 pts) | +5.7 pts (+4.0 to +7.5 pts) | p < 0.001 |

Intervals come from 5,000 bootstrap resamples of tweets within each disaster; McNemar is the exact test on per-tweet correctness.

**Limitations and disclosures.**
- Claude Opus 5.5 hit the account's API spending cap mid-run, so it is scored on the 2,592 (20-shot) and 1,920 (zero-shot) tweets it answered, a random subset of the shuffled test set; every comparison with it is paired on exactly those tweets. GPT-6.1 Terra answered all 3,001.
- A first Claude run used a 24-token output cap; Opus 5.5 always thinks first, so most answers were cut off. We discarded it (kept in `data/preds/_invalid/`) and reran with room to finish.
- Personal-data redaction (Presidio plus rules) is best-effort: some first names and payment handles can slip through, and the raw post is sent to the model before the redacted copy is shown to a human.
- Our model flags more posts as rescue-critical than Claude does (precision 60.2% vs 78.1%): it trades some false alarms for fewer missed requests.
- Latency is a measured weakness today: under 16-32 parallel requests, median 3.37 s per post for our model on Fireworks' shared training-sampler pool vs 1.31 s for Claude and 1.28 s for GPT-6.1 Terra through their APIs. A dispatcher queue tolerates seconds; a dedicated Fireworks deployment is the next step, and we did not deploy one today.
- Fireworks cost uses its published sampling rate, which includes a limited-time 50% discount (about 2x without it, still 25.5x cheaper than Claude 20-shot).
- Data is 2016-2019 Twitter; the urgent category is small; dataset is non-commercial (CC BY-NC-SA 4.0).

## Sponsor technology

- **Fireworks:** serverless LoRA training (Training API), serverless sampling for live inference and the benchmark, and checkpoint promotion to permanent models (`accounts/vnmoorthy/models/rescue-radar-nemotron`, the headline step-275 checkpoint, and `accounts/vnmoorthy/models/rescue-radar-nemotron-quick`, the small-data ablation).
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
