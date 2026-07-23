# Dataset placement

The experiments use UCI German Credit and UCI Bank Marketing. For a local run, place public dataset files as follows:

- `public_data/german.data`
- `public_data/bank/bank-full.csv`

The optional Bank Account Fraud Dataset Suite is evaluated only when one of these files is present:

- `public_data/bafs/Base.csv`
- `public_data/bafs/Variant I.csv`
- `public_data/bafs/Variant II.csv`
- `public_data/bafs/Variant III.csv`
- `public_data/bafs/Variant IV.csv`
- `public_data/bafs/Variant V.csv`

If no BAFS CSV is present, `run_validation_v8.py` writes `bafs_status_v8.json` and does not generate third-dataset metrics.
