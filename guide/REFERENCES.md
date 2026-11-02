# References

## Data and problem
- Alam, F., Qazi, U., Imran, M., Ofli, F. **HumAID: Human-Annotated Disaster Incidents Data from Twitter with Deep
  Learning Benchmarks.** ICWSM 2021. Dataset: [QCRI/HumAID-events](https://huggingface.co/datasets/QCRI/HumAID-events)
  (CC BY-NC-SA 4.0). Every training and test label in this repository comes from it.
- Kinder Institute for Urban Research, Rice University. Hurricane Harvey rescue-request study: over 1 million tweets
  from Aug 25 to Sep 8, 2017, about 5,200 rescue requests, 46% missed by FEMA. Reported by
  [Security Magazine, Sep 19, 2018](https://www.securitymagazine.com/articles/89430-federal-authorities-missed-nearly-half-of-social-media-distress-calls-during-harvey).

## Method
- Hu, E. J., et al. **LoRA: Low-Rank Adaptation of Large Language Models.** ICLR 2022. The fine-tuning method.
- McNemar, Q. **Note on the sampling error of the difference between correlated proportions or percentages.**
  Psychometrika, 1947. The paired significance test on per-post correctness.
- Efron, B., Tibshirani, R. J. **An Introduction to the Bootstrap.** Chapman & Hall, 1993. The confidence intervals,
  resampled within each disaster.
## Prior research by a team member (published before this hackathon)

NarasingaMoorthy VeiluKanthaPerumal, a member of this team, published the two papers below before the event. They
study the question Rescue Radar answers in practice: when a smaller, cheaper model can replace a frontier model, and how
to route requests between models. The Rescue Radar code, data split, fine-tune and benchmark were built during the
hackathon on Nov 2, 2026.

- NarasingaMoorthy V. **How Much Quality Survives LLM Downshifting? Judge Disagreement, Protocol Sensitivity, and a
  Matched Benchmark-Traffic Difference of at Most Three Points.** Transactions on Machine Learning Research (08/2026).
  [OpenReview](https://openreview.net/forum?id=6ccINAFoJi). It studies a 70B to 8B downshift on 10,000 prompts and finds
  that the cost saving is judge-independent while the "quality preserved" figure is not: it ranges from 61% to 97%
  depending on which LLM judge scores the same answers, and shifts with presentation order. It recommends reporting
  distributions with intervals, validating on real data, and testing confidence-aware escalation instead of blanket
  downshifting. **How Rescue Radar applies it:** no LLM judge (every system is scored against human labels), 95%
  intervals and paired tests on every comparison, two prompting protocols for each frontier model, real disaster posts
  rather than synthetic prompts, and confidence-aware escalation as the next step on our roadmap.
- NarasingaMoorthy VeiluKanthaPerumal, Mohammed Imthathullah. **PAVO: Pipeline-Aware Voice Orchestration with
  Demand-Conditioned Inference Routing.** Transactions on Machine Learning Research (08/2026).
  [OpenReview](https://openreview.net/forum?id=zrneoIxlFx), [code](https://github.com/vnmoorthy/pavo-bench). It routes
  each voice turn through an ASR, LLM and TTS pipeline using demand signals extracted before transcription, and reports
  34% lower median latency and 71% lower energy than rigid cloud baselines on a 50,000-turn simulated benchmark.
  **How Rescue Radar applies it:** it is the blueprint for our voice-intake roadmap item, where 911 audio is
  transcribed and each call is routed between Rescue Radar and a frontier model.

## Models
- NVIDIA Nemotron 3.5 Super VL 120B-A12B, the base model, served and fine-tuned through Fireworks
  ([model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16)).
- Frontier baselines: Claude Opus 5.5 (Anthropic) and GPT-6.1 Terra (OpenAI), called through their official APIs.
