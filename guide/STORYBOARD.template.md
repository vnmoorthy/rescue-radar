{#- Presenter storyboard for the 3-minute Rescue Radar pitch. Rendered by scripts/render_docs.py to guide/STORYBOARD.md.
    Every number is a placeholder filled from results/metrics.json or data/ at render time; missing values print "n/a". -#}
{% set fname = frontier.name or "Claude Opus 5.5" %}
{% set f1_gap = cmp.delta_macro_f1 if f(cmp.delta_macro_f1) is not none else ((f(ours.macro_f1) - f(frontier.macro_f1)) if (f(ours.macro_f1) is not none and f(frontier.macro_f1) is not none) else none) %}
{% set rec_gap = cmp.delta_critical_recall if f(cmp.delta_critical_recall) is not none else ((f(ours.critical.recall) - f(frontier.critical.recall)) if (f(ours.critical.recall) is not none and f(frontier.critical.recall) is not none) else none) %}
{% set f1_ci = cmp.bootstrap.macro_f1_delta_ci95 %}
{% set rec_ci = cmp.bootstrap.critical_recall_delta_ci95 %}
{% set miss = (1 - f(ours.critical.recall)) if f(ours.critical.recall) is not none else none %}
{% set n_eval = m.eval.n or d.eval_n %}
{% set n_dorian = m.eval.events.hurricane_dorian_2019 or d.eval_events.hurricane_dorian_2019 %}
{% set sh_a = cmp.a_on_shared or {} %}{% set sh_b = cmp.b_on_shared or {} %}
{#- lead(): CI-aware. A gap whose 95% interval includes zero is "level, within noise", never "ahead". -#}
{% macro lead(x, ci=none) %}{% set side = ci_side(ci) %}{% if f(x) is none %}a gap of n/a{% elif side == "spans" %}level with {{ fname }}, within noise ({{ pts(x) }}, 95% CI {{ ci_pts(ci) }}){% elif f(x) > 0 %}ahead by {{ pts(x) }}{% if side == "above" %}, and the whole 95% interval is above zero{% endif %}{% elif f(x) < 0 %}behind by {{ pts(x) }}{% else %}level{% endif %}{% endmacro %}
# Rescue Radar: 3-minute presenter storyboard

The deck is `docs/deck/index.html` (live at {{ site }}deck/) with the PowerPoint twin at `deck/RescueRadar.pptx`
(`python deck/build_pptx.py`). The web deck loads its numbers from `docs/data/results.json` at runtime; this
script is rendered from `results/metrics.json` by `scripts/render_docs.py`. If a number below reads n/a, the
benchmark has not landed yet: say "pending", never a guess.

**Controls:** arrow keys, space or click to advance, swipe on a phone, `F` for fullscreen, `#7` in the URL jumps to slide 7.

## Numbers at a glance

| What | Value |
| --- | --- |
| Held-out posts / unseen 2019 disasters / training disasters | {{ num(n_eval) }} / {{ num(m.eval.test_events) }} / {{ num(m.eval.train_events) }} |
| Posts both systems answered (every comparison is paired on these) | {{ num(cmp.n) }} ({{ fname }} hit the Anthropic spending cap) |
| Macro-F1: Rescue Radar vs {{ fname }}, paired | {{ pct(sh_a.macro_f1) }} vs {{ pct(sh_b.macro_f1) }} ({{ pts(f1_gap) }}, 95% CI {{ ci_pts(f1_ci) }}) |
| Rescue-critical recall: Rescue Radar vs {{ fname }}, paired | {{ pct(sh_a.critical_recall) }} vs {{ pct(sh_b.critical_recall) }} ({{ pts(rec_gap) }}, 95% CI {{ ci_pts(rec_ci) }}) |
| Accuracy: Rescue Radar vs {{ fname }}, paired | {{ pct(sh_a.accuracy) }} vs {{ pct(sh_b.accuracy) }} ({{ pts(cmp.delta) }}, 95% CI {{ ci_pts(cmp.bootstrap.delta_ci95) }}) |
| Headline system | {% if headline_ablation %}the small-data run ({{ num(ours_train.examples) }} examples), pre-registered as an ablation: the pre-registered main system is not scored yet. Say so if asked.{% else %}{{ ours.name or "n/a" }}{% endif %} |
| McNemar (posts only one system got right) | Rescue Radar {{ num(cmp.mcnemar.a_only) }}, Opus {{ num(cmp.mcnemar.b_only) }}, {{ pval(cmp.mcnemar.p) }} |
| Bootstrap resamples where Rescue Radar leads on macro-F1 | {{ num(cmp.bootstrap.a_wins) }} of {{ num(cmp.bootstrap.n) }} |
| Median / p95 latency per post | {{ ms(ours.latency_ms.p50) }} / {{ ms(ours.latency_ms.p95) }} vs {{ ms(frontier.latency_ms.p50) }} / {{ ms(frontier.latency_ms.p95) }} |
| Cost per 1M posts | {{ usd(ours.cost_per_1m_usd) }} vs {{ usd(frontier.cost_per_1m_usd) }} (ratio {{ ratio(frontier.cost_per_1m_usd, ours.cost_per_1m_usd) }}) |
| Base Nemotron, before fine-tuning (macro-F1 / critical recall) | {{ pct(base.macro_f1) }} / {{ pct(base.critical.recall) }} |

Cost basis, read it as labelled: Rescue Radar: {{ ours.cost_note or "n/a" }}. Opus: {{ frontier.cost_note or "n/a" }}.

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
{{ num(n_dorian) }} posts and the rescue-critical share.

**Say:**
> "In a major disaster, 911 saturates. People who can't get through post publicly instead: the street, the water
> level, who is trapped. But those pleas are needles in a haystack: only {{ pct(d.eval_critical_share) }} of our
> {{ num(n_eval) }} held-out posts are rescue-critical. No team can read the rest in time."

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

**Cut to live product (0:52):** switch to the browser tab with {{ site }} already open.

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
> {{ num(ours_train.examples) }} labelled posts from {{ num(m.eval.train_events) }} past disasters, and the live
> console serves the same checkpoint we scored."

## 1:42 to 1:58 · Slide 6 · The benchmark design

**On screen:** the 2016 to 2019 timeline draws in; the dashed "never seen in training" wall; the four 2019 test
disasters with their post counts; tiles count up.

**Say:**
> "The test is strict. We trained on 2016 to 2018 and tested on {{ num(m.eval.test_events) }} disasters from 2019 the
> model never saw: Hurricane Dorian, Cyclone Idai, the Pakistan earthquake and the Midwest floods.
> {{ num(n_eval) }} held-out posts, and every system gets the same instructions; the 20-shot baselines also get 20
> examples. Claude hit its spending cap, so we compare on the {{ num(cmp.n) }} posts both answered.
> We pre-registered the protocol before scoring{% if headline_ablation %}; one deviation: the headline is our small-data
> run, because the pre-registered main run is not scored yet{% endif %}."

## 1:58 to 2:22 · Slide 7 · Results vs Claude Opus 5.5

**On screen:** the headline gaps count up; bars draw in for macro-F1, accuracy and rescue-critical recall, with 95%
whiskers; the plain-words significance panel.

**Say:**
> "On the {{ num(cmp.n) }} posts both systems answered, Rescue Radar scores {{ pct(sh_a.macro_f1) }} macro-F1 against
> {{ pct(sh_b.macro_f1) }} for {{ fname }}: {{ lead(f1_gap, f1_ci) }}. On the error that costs lives, missing a rescue
> request, recall is {{ pct(sh_a.critical_recall) }} against {{ pct(sh_b.critical_recall) }}: {{ lead(rec_gap, rec_ci) }}.
> Is it luck? On the posts where only one system was right, we were right {{ num(cmp.mcnemar.a_only) }} times and
> Opus {{ num(cmp.mcnemar.b_only) }}, {{ pval(cmp.mcnemar.p) }}. And across {{ num(cmp.bootstrap.n) }} bootstrap
> re-draws of the test set, the macro-F1 gap stays between {{ ci_pts(f1_ci) }}."

**Honesty rule:** read the direction exactly as the numbers show it. If an interval includes zero, say
"we can't claim a difference on that one".

## 2:22 to 2:36 · Slide 8 · Speed and cost

**On screen:** latency and cost panels, each tagged MEASURED or ESTIMATED; the ratio counts up.

**Say:**
{% set ol = f(ours.latency_ms.p50) %}{% set fl = f(frontier.latency_ms.p50) %}
> "{% if ol is not none and fl is not none and ol > fl %}It is slower per post today: median {{ ms(ours.latency_ms.p50) }} against {{ ms(frontier.latency_ms.p50) }}
> for {{ fname }}, measured on every benchmark call with 32 parallel requests on shared serverless capacity (Claude: 24).
> A dedicated deployment is the fix.{% else %}It keeps up with a live feed: median {{ ms(ours.latency_ms.p50) }} per post against
> {{ ms(frontier.latency_ms.p50) }} for {{ fname }}, measured on every benchmark call.{% endif %} And it costs {{ usd(ours.cost_per_1m_usd) }} per million posts
> against {{ usd(frontier.cost_per_1m_usd) }}, from measured tokens at published prices."

## 2:36 to 2:48 · Slide 9 · Sponsor stack, responsible AI, limitations

**On screen:** Fireworks, NVIDIA and Microsoft cards; responsible-AI list; limitations list in orange.

**Say:**
> "Fireworks trains and serves it, NVIDIA's open Nemotron is the base, and Microsoft Presidio redacts personal data,
> best effort, before any human review. Microsoft Foundry deployment is a next step, not built yet. And the limits, plainly: it still misses {{ pct(miss) }} of
> rescue-critical posts and it's English-only so far, so it runs beside 911, never instead of it."

## 2:48 to 3:00 · Slide 10 · The ask

**On screen:** four asks, the team, the repo and demo URLs; the radar sweep returns.

**Say:**
> "Next: a dedicated Fireworks deployment, Microsoft Foundry for agencies, more languages and platforms, and pilot
> partners for the next storm season. We're vnmoorthy and Seth Caldwell; the code is at {{ repo }} and the demo is
> live. Thank you."

**Transition:** leave slide 10 up for questions.
