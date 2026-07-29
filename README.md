# MA-ABE-FU reproducibility package

Target manuscript: MA-ABE-FU: Policy-Authenticated and Evidence-Bound Federated Unlearning for Cross-Border Identity Authentication

Public repository: https://github.com/Kent919/MA-ABE-FU

This repository is intended for reviewer-facing reproducibility. It contains the
code, dataset placement instructions, generated numerical results, and figure
artifacts needed to inspect and rerun the experiments. Manuscript submission
files such as the main Word/PDF document, cover letter, title page, and author
biographies are handled through the journal submission system and are not part
of this repository.

## Contents

- `run_validation_v8.py`: federated partitioning, learning-plane baselines, leakage attacks, proxy ablations, RiskGap sensitivity, and cryptographic benchmarks.
- `redraw_ieee_figures_v8.py`: 600 dpi IEEE-style figure generation from CSV results.
- `results/*.csv|*.json`: exact experiment outputs used in the manuscript.
- `figures/Fig. *.pdf|*.tif`: vector PDFs and 600 dpi TIFF figures.
- `references.bib`: IEEE-formatted reference list exported for submission support.

## Reproduction

Install Python dependencies:

```bash
python -m pip install numpy pandas pillow cryptography py_ecc python-docx
```

Install Poppler, or set `PDFTOCAIRO` to the absolute path of `pdftocairo`, before redrawing figures.

Place public datasets under `public_data/`:

- `public_data/german.data`
- `public_data/bank/bank-full.csv`
- optional BAFS CSV files under `public_data/bafs/`

Run:

```bash
python run_validation_v8.py
python redraw_ieee_figures_v8.py
```

The scripts regenerate the experimental tables and exactly five main figures as vector PDFs plus 600 dpi TIFF files. If BAFS files are absent, the runner writes `bafs_status_v8.json` and skips BAFS numeric results.
