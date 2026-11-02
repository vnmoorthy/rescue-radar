## What this changes

<!-- One or two sentences. Link the issue it closes, if any: "Closes #12". -->

## Why

## How it was tested

- [ ] `python -m pytest tests/ -q` passes (no API keys needed)
- [ ] `python scripts/render_docs.py --check` passes (rendered docs are up to date)
- [ ] `python scripts/check_secrets.py` passes (no keys in tracked files)
- [ ] Tried in the console (`python -m rr.server`), if the change touches `web/` or `rr/server.py`

## Results impact

- [ ] No effect on the benchmark
- [ ] Changes the prompt, the data split, the model or the scoring. Before and after from `results/metrics.json`,
      with 95% intervals:

| Metric | Before | After |
| --- | --- | --- |
| Macro-F1 | | |
| Rescue-critical recall | | |

## Checklist

- [ ] No hand-typed benchmark numbers: docs are edited in `*.template.md` and rendered
- [ ] No personal data in code, tests, fixtures or screenshots
- [ ] A human still makes every dispatch decision
