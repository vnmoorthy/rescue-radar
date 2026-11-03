<!-- Generated from guide/DEMO_RUNBOOK.template.md by scripts/render_docs.py. Edit the template, then re-run the script. -->
# Demo runbook (10 minutes)

For the presenter. Numbers on this page are rendered from `results/metrics.json`
(generated 2026-11-02T16:18:45). If one shows `n/a`, do not
say a number out loud: point at the Benchmark view instead.

**Headline to remember:** paired on the 2,592 posts (from 4 disasters our fine-tune
never saw) that both systems answered, Rescue Radar catches **85.3%** of rescue-critical
posts vs **68.8%** for Claude Opus 5.5, 20-shot (+16.5 pts, 95% CI
+11.2 to +21.9 pts). Macro-F1 69.2% vs 63.7%
(+5.5 pts, 95% CI +2.6 to +8.5 pts).
Costs **$171** per million posts (Claude $8,738; the Fireworks
rate includes a limited-time 50% discount), but it is slower: median **3.37 s** per post
(Claude 1.31 s). Claude Opus 5.5, 20-shot answered 2,592 of the 3,001 posts before the Anthropic spending cap. Claude Opus 5.5, zero-shot answered 1,920 of the 3,001 posts before the Anthropic spending cap.

## T-30 minutes: setup checklist

- [ ] Laptop on power, notifications off, screen mirroring tested, browser zoom 100% (the console is laid out for
      1280x720 and up; do not zoom in).
- [ ] `git pull`, then `python scripts/render_docs.py` so this page and the README carry the final numbers.
- [ ] Start the server: `python -m rr.server`, open <http://localhost:8787>.
- [ ] `curl -s localhost:8787/api/health`: `model.ready` and `frontier.ready` should be true, and `model.scored`
      true (the header badge reads "step N · scored": the live model is exactly the checkpoint the Benchmark scored).
      If the scored system changed since the server started, it switches on the next classify call. If not, see Fallback.
- [ ] Warm the model: classify one post in Head-to-Head (the first call loads the tokenizer and sampler).
- [ ] Clear the queue (Live Replay (key 1) → Priority queue panel → Clear, or `curl -X DELETE localhost:8787/api/queue`).
- [ ] Open a second tab on the static demo <https://vnmoorthy.github.io/rescue-radar/> and a third on the deck
      <https://vnmoorthy.github.io/rescue-radar/deck/>.
- [ ] Have two posts ready to paste (below). Use only public, already-redacted examples.
- [ ] Phone hotspot ready as backup wifi.

Paste-ready posts for Head-to-Head:

1. `We are trapped on the roof at the end of the street, water still rising, two kids with us. Please send a boat`
2. `Praying for everyone in the path of the storm tonight. Stay safe`

## The 10 minutes

| Time | Screen | Do | Say |
| --- | --- | --- | --- |
| 0:00 | Deck, title | Open the deck tab. | "When a disaster hits, emergency lines saturate and people post for rescue in public. In our eval set only 8.5% of posts are rescue-critical. Rescue Radar finds them in real time." |
| 1:00 | Console, **Live Replay** (key 1) | Pick Hurricane Dorian, set speed **10x** (or 50x), then press Play. At 1x the first red flag takes about 17 s. | "These are real tweets from Hurricane Dorian, replayed in their original order. The model never saw this storm. Red means a person needs help: a request, injured or dead, missing or trapped." |
| 2:30 | Live Replay | Click a red post on the map. | "Personal data is redacted, best effort, before a human sees it, here with Microsoft Presidio. The location comes from a gazetteer; if a post names no place, we do not guess." |
| 3:30 | **Live Replay** (key 1) → **Priority queue** panel | Mark one item dispatched, one dismissed; show Export CSV. | "The model ranks; a dispatcher decides. Nothing is dispatched automatically." |
| 4:30 | **Head-to-Head** (key 3) | Paste post 1, then post 2. | "Same instructions to both; the frontier model also gets 20 examples. Our fine-tuned Nemotron on Fireworks next to the frontier model named on the card (Claude Opus 5.5, or GPT-6.1 Terra while the Anthropic account is capped): label, latency, cost per post." |
| 6:00 | **Benchmark** (key 4) | Show the table and the intervals. | "3,001 posts, 4 unseen disasters; paired on the 2,592 both systems answered. Rescue-critical recall 85.3% vs 68.8%, interval +11.2 to +21.9 pts: a real gain. Macro-F1 69.2% vs 63.7%, interval +2.6 to +8.5 pts. McNemar p = 0.013." |
| 7:30 | **How it works** (key 5) | Walk the pipeline. | "Trained on 15 disasters from 2016 to 2018 with LoRA on Fireworks serverless training. Base model NVIDIA Nemotron 3.5 Super. The live console serves the same checkpoint the benchmark scored; the header badge says so." (Only if the badge reads "scored".) |
| 8:30 | Deck, slide 9 | Limits and next steps. | "Old Twitter data, small urgent classes, non-commercial dataset license, human in the loop. Next: a dedicated Fireworks deployment and Microsoft Foundry, neither built yet." |
| 9:00 | Deck, slide 10 (the company) | Give the 60-second company close below, word for word; leave the slide up for questions. | Ends on: "Everything is open: github.com/vnmoorthy/rescue-radar." |

## 9:00 to 10:00: the company close (60 seconds)

On slide 10, "Rescue Radar as a company". About 150 words; every number comes from `results/metrics.json`.

> "Rescue Radar is a company, not just a model. Who pays: county and city emergency operations centers, 911 centers,
> state emergency management and relief NGOs. They get the dispatch console you just saw, an API that screens posts
> for their own tools, and, planned but not built yet, private deployment in the agency's own cloud. Pricing is an annual subscription per
> agency, budgeted before the storm, with a usage tier for surges; the pilots will set the price. The margin is there:
> screening a million posts costs us $171, measured, against $8,738
> on Claude, and $342 even at full price. It compounds: every dispatcher decision
> becomes a new label, and open weights give an agency a path to running it privately. We start with pilot operations centers next
> hurricane season, then dispatch-software partners and new regions. We're asking for pilot partners, dedicated
> Fireworks capacity and introductions to dispatch software teams. Everything is open: github.com/vnmoorthy/rescue-radar."

Do not add a price, a market size, a customer or a partner name: there are none yet.

## Investor questions (honest answers)

**How big is the market, and who signs the check?**
We have not sized it, and we will not quote a number we cannot defend. The buyers are emergency operations centers,
911 centers, state emergency management and relief NGOs, which buy software from annual budgets. We have no
customers, letters of intent or pilots yet; recruiting pilot operations centers and one relief NGO is the first job
of the next 90 days, and those pilots will tell us what an agency will pay.

**What stops a frontier lab or a dispatch-software vendor from building this?**
The model alone is not a moat: anyone can fine-tune an open model. What we have today is a measured edge on this one
task: on the 2,592 posts from unseen disasters that both systems answered, rescue-critical recall is
85.3% vs 68.8% for Claude Opus 5.5, 20-shot, while costing
51.1x less per post. The durable parts still have to be
built: dispatcher decisions as new labels, private deployment on open weights, and integration with the dispatch
software agencies already run. We see dispatch-software vendors as partners rather than competitors, but no
partnership exists yet.

**Are the unit economics real, and can you sell it?**
The cost is measured: tokens counted on every benchmark call times published prices, $171
per million posts vs $8,738. It includes a limited-time 50% Fireworks discount; at full
price it is $342, still 25.5x
cheaper. Two caveats: it is slower today (median 3.37 s per post vs 1.31 s
on shared serverless capacity), and the dedicated deployment that fixes latency will cost more, which we have not
measured. And the training data (HumAID) is licensed non-commercial, so a commercial product retrains on licensed or
agency data with the same code.

## Fallback plan

| Problem | Do this |
| --- | --- |
| Wifi down, or the model returns 503 | Switch to the static demo tab (or `python -m http.server -d docs 8000` offline). Live Replay, the Head-to-Head recorded race ("Run 20 random test posts") and Benchmark work from recorded predictions; Triage Desk classification and the live Head-to-Head comparison do not. Say: "this is the scored model's recorded output on the same posts." |
| Claude unavailable | The server switches the live comparison to GPT-6.1 Terra when the Anthropic account is out of quota, and the card names it. Otherwise use the Benchmark view for the comparison. |
| Model slow on first call | It is loading the tokenizer and sampler. Talk over it, or move to Benchmark and come back. |
| Server will not start | Use the static demo. Do not debug on stage. |
| Projector issues | Present from the deck's static numbers; every number in the deck comes from the same `results/metrics.json`. |

## Likely judge questions

**How do you know it is not memorizing the disasters?**
We split by event: trained on 15 disasters from 2016 to 2018, tested on 4
from 2019 the model never saw, and removed training tweets duplicated in the test events (1 tweet).

**Is the difference with Claude statistically real?**
Paired on the 2,592 posts both answered: Rescue Radar right and Claude wrong on 291
posts, the reverse on 233; exact McNemar p = 0.013. Bootstrap 95% interval
for the macro-F1 difference: +2.6 to +8.5 pts; accuracy: +0.5 to +4.0 pts; rescue-critical
recall: +11.2 to +21.9 pts. Only an interval that excludes zero is a real difference.

**Why does Claude have fewer posts?**
The Anthropic account hit its spending cap mid-run; Claude Opus 5.5, 20-shot answered 2,592; Claude Opus 5.5, zero-shot answered 1,920.
Every comparison is paired on the posts both systems answered.

**Was the comparison fair to Claude?**
Same instructions and category definitions for every system, and Claude also got 20 examples (two per category).
We report both zero-shot (62.2% macro-F1) and 20-shot (63.7%).

**What did fine-tuning add?**
The same Nemotron without LoRA, served the same way, scores 57.6% macro-F1 and
65.4% rescue-critical recall; with LoRA, 69.2% and 84.7%.

**What does it cost to run?**
$171 per million posts for Rescue Radar vs $8,738 for
Claude Opus 5.5, 20-shot, from measured tokens times published prices. The Fireworks rate includes a limited-time discount; without it: $342.
**How fast is it?**
Slower than Claude: median 3.37 s per post, p95 8.42 s, measured with 32
parallel requests on shared serverless capacity; Claude median 1.31 s (24 parallel requests).
A dedicated deployment is the next step for steady latency.

**What about the rare classes?**
The eval set has only 78 `requests_or_urgent_needs` posts and
4 `missing_or_found_people` posts, so per-class numbers have wide
intervals. That is why we also report rescue-critical recall as one group (254 posts).

**Privacy?**
Posts are redacted (best effort) before a human sees them (Microsoft Presidio plus regexes for handles, URLs and
addresses), the queue lives locally, and the model never acts on its own. The raw post is sent to the model providers
(Fireworks, and Anthropic or OpenAI for the comparison); redaction protects what the dispatcher reads.

**Can this be used commercially?**
The code is MIT. HumAID is CC BY-NC-SA 4.0, so the trained adapter is for non-commercial use; a commercial
deployment would retrain on licensed data with the same code.

**Where does Microsoft fit?**
Presidio does the PII redaction today. Microsoft Foundry is the deployment path for agencies on Azure; it is a
next step and not implemented yet.
