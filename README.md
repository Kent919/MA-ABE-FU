# MA-ABE-FU Reproducibility Package

This repository supports the experiments for:

**MA-ABE-FU: Policy-Hiding Access Control for Auditable Federated Unlearning in Multi-Cloud Identity Services**

It contains the code, dataset placement instructions, checked numerical outputs, and figure-generation scripts needed to inspect and rerun the experimental evidence. Journal submission files are intentionally excluded.

## Contents

- `run_validation.py`: data partitioning, learning-plane baselines, leakage attacks, proxy ablations, RiskGap sensitivity, and cryptographic benchmarks.
- `redraw_figures.py`: IEEE-style vector PDF and 600 dpi TIFF figure generation from checked CSV results.
- `results/*.csv|*.json`: numerical outputs used by the tables and figures.
- `figures/fig*.pdf|fig*.tif`: five generated figure artifacts.
- `DATASETS.md`: public dataset placement notes.
- `requirements.txt`: Python dependencies.

## Reproduction

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Install Poppler, or set `PDFTOCAIRO` to the absolute path of `pdftocairo`, before redrawing TIFF figures. If Poppler is unavailable, `redraw_figures.py` falls back to `pypdfium2` when installed.

Place public datasets under `public_data/`:

- `public_data/german.data`
- `public_data/bank/bank-full.csv`
- optional BAFS CSV files under `public_data/bafs/`

Run:

```bash
python run_validation.py
python redraw_figures.py
```

If BAFS files are absent, the runner writes `results/bafs_status.json` and skips BAFS numeric claims. The checked-in CSV and JSON files are the reference outputs for the submitted experiments.

## Experimental Scope

The federated utility, membership-inference residue, proxy calibration, and RiskGap tables are computed from public UCI financial datasets after documented non-IID client partitioning. The learning-side experiments use logistic regression on tabular financial data. The MA-ABE-FU control plane is model agnostic, while the reported empirical findings are limited to the included dataset and model settings.

The malicious-server leakage experiment is a controlled metadata-observability benchmark derived from the same run metadata and a process-independent SHA-256 random seed. Cryptographic timing is hardware-dependent; reruns should report local hardware and dependency versions when comparing absolute latency.
