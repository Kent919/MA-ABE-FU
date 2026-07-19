# Dataset placement

The experiments use UCI German Credit and UCI Bank Marketing. The submission archive contains the local copies used for the reported run. For a public repository, place the same files as follows:

- `public_data/german.data`
- `public_data/bank/bank-full.csv`

The optional Bank Account Fraud Dataset Suite is evaluated only when one of these files is present:

- `public_data/bafs/Base.csv`
- `public_data/bafs/Variant I.csv`
- `public_data/bafs/Variant II.csv`
- `public_data/bafs/Variant III.csv`
- `public_data/bafs/Variant IV.csv`
- `public_data/bafs/Variant V.csv`

If no BAFS CSV is present, `run_validation_v6.py` writes `bafs_status_v6.json` and does not generate third-dataset metrics.
