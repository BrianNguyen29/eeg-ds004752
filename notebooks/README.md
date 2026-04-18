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
7. Real decoder phases only after locked prereg and the required Phase 0.5 controls are complete.
