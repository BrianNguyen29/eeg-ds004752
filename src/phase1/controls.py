"""Phase 1 executable control-suite readiness checks.

This module is intentionally fail-closed. It records whether the control suite
is executable and claim-evaluable; it does not synthesize negative-control
evidence or promote smoke artifacts into final controls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_config


REQUIRED_CONTROL_CONFIGS = [
    "scalp_only_baseline",
    "grouped_permutation",
    "nuisance_shared_control",
    "spatial_control",
    "transfer_consistency",
    "shuffled_labels",
    "shuffled_teacher",
    "time_shifted_teacher",
]

REQUIRED_FINAL_CONTROL_RESULTS = [
    "scalp_only_baseline",
    "grouped_permutation",
    "nuisance_shared_control",
    "spatial_control",
    "transfer_consistency",
    "shuffled_labels",
    "shuffled_teacher",
    "time_shifted_teacher",
]


def evaluate_control_suite(
    *,
    control_config_path: str | Path,
    nuisance_config_path: str | Path,
    gate2_config_path: str | Path,
    final_control_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate control-suite readiness without running controls."""

    control_config_path = Path(control_config_path)
    nuisance_config_path = Path(nuisance_config_path)
    gate2_config_path = Path(gate2_config_path)
    control_config = load_config(control_config_path)
    nuisance_config = load_config(nuisance_config_path)
    gate2_config = load_config(gate2_config_path)
    manifest_path = Path(final_control_manifest_path) if final_control_manifest_path else None
    manifest = _load_optional_manifest(manifest_path)
    provided_results = sorted(manifest.get("results", [])) if isinstance(manifest.get("results"), list) else []
    manifest_status = str(manifest.get("status") or "")
    control_suite_passed = manifest.get("control_suite_passed")
    smoke_promoted = manifest.get("smoke_artifacts_promoted")

    status = str(control_config.get("control_suite_status") or control_config.get("status") or "")
    configured = control_config.get("controls") or {}
    configured_controls = sorted(configured) if isinstance(configured, dict) else []
    missing_config_controls = [item for item in REQUIRED_CONTROL_CONFIGS if item not in configured_controls]
    missing_final_results = [item for item in REQUIRED_FINAL_CONTROL_RESULTS if item not in provided_results]

    blockers = []
    if status != "executable":
        blockers.append("control_suite_config_still_draft")
    if missing_config_controls:
        blockers.append("required_control_configs_missing")
    if manifest_path is None or not manifest_path.exists():
        blockers.append("final_control_manifest_missing")
    elif manifest_status not in {
        "phase1_final_controls_complete_claim_closed",
        "phase1_final_controls_manifest_recorded",
    }:
        blockers.append("final_control_manifest_status_not_claim_evaluable")
    if manifest_path is not None and manifest_path.exists() and control_suite_passed is not True:
        blockers.append("final_control_suite_not_passed")
    if smoke_promoted is True:
        blockers.append("final_control_manifest_promotes_smoke_artifacts")
    if missing_final_results:
        blockers.append("final_negative_control_results_missing")

    thresholds = {
        "negative_control_max_abs_gain": gate2_config.get("pass_criteria", {}).get("negative_control_max_abs_gain"),
        "nuisance_relative_ceiling": gate2_config.get("frozen_threshold_defaults", {}).get(
            "nuisance_relative_ceiling"
        ),
        "nuisance_absolute_ceiling": gate2_config.get("frozen_threshold_defaults", {}).get(
            "nuisance_absolute_ceiling"
        ),
        "spatial_relative_ceiling": gate2_config.get("frozen_threshold_defaults", {}).get(
            "spatial_relative_ceiling"
        ),
    }
    return {
        "status": "phase1_control_suite_not_claim_evaluable" if blockers else "phase1_control_suite_claim_evaluable",
        "control_suite_executable": not blockers,
        "claim_evaluable": not blockers,
        "claim_blocker": bool(blockers),
        "blockers": blockers,
        "config_status": status,
        "config_path": str(control_config_path),
        "nuisance_config_path": str(nuisance_config_path),
        "gate2_config_path": str(gate2_config_path),
        "final_control_manifest_path": str(manifest_path) if manifest_path else None,
        "final_control_manifest_status": manifest_status or None,
        "control_suite_passed": control_suite_passed,
        "smoke_artifacts_promoted": smoke_promoted if smoke_promoted is not None else False,
        "configured_controls": configured_controls,
        "required_control_configs": REQUIRED_CONTROL_CONFIGS,
        "missing_config_controls": missing_config_controls,
        "provided_final_control_results": provided_results,
        "required_final_control_results": REQUIRED_FINAL_CONTROL_RESULTS,
        "missing_final_control_results": missing_final_results,
        "nuisance_families": nuisance_config.get("nuisance_families", []),
        "threshold_sources": thresholds,
        "scientific_limit": (
            "This readiness check does not execute controls or prove that controls pass. "
            "It keeps claims blocked until final control results exist."
        ),
    }


def _load_optional_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_config(path)
    return data if isinstance(data, dict) else {}
