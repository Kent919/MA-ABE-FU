# MA-ABE-FU reproducibility package

Target manuscript: MA-ABE-FU: Policy-Authenticated and Evidence-Bound Federated Unlearning for Cross-Border Identity Authentication

Public repository: https://github.com/Kent919/MA-ABE-FU

## Contents

- `run_validation_v6.py`: federated partitioning, learning-plane baselines, leakage attacks, proxy ablations, RiskGap sensitivity, and cryptographic benchmarks.
- `redraw_ieee_figures_v6.py`: 600 dpi IEEE-style figure generation from CSV results.
- `prebuild_validation_v6.py`: terminology, symbol, figure, format, reference, and trace audit before manuscript construction.
- `build_submission_v6.py`: manuscript, supplementary material, title page, highlights, cover letter, and package builder.
- `submission_tifs_v6/reproducibility/*.csv|*.json`: exact experiment outputs and validation records used in the manuscript.
- `submission_tifs_v6/figure/Fig. *.pdf|*.tif`: vector PDFs and 600 dpi TIFF figures.
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
python run_validation_v6.py
python redraw_ieee_figures_v6.py
python prebuild_validation_v6.py
python build_submission_v6.py
```

The scripts regenerate all manuscript tables, exactly five main figures as vector PDFs plus 600 dpi TIFF files, the validation records, and the manuscript package. If BAFS files are absent, the runner writes `bafs_status_v6.json` and skips BAFS numeric results.
