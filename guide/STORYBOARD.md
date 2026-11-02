<!-- Generated from guide/STORYBOARD.template.md by scripts/render_docs.py. Edit the template, then re-run the script. -->
# Rescue Radar: 3-minute presenter storyboard

The deck is `docs/deck/index.html` (live at https://vnmoorthy.github.io/rescue-radar/deck/) with the PowerPoint twin at `deck/RescueRadar.pptx`
(`python deck/build_pptx.py`). The web deck loads its numbers from `docs/data/results.json` at runtime; this
script is rendered from `results/metrics.json` by `scripts/render_docs.py`. If a number below reads n/a, the
benchmark has not landed yet: say "pending", never a guess.

**Controls:** arrow keys, space or click to advance, swipe on a phone, `F` for fullscreen, `#7` in the URL jumps to slide 7.

## Numbers at a glance

| What | Value |
| --- | --- |
| Held-out posts / unseen 2019 disasters / training disasters | 3,001 / 4 / 15 |
| Posts both systems answered (every comparison is paired on these) | 2,592 (Claude Opus 5.5, 20-shot hit the Anthropic spending cap) |
| Macro-F1: Rescue Radar vs Claude Opus 5.5, 20-shot, paired | 69.2% vs 63.7% (+5.5 pts, 95% CI +2.6 to +8.5 pts) |
| Rescue-critical recall: Rescue Radar vs Claude Opus 5.5, 20-shot, paired | 85.3% vs 68.8% (+16.5 pts, 95% CI +11.2 to +21.9 pts) |
| Accuracy: Rescue Radar vs Claude Opus 5.5, 20-shot, paired | 73.1% vs 70.9% (+2.2 pts, 95% CI +0.5 to +4.0 pts) |
| Headline system | Rescue Radar, main run (13,839 examples) |
| McNemar (posts only one system got right) | Rescue Radar 291, Opus 233, p = 0.013 |
| Bootstrap resamples where Rescue Radar leads on macro-F1 | 4,997 of 5,000 |
| Median / p95 latency per post | 3.37 s / 8.42 s vs 1.31 s / 2.71 s |
| Cost per 1M posts | $171 vs $8,738 (ratio 51.1x) |
| Base Nemotron, before fine-tuning (macro-F1 / critical recall) | 57.6% / 65.3% |

Cost basis, read it as labelled: Rescue Radar: measured tokens x Fireworks published sampling rate for Nemotron 3.5 Super ($0.57 prefill / $1.44 sample per 1M tokens, includes a limited-time 50% discount; about 2x without it). Opus: measured tokens x Anthropic list price ($4 in / $20 out per 1M tokens, thinking tokens included).

---

## 0:00 to 0:15 · Slide 1 · Title and hook

**On screen:** the radar sweeps in; "RESCUE RADAR"; a real Hurricane Dorian post types itself out, PII scrubbed,
then its label chip appears.

**Say:**
> "This was posted publicly during Hurricane Dorian. Someone in Abaco lost contact with a friend, and a cousin's church
> shelter had its roof ripped off, with people stuck by flooding. They asked strangers online for help.
> Rescue Radar exists so a post like this never sits unread."

(The deck pins this hand-checked post, id 1168306378944987141. If a different post shows, describe only what it says.)

**Transition:** wait for the label chip, then advance (crossfade).

## 0:15 to 0:30 · Slide 2 · The problem

**On screen:** three beats build in; the Dorian post stream scrolls; the counters run up to
1,485 posts and the rescue-critical share.

**Say:**
> "In a major disaster, 911 saturates. People who can't get through post publicly instead: the street, the water
> level, who is trapped. But those pleas are needles in a haystack: only 8.5% of our
> 3,001 held-out posts are rescue-critical. No team can read the rest in time."

**Transition:** advance on "in time".

## 0:30 to 0:42 · Slide 3 · Who it is for

**On screen:** three cards (dispatchers, emergency operations centers, NGOs and volunteer rescue), then the
job-to-be-done banner.

**Say:**
> "It's built for 911 dispatchers, emergency operations centers and volunteer rescue groups, with one job:
> find every public cry for rescue, see where it is, and hand it to a team before the window closes."

## 0:42 to 0:52 · Slide 4 · The product

**On screen:** the console mock replays Hurricane Dorian: posts stream in, rescue-critical ones turn red, pins
pulse on the map, the priority queue fills.

**Say:**
> "Here's the dispatch console. Let me show you the real thing."

**Cut to live product (0:52):** switch to the browser tab with https://vnmoorthy.github.io/rescue-radar/ already open.

## 0:52 to 1:25 · LIVE DEMO · the dispatch console

**On screen:** the live console, not the deck.

1. Start the **Hurricane Dorian replay**. Point at a red post as it lands: "Rescue-critical. It's on the map and at
   the top of the queue, and names, phone numbers and handles are redacted, best effort."
2. Mark one queue item **dispatched**: "The model ranks. A person decides."
3. Open **Head-to-Head**, paste a fresh post, run it: "Same post, our fine-tuned model and the frontier model named on
   the card side by side (Claude Opus 5.5, or GPT-6.1 Terra while the Anthropic account is capped), with the latency
   and cost of each call."

**Fallback:** if the live model call fails, the replay still runs from recorded predictions; say "the live endpoint
is cold, so this is the recorded run of the same model" and keep going.

**Transition:** back to the deck on slide 5 (press `5`, or `#5` in the URL).

## 1:25 to 1:42 · Slide 5 · How it works

**On screen:** the six-step pipeline builds left to right with a red packet travelling through it; the training strip below.

**Say:**
> "Under the hood: every post is classified into the 10 HumAID humanitarian categories by NVIDIA Nemotron 3.5 Super
> with our LoRA adapter, fine-tuned and served on Fireworks, and redacted before a dispatcher reads it. We trained on
> 13,839 labelled posts from 15 past disasters, and the live
> console serves the same checkpoint we scored."

## 1:42 to 1:58 · Slide 6 · The benchmark design

**On screen:** the 2016 to 2019 timeline draws in; the dashed "never seen in training" wall; the four 2019 test
disasters with their post counts; tiles count up.

**Say:**
> "The test is strict. We trained on 2016 to 2018 and tested on 4 disasters from 2019 the
> model never saw: Hurricane Dorian, Cyclone Idai, the Pakistan earthquake and the Midwest floods.
> 3,001 held-out posts, and every system gets the same instructions; the 20-shot baselines also get 20
> examples. Claude hit its spending cap, so we compare on the 2,592 posts both answered.
> We pre-registered the protocol before scoring."

## 1:58 to 2:22 · Slide 7 · Results vs Claude Opus 5.5

**On screen:** the headline gaps count up; bars draw in for macro-F1, accuracy and rescue-critical recall, with 95%
whiskers; the plain-words significance panel.

**Say:**
> "On the 2,592 posts both systems answered, Rescue Radar scores 69.2% macro-F1 against
> 63.7% for Claude Opus 5.5, 20-shot: ahead by +5.5 pts, and the whole 95% interval is above zero. On the error that costs lives, missing a rescue
> request, recall is 85.3% against 68.8%: ahead by +16.5 pts, and the whole 95% interval is above zero.
> Is it luck? On the posts where only one system was right, we were right 291 times and
> Opus 233, p = 0.013. And across 5,000 bootstrap
> re-draws of the test set, the macro-F1 gap stays between +2.6 to +8.5 pts."

**Honesty rule:** read the direction exactly as the numbers show it. If an interval includes zero, say
"we can't claim a difference on that one".

## 2:22 to 2:36 · Slide 8 · Speed and cost

**On screen:** latency and cost panels, each tagged MEASURED or ESTIMATED; the ratio counts up.

**Say:**
> "It is slower per post today: median 3.37 s against 1.31 s
> for Claude Opus 5.5, 20-shot, measured on every benchmark call with 32 parallel requests on shared serverless capacity (Claude: 24).
> A dedicated deployment is the fix. And it costs $171 per million posts
> against $8,738, from measured tokens at published prices."

## 2:36 to 2:48 · Slide 9 · Sponsor stack, responsible AI, limitations

**On screen:** Fireworks, NVIDIA and Microsoft cards; responsible-AI list; limitations list in orange.

**Say:**
> "Fireworks trains and serves it, NVIDIA's open Nemotron is the base, and Microsoft Presidio redacts personal data,
> best effort, before any human review. Microsoft Foundry deployment is a next step, not built yet. And the limits, plainly: it still misses 15.3% of
> rescue-critical posts and it's English-only so far, so it runs beside 911, never instead of it."

## 2:48 to 3:00 · Slide 10 · The ask

**On screen:** four asks, the team, the repo and demo URLs; the radar sweep returns.

**Say:**
> "Next: a dedicated Fireworks deployment, Microsoft Foundry for agencies, more languages and platforms, and pilot
> partners for the next storm season. We're vnmoorthy and Seth Caldwell; the code is at https://github.com/vnmoorthy/rescue-radar and the demo is
> live. Thank you."

**Transition:** leave slide 10 up for questions.
