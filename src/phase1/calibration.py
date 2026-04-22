"""Phase 1 calibration-package readiness checks.

This module is intentionally fail-closed. It verifies whether the final
calibration package exists and is claim-evaluable; it does not fabricate logits,
calibration curves, or claim-bearing calibration evidence from smoke outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_config


REQUIRED_FINAL_CALIBRATION_ARTIFACTS = [
    "final_comparator_logits",
    "pooled_ece_10_bins",
    "subject_level_ece",
    "brier_score",
    "negative_log_likelihood",
    "reliability_table",
    "reliability_diagram",
    "risk_coverage_curve",
    "calibration_delta_vs_baseline",
]


def evaluate_calibration_package(
    *,
    metrics_config_path: str | Path,
    inference_config_path: str | Path,
    gate1_config_path: str | Path,
    final_calibration_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    """Evaluate calibration-package readiness without estimating calibration."""

    metrics_config_path = Path(metrics_config_path)
    inference_config_path = Path(inference_config_path)
    gate1_config_path = Path(gate1_config_path)
    metrics_config = load_config(metrics_config_path)
    inference_config = load_config(inference_config_path)
    gate1_config = load_config(gate1_config_path)

    manifest_path = Path(final_calibration_manifest_path) if final_calibration_manifest_path else None
    manifest = _load_optional_manifest(manifest_path)
    provided_artifacts = sorted(manifest.get("artifacts", [])) if isinstance(manifest.get("artifacts"), list) else []
    manifest_status = str(manifest.get("status") or "")
    calibration_package_passed = manifest.get("calibration_package_passed")
    smoke_promoted = manifest.get("smoke_artifacts_promoted")
    missing_artifacts = [
        item for item in REQUIRED_FINAL_CALIBRATION_ARTIFACTS if item not in provided_artifacts
    ]

    metrics_status = str(metrics_config.get("metrics_status") or metrics_config.get("status") or "")
    inference_status = str(inference_config.get("inference_status") or inference_config.get("status") or "")
    blockers = []
    if metrics_status != "executable":
        blockers.append("metrics_config_still_draft")
    if inference_status != "executable":
        blockers.append("inference_config_still_draft")
    if manifest_path is None or not manifest_path.exists():
        blockers.append("final_calibration_manifest_missing")
    elif manifest_status not in {
        "phase1_final_calibration_manifest_recorded",
        "phase1_final_calibration_complete_claim_closed",
    }:
        blockers.append("final_calibration_manifest_status_not_claim_evaluable")
    if manifest_path is not None and manifest_path.exists() and calibration_package_passed is not True:
        blockers.append("final_calibration_package_not_passed")
    if smoke_promoted is True:
        blockers.append("final_calibration_manifest_promotes_smoke_artifacts")
    if missing_artifacts:
        blockers.append("final_calibration_artifacts_missing")

    max_allowed_delta_ece = gate1_config.get("max_allowed_delta_ece")
    return {
        "status": (
            "phase1_calibration_package_not_claim_evaluable"
            if blockers
            else "phase1_calibration_package_claim_evaluable"
        ),
        "calibration_package_executable": not blockers,
        "claim_evaluable": not blockers,
        "claim_blocker": bool(blockers),
        "blockers": blockers,
        "metrics_config_status": metrics_status,
        "inference_config_status": inference_status,
        "metrics_config_path": str(metrics_config_path),
        "inference_config_path": str(inference_config_path),
        "gate1_config_path": str(gate1_config_path),
        "final_calibration_manifest_path": str(manifest_path) if manifest_path else None,
        "final_calibration_manifest_status": manifest_status or None,
        "calibration_package_passed": calibration_package_passed,
        "smoke_artifacts_promoted": smoke_promoted if smoke_promoted is not None else False,
        "provided_artifacts": provided_artifacts,
        "required_final_calibration_artifacts": REQUIRED_FINAL_CALIBRATION_ARTIFACTS,
        "missing_final_calibration_artifacts": missing_artifacts,
        "threshold_sources": {
            "max_allowed_delta_ece": max_allowed_delta_ece,
            "source": str(gate1_config_path),
        },
        "scientific_limit": (
            "This readiness check does not compute ECE, Brier, NLL, reliability diagrams, "
            "or any calibration claim. Smoke-logit diagnostics remain non-claim."
        ),
    }


def _load_optional_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_config(path)
    return data if isinstance(data, dict) else {}
