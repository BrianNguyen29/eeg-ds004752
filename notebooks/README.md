# Notebook orchestration

Notebook files should only orchestrate the CLI and must not introduce
separate scientific logic.

Recommended Colab sequence:

1. `00_bootstrap_runtime`: clone repo, install runtime, mount Drive.
2. `01_colab_gate0_audit.ipynb`: call `python -m src.cli audit`.
3. `02_colab_gate1_decision_layer.ipynb`: prepare decision simulation artefacts.
4. `03_colab_gate2_synthetic_validation.ipynb`: run synthetic validation.
5. `04_colab_gate25_preregistration_bundle.ipynb`: lock prereg bundle after Gate 2 pass.
6. `EEG_Phase05_Observability_Estimators.ipynb`: run Phase 0.5 observability estimator workflow under the locked prereg bundle.
7. `06_colab_phase1_input_freeze_and_decoder_readiness.ipynb`: hash-link Gate 0/1/2/2.5 and Phase 0.5 sources, freeze Phase 1 split/teacher/comparator readiness, and run guard smoke without training a decoder.
8. `07_colab_phase1_decoder_smoke.ipynb`: run the guarded Phase 1 smoke contract on 1-2 outer folds, producing fold/comparator/calibration/control/influence artifact shells without claiming model efficacy.
9. `08_colab_phase1_model_smoke_a2_a2b.ipynb`: prepare and, when manually enabled, run the first guarded real model implementation smoke for A2/A2b scalp-only comparators, hash-linking prior sources and writing an explicit blocker if the CLI-backed model runner is unavailable.
10. `09_colab_phase1_a2d_riemannian_smoke.ipynb`: prepare the next mandatory A2d Riemannian comparator smoke/readiness plan, hash-link the reviewed sources, and use a manual hold before launching the CLI-backed non-claim A2d smoke runner.
11. `10_colab_phase1_a2c_coral_smoke.ipynb`: prepare the mandatory A2c CORAL comparator smoke/readiness plan, hash-link the reviewed A2/A2b and A2d non-claim sources, and use a manual hold before launching the CLI-backed non-claim A2c smoke runner.
12. `11_colab_phase1_comparator_suite_gap_review.ipynb`: run the CLI-backed non-claim gap review that records remaining A3/A4/control/calibration/influence/reporting blockers.
13. `12_colab_phase1_a3_distillation_smoke.ipynb`: prepare the A3 distillation smoke/readiness plan, hash-link reviewed A2/A2b, A2c, A2d and gap-review sources, and use a manual hold before launching the CLI-backed non-claim A3 smoke runner.
14. `13_colab_phase1_a4_privileged_smoke.ipynb`: prepare the A4 privileged train-time-only smoke/readiness plan, hash-link reviewed A2/A2b, A2c, A2d, A3 and gap-review sources, and use a manual hold before launching the CLI-backed non-claim A4 smoke runner.
15. `14_colab_phase1_post_a4_gap_review.ipynb`: refresh the CLI-backed non-claim gap review after A3/A4 smoke review notes, recording all comparator smoke reviews while keeping headline claims closed.
16. `15_colab_phase1_governance_readiness.ipynb`: run the CLI-backed governance readiness package for controls, calibration, influence, reporting and claim-state surfaces; expected current result is blocked/non-claim.
17. `16_colab_phase1_final_claim_package_plan.ipynb`: record the CLI-backed final claim-package artifact contract and blockers before any claim-bearing runner implementation.
18. `17_colab_phase1_final_comparator_artifact_plan.ipynb`: record the CLI-backed final comparator manifest schema and missing artifact inventory before final comparator runner implementation.
19. `18_colab_phase1_final_split_feature_leakage_plan.ipynb`: record the CLI-backed final split, feature provenance and leakage-audit readiness contract before final comparator runner implementation.
20. `19_colab_phase1_final_split_manifest.ipynb`: generate the final LOSO split manifest only if Gate 0 has a signal-ready cohort lock; otherwise record a blocked non-claim artifact.
21. `20_colab_phase1_final_feature_manifest.ipynb`: generate the final scalp feature schema/provenance manifest only if final split, Gate 0, materialization and dataset sidecar/event prerequisites pass; otherwise record a blocked non-claim artifact.
22. `21_colab_phase1_final_leakage_audit.ipynb`: generate the manifest-level leakage audit from final split and final feature manifests, recording planned fit/transform subjects per fold and stage while keeping runtime comparator-log audit and claims blocked.
23. `22_colab_phase1_final_comparator_runner_readiness.ipynb`: record the CLI-backed final comparator runner/output-manifest readiness package, linking final split/feature/leakage artifacts while explicitly marking final comparator outputs and runtime leakage logs as missing.
24. `23_colab_phase1_final_feature_matrix.ipynb`: materialize the final scalp EEG feature matrix from reviewed split/feature/leakage/readiness sources, requiring signal extras and real EDF payloads; the matrix contains feature values and labels only, not model outputs.
25. `24_colab_phase1_final_comparator_runner.ipynb`: run the CLI-backed claim-closed final feature-matrix comparator runner after reviewed feature-matrix materialization, writing output manifests and runtime leakage logs while blocking A2d unless final covariance/tangent inputs exist.
26. `25_colab_phase1_final_a2d_covariance_tangent_runner.ipynb`: run the CLI-backed claim-closed final A2d covariance/tangent runner, using the final feature row index as contract and EDF covariance extraction rather than a bandpower proxy.
27. `26_colab_phase1_final_comparator_reconciliation.ipynb`: reconcile the feature-matrix comparator outputs with the final A2d covariance/tangent outputs, recording all-six-comparator artifact completeness while keeping claims closed.
28. `27_colab_phase1_final_governance_reconciliation.ipynb`: reconcile final comparator completeness against final controls, calibration, influence and reporting manifests; expected current result is blocked/non-claim until those governance manifests exist.
29. `28_colab_phase1_final_controls.ipynb`: compute claim-closed final logit-level controls from reconciled final comparator logits and explicitly record dedicated nuisance/spatial/teacher rerun controls as missing blockers.
30. `29_colab_phase1_final_calibration.ipynb`: compute claim-closed final calibration diagnostics from reconciled final comparator logits, recording calibration threshold pass/fail without recalibrating, retraining or opening claims.
31. `30_colab_phase1_final_influence.ipynb`: compute claim-closed subject-level and leave-one-subject-out influence diagnostics from reconciled final comparator logits, recording influence ceiling pass/fail without retraining, editing logits or opening claims.
32. `31_colab_phase1_final_reporting.ipynb`: assemble the claim-closed final reporting package from final governance reconciliation artifacts, preserving controls/calibration/influence blockers and writing a closed claim table without fabricating missing evidence.
33. `32_colab_phase1_final_dedicated_controls.ipynb`: compute claim-closed dedicated final negative controls from the reviewed final feature matrix and locked LOSO folds; failed controls remain blockers and must not be threshold-edited in the notebook.
34. `33_colab_phase1_final_claim_state_closeout.ipynb`: record the final fail-closed Phase 1 claim-state disposition from reviewed governance reconciliation, preserving blockers and writing a revision decision memo without opening claims.
35. `34_colab_phase1_final_remediation_plan.ipynb`: record the claim-closed remediation plan after fail-closed closeout, classifying controls/calibration/influence blockers and revision-policy guardrails without rerunning analyses or opening claims.
36. `35_colab_phase1_final_controls_remediation_audit.ipynb`: audit failed final controls and dedicated controls under the claim-closed remediation plan, recording failure reasons and threshold-source consistency without changing thresholds or rerunning controls.
37. `36_colab_phase1_final_controls_metric_contract_audit.ipynb`: audit the relative-metric contract for failed nuisance/spatial controls, comparing candidate formulas and recording ambiguity without changing thresholds, logits, metrics or claim state.
38. Full real decoder phases only after locked prereg, required Phase 0.5 controls, Phase 1 readiness checks, Phase 1 smoke contract review pass, real model-smoke artifacts are reviewed, gap review blockers are resolved, final claim-package plan, final comparator artifact plan, final split/feature/leakage plan, final split manifest, final feature manifest, final leakage audit, final comparator runner readiness, final feature matrix, final comparator runner outputs, final A2d covariance/tangent outputs, final comparator reconciliation, final controls, final dedicated controls, final calibration, final influence, final reporting, final governance reconciliation, final claim-state closeout, final remediation plan, final controls remediation audit, final controls metric-contract audit and the required comparator/control/calibration/influence/reporting package are implemented and reviewed.

Notebook integrity rules:

- Notebooks are orchestration and audit surfaces; durable scientific logic must live in `src/` and be covered by tests.
- Saved outputs and execution counts should be cleared before committing notebooks.
- Source-of-truth paths must be explicit for reviewed runs; avoid silently following `latest.txt` for claim-affecting steps.
- Smoke notebooks may compute implementation diagnostics, but must label them as non-claim unless the full preregistered comparator/control/reporting package is complete.
- Any notebook cell that enables real model execution should default to a manual hold flag rather than running automatically after `git pull`.
