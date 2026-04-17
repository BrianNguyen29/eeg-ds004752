# Colab and Google Drive deployment plan

## Goal

Run the V5.5 ds004752 pipeline from GitHub code while storing data,
artifacts, cache, and checkpoints on Google Drive.

## Repository responsibilities

- Source code under `src/`.
- Governance and runtime configs under `configs/`.
- Colab/bootstrap scripts under `bootstrap/`.
- Notebook orchestration under `notebooks/`.
- Tests under `tests/`.
- Scientific and implementation docs under `docs/`.

The repo must not track raw EDF/MAT payloads or runtime artifacts.

## Drive layout

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

## Standard Colab sequence

```python
from google.colab import drive
drive.mount('/content/drive')
```

```bash
cd /content
git clone https://github.com/BrianNguyen29/eeg-ds004752.git
cd eeg-ds004752
bash bootstrap/install_runtime.sh
python bootstrap/colab_quickstart.py
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data metadata
python -m unittest discover -s tests
python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml
```

## Data materialization modes

- `metadata`: install DataLad working tree only; EDF/MAT remain pointers.
- `sample`: download `sub-01/ses-01` EEG/iEEG and subject beamforming file.
- `all`: download the full dataset; use only when Drive space and runtime are adequate.

## Current blockers

- Signal-level audit requires materialized EDF payloads.
- Beamforming/bridge audit requires materialized MAT derivatives.
- `cohort_lock.json` remains draft until signal-level audit passes.
- Real-data phases are intentionally blocked until Gate 2.5 preregistration lock.

## Next implementation tranche

1. Add signal-level audit using optional `mne`.
2. Add MAT derivative audit using optional `scipy`.
3. Promote Gate 0 from metadata-only to signal-level-ready when payloads exist.
4. Implement Gate 1 decision simulation and SESOI registry.
5. Implement Gate 2 synthetic recovery and threshold registry.
