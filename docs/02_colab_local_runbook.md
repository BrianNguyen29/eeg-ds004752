# Colab and local runbook

Ngay khoa: 2026-04-19

Muc tieu: chay pipeline theo dung thu tu governance V5.5, khong mo real-data substantive phase truoc khi Gate 2.5 prereg bundle hop le.

## Local setup

Use the bundled Python in this desktop workspace, or any Python 3.10+ environment:

```powershell
& "C:\Users\Duong Nguyen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests
```

Expected baseline after the current fix: `python -m unittest discover -s tests` exits with `OK`. The exact test count is allowed to increase as new governance packages are added.

Optional signal dependencies are needed only for EDF/MAT signal-level workflows:

```bash
INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh
```

## Colab setup

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
python -m unittest discover -s tests
```

Supported Drive layouts:

```text
/content/drive/MyDrive/eeg-ds004752/
  data/ds004752/
  artifacts/
  cache/
  checkpoints/
```

or:

```text
/content/drive/MyDrive/eeg/eeg-ds004752/
  data/ds004752/
  artifacts/
  cache/
  checkpoints/
```

Use `configs/data/snapshot_colab.yaml` for the first layout and `configs/data/snapshot_colab_nested.yaml` for the nested layout.

## Data materialization

Metadata-only bootstrap:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data metadata
```

Sample payload bootstrap:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data sample
```

Subject payload bootstrap:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data subjects sub-01 sub-02
```

Full payload bootstrap should only be used when Drive space and runtime are adequate:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data all
```

## Gate 0

Metadata-level audit:

```bash
python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml
```

Local equivalent:

```powershell
python -m src.cli audit --profile t4_safe --config configs/data/snapshot.yaml
```

Signal-level audit is allowed only after EDF/MAT payloads are materialized and signal extras are installed:

```bash
INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh
python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml --include-signal --signal-max-sessions 1
```

Do not treat `cohort_lock.json` as primary-ready unless `manifest_status` and `cohort_lock_status` are signal-audit ready and `gate0_blockers` is empty.

## Gate 1

Gate 1 must read a full signal-ready Gate 0 run:

```bash
python -m src.cli gate1 \
  --profile t4_safe \
  --gate0-run artifacts/gate0/<gate0_run> \
  --config configs/gate1/decision_simulation.json \
  --output-root artifacts/gate1
```

Expected output family:

- `gate1_inputs.json`
- `gate1_input_integrity.json`
- `n_eff_statement.json`
- `simulation_registry.json`
- `sesoi_registry.json`
- `influence_rule.json`
- `decision_memo.md`
- `gate1_summary.json`

Gate 1 must fail if Gate 0 is metadata-only, filtered signal-only, pointer-backed, or has blockers.

## Gate 2

Gate 2 must read a ready Gate 1 run:

```bash
python -m src.cli gate2 \
  --profile t4_safe \
  --gate1-run artifacts/gate1/<gate1_run> \
  --config configs/gate2/synthetic_validation.json \
  --output-root artifacts/gate2
```

Expected output family:

- `synthetic_generator_spec.json`
- `synthetic_recovery_report.json`
- `synthetic_recovery_report.md`
- `gate_threshold_registry.json`
- `gate2_summary.json`

Gate 2 does not authorize real-data phases. Its threshold registry is necessary input for Gate 2.5.

## Gate 2.5

Gate 2.5 must read a passed Gate 2 run:

```bash
python -m src.cli gate25 \
  --profile t4_safe \
  --gate2-run artifacts/gate2/<gate2_run> \
  --config configs/prereg/prereg_assembly.json \
  --output-root artifacts/prereg
```

Expected output family:

- `prereg_bundle.json`
- `environment_lock.json`
- `prereg_validation_report.md`
- `revision_policy.md`
- comparator cards
- `gate25_summary.json`

The prereg bundle must have `status: locked` and non-empty `artifact_hashes`.

## Phase 0.5 and Phase 1

Phase 0.5 observability preflight:

```bash
python -m src.cli phase05_real \
  --profile a100_fast \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --phase-config configs/phase05/observability.json \
  --output-root artifacts/phase05
```

Phase 0.5 estimators:

```bash
python -m src.cli phase05_estimators \
  --profile t4_safe \
  --prereg-bundle artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --phase05-run artifacts/phase05/<phase05_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --config configs/phase05/estimators.json \
  --output-root artifacts/phase05_estimators
```

Phase 1 smoke contract:

```bash
python -m src.cli phase1_real \
  --profile a100_fast \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --smoke \
  --max-outer-folds 2
```

Final reporting package after comparator/governance reconciliation:

```bash
python -m src.cli phase1_final_reporting \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --governance-reconciliation-run artifacts/phase1_final_governance_reconciliation/<governance_run> \
  --output-root artifacts/phase1_final_reporting \
  --reporting-config configs/phase1/final_reporting.json \
  --governance-config configs/phase1/final_governance_reconciliation.json
```

This command only assembles the reporting package and closed claim table from existing governance artifacts. It must preserve any controls, calibration or influence blockers and must not be interpreted as Phase 1 efficacy evidence.

Phase 1 A2/A2b model smoke:

```bash
python -m src.cli phase1_real \
  --profile a100_fast \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --model-smoke \
  --phase-config configs/phase1/model_smoke.json \
  --comparators A2 A2b \
  --max-outer-folds 2
```

Phase 1 A2d Riemannian smoke:

```bash
python -m src.cli phase1_real \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --a2d-smoke \
  --phase-config configs/phase1/a2d_smoke.json \
  --max-outer-folds 2
```

A2d smoke is non-claim. It validates covariance extraction, training-only tangent reference fitting, split isolation and artifact writing. It is not the final A2d comparator estimate.

Phase 1 A2c CORAL smoke:

```bash
python -m src.cli phase1_real \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --a2c-smoke \
  --phase-config configs/phase1/a2c_smoke.json \
  --max-outer-folds 2
```

A2c smoke is non-claim. It validates scalp feature extraction, training-only normalization, training-domain CORAL covariance diagnostics, fixed smoke beta handling, split isolation and artifact writing. It is not the final neural CORAL comparator estimate.

Phase 1 comparator-suite gap review after A2/A2b, A2c and A2d smoke reviews:

```bash
python -m src.cli phase1_gap_review \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --output-root artifacts/phase1_gap_review \
  --a2-a2b-run artifacts/phase1_model_smoke/<a2_a2b_run> \
  --a2c-run artifacts/phase1_a2c_smoke/<a2c_run> \
  --a2d-run artifacts/phase1_a2d_smoke/<a2d_run>
```

Gap review is non-claim. It does not train models; it records remaining A3/A4/final-control/calibration/influence/reporting blockers before any claim-bearing Phase 1 run can be considered.

Phase 1 A3 distillation smoke:

```bash
python -m src.cli phase1_real \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --a3-smoke \
  --phase-config configs/phase1/a3_smoke.json \
  --max-outer-folds 2
```

A3 smoke is non-claim. It validates scalp feature extraction, training-only normalization, training-only teacher proxy fitting, teacher-output generation for training rows only, student distillation fitting, split isolation and artifact writing. The smoke teacher is an internal scalp-feature proxy, not a final iEEG teacher and not privileged-transfer evidence.

Phase 1 A4 privileged train-time-only smoke:

```bash
python -m src.cli phase1_real \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --dataset-root /content/drive/MyDrive/eeg-ds004752/data/ds004752 \
  --a4-smoke \
  --phase-config configs/phase1/a4_smoke.json \
  --max-outer-folds 2
```

A4 smoke is non-claim. It validates scalp feature extraction, training-only normalization, training-only gate/weight fitting, training-only privileged proxy fitting, privileged-output generation for training rows only, student fitting, scalp-only inference, split isolation and artifact writing. The smoke privileged path is an internal proxy, not final iEEG privileged evidence and not privileged-transfer efficacy evidence.

Phase 1 post-A4 gap review after A3/A4 smoke review notes exist:

```bash
python -m src.cli phase1_gap_review \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --readiness-run artifacts/phase1_readiness/<readiness_run> \
  --output-root artifacts/phase1_gap_review \
  --a2-a2b-run artifacts/phase1_model_smoke/<a2_a2b_run> \
  --a2c-run artifacts/phase1_a2c_smoke/<a2c_run> \
  --a2d-run artifacts/phase1_a2d_smoke/<a2d_run> \
  --a3-run artifacts/phase1_a3_smoke/<a3_run> \
  --a4-run artifacts/phase1_a4_smoke/<a4_run>
```

Post-A4 gap review is still non-claim. It records A2/A2b, A2c, A2d, A3 and A4 as completed non-claim smoke reviews, while keeping `claim_ready=false` until final comparator readiness, executable controls, calibration, influence and reporting are complete.

Phase 1 governance readiness after post-A4 gap review:

```bash
python -m src.cli phase1_governance_readiness \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --gap-review-run artifacts/phase1_gap_review/<post_a4_gap_review_run> \
  --output-root artifacts/phase1_governance_readiness
```

Governance readiness is non-claim. It aggregates the post-A4 gap review with control-suite, calibration, influence and reporting readiness surfaces. It must remain fail-closed while final control results, final calibration artifacts, final influence artifacts and final reporting artifacts are missing.

Phase 1 final claim-package plan after governance readiness:

```bash
python -m src.cli phase1_final_claim_package_plan \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --governance-run artifacts/phase1_governance_readiness/<governance_run> \
  --output-root artifacts/phase1_final_claim_package_plan \
  --package-config configs/phase1/final_claim_package.json
```

Final claim-package planning is non-claim. It records the machine-readable contract for final comparator, control, calibration, influence and reporting artifacts. It must not be interpreted as evidence and must keep `claim_ready=false` until the final package is implemented and passes locked rules.

Phase 1 final comparator artifact plan after final claim-package planning:

```bash
python -m src.cli phase1_final_comparator_artifact_plan \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --claim-package-run artifacts/phase1_final_claim_package_plan/<claim_package_plan_run> \
  --output-root artifacts/phase1_final_comparator_artifact_plan \
  --artifact-config configs/phase1/final_comparator_artifacts.json \
  --claim-package-config configs/phase1/final_claim_package.json
```

Final comparator artifact planning is non-claim. It records the required fold log, metric, logit, split, feature and leakage-audit schema for A2/A2b/A2c/A2d/A3/A4. Smoke outputs must remain non-evidentiary and cannot satisfy this contract.

Phase 1 final split/feature/leakage readiness after final comparator artifact planning:

```bash
python -m src.cli phase1_final_split_feature_leakage_plan \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --comparator-artifact-run artifacts/phase1_final_comparator_artifact_plan/<comparator_artifact_plan_run> \
  --output-root artifacts/phase1_final_split_feature_leakage_plan \
  --readiness-config configs/phase1/final_split_feature_leakage.json \
  --artifact-config configs/phase1/final_comparator_artifacts.json
```

Final split/feature/leakage readiness is non-claim. It records the LOSO split, feature provenance and leakage-audit manifest contract required before final comparator runners. It does not create final folds, extract final features or run leakage audits.

Phase 1 final LOSO split manifest after split/feature/leakage readiness:

```bash
python -m src.cli phase1_final_split_manifest \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --split-feature-leakage-run artifacts/phase1_final_split_feature_leakage_plan/<split_feature_leakage_plan_run> \
  --gate0-run artifacts/gate0/<gate0_signal_ready_run> \
  --output-root artifacts/phase1_final_split_manifest \
  --manifest-config configs/phase1/final_split_manifest.json \
  --readiness-config configs/phase1/final_split_feature_leakage.json
```

The final split manifest runner is fail-closed. It writes `final_split_manifest.json` only when Gate 0 `manifest_status` and `cohort_lock_status` are both `signal_audit_ready`, Gate 0 blockers are empty, and primary eligible subjects are explicit. If those conditions are not met, it writes `phase1_final_split_manifest_blocked.json` and must not be used by final comparator runners.

Phase 1 final feature schema/provenance manifest after final LOSO split manifest:

```bash
python -m src.cli phase1_final_feature_manifest \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --final-split-run artifacts/phase1_final_split_manifest/<final_split_manifest_run> \
  --dataset-root data/ds004752 \
  --output-root artifacts/phase1_final_feature_manifest \
  --feature-config configs/phase1/final_feature_manifest.json \
  --readiness-config configs/phase1/final_split_feature_leakage.json
```

The final feature manifest runner is non-claim and fail-closed. It records feature schema/provenance only: feature set ID, scalp channel/band feature names, task window, trial filter, dataset sidecar/event inventory and source hashes. It does not write feature matrices, train comparators, compute metrics or run leakage audits. If split, Gate 0, materialization or dataset sidecar prerequisites are missing, it writes `phase1_final_feature_manifest_blocked.json`.

Phase 1 final manifest-level leakage audit after final split and feature manifests:

```bash
python -m src.cli phase1_final_leakage_audit \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --final-split-run artifacts/phase1_final_split_manifest/<final_split_manifest_run> \
  --final-feature-run artifacts/phase1_final_feature_manifest/<final_feature_manifest_run> \
  --output-root artifacts/phase1_final_leakage_audit \
  --audit-config configs/phase1/final_leakage_audit.json \
  --readiness-config configs/phase1/final_split_feature_leakage.json
```

The final leakage audit runner is non-claim and manifest-level. It records fit and transform subjects for preprocessing, normalization, alignment, teacher, privileged, gate/weight and calibration stages for every LOSO fold. It must show that the outer-test subject is not in any fit scope and that test-time privileged/teacher outputs are disallowed. It does not audit final comparator runtime logs, because final comparator runners have not executed yet.

Phase 1 final comparator runner/output-manifest readiness after final split, feature and manifest-level leakage artifacts:

```bash
python -m src.cli phase1_final_comparator_runner_readiness \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --final-split-run artifacts/phase1_final_split_manifest/<final_split_manifest_run> \
  --final-feature-run artifacts/phase1_final_feature_manifest/<final_feature_manifest_run> \
  --final-leakage-run artifacts/phase1_final_leakage_audit/<final_leakage_audit_run> \
  --output-root artifacts/phase1_final_comparator_runner_readiness \
  --runner-config configs/phase1/final_comparator_runner_readiness.json \
  --artifact-config configs/phase1/final_comparator_artifacts.json
```

The final comparator runner readiness package is non-claim. It links reviewed final split, feature and manifest-level leakage artifacts to the required output contract for A2/A2b/A2c/A2d/A3/A4, then records final fold logs, logits, subject-level metrics, runtime leakage logs and comparator output manifests as missing. It must not be interpreted as model evidence, and it must not feed controls, calibration, influence or reporting until final comparator runners write real outputs and runtime leakage logs.

Phase 1 final feature matrix materialization after final comparator runner readiness:

```bash
python -m src.cli phase1_final_feature_matrix \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --final-split-run artifacts/phase1_final_split_manifest/<final_split_manifest_run> \
  --final-feature-run artifacts/phase1_final_feature_manifest/<final_feature_manifest_run> \
  --final-leakage-run artifacts/phase1_final_leakage_audit/<final_leakage_audit_run> \
  --runner-readiness-run artifacts/phase1_final_comparator_runner_readiness/<runner_readiness_run> \
  --dataset-root data/ds004752 \
  --output-root artifacts/phase1_final_feature_matrix \
  --matrix-config configs/phase1/final_feature_matrix.json
```

The final feature matrix materializer is non-claim and fail-closed. It requires signal extras and real EDF payloads. It writes `final_feature_matrix.csv` only when the extracted row count matches the final feature manifest, feature names match the reviewed schema, every feature value is finite, and no source session is skipped. The matrix contains row identity, labels and scalp EEG feature values only; it must not contain logits, metrics, model outputs, controls, calibration, influence or runtime leakage logs.

Phase 1 final comparator runner after final feature matrix materialization:

```bash
python -m src.cli phase1_final_comparator_runner \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --feature-matrix-run artifacts/phase1_final_feature_matrix/<feature_matrix_run> \
  --runner-readiness-run artifacts/phase1_final_comparator_runner_readiness/<runner_readiness_run> \
  --output-root artifacts/phase1_final_comparator_runner \
  --runner-config configs/phase1/final_comparator_runner.json
```

The final comparator runner is claim-closed. It consumes `final_feature_matrix.csv` and writes comparator logits, subject-level metrics, output manifests and runtime leakage logs for comparator implementations that are valid from that matrix. It must not promote smoke artifacts. A2d Riemannian must remain blocked unless a valid final covariance/tangent input path exists; the runner must not approximate A2d from bandpower features.

Phase 1 final A2d covariance/tangent runner after the feature-matrix comparator runner records the A2d blocker:

```bash
python -m src.cli phase1_final_a2d_runner \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --final-split-run artifacts/phase1_final_split_manifest/<final_split_manifest_run> \
  --final-feature-run artifacts/phase1_final_feature_manifest/<final_feature_manifest_run> \
  --final-leakage-run artifacts/phase1_final_leakage_audit/<final_leakage_audit_run> \
  --feature-matrix-run artifacts/phase1_final_feature_matrix/<feature_matrix_run> \
  --feature-matrix-comparator-run artifacts/phase1_final_comparator_runner/<feature_matrix_comparator_run> \
  --dataset-root data/ds004752 \
  --output-root artifacts/phase1_final_a2d_runner \
  --runner-config configs/phase1/final_a2d_runner.json
```

The final A2d runner is claim-closed. It uses the final feature matrix row index as row/provenance contract but extracts covariance matrices directly from EDF payloads, fits the log-Euclidean reference and tangent projection on training subjects only per LOSO fold, and writes A2d logits, subject-level diagnostics, output manifest and runtime leakage log. It can resolve the A2d missing-output engineering blocker for downstream reconciliation, but it does not make A2d or Phase 1 claim-evaluable without controls, calibration, influence and reporting.

Phase 1 final comparator reconciliation after both final comparator runners exist:

```bash
python -m src.cli phase1_final_comparator_reconciliation \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --feature-matrix-comparator-run artifacts/phase1_final_comparator_runner/<feature_matrix_comparator_run> \
  --final-a2d-run artifacts/phase1_final_a2d_runner/<final_a2d_run> \
  --output-root artifacts/phase1_final_comparator_reconciliation \
  --reconciliation-config configs/phase1/final_comparator_reconciliation.json
```

The final comparator reconciliation package is claim-closed. It links the feature-matrix comparator outputs with the final A2d covariance/tangent outputs, verifies all six comparator manifests/logits/subject metrics/runtime leakage logs are present, and records whether the A2d missing-output blocker is cleared at artifact level. It must not rerun models, edit logits, recompute metrics, fabricate missing files or open claims. Downstream controls, calibration, influence and reporting remain required before any headline Phase 1 claim can be evaluated.

Phase 1 final controls package after final comparator reconciliation:

```bash
python -m src.cli phase1_final_controls \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --comparator-reconciliation-run artifacts/phase1_final_comparator_reconciliation/<comparator_reconciliation_run> \
  --output-root artifacts/phase1_final_controls \
  --controls-config configs/phase1/final_controls.json \
  --control-suite-config configs/controls/control_suite_spec.yaml \
  --gate2-config configs/gate2/synthetic_validation.json
```

The final controls package is claim-closed and fail-closed. It may compute only controls that are technically valid from final comparator logits, currently A2 scalp baseline diagnostics, grouped label-rotation diagnostics, shuffled-label logit diagnostics and transfer-consistency row-alignment checks. It must not infer nuisance, spatial, shuffled-teacher or time-shifted-teacher controls from logits; those require dedicated final control reruns and remain blockers until real artifacts exist. A blocked final controls manifest is an honest result when dedicated controls are still missing.

Phase 1 final calibration package after final comparator reconciliation:

```bash
python -m src.cli phase1_final_calibration \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --comparator-reconciliation-run artifacts/phase1_final_comparator_reconciliation/<comparator_reconciliation_run> \
  --output-root artifacts/phase1_final_calibration \
  --calibration-config configs/phase1/final_calibration.json \
  --metrics-config configs/eval/metrics.yaml \
  --inference-config configs/eval/inference_defaults.yaml \
  --gate1-config configs/gate1/decision_simulation.json
```

The final calibration package is claim-closed. It computes pooled ECE, subject-level ECE, Brier score, negative log-likelihood, reliability-table/diagram data, risk-coverage curves and delta ECE versus the locked baseline from final comparator logits only. It must not recalibrate predictions, retrain comparators, edit logits, fabricate diagrams or promote smoke calibration diagnostics. If the locked delta-ECE threshold fails, the correct result is a blocked final calibration manifest.

Phase 1 final influence package after final comparator reconciliation:

```bash
python -m src.cli phase1_final_influence \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --comparator-reconciliation-run artifacts/phase1_final_comparator_reconciliation/<comparator_reconciliation_run> \
  --output-root artifacts/phase1_final_influence \
  --influence-config configs/phase1/final_influence.json \
  --gate1-config configs/gate1/decision_simulation.json \
  --gate2-config configs/gate2/synthetic_validation.json
```

The final influence package is claim-closed. It computes subject-level balanced-accuracy diagnostics, leave-one-subject-out delta shifts, and single-subject contribution shares from final comparator logits only. It must not retrain comparators, edit logits, fabricate leave-one-subject-out checks, or promote smoke influence diagnostics. If a single subject exceeds the locked influence ceiling, the correct result is a blocked final influence manifest.

Phase 1 final governance reconciliation after final comparator reconciliation:

```bash
python -m src.cli phase1_final_governance_reconciliation \
  --profile t4_safe \
  --config artifacts/prereg/<prereg_run>/prereg_bundle.json \
  --comparator-reconciliation-run artifacts/phase1_final_comparator_reconciliation/<comparator_reconciliation_run> \
  --output-root artifacts/phase1_final_governance_reconciliation \
  --governance-config configs/phase1/final_governance_reconciliation.json
```

Optional final governance manifests can be supplied only when they exist:

```bash
  --final-control-manifest artifacts/phase1_final_controls/<run>/final_control_manifest.json \
  --final-calibration-manifest artifacts/phase1_final_calibration/<run>/final_calibration_manifest.json \
  --final-influence-manifest artifacts/phase1_final_influence/<run>/final_influence_manifest.json \
  --final-reporting-manifest artifacts/phase1_final_reporting/<run>/final_reporting_manifest.json
```

The final governance reconciliation package is claim-closed. It verifies that comparator reconciliation is complete, then checks whether final controls, calibration, influence and reporting manifests exist and satisfy the required artifact lists. If those manifests are absent, the correct result is blocked/non-claim; the runner must not fabricate governance evidence from comparator metrics or smoke artifacts.

## Conditions for opening real phases

Real phases may be opened only when all conditions are true:

- Gate 0 is full signal-audit ready.
- EDF/MAT payloads are materialized for the required scope.
- Gate 0 blockers are empty.
- Gate 1 decision layer completed from the full Gate 0 source of truth.
- Gate 2 synthetic validation passed and threshold registry is locked.
- Gate 2.5 prereg bundle has `status: locked`.
- The real phase command uses that exact locked prereg bundle.
- Any post-prereg claim-affecting change has a revision log and is refrozen/rerun or demoted to post-hoc.
- Phase 1 headline claims additionally require final comparator readiness plus executable controls, calibration, influence and reporting artifacts that pass the locked thresholds.
- The final claim-package plan must be reviewed as a contract before any claim-bearing runner is implemented.
- Final comparator artifact manifests must exist before controls, calibration, influence or final reporting can be claim-evaluable.
- Final split, feature and leakage-audit manifests must exist before final comparator outputs can be claim-evaluable.
- Final comparator runner/output-manifest readiness must be reviewed before final comparator runner implementation, but it does not make comparator outputs claim-evaluable.
- The final feature matrix may be used as final comparator runner input only after materialization validation passes; by itself it is not model evidence and does not open claims.
- Final comparator runner outputs may feed downstream controls/calibration/influence/reporting only after runtime leakage logs are reviewed; partial output packages with blocked comparators remain non-claim.
- Final A2d covariance/tangent outputs may clear the A2d missing-output blocker only after their runtime leakage log passes and downstream comparator-package reconciliation links the A2d run with the feature-matrix comparator run.
- Final comparator reconciliation may mark all six comparator output manifests present, but it remains non-claim until controls, calibration, influence and reporting are implemented, reconciled and pass the locked governance thresholds.
- Final controls may use final logits for logit-level diagnostics only. Dedicated nuisance, spatial, shuffled-teacher and time-shifted-teacher reruns cannot be fabricated or inferred from logits and must remain blockers until executed.
- Final calibration may compute calibration diagnostics from final logits, but it cannot modify predictions or convert calibration pass/fail into decoder efficacy evidence.
- Final influence may compute leave-one-subject-out diagnostics from final logits, but it cannot convert influence pass/fail into decoder efficacy evidence.
- Final governance reconciliation may record governance surfaces as ready for review only when final controls, calibration, influence and reporting manifests exist. It still must not open headline claims by itself.

## Current local status

The local `ds004752` tree currently supports metadata-level Gate 0 only:

- 15 subjects.
- 68 sessions.
- 3353 EEG event trials and 3353 iEEG event trials.
- 0 EEG/iEEG core event mismatches.
- 136 EDF files are pointer-like.
- 15 MAT files are pointer-like.

Therefore local Gate 1 is expected to reject the latest local Gate 0 run until payloads are materialized and full signal audit passes.
