{#- Rendered to guide/DEMO_RUNBOOK.md by scripts/render_docs.py. Re-render right before the demo. -#}
{% set test_events = m.eval.test_events or d.test_events_n %}
{% set train_events = m.eval.train_events or d.train_events_n %}
{% set eval_n = m.eval.n or d.eval_n %}
{% set sh_a = cmp.a_on_shared or {} %}{% set sh_b = cmp.b_on_shared or {} %}{% set bs = cmp.bootstrap or {} %}
{% set mf_side = ci_side(bs.macro_f1_delta_ci95) %}{% set cr_side = ci_side(bs.critical_recall_delta_ci95) %}
# Demo runbook (10 minutes)

For the presenter. Numbers on this page are rendered from `results/metrics.json`
({% if m.generated_at %}generated {{ m.generated_at }}{% else %}pending{% endif %}). If one shows `n/a`, do not
say a number out loud: point at the Benchmark view instead.

**Headline to remember:** paired on the {{ num(cmp.n) }} posts (from {{ num(test_events) }} disasters our fine-tune
never saw) that both systems answered, Rescue Radar catches **{{ pct(sh_a.critical_recall) }}** of rescue-critical
posts vs **{{ pct(sh_b.critical_recall) }}** for {{ frontier_name }} ({{ pts(cmp.delta_critical_recall) }}, 95% CI
{{ ci_pts(bs.critical_recall_delta_ci95) }}). Macro-F1 {{ pct(sh_a.macro_f1) }} vs {{ pct(sh_b.macro_f1) }}
({{ pts(cmp.delta_macro_f1) }}, 95% CI {{ ci_pts(bs.macro_f1_delta_ci95) }}){% if mf_side == "spans" %}: **level, within noise; never say "more accurate"**{% endif %}.
Costs **{{ usd(ours.cost_per_1m_usd) }}** per million posts (Claude {{ usd(frontier.cost_per_1m_usd) }}; the Fireworks
rate includes a limited-time 50% discount), but it is slower: median **{{ ms(ours.latency_ms.p50) }}** per post
(Claude {{ ms(frontier.latency_ms.p50) }}).{% if headline_ablation %} These are the **small-data run's** numbers
({{ num(ours_train.examples) }} training examples); the pre-registration lists that run as an ablation and the
pre-registered main system is not scored yet. Say so if asked.{% endif %}{% for k in ("opus_few", "opus_zero") if (systems.get(k) or {}).get("coverage") is number and systems[k].coverage < 1 %} {{ systems[k].name }} answered {{ num(systems[k].n) }} of the {{ num(eval_n) }} posts before the Anthropic spending cap.{% endfor %}


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
| 0:00 | Deck, title | Open the deck tab. | "When a disaster hits, emergency lines saturate and people post for rescue in public. In our eval set only {{ pct(d.eval_critical_share) }} of posts are rescue-critical. Rescue Radar finds them in real time." |
| 1:00 | Console, **Live Replay** (key 1) | Pick Hurricane Dorian, set speed **10x** (or 50x), then press Play. At 1x the first red flag takes about 17 s. | "These are real tweets from Hurricane Dorian, replayed in their original order. The model never saw this storm. Red means a person needs help: a request, injured or dead, missing or trapped." |
| 2:30 | Live Replay | Click a red post on the map. | "Personal data is redacted, best effort, before a human sees it, here with Microsoft Presidio. The location comes from a gazetteer; if a post names no place, we do not guess." |
| 3:30 | **Live Replay** (key 1) → **Priority queue** panel | Mark one item dispatched, one dismissed; show Export CSV. | "The model ranks; a dispatcher decides. Nothing is dispatched automatically." |
| 4:30 | **Head-to-Head** (key 3) | Paste post 1, then post 2. | "Same instructions to both; the frontier model also gets 20 examples. Our fine-tuned Nemotron on Fireworks next to the frontier model named on the card (Claude Opus 5.5, or GPT-6.1 Terra while the Anthropic account is capped): label, latency, cost per post." |
| 6:00 | **Benchmark** (key 4) | Show the table and the intervals. | "{{ num(eval_n) }} posts, {{ num(test_events) }} unseen disasters; paired on the {{ num(cmp.n) }} both systems answered. Rescue-critical recall {{ pct(sh_a.critical_recall) }} vs {{ pct(sh_b.critical_recall) }}, interval {{ ci_pts(bs.critical_recall_delta_ci95) }}{{ ": a real gain" if cr_side == "above" else "" }}. Macro-F1 {{ pct(sh_a.macro_f1) }} vs {{ pct(sh_b.macro_f1) }}, interval {{ ci_pts(bs.macro_f1_delta_ci95) }}{{ ": level, within noise" if mf_side == "spans" else "" }}. McNemar {{ pval(cmp.mcnemar.p) }}." |
| 7:30 | **How it works** (key 5) | Walk the pipeline. | "Trained on {{ num(train_events) }} disasters from 2016 to 2018 with LoRA on Fireworks serverless training. Base model NVIDIA Nemotron 3.5 Super. The live console serves the same checkpoint the benchmark scored; the header badge says so." (Only if the badge reads "scored".) |
| 8:30 | Deck, last slides | Limits and next steps. | "Old Twitter data, small urgent classes, non-commercial dataset license, human in the loop. Next: a dedicated Fireworks deployment and Microsoft Foundry, neither built yet." |
| 9:30 | Deck, close | Show the repo and live demo URLs. | "Everything is open: github.com/vnmoorthy/rescue-radar." |

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
We split by event: trained on {{ num(train_events) }} disasters from 2016 to 2018, tested on {{ num(test_events) }}
from 2019 the model never saw, and removed training tweets duplicated in the test events{% if d.dedup_removed is number %} ({{ num(d.dedup_removed) }} tweets){% endif %}.

**Is the difference with Claude statistically real?**
Paired on the {{ num(cmp.n) }} posts both answered: Rescue Radar right and Claude wrong on {{ num(cmp.mcnemar.a_only) }}
posts, the reverse on {{ num(cmp.mcnemar.b_only) }}; exact McNemar {{ pval(cmp.mcnemar.p) }}. Bootstrap 95% interval
for the macro-F1 difference: {{ ci_pts(bs.macro_f1_delta_ci95) }}; accuracy: {{ ci_pts(bs.delta_ci95) }}; rescue-critical
recall: {{ ci_pts(bs.critical_recall_delta_ci95) }}. Only an interval that excludes zero is a real difference.

**Why does Claude have fewer posts?**
The Anthropic account hit its spending cap mid-run{% for k in ("opus_few", "opus_zero") if (systems.get(k) or {}).get("n") is number %}; {{ systems[k].name }} answered {{ num(systems[k].n) }}{% endfor %}.
Every comparison is paired on the posts both systems answered.
{% if headline_ablation %}

**Why is the headline the small-data run?**
The pre-registered main system (the larger run's checkpoint frozen at 14:55) has not been scored yet. The headline
numbers come from the small-data run ({{ num(ours_train.examples) }} examples), which the pre-registration lists as
an ablation; we disclose that deviation in the README and the Benchmark view.
{% endif %}

**Was the comparison fair to Claude?**
Same instructions and category definitions for every system, and Claude also got 20 examples (two per category).
We report both zero-shot ({{ pct(frontier_zero.macro_f1) }} macro-F1) and 20-shot ({{ pct(systems.get('opus_few', {}).get('macro_f1')) }}).

**What did fine-tuning add?**
The same Nemotron without LoRA, served the same way, scores {{ pct(base.macro_f1) }} macro-F1 and
{{ pct(base.critical.recall) }} rescue-critical recall; with LoRA, {{ pct(ours.macro_f1) }} and {{ pct(ours.critical.recall) }}.

**What does it cost to run?**
{{ usd(ours.cost_per_1m_usd) }} per million posts for Rescue Radar vs {{ usd(frontier.cost_per_1m_usd) }} for
{{ frontier_name }}, from measured tokens times published prices.{% if ours.cost_per_1m_usd_undiscounted is number %} The Fireworks rate includes a limited-time discount; without it: {{ usd(ours.cost_per_1m_usd_undiscounted) }}.{% endif %}

**How fast is it?**
Slower than Claude: median {{ ms(ours.latency_ms.p50) }} per post, p95 {{ ms(ours.latency_ms.p95) }}, measured with 32
parallel requests on shared serverless capacity; Claude median {{ ms(frontier.latency_ms.p50) }} (24 parallel requests).
A dedicated deployment is the next step for steady latency.

**What about the rare classes?**
The eval set has only {{ num(d.eval_labels.requests_or_urgent_needs) }} `requests_or_urgent_needs` posts and
{{ num(d.eval_labels.missing_or_found_people) }} `missing_or_found_people` posts, so per-class numbers have wide
intervals. That is why we also report rescue-critical recall as one group ({{ num(d.eval_critical_n) }} posts).

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
