"""Single CLI entrypoint required by the V5.5 Colab blueprint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit.gate0 import run_gate0_audit
from .config import load_config
from .guards import GuardError, assert_real_phase_allowed
from .phase1.a2c_smoke import Phase1A2cSmokeError, run_phase1_a2c_smoke
from .phase1.a2d_smoke import Phase1A2dSmokeError, run_phase1_a2d_smoke
from .phase1.a3_smoke import Phase1A3SmokeError, run_phase1_a3_smoke
from .phase1.a4_smoke import Phase1A4SmokeError, run_phase1_a4_smoke
from .phase1.claim_state import Phase1GovernanceReadinessError, run_phase1_governance_readiness
from .phase1.final_comparator_artifacts import (
    Phase1FinalComparatorArtifactError,
    run_phase1_final_comparator_artifact_plan,
)
from .phase1.final_comparator_runner_readiness import (
    Phase1FinalComparatorRunnerReadinessError,
    run_phase1_final_comparator_runner_readiness,
)
from .phase1.final_comparator_runner import (
    Phase1FinalComparatorRunnerError,
    run_phase1_final_comparator_runner,
)
from .phase1.final_comparator_reconciliation import (
    Phase1FinalComparatorReconciliationError,
    run_phase1_final_comparator_reconciliation,
)
from .phase1.final_governance_reconciliation import (
    Phase1FinalGovernanceReconciliationError,
    run_phase1_final_governance_reconciliation,
)
from .phase1.final_controls import Phase1FinalControlsError, run_phase1_final_controls
from .phase1.final_dedicated_controls import (
    Phase1FinalDedicatedControlsError,
    run_phase1_final_dedicated_controls,
)
from .phase1.final_calibration import Phase1FinalCalibrationError, run_phase1_final_calibration
from .phase1.final_influence import Phase1FinalInfluenceError, run_phase1_final_influence
from .phase1.final_reporting import Phase1FinalReportingError, run_phase1_final_reporting
from .phase1.final_claim_state_closeout import (
    Phase1FinalClaimStateCloseoutError,
    run_phase1_final_claim_state_closeout,
)
from .phase1.final_remediation_plan import (
    Phase1FinalRemediationPlanError,
    run_phase1_final_remediation_plan,
)
from .phase1.final_controls_remediation_audit import (
    Phase1FinalControlsRemediationAuditError,
    run_phase1_final_controls_remediation_audit,
)
from .phase1.final_a2d_runner import Phase1FinalA2dRunnerError, run_phase1_final_a2d_runner
from .phase1.final_claim_package import Phase1FinalClaimPackageError, run_phase1_final_claim_package_plan
from .phase1.final_split_feature_leakage import (
    Phase1FinalSplitFeatureLeakageError,
    run_phase1_final_split_feature_leakage_plan,
)
from .phase1.final_feature_manifest import Phase1FinalFeatureManifestError, run_phase1_final_feature_manifest
from .phase1.final_feature_matrix import Phase1FinalFeatureMatrixError, run_phase1_final_feature_matrix
from .phase1.final_leakage_audit import Phase1FinalLeakageAuditError, run_phase1_final_leakage_audit
from .phase1.final_split_manifest import Phase1FinalSplitManifestError, run_phase1_final_split_manifest
from .phase1.gap_review import Phase1GapReviewError, run_phase1_gap_review
from .phase1.model_smoke import Phase1ModelSmokeError, run_phase1_model_smoke
from .phase1.smoke import Phase1SmokeError, run_phase1_smoke
from .phase05.estimators import Phase05EstimatorError, run_phase05_estimators
from .phase05.observability import Phase05Error, run_phase05_observability
from .prereg.bundle import PreregError, run_prereg_assembly
from .simulation.decision import Gate1Error, run_gate1_decision
from .synthetic.gate2 import Gate2Error, run_gate2_synthetic_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Run Gate 0 metadata audit")
    audit.add_argument("--profile", default="t4_safe")
    audit.add_argument("--config", default="configs/data/snapshot.yaml")
    audit.add_argument("--dataset-root")
    audit.add_argument("--output-root")
    audit.add_argument("--include-signal", action="store_true")
    audit.add_argument("--signal-max-sessions", type=int, default=4)
    audit.add_argument("--subjects", nargs="*", help="Restrict signal audit to subject IDs, e.g. sub-01 sub-02")
    audit.add_argument("--sessions", nargs="*", help="Restrict signal audit to session IDs, e.g. ses-01 ses-02")

    smoke = subparsers.add_parser("smoke", help="Validate config and project paths")
    smoke.add_argument("--profile", default="t4_safe")
    smoke.add_argument("--config", default="configs/data/snapshot.yaml")
    smoke.add_argument("--dataset-root")

    synthetic = subparsers.add_parser("synthetic", help="Create Gate 2 placeholder artefact")
    synthetic.add_argument("--profile", default="a100_fast")
    synthetic.add_argument("--config", default="configs/prereg/prereg_bundle.json")
    synthetic.add_argument("--output-root", default="artifacts/gate2")

    gate2 = subparsers.add_parser("gate2", help="Run Gate 2 synthetic validation and threshold registry")
    gate2.add_argument("--profile", default="t4_safe")
    gate2.add_argument("--gate1-run", required=True)
    gate2.add_argument("--config", default="configs/gate2/synthetic_validation.json")
    gate2.add_argument("--output-root", default="artifacts/gate2")

    gate25 = subparsers.add_parser("gate25", help="Assemble Gate 2.5 preregistration bundle")
    gate25.add_argument("--profile", default="t4_safe")
    gate25.add_argument("--gate2-run", required=True)
    gate25.add_argument("--config", default="configs/prereg/prereg_assembly.json")
    gate25.add_argument("--output-root", default="artifacts/prereg")

    gate1 = subparsers.add_parser("gate1", help="Run Gate 1 decision simulation and governance artefact generation")
    gate1.add_argument("--profile", default="t4_safe")
    gate1.add_argument("--gate0-run", required=True)
    gate1.add_argument("--config", default="configs/gate1/decision_simulation.json")
    gate1.add_argument("--output-root", default="artifacts/gate1")

    phase05_estimators = subparsers.add_parser(
        "phase05_estimators",
        help="Run Phase 0.5 task-contrast observability estimator workflow",
    )
    phase05_estimators.add_argument("--profile", default="t4_safe")
    phase05_estimators.add_argument("--prereg-bundle", required=True)
    phase05_estimators.add_argument("--phase05-run", required=True)
    phase05_estimators.add_argument("--dataset-root", required=True)
    phase05_estimators.add_argument("--config", default="configs/phase05/estimators.json")
    phase05_estimators.add_argument("--output-root", default="artifacts/phase05_estimators")
    phase05_estimators.add_argument("--subjects", nargs="*")
    phase05_estimators.add_argument("--max-subjects", type=int)
    phase05_estimators.add_argument("--max-sessions", type=int)
    phase05_estimators.add_argument("--max-trials-per-session", type=int)
    phase05_estimators.add_argument("--n-permutations", type=int)

    phase1_gap_review = subparsers.add_parser(
        "phase1_gap_review",
        help="Review remaining Phase 1 comparator/control gaps without launching training",
    )
    phase1_gap_review.add_argument("--profile", default="t4_safe")
    phase1_gap_review.add_argument("--config", required=True)
    phase1_gap_review.add_argument("--readiness-run", required=True)
    phase1_gap_review.add_argument("--output-root", default="artifacts/phase1_gap_review")
    phase1_gap_review.add_argument("--a2-a2b-run")
    phase1_gap_review.add_argument("--a2c-run")
    phase1_gap_review.add_argument("--a2d-run")
    phase1_gap_review.add_argument("--a3-run")
    phase1_gap_review.add_argument("--a4-run")

    phase1_governance = subparsers.add_parser(
        "phase1_governance_readiness",
        help="Aggregate Phase 1 controls/calibration/influence/reporting readiness without opening claims",
    )
    phase1_governance.add_argument("--profile", default="t4_safe")
    phase1_governance.add_argument("--config", required=True)
    phase1_governance.add_argument("--gap-review-run", required=True)
    phase1_governance.add_argument("--output-root", default="artifacts/phase1_governance_readiness")

    phase1_final_claim = subparsers.add_parser(
        "phase1_final_claim_package_plan",
        help="Record the final Phase 1 claim-package contract and blockers without opening claims",
    )
    phase1_final_claim.add_argument("--profile", default="t4_safe")
    phase1_final_claim.add_argument("--config", required=True)
    phase1_final_claim.add_argument("--governance-run", required=True)
    phase1_final_claim.add_argument("--output-root", default="artifacts/phase1_final_claim_package_plan")
    phase1_final_claim.add_argument("--package-config", default="configs/phase1/final_claim_package.json")

    phase1_final_comparator_artifact = subparsers.add_parser(
        "phase1_final_comparator_artifact_plan",
        help="Record final Phase 1 comparator artifact schema and missing manifests without opening claims",
    )
    phase1_final_comparator_artifact.add_argument("--profile", default="t4_safe")
    phase1_final_comparator_artifact.add_argument("--config", required=True)
    phase1_final_comparator_artifact.add_argument("--claim-package-run", required=True)
    phase1_final_comparator_artifact.add_argument(
        "--output-root",
        default="artifacts/phase1_final_comparator_artifact_plan",
    )
    phase1_final_comparator_artifact.add_argument(
        "--artifact-config",
        default="configs/phase1/final_comparator_artifacts.json",
    )
    phase1_final_comparator_artifact.add_argument(
        "--claim-package-config",
        default="configs/phase1/final_claim_package.json",
    )

    phase1_final_sfl = subparsers.add_parser(
        "phase1_final_split_feature_leakage_plan",
        help="Record final Phase 1 split/feature/leakage readiness without opening claims",
    )
    phase1_final_sfl.add_argument("--profile", default="t4_safe")
    phase1_final_sfl.add_argument("--config", required=True)
    phase1_final_sfl.add_argument("--comparator-artifact-run", required=True)
    phase1_final_sfl.add_argument(
        "--output-root",
        default="artifacts/phase1_final_split_feature_leakage_plan",
    )
    phase1_final_sfl.add_argument(
        "--readiness-config",
        default="configs/phase1/final_split_feature_leakage.json",
    )
    phase1_final_sfl.add_argument(
        "--artifact-config",
        default="configs/phase1/final_comparator_artifacts.json",
    )

    phase1_final_split_manifest = subparsers.add_parser(
        "phase1_final_split_manifest",
        help="Generate or block the final Phase 1 LOSO split manifest without opening claims",
    )
    phase1_final_split_manifest.add_argument("--profile", default="t4_safe")
    phase1_final_split_manifest.add_argument("--config", required=True)
    phase1_final_split_manifest.add_argument("--split-feature-leakage-run", required=True)
    phase1_final_split_manifest.add_argument("--gate0-run", required=True)
    phase1_final_split_manifest.add_argument(
        "--output-root",
        default="artifacts/phase1_final_split_manifest",
    )
    phase1_final_split_manifest.add_argument(
        "--manifest-config",
        default="configs/phase1/final_split_manifest.json",
    )
    phase1_final_split_manifest.add_argument(
        "--readiness-config",
        default="configs/phase1/final_split_feature_leakage.json",
    )

    phase1_final_feature_manifest = subparsers.add_parser(
        "phase1_final_feature_manifest",
        help="Generate or block the final Phase 1 feature schema/provenance manifest without opening claims",
    )
    phase1_final_feature_manifest.add_argument("--profile", default="t4_safe")
    phase1_final_feature_manifest.add_argument("--config", required=True)
    phase1_final_feature_manifest.add_argument("--final-split-run", required=True)
    phase1_final_feature_manifest.add_argument("--dataset-root", required=True)
    phase1_final_feature_manifest.add_argument(
        "--output-root",
        default="artifacts/phase1_final_feature_manifest",
    )
    phase1_final_feature_manifest.add_argument(
        "--feature-config",
        default="configs/phase1/final_feature_manifest.json",
    )
    phase1_final_feature_manifest.add_argument(
        "--readiness-config",
        default="configs/phase1/final_split_feature_leakage.json",
    )

    phase1_final_leakage_audit = subparsers.add_parser(
        "phase1_final_leakage_audit",
        help="Generate the final Phase 1 manifest-level leakage audit without opening claims",
    )
    phase1_final_leakage_audit.add_argument("--profile", default="t4_safe")
    phase1_final_leakage_audit.add_argument("--config", required=True)
    phase1_final_leakage_audit.add_argument("--final-split-run", required=True)
    phase1_final_leakage_audit.add_argument("--final-feature-run", required=True)
    phase1_final_leakage_audit.add_argument(
        "--output-root",
        default="artifacts/phase1_final_leakage_audit",
    )
    phase1_final_leakage_audit.add_argument(
        "--audit-config",
        default="configs/phase1/final_leakage_audit.json",
    )
    phase1_final_leakage_audit.add_argument(
        "--readiness-config",
        default="configs/phase1/final_split_feature_leakage.json",
    )

    phase1_final_comparator_runner = subparsers.add_parser(
        "phase1_final_comparator_runner_readiness",
        help="Record final comparator runner/output-manifest readiness without opening claims",
    )
    phase1_final_comparator_runner.add_argument("--profile", default="t4_safe")
    phase1_final_comparator_runner.add_argument("--config", required=True)
    phase1_final_comparator_runner.add_argument("--final-split-run", required=True)
    phase1_final_comparator_runner.add_argument("--final-feature-run", required=True)
    phase1_final_comparator_runner.add_argument("--final-leakage-run", required=True)
    phase1_final_comparator_runner.add_argument(
        "--output-root",
        default="artifacts/phase1_final_comparator_runner_readiness",
    )
    phase1_final_comparator_runner.add_argument(
        "--runner-config",
        default="configs/phase1/final_comparator_runner_readiness.json",
    )
    phase1_final_comparator_runner.add_argument(
        "--artifact-config",
        default="configs/phase1/final_comparator_artifacts.json",
    )

    phase1_final_feature_matrix = subparsers.add_parser(
        "phase1_final_feature_matrix",
        help="Materialize the final Phase 1 feature matrix without opening claims",
    )
    phase1_final_feature_matrix.add_argument("--profile", default="t4_safe")
    phase1_final_feature_matrix.add_argument("--config", required=True)
    phase1_final_feature_matrix.add_argument("--final-split-run", required=True)
    phase1_final_feature_matrix.add_argument("--final-feature-run", required=True)
    phase1_final_feature_matrix.add_argument("--final-leakage-run", required=True)
    phase1_final_feature_matrix.add_argument("--runner-readiness-run", required=True)
    phase1_final_feature_matrix.add_argument("--dataset-root", required=True)
    phase1_final_feature_matrix.add_argument(
        "--output-root",
        default="artifacts/phase1_final_feature_matrix",
    )
    phase1_final_feature_matrix.add_argument(
        "--matrix-config",
        default="configs/phase1/final_feature_matrix.json",
    )

    phase1_final_comparator_run = subparsers.add_parser(
        "phase1_final_comparator_runner",
        help="Run claim-closed final feature-matrix comparators and write output manifests",
    )
    phase1_final_comparator_run.add_argument("--profile", default="t4_safe")
    phase1_final_comparator_run.add_argument("--config", required=True)
    phase1_final_comparator_run.add_argument("--feature-matrix-run", required=True)
    phase1_final_comparator_run.add_argument("--runner-readiness-run", required=True)
    phase1_final_comparator_run.add_argument(
        "--output-root",
        default="artifacts/phase1_final_comparator_runner",
    )
    phase1_final_comparator_run.add_argument(
        "--runner-config",
        default="configs/phase1/final_comparator_runner.json",
    )
    phase1_final_comparator_run.add_argument("--comparators", nargs="*")
    phase1_final_comparator_run.add_argument("--max-outer-folds", type=int)

    phase1_final_a2d_run = subparsers.add_parser(
        "phase1_final_a2d_runner",
        help="Run claim-closed final A2d covariance/tangent comparator outputs",
    )
    phase1_final_a2d_run.add_argument("--profile", default="t4_safe")
    phase1_final_a2d_run.add_argument("--config", required=True)
    phase1_final_a2d_run.add_argument("--final-split-run", required=True)
    phase1_final_a2d_run.add_argument("--final-feature-run", required=True)
    phase1_final_a2d_run.add_argument("--final-leakage-run", required=True)
    phase1_final_a2d_run.add_argument("--feature-matrix-run", required=True)
    phase1_final_a2d_run.add_argument("--dataset-root", required=True)
    phase1_final_a2d_run.add_argument("--feature-matrix-comparator-run")
    phase1_final_a2d_run.add_argument(
        "--output-root",
        default="artifacts/phase1_final_a2d_runner",
    )
    phase1_final_a2d_run.add_argument(
        "--runner-config",
        default="configs/phase1/final_a2d_runner.json",
    )
    phase1_final_a2d_run.add_argument("--max-outer-folds", type=int)

    phase1_final_reconciliation = subparsers.add_parser(
        "phase1_final_comparator_reconciliation",
        help="Reconcile feature-matrix final comparator outputs with final A2d outputs without opening claims",
    )
    phase1_final_reconciliation.add_argument("--profile", default="t4_safe")
    phase1_final_reconciliation.add_argument("--config", required=True)
    phase1_final_reconciliation.add_argument("--feature-matrix-comparator-run", required=True)
    phase1_final_reconciliation.add_argument("--final-a2d-run", required=True)
    phase1_final_reconciliation.add_argument(
        "--output-root",
        default="artifacts/phase1_final_comparator_reconciliation",
    )
    phase1_final_reconciliation.add_argument(
        "--reconciliation-config",
        default="configs/phase1/final_comparator_reconciliation.json",
    )

    phase1_final_governance_reconciliation = subparsers.add_parser(
        "phase1_final_governance_reconciliation",
        help="Reconcile final comparator outputs with controls/calibration/influence/reporting manifests without opening claims",
    )
    phase1_final_governance_reconciliation.add_argument("--profile", default="t4_safe")
    phase1_final_governance_reconciliation.add_argument("--config", required=True)
    phase1_final_governance_reconciliation.add_argument("--comparator-reconciliation-run", required=True)
    phase1_final_governance_reconciliation.add_argument(
        "--output-root",
        default="artifacts/phase1_final_governance_reconciliation",
    )
    phase1_final_governance_reconciliation.add_argument(
        "--governance-config",
        default="configs/phase1/final_governance_reconciliation.json",
    )
    phase1_final_governance_reconciliation.add_argument("--controls-config", default="configs/controls/control_suite_spec.yaml")
    phase1_final_governance_reconciliation.add_argument("--nuisance-config", default="configs/controls/nuisance_block_spec.yaml")
    phase1_final_governance_reconciliation.add_argument("--metrics-config", default="configs/eval/metrics.yaml")
    phase1_final_governance_reconciliation.add_argument("--inference-config", default="configs/eval/inference_defaults.yaml")
    phase1_final_governance_reconciliation.add_argument("--gate1-config", default="configs/gate1/decision_simulation.json")
    phase1_final_governance_reconciliation.add_argument("--gate2-config", default="configs/gate2/synthetic_validation.json")
    phase1_final_governance_reconciliation.add_argument("--final-control-manifest")
    phase1_final_governance_reconciliation.add_argument("--final-calibration-manifest")
    phase1_final_governance_reconciliation.add_argument("--final-influence-manifest")
    phase1_final_governance_reconciliation.add_argument("--final-reporting-manifest")

    phase1_final_controls = subparsers.add_parser(
        "phase1_final_controls",
        help="Compute claim-closed final logit-level controls and record missing dedicated control reruns",
    )
    phase1_final_controls.add_argument("--profile", default="t4_safe")
    phase1_final_controls.add_argument("--config", required=True)
    phase1_final_controls.add_argument("--comparator-reconciliation-run", required=True)
    phase1_final_controls.add_argument("--output-root", default="artifacts/phase1_final_controls")
    phase1_final_controls.add_argument("--controls-config", default="configs/phase1/final_controls.json")
    phase1_final_controls.add_argument("--control-suite-config", default="configs/controls/control_suite_spec.yaml")
    phase1_final_controls.add_argument("--gate2-config", default="configs/gate2/synthetic_validation.json")
    phase1_final_controls.add_argument("--dedicated-control-manifest")

    phase1_final_dedicated_controls = subparsers.add_parser(
        "phase1_final_dedicated_controls",
        help="Compute claim-closed dedicated final negative controls from the final feature matrix",
    )
    phase1_final_dedicated_controls.add_argument("--profile", default="t4_safe")
    phase1_final_dedicated_controls.add_argument("--config", required=True)
    phase1_final_dedicated_controls.add_argument("--feature-matrix-run", required=True)
    phase1_final_dedicated_controls.add_argument("--comparator-reconciliation-run", required=True)
    phase1_final_dedicated_controls.add_argument(
        "--output-root",
        default="artifacts/phase1_final_dedicated_controls",
    )
    phase1_final_dedicated_controls.add_argument(
        "--dedicated-controls-config",
        default="configs/phase1/final_dedicated_controls.json",
    )
    phase1_final_dedicated_controls.add_argument(
        "--comparator-runner-config",
        default="configs/phase1/final_comparator_runner.json",
    )
    phase1_final_dedicated_controls.add_argument("--gate2-config", default="configs/gate2/synthetic_validation.json")
    phase1_final_dedicated_controls.add_argument("--max-outer-folds", type=int)

    phase1_final_calibration = subparsers.add_parser(
        "phase1_final_calibration",
        help="Compute claim-closed final calibration diagnostics from reconciled final logits",
    )
    phase1_final_calibration.add_argument("--profile", default="t4_safe")
    phase1_final_calibration.add_argument("--config", required=True)
    phase1_final_calibration.add_argument("--comparator-reconciliation-run", required=True)
    phase1_final_calibration.add_argument("--output-root", default="artifacts/phase1_final_calibration")
    phase1_final_calibration.add_argument("--calibration-config", default="configs/phase1/final_calibration.json")
    phase1_final_calibration.add_argument("--metrics-config", default="configs/eval/metrics.yaml")
    phase1_final_calibration.add_argument("--inference-config", default="configs/eval/inference_defaults.yaml")
    phase1_final_calibration.add_argument("--gate1-config", default="configs/gate1/decision_simulation.json")

    phase1_final_influence = subparsers.add_parser(
        "phase1_final_influence",
        help="Compute claim-closed final subject influence diagnostics from reconciled final logits",
    )
    phase1_final_influence.add_argument("--profile", default="t4_safe")
    phase1_final_influence.add_argument("--config", required=True)
    phase1_final_influence.add_argument("--comparator-reconciliation-run", required=True)
    phase1_final_influence.add_argument("--output-root", default="artifacts/phase1_final_influence")
    phase1_final_influence.add_argument("--influence-config", default="configs/phase1/final_influence.json")
    phase1_final_influence.add_argument("--gate1-config", default="configs/gate1/decision_simulation.json")
    phase1_final_influence.add_argument("--gate2-config", default="configs/gate2/synthetic_validation.json")

    phase1_final_reporting = subparsers.add_parser(
        "phase1_final_reporting",
        help="Assemble the claim-closed final Phase 1 reporting package from governance reconciliation artifacts",
    )
    phase1_final_reporting.add_argument("--profile", default="t4_safe")
    phase1_final_reporting.add_argument("--config", required=True)
    phase1_final_reporting.add_argument("--governance-reconciliation-run", required=True)
    phase1_final_reporting.add_argument("--output-root", default="artifacts/phase1_final_reporting")
    phase1_final_reporting.add_argument("--reporting-config", default="configs/phase1/final_reporting.json")
    phase1_final_reporting.add_argument(
        "--governance-config",
        default="configs/phase1/final_governance_reconciliation.json",
    )

    phase1_final_claim_state_closeout = subparsers.add_parser(
        "phase1_final_claim_state_closeout",
        help="Record final Phase 1 fail-closed claim-state disposition from governance reconciliation",
    )
    phase1_final_claim_state_closeout.add_argument("--profile", default="t4_safe")
    phase1_final_claim_state_closeout.add_argument("--config", required=True)
    phase1_final_claim_state_closeout.add_argument("--governance-reconciliation-run", required=True)
    phase1_final_claim_state_closeout.add_argument(
        "--output-root",
        default="artifacts/phase1_final_claim_state_closeout",
    )
    phase1_final_claim_state_closeout.add_argument(
        "--closeout-config",
        default="configs/phase1/final_claim_state_closeout.json",
    )

    phase1_final_remediation_plan = subparsers.add_parser(
        "phase1_final_remediation_plan",
        help="Record claim-closed remediation plan after fail-closed final claim-state closeout",
    )
    phase1_final_remediation_plan.add_argument("--profile", default="t4_safe")
    phase1_final_remediation_plan.add_argument("--config", required=True)
    phase1_final_remediation_plan.add_argument("--claim-state-closeout-run", required=True)
    phase1_final_remediation_plan.add_argument(
        "--output-root",
        default="artifacts/phase1_final_remediation_plan",
    )
    phase1_final_remediation_plan.add_argument(
        "--remediation-config",
        default="configs/phase1/final_remediation_plan.json",
    )

    phase1_final_controls_remediation_audit = subparsers.add_parser(
        "phase1_final_controls_remediation_audit",
        help="Audit failed final controls after claim-closed remediation planning",
    )
    phase1_final_controls_remediation_audit.add_argument("--profile", default="t4_safe")
    phase1_final_controls_remediation_audit.add_argument("--config", required=True)
    phase1_final_controls_remediation_audit.add_argument("--final-remediation-plan-run", required=True)
    phase1_final_controls_remediation_audit.add_argument("--final-controls-run", required=True)
    phase1_final_controls_remediation_audit.add_argument("--final-dedicated-controls-run", required=True)
    phase1_final_controls_remediation_audit.add_argument(
        "--output-root",
        default="artifacts/phase1_final_controls_remediation_audit",
    )
    phase1_final_controls_remediation_audit.add_argument(
        "--audit-config",
        default="configs/phase1/final_controls_remediation_audit.json",
    )
    phase1_final_controls_remediation_audit.add_argument(
        "--final-controls-config",
        default="configs/phase1/final_controls.json",
    )
    phase1_final_controls_remediation_audit.add_argument(
        "--dedicated-controls-config",
        default="configs/phase1/final_dedicated_controls.json",
    )
    phase1_final_controls_remediation_audit.add_argument(
        "--control-suite-config",
        default="configs/controls/control_suite_spec.yaml",
    )
    phase1_final_controls_remediation_audit.add_argument(
        "--gate2-config",
        default="configs/gate2/synthetic_validation.json",
    )

    for phase in ("phase05_real", "phase1_real", "phase2_real", "phase3_real"):
        phase_parser = subparsers.add_parser(phase, help=f"Guarded {phase} command")
        phase_parser.add_argument("--profile", default="a100_fast")
        phase_parser.add_argument("--config", default="configs/prereg/prereg_bundle.json")
        phase_parser.add_argument("--phase-config", default="configs/phase05/observability.json")
        phase_parser.add_argument("--output-root", default="artifacts/phase05")
        phase_parser.add_argument("--readiness-run")
        phase_parser.add_argument("--dataset-root")
        phase_parser.add_argument("--smoke", action="store_true")
        phase_parser.add_argument("--model-smoke", action="store_true")
        phase_parser.add_argument("--a2c-smoke", action="store_true")
        phase_parser.add_argument("--a2d-smoke", action="store_true")
        phase_parser.add_argument("--a3-smoke", action="store_true")
        phase_parser.add_argument("--a4-smoke", action="store_true")
        phase_parser.add_argument("--comparators", nargs="*")
        phase_parser.add_argument("--max-outer-folds", type=int, default=2)
        phase_parser.add_argument("--outer-test-subjects", nargs="*")
        phase_parser.add_argument("--max-trials-per-session", type=int)

    report = subparsers.add_parser("report_compile", help="Compile available artefact summary")
    report.add_argument("--profile", default="t4_safe")
    report.add_argument("--run", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "audit":
            config = load_config(args.config)
            dataset_root = Path(args.dataset_root or config.get("dataset_root", "ds004752"))
            output_root = Path(args.output_root or config.get("gate0_output_root", "artifacts/gate0"))
            result = run_gate0_audit(
                dataset_root=dataset_root,
                output_root=output_root,
                include_signal=args.include_signal,
                signal_max_sessions=args.signal_max_sessions,
                signal_subjects=args.subjects,
                signal_sessions=args.sessions,
            )
            print(f"Gate 0 audit complete: {result.output_dir}")
            print(f"Manifest: {result.manifest_path}")
            print(f"Materialization report: {result.materialization_report_path}")
            return 0

        if args.command == "smoke":
            config = load_config(args.config)
            dataset_root = Path(args.dataset_root or config.get("dataset_root", "ds004752"))
            if not dataset_root.exists():
                raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
            print(f"Smoke OK: profile={args.profile} config={args.config} dataset={dataset_root}")
            return 0

        if args.command == "synthetic":
            output_root = Path(args.output_root)
            output_root.mkdir(parents=True, exist_ok=True)
            path = output_root / "synthetic_placeholder.json"
            path.write_text(
                '{\n'
                '  "status": "placeholder",\n'
                '  "message": "Implement Gate 2 generator/recovery before locking thresholds."\n'
                '}\n',
                encoding="utf-8",
            )
            print(f"Synthetic placeholder written: {path}")
            return 0

        if args.command == "gate1":
            config = load_config(args.config)
            result = run_gate1_decision(
                gate0_run=args.gate0_run,
                config=config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Gate 1 decision layer complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Decision memo: {result.decision_memo_path}")
            return 0

        if args.command == "gate2":
            config = load_config(args.config)
            result = run_gate2_synthetic_validation(
                gate1_run=args.gate1_run,
                config=config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Gate 2 synthetic validation complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Threshold registry: {result.threshold_registry_path}")
            return 0

        if args.command == "gate25":
            config = load_config(args.config)
            result = run_prereg_assembly(
                gate2_run=args.gate2_run,
                config=config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Gate 2.5 prereg bundle complete: {result.output_dir}")
            print(f"Prereg bundle: {result.prereg_bundle_path}")
            print(f"Summary: {result.summary_path}")
            return 0

        if args.command == "phase05_real":
            phase_config = load_config(args.phase_config)
            result = run_phase05_observability(
                prereg_bundle=args.config,
                config=phase_config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Phase 0.5 observability-only workflow complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase05_estimators":
            estimator_config = load_config(args.config)
            result = run_phase05_estimators(
                prereg_bundle=args.prereg_bundle,
                phase05_run=args.phase05_run,
                dataset_root=args.dataset_root,
                config=estimator_config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                subjects=args.subjects,
                max_subjects=args.max_subjects,
                max_sessions=args.max_sessions,
                max_trials_per_session=args.max_trials_per_session,
                n_permutations=args.n_permutations,
            )
            print(f"Phase 0.5 observability estimators complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_gap_review":
            result = run_phase1_gap_review(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                reviewed_runs={
                    "A2_A2b": args.a2_a2b_run,
                    "A2c_CORAL": args.a2c_run,
                    "A2d_riemannian": args.a2d_run,
                    "A3_distillation": args.a3_run,
                    "A4_privileged": args.a4_run,
                },
            )
            print(f"Phase 1 comparator-suite gap review complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_governance_readiness":
            result = run_phase1_governance_readiness(
                prereg_bundle=args.config,
                gap_review_run=args.gap_review_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Phase 1 governance readiness package complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_claim_package_plan":
            result = run_phase1_final_claim_package_plan(
                prereg_bundle=args.config,
                governance_run=args.governance_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"package": args.package_config},
            )
            print(f"Phase 1 final claim-package plan complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_comparator_artifact_plan":
            result = run_phase1_final_comparator_artifact_plan(
                prereg_bundle=args.config,
                claim_package_run=args.claim_package_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "artifact": args.artifact_config,
                    "claim_package": args.claim_package_config,
                },
            )
            print(f"Phase 1 final comparator artifact plan complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_split_feature_leakage_plan":
            result = run_phase1_final_split_feature_leakage_plan(
                prereg_bundle=args.config,
                comparator_artifact_run=args.comparator_artifact_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "readiness": args.readiness_config,
                    "artifact": args.artifact_config,
                },
            )
            print(f"Phase 1 final split/feature/leakage plan complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_split_manifest":
            result = run_phase1_final_split_manifest(
                prereg_bundle=args.config,
                split_feature_leakage_run=args.split_feature_leakage_run,
                gate0_run=args.gate0_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "manifest": args.manifest_config,
                    "readiness": args.readiness_config,
                },
            )
            print(f"Phase 1 final split manifest complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_feature_manifest":
            result = run_phase1_final_feature_manifest(
                prereg_bundle=args.config,
                final_split_run=args.final_split_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "manifest": args.feature_config,
                    "readiness": args.readiness_config,
                },
            )
            print(f"Phase 1 final feature manifest complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_leakage_audit":
            result = run_phase1_final_leakage_audit(
                prereg_bundle=args.config,
                final_split_run=args.final_split_run,
                final_feature_run=args.final_feature_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "audit": args.audit_config,
                    "readiness": args.readiness_config,
                },
            )
            print(f"Phase 1 final leakage audit complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_comparator_runner_readiness":
            result = run_phase1_final_comparator_runner_readiness(
                prereg_bundle=args.config,
                final_split_run=args.final_split_run,
                final_feature_run=args.final_feature_run,
                final_leakage_run=args.final_leakage_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "runner": args.runner_config,
                    "artifact": args.artifact_config,
                },
            )
            print(f"Phase 1 final comparator runner readiness complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_feature_matrix":
            result = run_phase1_final_feature_matrix(
                prereg_bundle=args.config,
                final_split_run=args.final_split_run,
                final_feature_run=args.final_feature_run,
                final_leakage_run=args.final_leakage_run,
                runner_readiness_run=args.runner_readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"matrix": args.matrix_config},
            )
            print(f"Phase 1 final feature matrix materialization complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_comparator_runner":
            result = run_phase1_final_comparator_runner(
                prereg_bundle=args.config,
                feature_matrix_run=args.feature_matrix_run,
                runner_readiness_run=args.runner_readiness_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"runner": args.runner_config},
                comparators=args.comparators,
                max_outer_folds=args.max_outer_folds,
            )
            print(f"Phase 1 final comparator runner complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_a2d_runner":
            result = run_phase1_final_a2d_runner(
                prereg_bundle=args.config,
                final_split_run=args.final_split_run,
                final_feature_run=args.final_feature_run,
                final_leakage_run=args.final_leakage_run,
                feature_matrix_run=args.feature_matrix_run,
                feature_matrix_comparator_run=args.feature_matrix_comparator_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"runner": args.runner_config},
                max_outer_folds=args.max_outer_folds,
            )
            print(f"Phase 1 final A2d covariance/tangent runner complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_comparator_reconciliation":
            result = run_phase1_final_comparator_reconciliation(
                prereg_bundle=args.config,
                feature_matrix_comparator_run=args.feature_matrix_comparator_run,
                final_a2d_run=args.final_a2d_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"reconciliation": args.reconciliation_config},
            )
            print(f"Phase 1 final comparator reconciliation complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_governance_reconciliation":
            result = run_phase1_final_governance_reconciliation(
                prereg_bundle=args.config,
                comparator_reconciliation_run=args.comparator_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "governance": args.governance_config,
                    "controls": args.controls_config,
                    "nuisance": args.nuisance_config,
                    "metrics": args.metrics_config,
                    "inference": args.inference_config,
                    "gate1": args.gate1_config,
                    "gate2": args.gate2_config,
                },
                final_control_manifest=args.final_control_manifest,
                final_calibration_manifest=args.final_calibration_manifest,
                final_influence_manifest=args.final_influence_manifest,
                final_reporting_manifest=args.final_reporting_manifest,
            )
            print(f"Phase 1 final governance reconciliation complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_controls":
            result = run_phase1_final_controls(
                prereg_bundle=args.config,
                comparator_reconciliation_run=args.comparator_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "controls": args.controls_config,
                    "control_suite": args.control_suite_config,
                    "gate2": args.gate2_config,
                },
                dedicated_control_manifest=args.dedicated_control_manifest,
            )
            print(f"Phase 1 final controls complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_dedicated_controls":
            result = run_phase1_final_dedicated_controls(
                prereg_bundle=args.config,
                feature_matrix_run=args.feature_matrix_run,
                comparator_reconciliation_run=args.comparator_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "dedicated_controls": args.dedicated_controls_config,
                    "comparator_runner": args.comparator_runner_config,
                    "gate2": args.gate2_config,
                },
                max_outer_folds=args.max_outer_folds,
            )
            print(f"Phase 1 final dedicated controls complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_calibration":
            result = run_phase1_final_calibration(
                prereg_bundle=args.config,
                comparator_reconciliation_run=args.comparator_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "calibration": args.calibration_config,
                    "metrics": args.metrics_config,
                    "inference": args.inference_config,
                    "gate1": args.gate1_config,
                },
            )
            print(f"Phase 1 final calibration complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_influence":
            result = run_phase1_final_influence(
                prereg_bundle=args.config,
                comparator_reconciliation_run=args.comparator_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "influence": args.influence_config,
                    "gate1": args.gate1_config,
                    "gate2": args.gate2_config,
                },
            )
            print(f"Phase 1 final influence complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_reporting":
            result = run_phase1_final_reporting(
                prereg_bundle=args.config,
                final_governance_reconciliation_run=args.governance_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "reporting": args.reporting_config,
                    "governance": args.governance_config,
                },
            )
            print(f"Phase 1 final reporting complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_claim_state_closeout":
            result = run_phase1_final_claim_state_closeout(
                prereg_bundle=args.config,
                final_governance_reconciliation_run=args.governance_reconciliation_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"closeout": args.closeout_config},
            )
            print(f"Phase 1 final claim-state closeout complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_remediation_plan":
            result = run_phase1_final_remediation_plan(
                prereg_bundle=args.config,
                final_claim_state_closeout_run=args.claim_state_closeout_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={"remediation": args.remediation_config},
            )
            print(f"Phase 1 final remediation plan complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_final_controls_remediation_audit":
            result = run_phase1_final_controls_remediation_audit(
                prereg_bundle=args.config,
                final_remediation_plan_run=args.final_remediation_plan_run,
                final_controls_run=args.final_controls_run,
                final_dedicated_controls_run=args.final_dedicated_controls_run,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                config_paths={
                    "audit": args.audit_config,
                    "final_controls": args.final_controls_config,
                    "dedicated_controls": args.dedicated_controls_config,
                    "control_suite": args.control_suite_config,
                    "gate2": args.gate2_config,
                },
            )
            print(f"Phase 1 final controls remediation audit complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and sum(
            bool(flag)
            for flag in [args.smoke, args.model_smoke, args.a2c_smoke, args.a2d_smoke, args.a3_smoke, args.a4_smoke]
        ) > 1:
            raise ValueError(
                "phase1_real can use only one of --smoke, --model-smoke, --a2c-smoke, --a2d-smoke, --a3-smoke or --a4-smoke"
            )

        if args.command == "phase1_real" and args.a4_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --a4-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --a4-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/a4_smoke.json"
            a4_config = load_config(phase_config_path)
            result = run_phase1_a4_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=a4_config,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A4 privileged smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.a3_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --a3-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --a3-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/a3_smoke.json"
            a3_config = load_config(phase_config_path)
            result = run_phase1_a3_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=a3_config,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A3 distillation smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.a2c_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --a2c-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --a2c-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/a2c_smoke.json"
            a2c_config = load_config(phase_config_path)
            result = run_phase1_a2c_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=a2c_config,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A2c CORAL smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.a2d_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --a2d-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --a2d-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/a2d_smoke.json"
            a2d_config = load_config(phase_config_path)
            result = run_phase1_a2d_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=a2d_config,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A2d Riemannian smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.model_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --model-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --model-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/model_smoke.json"
            model_config = load_config(phase_config_path)
            result = run_phase1_model_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=model_config,
                repo_root=Path.cwd(),
                comparators=args.comparators,
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A2/A2b model smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --smoke requires --dataset-root")
            result = run_phase1_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
            )
            print(f"Phase 1 decoder smoke contract complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command in {"phase1_real", "phase2_real", "phase3_real"}:
            assert_real_phase_allowed(args.command, args.config)
            print(f"{args.command} allowed by locked prereg bundle")
            return 0

        if args.command == "report_compile":
            run_path = Path(args.run)
            if run_path.is_file():
                run_path = Path(run_path.read_text(encoding="utf-8").strip())
            if not run_path.exists():
                raise FileNotFoundError(f"Run path not found: {run_path}")
            files = sorted(p for p in run_path.rglob("*") if p.is_file())
            print(f"Report compile input: {run_path}")
            print(f"Files discovered: {len(files)}")
            return 0

    except (
        FileNotFoundError,
        ValueError,
        GuardError,
        Gate1Error,
        Gate2Error,
        PreregError,
        Phase05Error,
        Phase05EstimatorError,
        Phase1SmokeError,
        Phase1ModelSmokeError,
        Phase1GapReviewError,
        Phase1A2cSmokeError,
        Phase1A2dSmokeError,
        Phase1A3SmokeError,
        Phase1A4SmokeError,
        Phase1GovernanceReadinessError,
        Phase1FinalClaimPackageError,
        Phase1FinalComparatorArtifactError,
        Phase1FinalComparatorRunnerReadinessError,
        Phase1FinalComparatorRunnerError,
        Phase1FinalComparatorReconciliationError,
        Phase1FinalGovernanceReconciliationError,
        Phase1FinalControlsError,
        Phase1FinalDedicatedControlsError,
        Phase1FinalCalibrationError,
        Phase1FinalInfluenceError,
        Phase1FinalReportingError,
        Phase1FinalClaimStateCloseoutError,
        Phase1FinalRemediationPlanError,
        Phase1FinalControlsRemediationAuditError,
        Phase1FinalA2dRunnerError,
        Phase1FinalSplitFeatureLeakageError,
        Phase1FinalFeatureManifestError,
        Phase1FinalFeatureMatrixError,
        Phase1FinalLeakageAuditError,
        Phase1FinalSplitManifestError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
