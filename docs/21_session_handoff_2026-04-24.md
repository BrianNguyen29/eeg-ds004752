# Session Handoff - 2026-04-24

This note preserves the current working state after the V5.5 closeout and the
V5.6 transition work. It is intended as the first document to read before
continuing the next implementation session.

## Executive State

- Current branch: `main`
- Current pushed head at handoff: `5561fdd Add V5.6 scaffold artifact writers`
- Scientific state:
  - V5.5 remains `fail-closed` and `claim-closed`.
  - V5.5 does not support decoder efficacy, A3/A4 efficacy, A4 superiority, or iEEG-assisted superiority claims.
  - V5.6 has moved to a benchmark-first and control-first direction.
  - V5.6 Gate 0 has reached full-cohort `signal_audit_ready`.
  - V5.6 Tranche 2 scaffold and artifact writers are implemented.
  - No V5.6 model training, comparator execution, or efficacy claim has been implemented.

## V5.5 Locked Historical Record

The V5.5 record was closed before the V5.6 transition.

Locked interpretation:

- Status: `fail-closed`
- Claim state: `claim-closed`
- Formula contract issue: resolved
- Locked relative metric formula: `raw_ba_ratio`
- Historical blocking controls:
  - `nuisance_shared_control`
  - `spatial_control`
- Interpretation:
  - The V5.5 pipeline and governance behavior are useful methodological evidence.
  - The observed V5.5 failures are treated as a negative finding.
  - V5.5 must not be used as positive support for efficacy or iEEG-assisted superiority.

Primary V5.5 documentation chain:

- `docs/06_bao_cao_tien_do_ket_qua_va_claim_boundary_2026-04-24.md`
- `docs/07_phase1_controls_technical_conclusion_2026-04-24.md`
- `docs/08_phase1_negative_finding_report_2026-04-24.md`
- `docs/10_phase1_consistency_audit_report_2026-04-24.md`
- `docs/17_v55_to_v56_transition_lock_2026-04-24.md`
- `docs/18_v55_to_v56_transition_lock_manifest_2026-04-24.json`

Important note: these files may currently appear as deleted in the local
working tree because of unrelated local file movement. They were previously
committed to `main`. Do not treat those deletions as part of the V5.6 work
unless explicitly requested.

## V5.6 Direction

V5.6 shifts the project from a model-first A4 rescue direction to:

- benchmark-first implementation
- control-first evaluation
- claim-disciplined reporting
- scalp-only test-time inference
- privileged/iEEG information only in audited train-time paths

Main target:

- Benchmark: `NOST-Bench`
- Primary prospective target: `A4_privileged`
- Claim boundary: closed by default
- Strong rule: no efficacy claim without audited comparators, controls,
  calibration/influence/reporting, and claim-state closeout.

Primary V5.6 planning docs:

- `docs/11_phase1_prospective_ieeg_assisted_proposal_2026-04-24.md`
- `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- `docs/13_phase1_ieeg_assisted_contract_2026-04-24.md`
- `docs/14_phase1_go_no_go_decision_memo_2026-04-24.md`
- `docs/15_phase1_signal_readiness_operational_checklist_2026-04-24.md`
- `docs/16_phase1_prospective_execution_roadmap_2026-04-24.md`
- `docs/19_v56_repo_mapping_and_execution_roadmap_2026-04-24.md`
- `docs/20_v56_tranche1_signal_pilot_runbook_2026-04-24.md`

## Gate 0 Full-Cohort Signal Readiness

The data-readiness blocker was resolved during this session.

Authoritative Gate 0 run:

- Run id: `20260424T100159866284Z`
- Run root on Colab/Drive:
  - `/content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z`

Observed final report conclusion:

```text
Signal-level Gate 0 audit is complete. Payloads are materialized and the
primary cohort lock is ready.
```

Key Gate 0 state:

- `manifest_status = signal_audit_ready`
- `primary_eligibility_status = signal_audit_ready`
- `gate0_blockers = []`
- `signal_status = ok`
- `sessions_checked = 68`
- `mat_files_checked = 15`
- `cohort_lock_status = signal_audit_ready`
- `n_primary_eligible = 15`
- EDF materialization: `136 / 136`
- MAT materialization: `15 / 15`

Interpretation:

- Tranche 1 is complete.
- The data materialization blocker is closed.
- The project can move into benchmark/control-first implementation.
- This is not model efficacy evidence.

## Relevant Commits

Recent pushed commits:

- `5561fdd Add V5.6 scaffold artifact writers`
- `4f92fbb Add V5.6 Tranche 2 benchmark scaffold`
- `596167b Update V5.6 readiness docs after full-cohort Gate 0 pass`
- `b16bcc2 Update Colab Gate 0 notebook for full-cohort audit`
- `3d0a63c Fix Gate 0 reporting for materialized signal audits`
- `e5a4997 Add V5.6 transition lock and pilot runbook`
- `fd6606f Add Phase 1 prospective iEEG planning docs`
- `f2bd42c Add Phase 1 consistency audit report`
- `d252b71 Document Phase 1 fail-closed negative finding`
- `c3c8e56 Add Phase 1 controls technical conclusion docs`

## Tranche 2 Scaffold Implemented

Config files added:

- `configs/v56/benchmark_spec.json`
- `configs/v56/comparators.json`
- `configs/v56/controls.json`
- `configs/v56/splits.json`

Source modules added:

- `src/v56/__init__.py`
- `src/v56/benchmark.py`
- `src/v56/splits.py`
- `src/v56/provenance.py`
- `src/v56/controls.py`
- `src/v56/leaderboard.py`
- `src/v56/artifacts.py`

Tests added:

- `tests/unit/test_v56_scaffold.py`
- `tests/unit/test_v56_artifacts.py`

Implemented artifact writers:

- `write_split_registry_artifact`
- `write_feature_provenance_artifact`
- `write_control_registry_artifact`
- `write_leaderboard_artifact`

Artifact families now supported:

- `v56_split_registry`
- `v56_feature_provenance`
- `v56_control_registry`
- `v56_leaderboard`

Writer behavior:

- Requires Gate 0 `signal_audit_ready`.
- Requires cohort lock `signal_audit_ready`.
- Writes timestamped artifact directories.
- Writes `latest.txt` pointer.
- Writes artifact JSON, summary JSON, benchmark scaffold record, and markdown report.
- Keeps claim state closed.
- Does not train models.
- Does not compute efficacy metrics.

Verification run:

```bash
python -m unittest tests.unit.test_v56_scaffold tests.unit.test_v56_artifacts
python -m py_compile src\v56\__init__.py src\v56\benchmark.py src\v56\splits.py src\v56\provenance.py src\v56\controls.py src\v56\leaderboard.py src\v56\artifacts.py
```

Observed result:

- `Ran 10 tests ... OK`
- py_compile passed

## Colab Notebook State

Notebook:

- `notebooks/01_colab_gate0_audit.ipynb`

Purpose:

- Full-cohort Gate 0 signal audit.
- It verifies runtime patch markers, materializes full payload, runs signal audit,
  inspects artifact state, and keeps `phase1_real` guarded.

Important local note:

- A later local notebook edit fixed a Colab here-doc issue by replacing
  `!python - <<'PY' ... PY` with pure Python in the notebook cell.
- That notebook edit was not included in commit `5561fdd`.
- Check `git status --short` before deciding whether to commit the notebook.

## Current Working Tree Caution

At handoff, the local working tree had unrelated modifications and deletions.
Do not stage them unless explicitly requested.

Known unrelated local changes included:

- `M bootstrap/get_data_colab.sh`
- `M notebooks/01_colab_gate0_audit.ipynb`
- deleted historical docs under `docs/`
- untracked `docs/V5.5/`
- untracked `docs/V5.6/`
- untracked local export directory:
  - `20260423T170320725358Z-20260423T172013Z-3-001/`

Recommended staging discipline:

- Stage exact files only.
- Avoid `git add .`.
- Run `git status --short` before every commit.

## Scientific Integrity Rules Going Forward

These rules remain active:

- Do not reinterpret V5.5 negative controls as passed.
- Do not use V5.5 as positive efficacy evidence.
- Do not open A3/A4 or iEEG-assisted superiority claims from scaffold artifacts.
- Do not treat Gate 0 signal readiness as model evidence.
- Do not add heavy modeling to Tranche 2.
- Keep test-time inference scalp-only.
- Keep real iEEG/bridge data restricted to audited train-time privileged paths.
- Claims can only be considered after:
  - split registry is locked,
  - feature provenance is complete,
  - control registry is executable,
  - leaderboard rows are produced by audited comparator execution,
  - calibration/influence/reporting are complete,
  - claim-state closeout explicitly allows it.

## Recommended Next Step

Next implementation step:

1. Add a minimal CLI command for Tranche 2 scaffold artifact generation.
2. The command should be scaffold-only and should not run models.
3. Inputs should include:
   - Gate 0 run directory
   - `configs/v56/benchmark_spec.json`
   - `configs/v56/splits.json`
   - `configs/v56/controls.json`
   - `configs/v56/comparators.json`
4. Outputs should be only:
   - `v56_split_registry`
   - `v56_feature_provenance`
   - `v56_control_registry`
   - `v56_leaderboard`
5. The command should fail if Gate 0 is not `signal_audit_ready`.
6. The command should keep claim state closed and report that no efficacy metric
   was computed.

Suggested CLI shape:

```bash
python -m src.cli v56-scaffold \
  --gate0-run artifacts/gate0/20260424T100159866284Z \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --splits configs/v56/splits.json \
  --controls configs/v56/controls.json \
  --comparators configs/v56/comparators.json
```

Expected implementation files for next step:

- `src/cli.py`
- possibly `src/v56/runner.py`
- `tests/unit/test_cli.py` or a new focused `tests/unit/test_v56_cli.py`

Do not implement model training or comparator execution in that CLI command.

