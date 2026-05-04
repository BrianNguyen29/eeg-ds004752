# V5.6 Tranche 2.1 Split Lock and Feature Provenance Runbook

Ngay cap nhat: 2026-05-04

Pham vi: khoa subject-level split registry va populate feature provenance sau
khi `notebooks/41_colab_v56_tranche2_scaffold.ipynb` da ghi dung scaffold
artifacts. Tai lieu nay khong mo claim, khong materialize feature matrix,
khong train model, khong tinh efficacy metric.

## 1. Source of Truth

Gate 0 authoritative run:

- `artifacts/gate0/20260424T100159866284Z`

Tranche 2 scaffold inputs:

- `artifacts/v56_split_registry/latest.txt`
- `artifacts/v56_feature_provenance/latest.txt`

Code/config source:

- `configs/v56/benchmark_spec.json`
- `configs/v56/splits.json`
- `src/v56/tranche2_lock.py`
- `src/cli.py`
- `bootstrap/run_v56_tranche2_lock.sh`

## 2. Integrity Boundary

Tranche 2.1 duoc phep:

- doc Gate 0 signal-ready run;
- doc scaffold split registry va feature provenance artifacts;
- khoa subject-level split folds;
- enforce subject isolation;
- enforce scalp-only test-time inference;
- hash/link source config va scaffold artifacts;
- giu `claim_closed`.

Tranche 2.1 khong duoc:

- extract feature matrix;
- train RIFT-Net Lite;
- train A3/A4;
- chay comparator execution;
- tinh BA/CI/p-value/CRTG;
- mo efficacy claim;
- dung V5.5 negative finding lam positive evidence.

## 3. Lenh Chay Tren Colab

Tu repo root `/content/eeg-ds004752`:

```bash
bash bootstrap/run_v56_tranche2_lock.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts
```

CLI tuong duong:

```bash
python -m src.cli v56-tranche2-lock \
  --gate0-run /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  --split-registry-run /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry/latest.txt \
  --feature-provenance-run /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance/latest.txt \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --splits configs/v56/splits.json \
  --output-root /content/drive/MyDrive/eeg-ds004752/artifacts
```

## 4. Expected Outputs

CLI se ghi:

- `artifacts/v56_split_registry_lock/<run_id>`
- `artifacts/v56_feature_provenance_populated/<run_id>`
- `artifacts/v56_tranche2_lock_latest_summary.json`

Split lock run phai co:

- `v56_split_registry_lock.json`
- `v56_split_registry_lock_summary.json`
- `v56_split_registry_lock_report.md`
- `latest.txt` tai artifact root

Feature provenance run phai co:

- `v56_feature_provenance_populated.json`
- `v56_feature_provenance_populated_summary.json`
- `v56_feature_provenance_populated_report.md`
- `latest.txt` tai artifact root

## 5. Review Checklist

Split registry lock:

- `status = locked_subject_level_split_registry`
- `claim_closed = true`
- `subject_isolation_enforced = true`
- `test_time_inference.modality = scalp_eeg_only`
- `test_time_inference.allow_ieeg = false`
- `test_time_inference.allow_beamforming_bridge = false`
- moi fold co outer test subject khong nam trong train subjects

Feature provenance:

- `status = populated_source_hashes_and_split_links`
- `claim_closed = true`
- `required_links_satisfied.split_registry = true`
- `required_links_satisfied.source_hashes = true`
- `required_links_satisfied.manifest = true`
- `feature_matrix_materialized = false`
- `model_training_run = false`
- `efficacy_metrics_computed = false`

## 6. Decision Gate

Neu ca hai artifact pass checklist:

- ghi nhan Tranche 2.1 da hoan tat;
- co the mo buoc planning cho feature matrix/baseline execution;
- van chua mo model efficacy claim.

Neu co mismatch:

- sua registry/provenance writer hoac config;
- rerun `v56-tranche2-lock`;
- khong chay feature extraction, comparator, hoac model.

## 7. Next Recommendation

Sau Tranche 2.1 pass, buoc tiep theo la Tranche 2.2 theo
`docs/24_v56_feature_matrix_plan_runbook_2026-05-04.md`:

1. `v56_feature_matrix_plan`
   - record feature-matrix contract;
   - tach scalp-only test-time feature sets va privileged train-time sources;
   - khong materialize feature values;
   - khong train RIFT-Net Lite.

2. `v56_baseline_leaderboard_plan`
   - chi mo sau khi feature matrix provenance pass;
   - bat dau bang baseline scalp-only/strong classical comparators;
   - control registry van claim-blocking.

RIFT-Net Lite va A4 privileged execution chi nen mo sau khi baseline/control
surface da co artifact contract ro rang.

Lenh Tranche 2.2 khuyen nghi:

```bash
bash bootstrap/run_v56_feature_matrix_plan.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan
```
