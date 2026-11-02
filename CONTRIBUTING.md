# Contributing to Rescue Radar

Thanks for helping. Rescue Radar is a disaster-response tool, so we care about two things above all:
**claims that are backed by measurements**, and **a human staying in charge of every decision**.

## Ways to help

- **Report a bug** with the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md).
- **Propose a feature or an evaluation idea** with the [feature request template](.github/ISSUE_TEMPLATE/feature_request.md).
- **Improve the evaluation**: new held-out disasters, other crisis datasets, error analysis.
- **Improve safety**: better PII redaction, better location handling, accessibility of the console.
- **Fix docs**: unclear steps in the [Quickstart](README.md#quickstart) are bugs.

## Development setup

```bash
git clone https://github.com/vnmoorthy/rescue-radar.git
cd rescue-radar
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -q          # the suite runs without any API key
python -m rr.server                 # console at http://localhost:8787
```

API keys go in a git-ignored `.env` file in the repo root (`FIREWORKS_API_KEY`, `ANTHROPIC_API_KEY`, `HF_TOKEN`).
Code reads them only through `rr.env.load_env()`. Never print, log or commit them; before you push, run:

```bash
python scripts/check_secrets.py
```

## Ground rules for changes

1. **No hand-typed numbers.** Every benchmark number in the README, the guides, the console and the deck comes
   from `results/metrics.json` or `data/` at render time. Edit `README.template.md` (or another
   `*.template.md`), then run `python scripts/render_docs.py`. Missing values must render as `n/a`.
2. **One prompt for everyone.** All systems share the prompt in `rr/labels.py`. A change there changes every
   result: re-run the benchmark and say so in the pull request.
3. **Same path for demo and benchmark.** The live console must call the same classifier the benchmark scored
   (`rr.infer.get_classifier()`). Do not add a separate "demo model".
4. **`data/` is generated, never hand-edited.** Regenerate it with the scripts in `rr/`.
5. **Fail soft.** When a model or key is unavailable the API returns HTTP 503 with a readable `detail`; the
   console keeps working from recorded data.
6. **Tests run offline.** New tests must not need network access or API keys.

## Pull requests

- Keep each pull request focused on one change, and fill in the [template](.github/pull_request_template.md).
- Run `python -m pytest tests/ -q` and `python scripts/render_docs.py --check` before you open it.
- If your change moves a metric, include the before and after from `results/metrics.json`, with intervals.
- Use clear commit messages in the imperative mood ("Add per-event recall to the Benchmark view").

## Code style

- Python 3.12, standard library first, small modules with a docstring that says what the file is for.
- Keep functions short and names plain. Prefer readable over clever.
- Front end: no build step; plain HTML, CSS and JavaScript in `web/`. Rescue-critical categories must read as
  urgent (red or orange) in both light and dark themes.

## Data and licensing

Code contributions are accepted under the [MIT License](LICENSE). HumAID data and anything derived from it are
CC BY-NC-SA 4.0 (non-commercial); see [DATA_LICENSE.md](DATA_LICENSE.md). Do not add data you do not have the
rights to share, and never add data that identifies private individuals.

## Conduct

Everyone taking part is expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md).
