# Session Handoff - 2026-04-24

This note preserves the current working state after the V5.5 closeout and the
V5.6 transition work. It is intended as the first document to read before
continuing the next implementation session.

## Executive State

- Current branch: `main`
- Most recent implementation commit before this doc-only update:
  `37e87a9 Organize V5 docs and update Gate 0 Colab`
- Last known pushed head before local follow-up commits:
  `06a2f40 Add session handoff note`
- Scientific state:
  - V5.5 remains `fail-closed` and `claim-closed`.
  - V5.5 does not support decoder efficacy, A3/A4 efficacy, A4 superiority, or iEEG-assisted superiority claims.
  - V5.6 has moved to a benchmark-first and control-first direction.
  - V5.6 Gate 0 has reached full-cohort `signal_audit_ready`.
  - V5.6 Tranche 2 scaffold, artifact writers, and scaffold-only CLI are implemented.
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

- `docs/V5.5/06_bao_cao_tien_do_ket_qua_va_claim_boundary_2026-04-24.md`
- `docs/V5.5/07_phase1_controls_technical_conclusion_2026-04-24.md`
- `docs/V5.5/08_phase1_negative_finding_report_2026-04-24.md`
- `docs/V5.5/10_phase1_consistency_audit_report_2026-04-24.md`
- `docs/17_v55_to_v56_transition_lock_2026-04-24.md`
- `docs/18_v55_to_v56_transition_lock_manifest_2026-04-24.json`

Important note: V5.5 historical docs are now archived under `docs/V5.5/`.
Do not move them back into the docs root unless explicitly requested.

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

- `docs/V5.5/11_phase1_prospective_ieeg_assisted_proposal_2026-04-24.md`
- `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- `docs/V5.5/13_phase1_ieeg_assisted_contract_2026-04-24.md`
- `docs/14_phase1_go_no_go_decision_memo_2026-04-24.md`
- `docs/15_phase1_signal_readiness_operational_checklist_2026-04-24.md`
- `docs/16_phase1_prospective_execution_roadmap_2026-04-24.md`
- `docs/19_v56_repo_mapping_and_execution_roadmap_2026-04-24.md`
- `docs/20_v56_tranche1_signal_pilot_runbook_2026-04-24.md`
- `docs/22_v56_tranche2_scaffold_runbook_2026-04-24.md`

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

Recent local commits:

- `37e87a9 Organize V5 docs and update Gate 0 Colab`
- `8f2dfb0 Add V5.6 scaffold CLI`
- `06a2f40 Add session handoff note`
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
- `src/v56/runner.py`

Tests added:

- `tests/unit/test_v56_scaffold.py`
- `tests/unit/test_v56_artifacts.py`
- `tests/unit/test_v56_cli.py`

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

## Current Working Tree State

After commit `37e87a9`, the worktree was cleaned. The branch was ahead of
`origin/main` by two commits before this documentation update:

- `8f2dfb0 Add V5.6 scaffold CLI`
- `37e87a9 Organize V5 docs and update Gate 0 Colab`

Recommended staging discipline remains:

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

This step has been implemented:

- `src/v56/runner.py`
- CLI command `v56-scaffold`
- `bootstrap/run_v56_tranche2_scaffold.sh`
- `tests/unit/test_v56_cli.py`

The command remains scaffold-only. It writes V5.6 benchmark/control artifacts
from a signal-ready Gate 0 run and does not train models or compute efficacy
metrics.

Implementation contract:

1. The command is scaffold-only and must not run models.
2. Inputs should include:
   - Gate 0 run directory
   - `configs/v56/benchmark_spec.json`
   - `configs/v56/splits.json`
   - `configs/v56/controls.json`
   - `configs/v56/comparators.json`
3. Outputs should be only:
   - `v56_split_registry`
   - `v56_feature_provenance`
   - `v56_control_registry`
   - `v56_leaderboard`
4. The command should fail if Gate 0 is not `signal_audit_ready`.
5. The command should keep claim state closed and report that no efficacy metric
   was computed.

Suggested CLI shape:

```bash
bash bootstrap/run_v56_tranche2_scaffold.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts
```

Expected implementation files for next step:

- `bootstrap/run_v56_tranche2_scaffold.sh`
- `src/cli.py`
- `src/v56/runner.py`
- `tests/unit/test_v56_cli.py`

Do not implement model training or comparator execution in that CLI command.

Next step after this implementation:

1. Run the command on the authoritative Gate 0 run.
2. Review the four generated artifact families before any comparator or model
   execution is considered.
3. If scaffold artifacts are consistent, open a separate split/provenance
   registry lock step.
4. If scaffold artifacts show missing source links or status drift, fix the
   scaffold first. Do not proceed to model execution.
