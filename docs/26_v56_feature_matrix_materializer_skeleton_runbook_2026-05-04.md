# V5.6 Tranche 2.4 Feature Matrix Materializer Skeleton Runbook

Ngay cap nhat: 2026-05-04

Pham vi: ghi materializer skeleton artifact sau khi Tranche 2.3 leakage-audit
plan pass. Tai lieu nay khong doc EDF, khong materialize feature values, khong
train model, khong chay comparator, khong tinh efficacy metric, va khong mo
claim.

## 1. Source of Truth

Required upstream artifacts:

- Gate 0: `artifacts/gate0/20260424T100159866284Z`
- Split lock: `artifacts/v56_split_registry_lock/latest.txt`
- Feature provenance: `artifacts/v56_feature_provenance_populated/latest.txt`
- Feature matrix plan: `artifacts/v56_feature_matrix_plan/latest.txt`
- Leakage-audit plan: `artifacts/v56_feature_matrix_leakage_audit_plan/latest.txt`

Code/config source:

- `configs/v56/feature_matrix_materializer_skeleton.json`
- `src/v56/feature_matrix_materializer_skeleton.py`
- `src/cli.py`
- `bootstrap/run_v56_feature_matrix_materializer_skeleton.sh`

## 2. Integrity Boundary

Tranche 2.4 duoc phep:

- xac nhan upstream Tranche 2.1/2.2/2.3 da pass;
- record materializer contract;
- record future output schema expectations;
- verify no EDF read/write is performed now;
- giu claim-closed.

Tranche 2.4 khong duoc:

- doc EDF payloads;
- write feature values;
- write `v56_feature_matrix.csv`;
- train RIFT-Net Lite;
- train A3/A4;
- chay comparator execution;
- tinh BA/CI/p-value/CRTG;
- mo efficacy claim.

## 3. Lenh Chay Tren Colab

Tu repo root `/content/eeg-ds004752`:

```bash
bash bootstrap/run_v56_feature_matrix_materializer_skeleton.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_leakage_audit_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_materializer_skeleton
```

## 4. Expected Outputs

Output root:

- `artifacts/v56_feature_matrix_materializer_skeleton/<run_id>`

Required files:

- `v56_feature_matrix_materializer_skeleton.json`
- `v56_feature_matrix_materializer_skeleton_summary.json`
- `v56_feature_matrix_materializer_skeleton_validation.json`
- `v56_feature_matrix_materializer_skeleton_report.md`
- `latest.txt` tai artifact root

Expected statuses:

- `status = planned_feature_matrix_materializer_skeleton_recorded`
- `validation_status = v56_feature_matrix_materializer_skeleton_validation_passed`
- `claim_closed = true`
- `claim_ready = false`
- `edf_payloads_read = false`
- `feature_matrix_materialized = false`
- `feature_values_written = false`
- `model_training_run = false`
- `efficacy_metrics_computed = false`

## 5. Decision Gate

Neu materializer skeleton pass:

- co the implement real scalp EEG feature matrix materializer;
- real materializer dau tien chi duoc ghi feature values, row provenance, schema,
  validation va claim-state;
- van khong train model hoac chay comparator.

Neu skeleton fail:

- sua config/runner;
- rerun `v56-feature-matrix-materializer-skeleton`;
- khong doc EDF hoac materialize feature values.

## 6. Next Recommendation

Sau Tranche 2.4 pass, buoc tiep theo la **real materializer implementation**
nhung van claim-closed:

1. doc scalp EEG EDF/events theo split lock;
2. materialize row-level scalp features only;
3. validate finite feature values va row provenance;
4. write claim blockers;
5. khong train/comparator/metric.
