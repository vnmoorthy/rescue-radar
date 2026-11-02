#!/usr/bin/env bash
# Rebuild every derived artifact from the saved predictions, then check everything. Run from the repo root.
#   bash scripts/finalize.sh
set -euo pipefail
PY=.venv/bin/python
$PY -m rr.evaluate                 # results/metrics.json from data/preds/*.jsonl
$PY scripts/export_static.py       # docs/ (GitHub Pages console + data)
$PY scripts/render_docs.py         # README.md, guide/*.md from their templates
$PY deck/build_pptx.py             # deck/RescueRadar.pptx
$PY -m pytest -q tests/            # API tests, no network
for f in web/*.js web/views/*.js; do node --check "$f"; done
python3 scripts/check_secrets.py   # no API keys in anything git would commit
echo "finalize: all good"
