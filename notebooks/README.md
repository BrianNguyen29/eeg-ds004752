# Notebook orchestration

Notebook files should only orchestrate the CLI and must not introduce
separate scientific logic.

Recommended Colab sequence:

1. `00_bootstrap_runtime`: clone repo, install runtime, mount Drive.
2. `01_gate0_audit`: call `python -m src.cli audit`.
3. `02_gate1_decision`: prepare decision simulation artefacts.
4. `03_gate2_synthetic`: run synthetic validation.
5. `04_prereg_validation`: lock prereg bundle after Gate 2 pass.
6. Real phases only after locked prereg.

