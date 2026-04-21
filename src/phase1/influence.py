"""Phase 1 influence-package readiness checks.

The influence package must be based on final fold-level results and
leave-one-subject-out claim-state checks. This module records readiness only;
it never promotes smoke diagnostics into influence evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_config


REQUIRED_FINAL_INFLUENCE_ARTIFACTS = [
    "subject_level_fold_metrics",
    "leave_one_subject_out_deltas",
    "max_single_subject_contribution_share",
    "claim_state_leave_one_subject_out",
    "influence_veto_decision",
]


def evaluate_influence_package(
    *,
    gate1_config_path: str | Path,
    gate2_config_path: str | Path,
    final_influence_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate influence-package readiness without estimating influence."""

    gate1_config_path = Path(gate1_config_path)
    gate2_config_path = Path(gate2_config_path)
    gate1_config = load_config(gate1_config_path)
    gate2_config = load_config(gate2_config_path)

    manifest_path = Path(final_influence_manifest_path) if final_influence_manifest_path else None
    manifest = _load_optional_manifest(manifest_path)
    provided_artifacts = sorted(manifest.get("artifacts", [])) if isinstance(manifest.get("artifacts"), list) else []
    missing_artifacts = [item for item in REQUIRED_FINAL_INFLUENCE_ARTIFACTS if item not in provided_artifacts]

    blockers = []
    if manifest_path is None or not manifest_path.exists():
        blockers.append("final_influence_manifest_missing")
    if missing_artifacts:
        blockers.append("final_influence_artifacts_missing")
    if manifest.get("leave_one_subject_out_executed") is not True:
        blockers.append("leave_one_subject_out_claim_state_checks_missing")

    gate1_ceiling = gate1_config.get("influence_ceiling")
    gate2_ceiling = gate2_config.get("frozen_threshold_defaults", {}).get("influence_ceiling")
    return {
        "status": (
            "phase1_influence_package_not_claim_evaluable"
            if blockers
            else "phase1_influence_package_claim_evaluable"
        ),
        "influence_package_executable": not blockers,
        "claim_evaluable": not blockers,
        "claim_blocker": bool(blockers),
        "blockers": blockers,
        "gate1_config_path": str(gate1_config_path),
        "gate2_config_path": str(gate2_config_path),
        "final_influence_manifest_path": str(manifest_path) if manifest_path else None,
        "provided_artifacts": provided_artifacts,
        "required_final_influence_artifacts": REQUIRED_FINAL_INFLUENCE_ARTIFACTS,
        "missing_final_influence_artifacts": missing_artifacts,
        "threshold_sources": {
            "gate1_influence_ceiling": gate1_ceiling,
            "gate2_frozen_influence_ceiling": gate2_ceiling,
        },
        "scientific_limit": (
            "This readiness check does not compute subject influence, leave-one-subject-out "
            "deltas, or influence vetoes. Smoke influence reports remain non-claim."
        ),
    }


def _load_optional_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_config(path)
    return data if isinstance(data, dict) else {}
