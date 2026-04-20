# V5.5 doc-code crosswalk

Ngay khoa: 2026-04-19

Muc tieu: khoa ban do giua bo tai lieu V5.5 va source code hien co, de moi thay doi tiep theo co the doi chieu voi dung nguon su that. Tai lieu nay khong thay Technical Specification, Annex, Dossier hoac README; no chi la lop crosswalk van hanh.

## Thu tu uu tien tai lieu

| Nguon | Vai tro | Khi xung dot |
|---|---|---|
| `V5_5_Technical_Implementation_Spec_vi_complete.docx` | Execution rules: split, leakage, comparator, observability, threshold, control, reporting | Uu tien cao nhat cho code behavior |
| `V5_5_Execution_Supplement_Implementation_Annex_vi.docx` | SOP, pass criteria, run mode, freeze/release discipline | Dung de khoa cach van hanh |
| `V5_5_Master_Artifact_Dossier_Freeze_Prereg_Reporting_Control.docx` | Artifact binder, prereg/reporting package, QA checklist | Dung de kiem artifact family va hash linking |
| `V5_5_Integrated_Proposal_vi_complete.docx` | Rationale khoa hoc, claim boundary, publication logic | Dung de giai thich vi sao module ton tai va duoc dien giai den dau |
| `ds004752_dossier_trien_khai_vi.docx` | Dataset provenance, BIDS layout, local audit implications | Dung cho Gate 0 local audit va data materialization |
| `blueprint_trien_khai_v1_colab.docx` | Repo/Colab implementation blueprint, CLI and notebook orchestration | Dung cho file layout, runtime profile, Colab sequence |

## Gate semantics

| Gate/phase | Doc source | Code owner | Config owner | Test owner | Contract |
|---|---|---|---|---|---|
| Gate 0 dataset freeze | Technical Spec, Annex, Dataset dossier, Dossier | `src/audit/gate0.py`, `src/audit/materialization.py`, `src/audit/signal.py` | `configs/data/*.yaml` | `tests/unit/test_gate0.py`, `tests/unit/test_materialization.py`, `tests/unit/test_signal.py` | Must write manifest, cohort lock draft/ready, audit report, override log, bridge availability, materialization report. Cohort lock is not primary-ready until payloads and full signal audit pass. |
| Gate 1 decision layer | Technical Spec, Annex | `src/simulation/decision.py` | `configs/gate1/decision_simulation.json` | `tests/unit/test_gate1.py` | Must reject non-ready Gate 0. Must lock N_eff, SESOI, influence rule, decision memo. Must not authorize real data phases. |
| Gate 2 synthetic validation | Technical Spec, Annex | `src/synthetic/gate2.py` | `configs/gate2/synthetic_validation.json` | `tests/unit/test_gate2.py` | Must read Gate 1 artifacts, run synthetic recovery proxy, write threshold registry. Must not authorize real data phases. |
| Gate 2.5 prereg bundle | Annex, Master Artifact Dossier | `src/prereg/bundle.py` | `configs/prereg/prereg_assembly.json` | `tests/unit/test_prereg.py` | Must hash-link Gate 0/1/2 artifacts, comparator configs, registry configs and environment lock. Only locked bundle can satisfy release blocker. |
| Real phase guard | Technical Spec, Annex | `src/guards.py`, `src/cli.py` | `configs/prereg/prereg_bundle.json` | `tests/unit/test_guards.py` | `phase05_real`, `phase1_real`, `phase2_real`, `phase3_real` are blocked unless bundle status is `locked` and artifact hashes exist. |
| Phase 0.5 observability | Technical Spec, Annex | `src/phase05/observability.py`, `src/phase05/estimators.py` | `configs/phase05/*.json` | `tests/unit/test_phase05.py`, `tests/unit/test_phase05_estimators.py` | Predecoder observability only. No Phase 1 decoder claim. Smoke runs with low permutations are not final inference. |
| Phase 1 smoke/model smoke | Blueprint, Technical Spec, Annex | `src/phase1/smoke.py`, `src/phase1/model_smoke.py`, `src/phase1/gap_review.py` | `configs/phase1/model_smoke.json` | `tests/unit/test_phase1_smoke.py`, `tests/unit/test_phase1_model_smoke.py`, `tests/unit/test_phase1_gap_review.py` | Contract/model-smoke/gap-review only. A2/A2b/A2c/A2d smoke can compute implementation metrics but cannot support privileged-transfer efficacy claims. |

## Threshold and decision rules

| Rule family | Source of truth in code | Frozen output | Notes |
|---|---|---|---|
| SESOI | `configs/gate1/decision_simulation.json` | Gate 1 `sesoi_registry.json` | Current primary subject-level SESOI delta BA is `0.03`; calibration tolerance max delta ECE is `0.02`. |
| Influence ceiling | `configs/gate1/decision_simulation.json`, `configs/teacher/teacher_registry.yaml` | Gate 1 `influence_rule.json`, Gate 2 threshold registry, prereg bundle | Current ceiling is `0.40`; strong claim is blocked by single-subject dominance or leave-one-subject-out claim flip. |
| Synthetic pass thresholds | `configs/gate2/synthetic_validation.json` | Gate 2 `gate_threshold_registry.json` | Downstream phases must read the registry, not hard-code notebook constants. |
| Phase 0.5 estimator thresholds | `configs/phase05/estimators.json` | Phase 0.5 estimator artifacts | Includes spatial delta Q2, ICA robustness, task-vs-control windows and final minimum permutations. |

## Comparator map

| Comparator family | Config/module | Freeze path | Current status |
|---|---|---|---|
| A2/A2b scalp-only smoke | `src/phase1/model_smoke.py`, `configs/phase1/model_smoke.json` | Phase 1 model-smoke artifacts | Implementation smoke only; standard-library fold runner supports precomputed rows without `mne`. |
| A2c CORAL | `src/phase1/a2c_smoke.py`, `configs/phase1/a2c_smoke.json`, `configs/models/coral.yaml` | Gate 2.5 comparator card plus post-prereg smoke revision note | Non-claim implementation smoke is available with internal NumPy CORAL alignment proxy; not the final neural CORAL comparator estimate. |
| A2d Riemannian | `src/phase1/a2d_smoke.py`, `configs/phase1/a2d_smoke.json`, `configs/models/riemannian_a2d.yaml` | Gate 2.5 comparator card plus post-prereg smoke revision note | Non-claim implementation smoke is available with internal NumPy log-Euclidean/tangent backend; not the final A2d comparator estimate. |
| A3 distillation | `configs/models/distill_a3.yaml` | Gate 2.5 comparator card | Required comparator config hash in prereg assembly. |
| A4 privileged | `configs/models/privileged_a4.yaml` | Gate 2.5 comparator card | Must remain train-time privileged only; scalp-only at test time. |
| EEGNet/ShallowConvNet | `configs/models/eegnet.yaml`, `configs/models/shallowconvnet.yaml` | Gate 2.5 comparator cards | Backbone/comparator configs hash-linked during prereg assembly. |

## Control suite map

| Control | Config/code | Required by | Current implementation surface |
|---|---|---|---|
| Shuffled teacher / time-shifted teacher | `configs/gate2/synthetic_validation.json`, `configs/controls/control_suite_spec.yaml` | Gate 2 and future real phases | Synthetic proxy validates expected negative-control behavior; Phase 1 smoke writes non-executed control shells. |
| Nuisance shared control | `configs/gate2/synthetic_validation.json`, `configs/controls/nuisance_block_spec.yaml` | Gate 2 and Phase 0.5 | Synthetic nuisance profile must be vetoed; Phase 0.5 estimators include nuisance-only control. |
| Spatial permutation control | `configs/phase05/estimators.json`, `src/phase05/estimators.py` | Phase 0.5 | Implemented as rowwise spatial permutation control. |
| ICA robustness control | `configs/phase05/estimators.json`, `src/phase05/estimators.py` | Phase 0.5 | Implemented with configured target sampling, max components and robustness ratio. |
| Calibration/influence package | `src/phase1/smoke.py`, `src/phase1/model_smoke.py` | Phase 1 | Smoke artifacts are shells or implementation diagnostics, not final claim-evaluable reports. |
| Comparator-suite gap review | `src/phase1/gap_review.py` | Phase 1 governance before A3/A4/full run | Records remaining A3/A4/control/calibration/influence/reporting blockers and keeps `claim_ready=false`. |

## Prereg and artifact contract

| Artifact group | Producer | Required files or hashes |
|---|---|---|
| Gate 0 | `run_gate0_audit` | `manifest.json`, `cohort_lock.json`, `audit_report.md`, `override_log.md`, `bridge_availability.json`, `materialization_report.json` |
| Gate 1 | `run_gate1_decision` | `gate1_inputs.json`, `gate1_input_integrity.json`, `n_eff_statement.json`, `simulation_registry.json`, `sesoi_registry.json`, `influence_rule.json`, `decision_memo.md`, `gate1_summary.json` |
| Gate 2 | `run_gate2_synthetic_validation` | `synthetic_generator_spec.json`, `synthetic_recovery_report.json`, `synthetic_recovery_report.md`, `gate_threshold_registry.json`, `gate2_summary.json` |
| Gate 2.5 | `run_prereg_assembly` | `prereg_bundle.json`, `environment_lock.json`, `prereg_validation_report.md`, `revision_policy.md`, comparator cards, `gate25_summary.json` |

## Notebook rule

Durable scientific logic must live in `src/` and be tested. Notebook code may mount Drive, authenticate GitHub, call CLI, inspect JSON/Markdown outputs, hash files, and write review/readiness wrapper artifacts. Notebook code must not become the source of truth for teacher pool, thresholds, control suite, inference defaults or reporting map.

Notebook scan on 2026-04-19:

- All tracked notebooks contain CLI calls.
- Definitions found in notebooks are helper utilities such as `run`, `git_auth_header`, JSON/hash/path helpers, and guard wrappers.
- No notebook imports model-training stacks such as `mne`, `sklearn`, `torch`, or `tensorflow`.
- Phase 1 and Phase 0.5 notebooks still need periodic review because they write orchestration/readiness artifacts; any reusable logic should be promoted into `src/` with tests.

## Local verification snapshot

Commands run on 2026-04-19:

```powershell
python -m unittest discover -s tests
python -m src.cli audit --profile t4_safe --config configs/data/snapshot.yaml
```

Results:

- Unit tests: 36 tests passed.
- Gate 0 metadata audit run: `artifacts/gate0/20260419T170133426518Z`.
- Gate 0 required files: all present.
- Local dataset inventory: 15 subjects, 68 sessions, 3353 EEG event trials, 3353 iEEG event trials.
- EEG/iEEG core event mismatch count: 0.
- EDF materialization: 136 files, 136 pointer-like.
- MAT materialization: 15 files, 15 pointer-like.
- Gate 1 validation on this local Gate 0 run correctly fails because Gate 0 is metadata-only and signal-level audit is not ready.

Signal audit was intentionally not run because local EDF/MAT payloads are not materialized.
