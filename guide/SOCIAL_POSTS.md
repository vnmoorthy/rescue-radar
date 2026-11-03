# Launch posts

Every number below is from `results/metrics.json` (generated 2026-11-02 15:26 PT). If the benchmark is re-run, re-check each number against that file before posting. Each X post is at most 280 characters with X counting a link as 23.

## Launch thread for X and LinkedIn (5 posts)

On LinkedIn, post 1 can go out alone with posts 2 to 5 as the body, or the five can be pasted as one post.

**1/5**

> When disasters hit, people post rescue requests publicly, buried among prayers, news and donation drives. In our test set only 8.5% of posts are rescue-critical. Rescue Radar finds them and puts them at the top of a dispatcher's queue.
>
> Live demo: https://vnmoorthy.github.io/rescue-radar/

**2/5**

> How we tested it: fine-tuned on posts from 15 disasters (2016 to 2018), tested on 3,001 posts from 4 disasters of 2019 the model never saw. The protocol was pre-registered before any fine-tuned model was scored, with paired tests and 95% intervals on every number.

**3/5**

> Against Claude Opus 5.5 with 20 examples, on the 2,592 posts both answered:
>
> Rescue-critical recall 85.3% vs 68.8% (+16.5 pts, 95% CI +11.2 to +21.9)
> Macro-F1 69.2% vs 63.7%
> Cost per 1M posts $171 vs $8,738

**4/5**

> Where it is worse: rescue-critical precision is 60.2% vs 78.1%, so dispatchers dismiss more false alarms, and median latency is 3.37 s vs 1.31 s on shared serverless capacity. The data is 2016 to 2019 Twitter. The model ranks; a person decides every item.

**5/5**

> Built at Fireworks: Deploy with NVIDIA Nemotron 3.5 Super + LoRA on Fireworks serverless training, Microsoft Presidio for PII redaction and QCRI's HumAID data.
>
> Code, predictions and benchmark: https://github.com/vnmoorthy/rescue-radar
> Slides: https://vnmoorthy.github.io/rescue-radar/deck/

Optional LinkedIn tags: #DisasterResponse #CrisisInformatics #EmergencyManagement #OpenModels

## Hacker News

**Title:** Show HN: Rescue Radar – open model that flags rescue requests in disaster posts

**Description (2 sentences):**

> Rescue Radar fine-tunes NVIDIA Nemotron 3.5 Super with LoRA on Fireworks to sort disaster posts into 10 humanitarian categories and put rescue requests at the top of a dispatcher's queue; on 3,001 posts from four 2019 disasters it never saw in training, it caught 85.3% of rescue-critical posts against 68.8% for Claude Opus 5.5 with 20 examples (paired on the 2,592 posts both answered), at $171 against $8,738 per million posts. It is worse on precision (60.2% vs 78.1%) and median latency (3.37 s vs 1.31 s), the data is 2016 to 2019 Twitter, and the live demo replays real 2019 posts in the browser with no install: https://vnmoorthy.github.io/rescue-radar/

## Where each number comes from

| Number | Path in `results/metrics.json` |
| --- | --- |
| 8.5% rescue-critical | `eval.critical_support` / `eval.n` (254 / 3,001) |
| 15 and 4 disasters, 3,001 posts | `eval.train_events`, `eval.test_events`, `eval.n` |
| 2,592 paired posts | `comparisons[b=opus_few].n` |
| 85.3% vs 68.8%, +16.5 pts, CI +11.2 to +21.9 | `comparisons[b=opus_few]`: `a_on_shared.critical_recall`, `b_on_shared.critical_recall`, `delta_critical_recall`, `bootstrap.critical_recall_delta_ci95` |
| 69.2% vs 63.7% macro-F1 | `comparisons[b=opus_few]`: `a_on_shared.macro_f1`, `b_on_shared.macro_f1` |
| $171 vs $8,738 per 1M posts | `systems.rescue_radar.cost_per_1m_usd` (171.08, includes Fireworks' limited-time 50% discount; 342.16 without), `systems.opus_few.cost_per_1m_usd` |
| 60.2% vs 78.1% precision | `systems.rescue_radar.critical.precision`, `systems.opus_few.critical.precision` |
| 3.37 s vs 1.31 s median latency | `systems.rescue_radar.latency_ms.p50`, `systems.opus_few.latency_ms.p50` |

Words kept out on purpose: no "beats", "state of the art", "revolutionary", "real-time at scale" or user, partner and adoption claims. The recall gain is the claim the statistics support; precision and latency are worse and the posts say so.
