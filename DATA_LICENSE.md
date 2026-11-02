# Data license

The MIT license in [LICENSE](LICENSE) covers the **code** in this repository. It does not cover the data.

## HumAID (QCRI)

Rescue Radar is trained and evaluated on **HumAID: Human-Annotated Disaster Incidents Data from Twitter**
(Alam, Qazi, Imran and Ofli, ICWSM 2021), published by the Qatar Computing Research Institute (QCRI) and
downloaded by `python -m rr.prep` from <https://huggingface.co/datasets/QCRI/HumAID-events>.

HumAID is licensed **CC BY-NC-SA 4.0** (Attribution, NonCommercial, ShareAlike):
<https://creativecommons.org/licenses/by-nc-sa/4.0/>.

What that means here:

- Files in `data/` that are derived from HumAID (`eval.jsonl`, `test_full.jsonl`, `train_sft.jsonl`,
  `preds/*.jsonl`, and the replay files the static demo ships) remain under CC BY-NC-SA 4.0.
- Model weights or adapters trained on HumAID, including the Rescue Radar LoRA adapter, should be treated as
  derived from it: **non-commercial use only**, with attribution, and shared under the same terms.
- `data/raw/` (the original download) is git-ignored and is not redistributed by this repository.
- Tweets are public posts written by real people. Do not try to re-identify, contact or profile their authors.

If you need a commercial deployment, retrain on data you have the rights to use; the code supports that
unchanged (`rr/prep.py` builds the split, `rr/train.py` trains on any file in the same chat format).

Please cite HumAID when you use it (BibTeX in the [README](README.md#citation)).
