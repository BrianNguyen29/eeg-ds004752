"""V5.6 Tranche 2.4 feature-matrix materializer skeleton.

This runner records the non-claim contract for a future scalp EEG feature
matrix materializer. It does not read EDF payloads, materialize feature values,
train models, run comparators, compute metrics, or open claims.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..phase1.smoke import _write_json, _write_latest_pointer
from .benchmark import assert_signal_ready_gate0, load_benchmark_spec


class V56FeatureMatrixMaterializerSkeletonError(RuntimeError):
    """Raised when the V5.6 materializer skeleton cannot be recorded."""


@dataclass(frozen=True)
class V56FeatureMatrixMaterializerSkeletonResult:
    output_dir: Path
    skeleton_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


def run_v56_feature_matrix_materializer_skeleton(
    *,
    gate0_run: str | Path,
    split_registry_lock_run: str | Path,
    feature_provenance_run: str | Path,
    feature_matrix_plan_run: str | Path,
    leakage_audit_plan_run: str | Path,
    benchmark_spec: str | Path = "configs/v56/benchmark_spec.json",
    materializer_skeleton_config: str | Path = "configs/v56/feature_matrix_materializer_skeleton.json",
    output_root: str | Path = "artifacts/v56_feature_matrix_materializer_skeleton",
    repo_root: str | Path | None = None,
) -> V56FeatureMatrixMaterializerSkeletonResult:
    """Write a claim-closed materializer skeleton artifact."""

    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    gate0_path = _resolve_path(Path(gate0_run), must_be_dir=True)
    split_lock_run = _resolve_path(Path(split_registry_lock_run), must_be_dir=True)
    provenance_run = _resolve_path(Path(feature_provenance_run), must_be_dir=True)
    feature_plan_run = _resolve_path(Path(feature_matrix_plan_run), must_be_dir=True)
    leakage_plan_run = _resolve_path(Path(leakage_audit_plan_run), must_be_dir=True)
    output_root = Path(output_root)

    benchmark = load_benchmark_spec(_repo_path(repo, benchmark_spec))
    config = load_config(_repo_path(repo, materializer_skeleton_config))
    manifest = _read_json(gate0_path / "manifest.json")
    cohort_lock = _read_json(gate0_path / "cohort_lock.json")
    split_lock = _read_json(split_lock_run / "v56_split_registry_lock.json")
    provenance = _read_json(provenance_run / "v56_feature_provenance_populated.json")
    feature_plan = _read_json(feature_plan_run / "v56_feature_matrix_plan.json")
    feature_plan_validation = _read_json(feature_plan_run / "v56_feature_matrix_plan_validation.json")
    leakage_plan = _read_json(leakage_plan_run / "v56_feature_matrix_leakage_audit_plan.json")
    leakage_validation = _read_json(leakage_plan_run / "v56_feature_matrix_leakage_audit_plan_validation.json")

    assert_signal_ready_gate0(manifest, cohort_lock, benchmark)
    validation = _validate_inputs(
        config=config,
        manifest=manifest,
        cohort_lock=cohort_lock,
        split_lock=split_lock,
        provenance=provenance,
        feature_plan=feature_plan,
        feature_plan_validation=feature_plan_validation,
        leakage_plan=leakage_plan,
        leakage_validation=leakage_validation,
    )
    if validation["blocking_errors"]:
        raise V56FeatureMatrixMaterializerSkeletonError(
            f"Materializer skeleton prerequisites failed: {validation['blocking_errors']}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    skeleton = _build_skeleton(
        timestamp=timestamp,
        config=config,
        benchmark=benchmark,
        manifest=manifest,
        cohort_lock=cohort_lock,
        split_lock=split_lock,
        feature_plan=feature_plan,
        leakage_plan=leakage_plan,
        validation=validation,
        gate0_run=gate0_path,
        split_lock_run=split_lock_run,
        provenance_run=provenance_run,
        feature_plan_run=feature_plan_run,
        leakage_plan_run=leakage_plan_run,
        repo_root=repo,
        config_path=Path(materializer_skeleton_config),
    )
    summary = _build_summary(
        output_dir=output_dir,
        timestamp=timestamp,
        benchmark=benchmark,
        skeleton=skeleton,
        validation=validation,
        repo_root=repo,
    )

    skeleton_path = output_dir / "v56_feature_matrix_materializer_skeleton.json"
    summary_path = output_dir / "v56_feature_matrix_materializer_skeleton_summary.json"
    validation_path = output_dir / "v56_feature_matrix_materializer_skeleton_validation.json"
    report_path = output_dir / "v56_feature_matrix_materializer_skeleton_report.md"

    _write_json(skeleton_path, skeleton)
    _write_json(summary_path, summary)
    _write_json(validation_path, validation)
    report_path.write_text(_render_report(summary, validation, skeleton), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return V56FeatureMatrixMaterializerSkeletonResult(
        output_dir=output_dir,
        skeleton_path=skeleton_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _repo_path(repo: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else repo / value


def _resolve_path(path: Path, *, must_be_dir: bool) -> Path:
    if path.is_file() and path.name == "latest.txt":
        path = Path(path.read_text(encoding="utf-8").strip())
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if must_be_dir and not path.is_dir():
        raise V56FeatureMatrixMaterializerSkeletonError(f"Expected directory path, got: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise V56FeatureMatrixMaterializerSkeletonError(f"JSON root must be an object: {path}")
    return data


def _validate_inputs(
    *,
    config: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    split_lock: dict[str, Any],
    provenance: dict[str, Any],
    feature_plan: dict[str, Any],
    feature_plan_validation: dict[str, Any],
    leakage_plan: dict[str, Any],
    leakage_validation: dict[str, Any],
) -> dict[str, Any]:
    errors = []
    required = config["required_upstream"]
    if manifest.get("manifest_status") != required["gate0_manifest_status"]:
        errors.append("gate0_manifest_not_signal_ready")
    if cohort_lock.get("cohort_lock_status") != required["cohort_lock_status"]:
        errors.append("cohort_lock_not_signal_ready")
    if split_lock.get("status") != required["split_registry_lock_status"]:
        errors.append("split_registry_lock_status_mismatch")
    if provenance.get("status") != required["feature_provenance_status"]:
        errors.append("feature_provenance_status_mismatch")
    if feature_plan.get("status") != required["feature_matrix_plan_status"]:
        errors.append("feature_matrix_plan_status_mismatch")
    if feature_plan_validation.get("status") != required["feature_matrix_plan_validation_status"]:
        errors.append("feature_matrix_plan_validation_status_mismatch")
    if leakage_plan.get("status") != required["leakage_audit_plan_status"]:
        errors.append("leakage_audit_plan_status_mismatch")
    if leakage_validation.get("status") != required["leakage_audit_plan_validation_status"]:
        errors.append("leakage_audit_plan_validation_status_mismatch")
    if provenance.get("missing_sources"):
        errors.append("feature_provenance_has_missing_sources")

    contract = config["materializer_contract"]
    if contract.get("read_edf_payloads_now") is not False:
        errors.append("skeleton_attempts_to_read_edf_payloads")
    if contract.get("write_feature_values_now") is not False:
        errors.append("skeleton_attempts_to_write_feature_values")
    if contract.get("allowed_source_modality_at_test_time") != "scalp_eeg":
        errors.append("test_time_modality_not_scalp_eeg")
    inference = split_lock.get("test_time_inference", {})
    if inference.get("allow_ieeg") is not False:
        errors.append("test_time_ieeg_allowed")
    if inference.get("allow_beamforming_bridge") is not False:
        errors.append("test_time_beamforming_bridge_allowed")

    boundary = leakage_plan.get("scientific_boundary", {})
    if boundary.get("feature_matrix_materialized") is not False:
        errors.append("leakage_plan_indicates_feature_matrix_materialized")
    if boundary.get("runtime_comparator_logs_audited") is not False:
        errors.append("leakage_plan_indicates_runtime_logs_audited")

    return {
        "status": "v56_feature_matrix_materializer_skeleton_validation_passed" if not errors else "v56_feature_matrix_materializer_skeleton_validation_failed",
        "blocking_errors": errors,
        "claim_closed": True,
        "feature_matrix_materialized": False,
        "edf_payloads_read": False,
        "feature_values_written": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "n_locked_folds": len(split_lock.get("folds", [])),
        "n_primary_feature_sets": len(feature_plan.get("primary_feature_sets", [])),
        "test_time_inference": inference,
        "scientific_limit": "Validation covers materializer skeleton only; it is not feature data or model evidence.",
    }


def _build_skeleton(
    *,
    timestamp: str,
    config: dict[str, Any],
    benchmark: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    split_lock: dict[str, Any],
    feature_plan: dict[str, Any],
    leakage_plan: dict[str, Any],
    validation: dict[str, Any],
    gate0_run: Path,
    split_lock_run: Path,
    provenance_run: Path,
    feature_plan_run: Path,
    leakage_plan_run: Path,
    repo_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    return {
        "artifact_family": "v56_feature_matrix_materializer_skeleton",
        "created_utc": timestamp,
        "status": "planned_feature_matrix_materializer_skeleton_recorded",
        "skeleton_id": config["skeleton_id"],
        "benchmark_name": benchmark["benchmark_name"],
        "program_version": benchmark["program_version"],
        "record_scope": benchmark["record_scope"],
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "claim_ready": False,
        "gate0_run": str(gate0_run),
        "split_registry_lock_run": str(split_lock_run),
        "feature_provenance_run": str(provenance_run),
        "feature_matrix_plan_run": str(feature_plan_run),
        "leakage_audit_plan_run": str(leakage_plan_run),
        "gate0_manifest_status": manifest["manifest_status"],
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "n_locked_folds": validation["n_locked_folds"],
        "feature_matrix_plan_status": feature_plan["status"],
        "leakage_audit_plan_status": leakage_plan["status"],
        "test_time_inference": split_lock["test_time_inference"],
        "materializer_contract": config["materializer_contract"],
        "planned_validation_rules": config["planned_validation_rules"],
        "artifact_boundary": config["artifact_boundary"],
        "source_hashes": {
            "materializer_skeleton_config": _sha256(repo_root / config_path),
            "split_registry_lock": _sha256(split_lock_run / "v56_split_registry_lock.json"),
            "feature_matrix_plan": _sha256(feature_plan_run / "v56_feature_matrix_plan.json"),
            "leakage_audit_plan": _sha256(leakage_plan_run / "v56_feature_matrix_leakage_audit_plan.json"),
        },
        "validation_status": validation["status"],
        "scientific_boundary": {
            "edf_payloads_read": False,
            "feature_matrix_materialized": False,
            "feature_values_written": False,
            "model_training_run": False,
            "comparator_execution_run": False,
            "efficacy_metrics_computed": False,
            "claim_ready": False,
            "allowed_interpretation": "Materializer skeleton is ready for manual review before real feature values are written.",
        },
        "claim_blockers": config["claim_blockers_after_success"],
        "repo": _repo_state(repo_root),
    }


def _build_summary(
    *,
    output_dir: Path,
    timestamp: str,
    benchmark: dict[str, Any],
    skeleton: dict[str, Any],
    validation: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "artifact_family": "v56_feature_matrix_materializer_skeleton",
        "status": skeleton["status"],
        "validation_status": validation["status"],
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "claim_ready": False,
        "created_utc": timestamp,
        "output_dir": str(output_dir),
        "skeleton_id": skeleton["skeleton_id"],
        "n_locked_folds": skeleton["n_locked_folds"],
        "edf_payloads_read": False,
        "feature_matrix_materialized": False,
        "feature_values_written": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "artifact_sha256": _sha256_json(skeleton),
        "repo": _repo_state(repo_root),
        "next_step": "manual_review_then_implement_real_scalp_feature_matrix_materializer",
    }


def _render_report(summary: dict[str, Any], validation: dict[str, Any], skeleton: dict[str, Any]) -> str:
    lines = [
        "# V5.6 Feature Matrix Materializer Skeleton",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Validation: `{summary['validation_status']}`",
        f"- Claim closed: `{summary['claim_closed']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Locked folds: `{summary['n_locked_folds']}`",
        "",
        "## Integrity Boundary",
        "",
        "- This artifact is a materializer skeleton only.",
        "- No EDF payloads were read.",
        "- No feature values were materialized.",
        "- No model was trained.",
        "- No comparator was executed.",
        "- No efficacy metric was computed.",
        "- No claim is opened.",
        "",
        "## Test-Time Policy",
        "",
        f"- Modality: `{skeleton['test_time_inference'].get('modality')}`",
        f"- Allow iEEG: `{skeleton['test_time_inference'].get('allow_ieeg')}`",
        f"- Allow beamforming bridge: `{skeleton['test_time_inference'].get('allow_beamforming_bridge')}`",
        "",
        "## Claim Blockers",
        "",
    ]
    for blocker in skeleton["claim_blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Next Step", "", f"- {summary['next_step']}", ""])
    return "\n".join(lines)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _repo_state(repo_root: Path) -> dict[str, Any]:
    return {
        "path": str(repo_root),
        "commit": _git_output(repo_root, ["git", "rev-parse", "HEAD"]),
        "branch": _git_output(repo_root, ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "working_tree_clean": _git_output(repo_root, ["git", "status", "--short"]) == "",
    }


def _git_output(repo_root: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(args, cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"
