# Colab and local runbook

Ngay khoa: 2026-04-19

Muc tieu: chay pipeline theo dung thu tu governance V5.5, khong mo real-data substantive phase truoc khi Gate 2.5 prereg bundle hop le.

## Local setup

Use the bundled Python in this desktop workspace, or any Python 3.10+ environment:

```powershell
& "C:\Users\Duong Nguyen\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" -m unittest discover -s tests
```

Expected baseline after the current fix:

```text
Ran 44 tests
OK
```

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

## Current local status

The local `ds004752` tree currently supports metadata-level Gate 0 only:

- 15 subjects.
- 68 sessions.
- 3353 EEG event trials and 3353 iEEG event trials.
- 0 EEG/iEEG core event mismatches.
- 136 EDF files are pointer-like.
- 15 MAT files are pointer-like.

Therefore local Gate 1 is expected to reject the latest local Gate 0 run until payloads are materialized and full signal audit passes.
