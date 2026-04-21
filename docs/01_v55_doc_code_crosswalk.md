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
| Phase 1 smoke/model smoke | Blueprint, Technical Spec, Annex | `src/phase1/smoke.py`, `src/phase1/model_smoke.py`, `src/phase1/gap_review.py` | `configs/phase1/model_smoke.json` | `tests/unit/test_phase1_smoke.py`, `tests/unit/test_phase1_model_smoke.py`, `tests/unit/test_phase1_gap_review.py` | Contract/model-smoke/gap-review only. A2/A2b/A2c/A2d/A3/A4 smoke can compute implementation metrics but cannot support privileged-transfer efficacy claims. |
| Phase 1 governance readiness | Technical Spec, Annex, Dossier | `src/phase1/controls.py`, `src/phase1/calibration.py`, `src/phase1/influence.py`, `src/phase1/claim_state.py` | `configs/controls/*.yaml`, `configs/eval/*.yaml`, `configs/gate1/decision_simulation.json`, `configs/gate2/synthetic_validation.json` | `tests/unit/test_phase1_governance_readiness.py` | Fail-closed readiness package. Records that controls/calibration/influence/reporting are not claim-evaluable until final artifacts exist; keeps `claim_ready=false`. |
| Phase 1 final claim-package plan | Technical Spec, Annex, Dossier | `src/phase1/final_claim_package.py` | `configs/phase1/final_claim_package.json`, governance configs | `tests/unit/test_phase1_final_claim_package.py` | Non-claim plan/readiness contract. Records required final comparator/control/calibration/influence/reporting artifacts and blockers before any claim-bearing implementation. |
| Phase 1 final comparator artifact plan | Technical Spec, Annex, Dossier | `src/phase1/final_comparator_artifacts.py` | `configs/phase1/final_comparator_artifacts.json`, `configs/phase1/final_claim_package.json` | `tests/unit/test_phase1_final_comparator_artifacts.py` | Non-claim manifest/schema plan. Records required final comparator fold/logit/metric/split/feature/leakage artifacts and keeps smoke metrics non-evidentiary. |
| Phase 1 final split/feature/leakage plan | Technical Spec, Annex, Dossier | `src/phase1/final_split_feature_leakage.py` | `configs/phase1/final_split_feature_leakage.json`, `configs/split/loso_subject.yaml` | `tests/unit/test_phase1_final_split_feature_leakage.py` | Non-claim readiness plan for final LOSO split, feature provenance and leakage-audit manifests. Records missing manifests and keeps final comparator runners blocked. |
| Phase 1 final split manifest | Technical Spec, Annex, Dossier | `src/phase1/final_split_manifest.py` | `configs/phase1/final_split_manifest.json`, `configs/split/loso_subject.yaml` | `tests/unit/test_phase1_final_split_manifest.py` | Fail-closed final LOSO split manifest generator. Writes `final_split_manifest.json` only from signal-ready Gate 0 cohort lock; otherwise writes a blocked record and keeps claims closed. |
| Phase 1 final feature manifest | Technical Spec, Annex, Dossier | `src/phase1/final_feature_manifest.py` | `configs/phase1/final_feature_manifest.json`, `configs/phase1/final_split_feature_leakage.json` | `tests/unit/test_phase1_final_feature_manifest.py` | Fail-closed final scalp feature schema/provenance manifest generator. Writes `final_feature_manifest.json` only after final split and materialized Gate 0 provenance pass; it never writes feature matrices or metrics. |
| Phase 1 final leakage audit | Technical Spec, Annex, Dossier | `src/phase1/final_leakage_audit.py` | `configs/phase1/final_leakage_audit.json`, `configs/phase1/final_split_feature_leakage.json` | `tests/unit/test_phase1_final_leakage_audit.py` | Manifest-level leakage audit for planned final split/feature fit scopes. Records fit/transform subjects per stage and keeps runtime comparator log audit and claims blocked until final runners execute. |
| Phase 1 final comparator runner readiness | Technical Spec, Annex, Dossier | `src/phase1/final_comparator_runner_readiness.py` | `configs/phase1/final_comparator_runner_readiness.json`, `configs/phase1/final_comparator_artifacts.json` | `tests/unit/test_phase1_final_comparator_runner_readiness.py` | Non-claim output-manifest readiness package. Links final split, feature and manifest-level leakage artifacts to the required final comparator output contract while explicitly recording final comparator outputs and runtime leakage logs as missing. |
| Phase 1 final feature matrix | Technical Spec, Annex, Dossier | `src/phase1/final_feature_matrix.py` | `configs/phase1/final_feature_matrix.json`, `configs/phase1/final_feature_manifest.json` | `tests/unit/test_phase1_final_feature_matrix.py` | Fail-closed final scalp feature matrix materializer. Writes `final_feature_matrix.csv` only when reviewed split/feature/leakage/readiness sources pass and EDF/event extraction produces the exact planned rows/features; it never writes logits, metrics or model outputs. |

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
| A3 distillation | `src/phase1/a3_smoke.py`, `configs/phase1/a3_smoke.json`, `configs/models/distill_a3.yaml` | Gate 2.5 comparator card plus post-prereg smoke revision note | Non-claim implementation smoke is available with an internal training-scalp-feature teacher/student distillation proxy. It validates split discipline and artifact writing only; it is not the final A3 blind/full teacher distillation comparator estimate. |
| A4 privileged | `src/phase1/a4_smoke.py`, `configs/phase1/a4_smoke.json`, `configs/models/privileged_a4.yaml` | Gate 2.5 comparator card plus post-prereg smoke revision note | Non-claim implementation smoke is available with an internal train-time privileged proxy. It validates train-time-only privileged path discipline, split isolation and scalp-only inference only; it is not the final A4 privileged-transfer comparator estimate. |
| EEGNet/ShallowConvNet | `configs/models/eegnet.yaml`, `configs/models/shallowconvnet.yaml` | Gate 2.5 comparator cards | Backbone/comparator configs hash-linked during prereg assembly. |

## Control suite map

| Control | Config/code | Required by | Current implementation surface |
|---|---|---|---|
| Shuffled teacher / time-shifted teacher | `configs/gate2/synthetic_validation.json`, `configs/controls/control_suite_spec.yaml` | Gate 2 and future real phases | Synthetic proxy validates expected negative-control behavior; Phase 1 smoke writes non-executed control shells. |
| Nuisance shared control | `configs/gate2/synthetic_validation.json`, `configs/controls/nuisance_block_spec.yaml` | Gate 2 and Phase 0.5 | Synthetic nuisance profile must be vetoed; Phase 0.5 estimators include nuisance-only control. |
| Spatial permutation control | `configs/phase05/estimators.json`, `src/phase05/estimators.py` | Phase 0.5 | Implemented as rowwise spatial permutation control. |
| ICA robustness control | `configs/phase05/estimators.json`, `src/phase05/estimators.py` | Phase 0.5 | Implemented with configured target sampling, max components and robustness ratio. |
| Calibration/influence package | `src/phase1/calibration.py`, `src/phase1/influence.py`, `src/phase1/claim_state.py`, plus smoke runners | Phase 1 | Governance readiness artifacts are fail-closed. Smoke artifacts are shells or implementation diagnostics, not final claim-evaluable reports. |
| Comparator-suite gap review | `src/phase1/gap_review.py` | Phase 1 governance before full claim-bearing run | Records completed A2/A2b/A2c/A2d/A3/A4 non-claim smoke reviews while keeping final comparator/control/calibration/influence/reporting blockers and `claim_ready=false`. |
| Governance readiness package | `src/phase1/controls.py`, `src/phase1/calibration.py`, `src/phase1/influence.py`, `src/phase1/claim_state.py` | Phase 1 governance before final reporting | Aggregates post-A4 gap review, control-suite readiness, calibration readiness, influence readiness and reporting readiness. It does not execute missing final packages or open claims. |
| Final claim-package plan | `src/phase1/final_claim_package.py`, `configs/phase1/final_claim_package.json` | Phase 1 governance before claim-bearing implementation | Machine-readable artifact contract for final comparators, controls, calibration, influence and reporting. It records blockers and keeps claims closed. |
| Final comparator artifact plan | `src/phase1/final_comparator_artifacts.py`, `configs/phase1/final_comparator_artifacts.json` | Phase 1 governance before final comparator runners | Machine-readable manifest schema for final comparator outputs. It records missing final manifests and prevents smoke metrics from satisfying final evidence. |
| Final split/feature/leakage readiness | `src/phase1/final_split_feature_leakage.py`, `configs/phase1/final_split_feature_leakage.json` | Phase 1 governance before final comparator runners | Machine-readable readiness contract for final split manifest, feature manifest and leakage audit. It does not create final folds or final features. |
| Final LOSO split manifest | `src/phase1/final_split_manifest.py`, `configs/phase1/final_split_manifest.json` | Phase 1 governance before final feature extraction and final comparator runners | Deterministic subject-level LOSO manifest from locked Gate 0 cohort. It is a provenance artifact, not model evidence; it blocks when Gate 0 is not signal-ready. |
| Final feature manifest | `src/phase1/final_feature_manifest.py`, `configs/phase1/final_feature_manifest.json` | Phase 1 governance before final leakage audit and final comparator runners | Scalp feature schema/provenance manifest from final split, Gate 0 and dataset sidecars. It does not contain feature values, model outputs or metrics. |
| Final leakage audit | `src/phase1/final_leakage_audit.py`, `configs/phase1/final_leakage_audit.json` | Phase 1 governance before final comparator runners | Manifest-level audit of planned preprocessing, normalization, alignment, teacher, privileged, gate/weight and calibration fit scopes. It does not audit runtime comparator logs until final runners exist. |
| Final comparator runner readiness | `src/phase1/final_comparator_runner_readiness.py`, `configs/phase1/final_comparator_runner_readiness.json` | Phase 1 governance before final comparator runner implementation | Output-manifest readiness contract for A2/A2b/A2c/A2d/A3/A4. It records missing final fold logs, logits, subject-level metrics, runtime leakage logs and comparator output manifests; it does not run models or create evidence. |
| Final feature matrix | `src/phase1/final_feature_matrix.py`, `configs/phase1/final_feature_matrix.json` | Phase 1 final comparator runner inputs | Materialized scalp EEG feature values and labels from the reviewed final feature manifest. It contains no model outputs, logits, metrics, controls, calibration, influence or runtime leakage logs. |

## Prereg and artifact contract

| Artifact group | Producer | Required files or hashes |
|---|---|---|
| Gate 0 | `run_gate0_audit` | `manifest.json`, `cohort_lock.json`, `audit_report.md`, `override_log.md`, `bridge_availability.json`, `materialization_report.json` |
| Gate 1 | `run_gate1_decision` | `gate1_inputs.json`, `gate1_input_integrity.json`, `n_eff_statement.json`, `simulation_registry.json`, `sesoi_registry.json`, `influence_rule.json`, `decision_memo.md`, `gate1_summary.json` |
| Gate 2 | `run_gate2_synthetic_validation` | `synthetic_generator_spec.json`, `synthetic_recovery_report.json`, `synthetic_recovery_report.md`, `gate_threshold_registry.json`, `gate2_summary.json` |
| Phase 1 governance readiness | `run_phase1_governance_readiness` | `phase1_governance_readiness_inputs.json`, `phase1_governance_readiness_summary.json`, `phase1_governance_readiness_report.md`, `phase1_control_suite_status.json`, `phase1_calibration_package_status.json`, `phase1_influence_status.json`, `phase1_reporting_readiness.json`, `phase1_claim_state.json` |
| Phase 1 final claim-package plan | `run_phase1_final_claim_package_plan` | `phase1_final_claim_package_plan_inputs.json`, `phase1_final_claim_package_plan_summary.json`, `phase1_final_claim_package_plan_report.md`, `phase1_final_claim_package_contract.json`, `phase1_final_comparator_readiness.json`, `phase1_final_governance_boundary_review.json`, `phase1_final_claim_blocker_inventory.json`, `phase1_final_claim_state_plan.json`, `phase1_final_implementation_plan.json` |
| Phase 1 final comparator artifact plan | `run_phase1_final_comparator_artifact_plan` | `phase1_final_comparator_artifact_plan_inputs.json`, `phase1_final_comparator_artifact_plan_summary.json`, `phase1_final_comparator_artifact_plan_report.md`, `phase1_final_comparator_artifact_contract.json`, `phase1_final_comparator_manifest_status.json`, `phase1_final_comparator_missing_artifacts.json`, `phase1_final_comparator_leakage_requirements.json`, `phase1_final_comparator_claim_state.json`, `phase1_final_comparator_implementation_plan.json` |
| Phase 1 final split/feature/leakage plan | `run_phase1_final_split_feature_leakage_plan` | `phase1_final_split_feature_leakage_plan_inputs.json`, `phase1_final_split_feature_leakage_plan_summary.json`, `phase1_final_split_feature_leakage_plan_report.md`, `phase1_final_split_feature_leakage_contract.json`, `phase1_final_split_manifest_readiness.json`, `phase1_final_feature_manifest_readiness.json`, `phase1_final_leakage_audit_readiness.json`, `phase1_final_split_feature_leakage_source_links.json`, `phase1_final_split_feature_leakage_missing_manifests.json`, `phase1_final_split_feature_leakage_claim_state.json`, `phase1_final_split_feature_leakage_implementation_plan.json` |
| Phase 1 final split manifest | `run_phase1_final_split_manifest` | `phase1_final_split_manifest_inputs.json`, `phase1_final_split_manifest_summary.json`, `phase1_final_split_manifest_report.md`, `phase1_final_split_manifest_source_links.json`, `phase1_final_split_manifest_validation.json`, `phase1_final_split_manifest_claim_state.json`, and either `final_split_manifest.json` or `phase1_final_split_manifest_blocked.json` |
| Phase 1 final feature manifest | `run_phase1_final_feature_manifest` | `phase1_final_feature_manifest_inputs.json`, `phase1_final_feature_manifest_summary.json`, `phase1_final_feature_manifest_report.md`, `phase1_final_feature_manifest_source_links.json`, `phase1_final_feature_inventory.json`, `phase1_final_feature_manifest_validation.json`, `phase1_final_feature_manifest_claim_state.json`, and either `final_feature_manifest.json` or `phase1_final_feature_manifest_blocked.json` |
| Phase 1 final leakage audit | `run_phase1_final_leakage_audit` | `phase1_final_leakage_audit_inputs.json`, `phase1_final_leakage_audit_summary.json`, `phase1_final_leakage_audit_report.md`, `phase1_final_leakage_audit_source_links.json`, `phase1_final_leakage_audit_input_validation.json`, `phase1_final_leakage_audit_validation.json`, `phase1_final_leakage_audit_claim_state.json`, `final_leakage_audit.json` |
| Phase 1 final comparator runner readiness | `run_phase1_final_comparator_runner_readiness` | `phase1_final_comparator_runner_readiness_inputs.json`, `phase1_final_comparator_runner_readiness_summary.json`, `phase1_final_comparator_runner_readiness_report.md`, `phase1_final_comparator_runner_source_links.json`, `phase1_final_comparator_runner_input_validation.json`, `phase1_final_comparator_runner_output_contract.json`, `phase1_final_comparator_runner_manifest_status.json`, `phase1_final_comparator_missing_outputs.json`, `phase1_final_comparator_runtime_leakage_requirements.json`, `phase1_final_comparator_completeness_table.json`, `phase1_final_comparator_runner_claim_state.json`, `phase1_final_comparator_runner_implementation_plan.json` |
| Phase 1 final feature matrix | `run_phase1_final_feature_matrix` | `phase1_final_feature_matrix_inputs.json`, `phase1_final_feature_matrix_summary.json`, `phase1_final_feature_matrix_report.md`, `phase1_final_feature_matrix_source_links.json`, `phase1_final_feature_matrix_input_validation.json`, `phase1_final_feature_matrix_schema.json`, `final_feature_row_index.json`, `phase1_final_feature_matrix_validation.json`, `phase1_final_feature_matrix_claim_state.json`, and either `final_feature_matrix.csv` or `phase1_final_feature_matrix_blocked.json` |
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
