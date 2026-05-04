# V5.6 Tranche 2.3 Feature Matrix Leakage Audit Plan Runbook

Ngay cap nhat: 2026-05-04

Pham vi: ghi leakage-audit plan artifact sau khi Tranche 2.2 feature matrix
plan pass. Tai lieu nay khong materialize feature values, khong audit runtime
comparator logs, khong train model, khong chay comparator, khong tinh efficacy
metric, va khong mo claim.

## 1. Source of Truth

Required upstream artifacts:

- Gate 0: `artifacts/gate0/20260424T100159866284Z`
- Split lock: `artifacts/v56_split_registry_lock/latest.txt`
- Feature provenance: `artifacts/v56_feature_provenance_populated/latest.txt`
- Feature matrix plan: `artifacts/v56_feature_matrix_plan/latest.txt`

Code/config source:

- `configs/v56/feature_matrix_leakage_audit_plan.json`
- `src/v56/feature_matrix_leakage_audit_plan.py`
- `src/cli.py`
- `bootstrap/run_v56_feature_matrix_leakage_plan.sh`

## 2. Integrity Boundary

Tranche 2.3 duoc phep:

- xac nhan upstream Tranche 2.1/2.2 da pass;
- record leakage-audit requirements;
- verify planned fit-scope policy;
- verify test-time scalp-only policy;
- verify privileged sources remain train-time-only;
- giu claim-closed.

Tranche 2.3 khong duoc:

- materialize feature matrix;
- doc EDF de tinh feature values;
- audit runtime comparator logs;
- train RIFT-Net Lite;
- train A3/A4;
- chay comparator execution;
- tinh BA/CI/p-value/CRTG;
- mo efficacy claim.

## 3. Lenh Chay Tren Colab

Tu repo root `/content/eeg-ds004752`:

```bash
bash bootstrap/run_v56_feature_matrix_leakage_plan.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_leakage_audit_plan
```

## 4. Expected Outputs

Output root:

- `artifacts/v56_feature_matrix_leakage_audit_plan/<run_id>`

Required files:

- `v56_feature_matrix_leakage_audit_plan.json`
- `v56_feature_matrix_leakage_audit_plan_summary.json`
- `v56_feature_matrix_leakage_audit_plan_validation.json`
- `v56_feature_matrix_leakage_audit_plan_report.md`
- `latest.txt` tai artifact root

Expected statuses:

- `status = planned_feature_matrix_leakage_audit_recorded`
- `validation_status = v56_feature_matrix_leakage_audit_plan_validation_passed`
- `claim_closed = true`
- `claim_ready = false`
- `feature_matrix_materialized = false`
- `runtime_comparator_logs_audited = false`
- `model_training_run = false`
- `efficacy_metrics_computed = false`

## 5. Review Checklist

Policy:

- outer-test subject not in train subjects for every locked fold;
- test-time inference remains scalp EEG only;
- iEEG and beamforming bridge forbidden at test time;
- privileged sources remain train-time only;
- runtime comparator log audit explicitly deferred.

Claim boundary:

- no feature values;
- no logits;
- no model outputs;
- no metrics;
- no claim opened.

## 6. Decision Gate

Neu leakage-audit plan pass:

- co the implement feature matrix materializer skeleton;
- materializer dau tien nen materialize scalp EEG features only;
- van khong train model hoac chay comparator.

Neu leakage-audit plan fail:

- sua config/plan;
- rerun `v56-feature-matrix-leakage-plan`;
- khong materialize feature matrix.

## 7. Next Recommendation

Sau Tranche 2.3 pass, buoc code tiep theo la Tranche 2.4 theo
`docs/26_v56_feature_matrix_materializer_skeleton_runbook_2026-05-04.md`:

1. `v56_feature_matrix_materializer_skeleton`
   - record materializer contract;
   - record future output files va validation rules;
   - khong doc EDF;
   - khong write feature values.

2. `v56_feature_matrix_leakage_audit_runtime_placeholder`
  - chi audit runtime logs sau khi comparator execution ton tai;
  - khong tao positive claim tu materializer.

Lenh Tranche 2.4 khuyen nghi:

```bash
bash bootstrap/run_v56_feature_matrix_materializer_skeleton.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_leakage_audit_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_materializer_skeleton
```
