# V5.6 Tranche 2.2 Feature Matrix Plan Runbook

Ngay cap nhat: 2026-05-04

Pham vi: ghi feature-matrix plan artifact sau khi Tranche 2.1 split lock va
feature provenance da pass. Tai lieu nay khong materialize feature values,
khong train model, khong chay comparator, khong tinh efficacy metric, va khong
mo claim.

## 1. Source of Truth

Required upstream artifacts:

- Gate 0: `artifacts/gate0/20260424T100159866284Z`
- Split lock: `artifacts/v56_split_registry_lock/latest.txt`
- Feature provenance: `artifacts/v56_feature_provenance_populated/latest.txt`

Code/config source:

- `configs/v56/feature_matrix_plan.json`
- `src/v56/feature_matrix_plan.py`
- `src/cli.py`
- `bootstrap/run_v56_feature_matrix_plan.sh`

## 2. Integrity Boundary

Tranche 2.2 duoc phep:

- xac nhan Gate 0 signal-ready;
- xac nhan split registry da locked;
- xac nhan feature provenance da populated va khong missing sources;
- record feature matrix plan;
- tach ro scalp-only test-time feature sets va privileged train-time sources;
- giu claim-closed.

Tranche 2.2 khong duoc:

- materialize `final_feature_matrix.csv`;
- doc EDF de tinh feature values;
- train RIFT-Net Lite;
- train A3/A4;
- chay comparator execution;
- tinh BA/CI/p-value/CRTG;
- mo efficacy claim;
- dien giai split/provenance pass thanh bang chung mo hinh hieu qua.

## 3. Lenh Chay Tren Colab

Tu repo root `/content/eeg-ds004752`:

```bash
bash bootstrap/run_v56_feature_matrix_plan.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan
```

CLI tuong duong:

```bash
python -m src.cli v56-feature-matrix-plan \
  --gate0-run /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  --split-registry-lock-run /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  --feature-provenance-run /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --feature-matrix-plan-config configs/v56/feature_matrix_plan.json \
  --output-root /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan
```

## 4. Expected Outputs

Output root:

- `artifacts/v56_feature_matrix_plan/<run_id>`

Required files:

- `v56_feature_matrix_plan.json`
- `v56_feature_matrix_plan_summary.json`
- `v56_feature_matrix_plan_validation.json`
- `v56_feature_matrix_plan_report.md`
- `latest.txt` tai artifact root

Expected statuses:

- `status = planned_feature_matrix_contract_recorded`
- `validation_status = v56_feature_matrix_plan_validation_passed`
- `claim_closed = true`
- `claim_ready = false`
- `feature_matrix_materialized = false`
- `model_training_run = false`
- `efficacy_metrics_computed = false`

## 5. Review Checklist

Test-time policy:

- `test_time_inference.modality = scalp_eeg_only`
- `allow_ieeg = false`
- `allow_beamforming_bridge = false`

Feature sets:

- primary feature sets allowed at test time must be scalp EEG only;
- iEEG/beamforming sources must remain train-time-only proposals;
- all feature sets must remain `planned_not_materialized` or
  `proposal_only_not_materialized`.

Claim boundary:

- no feature values;
- no logits;
- no model outputs;
- no metrics;
- no comparator rows leave `pending_not_run`.

## 6. Decision Gate

Neu feature matrix plan pass:

- co the implement materializer o buoc sau;
- materializer dau tien nen chi tao scalp-only baseline feature matrix;
- van can leakage audit truoc comparator execution.

Neu feature matrix plan fail:

- sua config/plan;
- rerun `v56-feature-matrix-plan`;
- khong materialize feature matrix.

## 7. Next Recommendation

Sau Tranche 2.2 pass, buoc code tiep theo la Tranche 2.3 theo
`docs/25_v56_feature_matrix_leakage_audit_plan_runbook_2026-05-04.md`:

1. `v56_feature_matrix_leakage_audit_plan`
   - verify split-lock link;
   - verify train/test fit-scope policy;
   - verify no privileged test-time inputs.

Chua nen chay RIFT-Net Lite/A4 cho den khi feature matrix va leakage audit pass.

Lenh Tranche 2.3 khuyen nghi:

```bash
bash bootstrap/run_v56_feature_matrix_leakage_plan.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_leakage_audit_plan
```
