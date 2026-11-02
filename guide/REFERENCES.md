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

N. M. VeiluKanthaPerumal, a member of this team, has published on the question Rescue Radar answers in practice: when
can a smaller, cheaper model replace a frontier model, and how should inference be routed between them? This research
predates the event; the Rescue Radar code, data split, fine-tune and benchmark were all built during the hackathon
on Nov 2, 2026. Titles and venues are as listed on the author's
[Google Scholar profile](https://scholar.google.com/citations?user=s7C14hwAAAAJ&hl=en); the papers are on OpenReview
([1](https://openreview.net/pdf?id=31ONd9BL0C), [2](https://openreview.net/pdf?id=zrneoIxlFx),
[3](https://openreview.net/pdf?id=6ccINAFoJi)).

- VeiluKanthaPerumal, N. M. **How Much Quality Survives LLM Downshifting? Judge Disagreement, Protocol Sensitivity,
  and a Matched Benchmark-Traffic Difference of at Most Three Points.** Transactions on Machine Learning Research.
  Rescue Radar is a downshifting decision. Following the concerns that title names, we score every system against
  human labels instead of an LLM judge, and we report two frontier prompting protocols (zero-shot and 20-shot)
  for each of two frontier models instead of a single setting.
- VeiluKanthaPerumal, N. M., Imthathullah, M. **PAVO: Pipeline-Aware Voice Orchestration with Demand-Conditioned
  Inference Routing.** Transactions on Machine Learning Research.
- VeiluKanthaPerumal, N. M., Imthathullah, M. **PAVO: Coupling-Aware Resource-Adaptive Routing for ASR to LLM to TTS
  Inference.** AutoAI Meets Foundation Models.
  The two PAVO papers address routing in speech-to-LLM pipelines; they are the basis of our roadmap item for voice
  intake, where 911 audio is transcribed and routed by difficulty between Rescue Radar and a frontier model.

## Models
- NVIDIA Nemotron 3.5 Super VL 120B-A12B, the base model, served and fine-tuned through Fireworks
  ([model card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-BF16)).
- Frontier baselines: Claude Opus 5.5 (Anthropic) and GPT-6.1 Terra (OpenAI), called through their official APIs.
