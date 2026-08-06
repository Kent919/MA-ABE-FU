# MA-ABE-FU Reproducibility Package

This repository supports the experiments for:

**MA-ABE-FU: Policy-Hiding Access Control for Auditable Federated Unlearning in Multi-Cloud Identity Services**

It contains the code, dataset placement instructions, and checked numerical outputs needed to inspect and rerun the experimental evidence. Journal submission files and generated figure images are intentionally excluded.

## Contents

- `run_validation.py`: data partitioning, learning-plane baselines, leakage attacks, proxy ablations, RiskGap sensitivity, and cryptographic benchmarks.
- `redraw_figures.py`: optional vector PDF figure preview generation from checked CSV results.
- `results/*.csv|*.json`: numerical outputs used by the reported tables and plots.
- `DATASETS.md`: public dataset placement notes.
- `requirements.txt`: Python dependencies.

## Reproduction

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Place public datasets under `public_data/`:

- `public_data/german.data`
- `public_data/bank/bank-full.csv`
- optional BAFS CSV files under `public_data/bafs/`

Run:

```bash
python run_validation.py
```

If BAFS files are absent, the runner writes `results/bafs_status.json` and skips BAFS numeric claims. The checked-in CSV and JSON files are the reference outputs for the submitted experiments.

## Optional Figure Preview

The paper figures are submission artifacts, so generated figure files are not stored in this repository. To regenerate vector PDF previews from the checked CSV results:

```bash
python -m pip install reportlab
python redraw_figures.py
```

This optional step writes `figures/fig1.pdf` through `figures/fig5.pdf` and updates `results/figure_manifest.csv`. It is not required to reproduce the experimental metrics.

## Experimental Scope

The federated utility, membership-inference residue, proxy calibration, and RiskGap tables are computed from public UCI financial datasets after documented non-IID client partitioning. The learning-side experiments use logistic regression on tabular financial data. The MA-ABE-FU control plane is model agnostic, while the reported empirical findings are limited to the included dataset and model settings.

The malicious-server leakage experiment is a controlled metadata-observability benchmark derived from the same run metadata and a process-independent SHA-256 random seed. Cryptographic timing is hardware-dependent; reruns should report local hardware and dependency versions when comparing absolute latency.
