# eeg-ds004752 V5.5 implementation scaffold

This repository contains the implementation scaffold for the V5.5
observability-constrained privileged transfer project on OpenNeuro
dataset `ds004752`.

The current implementation prioritizes the governance/freeze layer:
Gate 0 dataset audit, manifest generation, cohort-lock draft, bridge
availability draft, and hard guards that prevent real-data phases from
running before preregistration is locked.

## Quick start in Colab

```python
from google.colab import drive
drive.mount('/content/drive')

!git clone https://github.com/BrianNguyen29/eeg-ds004752.git
%cd eeg-ds004752
!bash bootstrap/install_runtime.sh
!python bootstrap/colab_quickstart.py
!bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data metadata
!python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml
```

If your Drive layout is nested under `MyDrive/eeg/eeg-ds004752`, use:

```python
!bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg/eeg-ds004752/data metadata
!python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab_nested.yaml
```

The recommended notebook entrypoint is:

```text
notebooks/01_colab_gate0_audit.ipynb
```

The repository intentionally does not track `ds004752/` or runtime
artifacts. Data should live on Google Drive or be installed in Colab with
DataLad/OpenNeuro.

## CLI

The single entrypoint is `src/cli.py`, as required by the blueprint:

```bash
python -m src.cli audit --profile t4_safe --config configs/data/snapshot.yaml
python -m src.cli smoke --profile t4_safe --config configs/data/snapshot.yaml
python -m src.cli synthetic --profile a100_fast --config configs/prereg/prereg_bundle.json
python -m src.cli phase05_real --profile a100_fast --config configs/prereg/prereg_bundle.json
python -m src.cli phase1_real --profile a100_fast --config configs/prereg/prereg_bundle.json
python -m src.cli report_compile --profile t4_safe --run artifacts/gate0/latest.txt
```

Real-data phase commands intentionally fail until Gate 2.5 preregistration
is locked.

## Google Drive layout

```text
/content/drive/MyDrive/eeg-ds004752/
  data/
    ds004752/
  artifacts/
    gate0/
    gate1/
    gate2/
    prereg/
    runs/
    reports/
  cache/
  checkpoints/
```

Dataset bootstrap options:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data metadata
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data sample
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data all
```

## Local tests

```bash
python -m unittest discover -s tests
```

GitHub Actions runs the same standard-library test suite on every push and
pull request.

## Data status

The local dataset currently contains BIDS metadata, but `.edf` and `.mat`
files may be Git-annex/DataLad pointers. Gate 0 metadata audit can run with
metadata only. Signal-level checks, EDF duration validation, binary
checksums, and beamforming ROI audit require materialized payloads.

## Current implementation status

- Implemented: project scaffold, configs, CLI, Gate 0 metadata audit, real-phase guards, tests, Colab bootstrap.
- Blocked by data: signal-level EDF/MAT audit, preprocessing, feature extraction, model training.
- Next gate: materialize sample payload in Colab, then implement `src/preprocess` signal audit with MNE.
