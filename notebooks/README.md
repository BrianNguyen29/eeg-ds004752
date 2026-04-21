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
21. Full real decoder phases only after locked prereg, required Phase 0.5 controls, Phase 1 readiness checks, Phase 1 smoke contract review pass, real model-smoke artifacts are reviewed, gap review blockers are resolved, final claim-package plan, final comparator artifact plan, final split/feature/leakage plan and final split manifest are reviewed, and the required feature/leakage/comparator/control/calibration/influence/reporting package is implemented.

Notebook integrity rules:

- Notebooks are orchestration and audit surfaces; durable scientific logic must live in `src/` and be covered by tests.
- Saved outputs and execution counts should be cleared before committing notebooks.
- Source-of-truth paths must be explicit for reviewed runs; avoid silently following `latest.txt` for claim-affecting steps.
- Smoke notebooks may compute implementation diagnostics, but must label them as non-claim unless the full preregistered comparator/control/reporting package is complete.
- Any notebook cell that enables real model execution should default to a manual hold flag rather than running automatically after `git pull`.
