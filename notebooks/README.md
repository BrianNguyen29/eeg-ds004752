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
9. `08_colab_phase1_model_smoke_a2_a2b.ipynb`: prepare the first real model implementation smoke plan for A2/A2b scalp-only comparators, hash-linking prior sources and writing an explicit blocker if the CLI-backed model runner is not implemented.
10. Full real decoder phases only after locked prereg, required Phase 0.5 controls, Phase 1 readiness checks, Phase 1 smoke contract review pass, and real model-smoke artifacts are reviewed.
