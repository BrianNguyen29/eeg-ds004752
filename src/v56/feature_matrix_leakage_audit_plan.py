"""V5.6 Tranche 2.3 feature-matrix leakage audit planning.

This runner records the leakage-audit contract that must pass before feature
matrix materialization or comparator execution. It does not materialize feature
values, train models, inspect runtime comparator logs, compute metrics, or open
claims.
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


class V56FeatureMatrixLeakageAuditPlanError(RuntimeError):
    """Raised when the V5.6 leakage-audit plan cannot be recorded."""


@dataclass(frozen=True)
class V56FeatureMatrixLeakageAuditPlanResult:
    output_dir: Path
    plan_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


def run_v56_feature_matrix_leakage_audit_plan(
    *,
    gate0_run: str | Path,
    split_registry_lock_run: str | Path,
    feature_provenance_run: str | Path,
    feature_matrix_plan_run: str | Path,
    benchmark_spec: str | Path = "configs/v56/benchmark_spec.json",
    leakage_audit_plan_config: str | Path = "configs/v56/feature_matrix_leakage_audit_plan.json",
    output_root: str | Path = "artifacts/v56_feature_matrix_leakage_audit_plan",
    repo_root: str | Path | None = None,
) -> V56FeatureMatrixLeakageAuditPlanResult:
    """Write a claim-closed leakage-audit plan artifact."""

    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    gate0_path = _resolve_path(Path(gate0_run), must_be_dir=True)
    split_lock_run = _resolve_path(Path(split_registry_lock_run), must_be_dir=True)
    provenance_run = _resolve_path(Path(feature_provenance_run), must_be_dir=True)
    feature_plan_run = _resolve_path(Path(feature_matrix_plan_run), must_be_dir=True)
    output_root = Path(output_root)

    benchmark = load_benchmark_spec(_repo_path(repo, benchmark_spec))
    config = load_config(_repo_path(repo, leakage_audit_plan_config))
    manifest = _read_json(gate0_path / "manifest.json")
    cohort_lock = _read_json(gate0_path / "cohort_lock.json")
    split_lock = _read_json(split_lock_run / "v56_split_registry_lock.json")
    provenance = _read_json(provenance_run / "v56_feature_provenance_populated.json")
    feature_plan = _read_json(feature_plan_run / "v56_feature_matrix_plan.json")
    feature_plan_summary = _read_json(feature_plan_run / "v56_feature_matrix_plan_summary.json")
    feature_plan_validation = _read_json(feature_plan_run / "v56_feature_matrix_plan_validation.json")

    assert_signal_ready_gate0(manifest, cohort_lock, benchmark)
    validation = _validate_inputs(
        config=config,
        manifest=manifest,
        cohort_lock=cohort_lock,
        split_lock=split_lock,
        provenance=provenance,
        feature_plan=feature_plan,
        feature_plan_summary=feature_plan_summary,
        feature_plan_validation=feature_plan_validation,
    )
    if validation["blocking_errors"]:
        raise V56FeatureMatrixLeakageAuditPlanError(
            f"Leakage-audit plan prerequisites failed: {validation['blocking_errors']}"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    plan = _build_plan(
        timestamp=timestamp,
        config=config,
        benchmark=benchmark,
        manifest=manifest,
        cohort_lock=cohort_lock,
        split_lock=split_lock,
        provenance=provenance,
        feature_plan=feature_plan,
        validation=validation,
        gate0_run=gate0_path,
        split_lock_run=split_lock_run,
        provenance_run=provenance_run,
        feature_plan_run=feature_plan_run,
        repo_root=repo,
        config_path=Path(leakage_audit_plan_config),
    )
    summary = _build_summary(
        output_dir=output_dir,
        timestamp=timestamp,
        benchmark=benchmark,
        plan=plan,
        validation=validation,
        repo_root=repo,
    )

    plan_path = output_dir / "v56_feature_matrix_leakage_audit_plan.json"
    summary_path = output_dir / "v56_feature_matrix_leakage_audit_plan_summary.json"
    validation_path = output_dir / "v56_feature_matrix_leakage_audit_plan_validation.json"
    report_path = output_dir / "v56_feature_matrix_leakage_audit_plan_report.md"

    _write_json(plan_path, plan)
    _write_json(summary_path, summary)
    _write_json(validation_path, validation)
    report_path.write_text(_render_report(summary, validation, plan), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return V56FeatureMatrixLeakageAuditPlanResult(
        output_dir=output_dir,
        plan_path=plan_path,
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
        raise V56FeatureMatrixLeakageAuditPlanError(f"Expected directory path, got: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise V56FeatureMatrixLeakageAuditPlanError(f"JSON root must be an object: {path}")
    return data


def _validate_inputs(
    *,
    config: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    split_lock: dict[str, Any],
    provenance: dict[str, Any],
    feature_plan: dict[str, Any],
    feature_plan_summary: dict[str, Any],
    feature_plan_validation: dict[str, Any],
) -> dict[str, Any]:
    errors = []
    warnings = []
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

    if split_lock.get("subject_isolation_enforced") is not True:
        errors.append("subject_isolation_not_enforced")
    inference = split_lock.get("test_time_inference", {})
    policy = config["fit_scope_policy"]
    if inference.get("modality") != policy["test_time_inference_policy"]:
        errors.append("test_time_policy_mismatch")
    if inference.get("allow_ieeg") is not policy["test_time_ieeg_allowed"]:
        errors.append("test_time_ieeg_policy_mismatch")
    if inference.get("allow_beamforming_bridge") is not policy["test_time_beamforming_bridge_allowed"]:
        errors.append("test_time_beamforming_bridge_policy_mismatch")
    if provenance.get("missing_sources"):
        errors.append("feature_provenance_has_missing_sources")
    if feature_plan.get("claim_closed") is not True or feature_plan_summary.get("claim_closed") is not True:
        errors.append("feature_matrix_plan_not_claim_closed")
    boundary = feature_plan.get("scientific_boundary", {})
    for key in ("feature_matrix_materialized", "model_training_run", "comparator_execution_run", "efficacy_metrics_computed"):
        if boundary.get(key) is not False:
            errors.append(f"feature_matrix_plan_boundary_violation:{key}")

    for fold in split_lock.get("folds", []):
        outer = fold.get("outer_test_subject")
        if outer in set(fold.get("train_subjects", [])):
            errors.append(f"{fold.get('fold_id')}:outer_test_subject_in_train_subjects")
    for source in feature_plan.get("privileged_train_time_sources", []):
        if source.get("allowed_at_test_time") is not False:
            errors.append(f"privileged_source_allowed_at_test_time:{source.get('id')}")
        if source.get("requires_train_fold_fit_only") is not True:
            warnings.append(f"privileged_source_missing_train_fold_fit_only:{source.get('id')}")

    return {
        "status": "v56_feature_matrix_leakage_audit_plan_validation_passed" if not errors else "v56_feature_matrix_leakage_audit_plan_validation_failed",
        "blocking_errors": errors,
        "warnings": warnings,
        "claim_closed": True,
        "feature_matrix_materialized": False,
        "runtime_comparator_logs_audited": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "n_folds_checked": len(split_lock.get("folds", [])),
        "n_planned_audit_checks": len(config.get("planned_audit_checks", [])),
        "test_time_inference": inference,
        "scientific_limit": "Validation covers leakage-audit planning only; it is not model evidence.",
    }


def _build_plan(
    *,
    timestamp: str,
    config: dict[str, Any],
    benchmark: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    split_lock: dict[str, Any],
    provenance: dict[str, Any],
    feature_plan: dict[str, Any],
    validation: dict[str, Any],
    gate0_run: Path,
    split_lock_run: Path,
    provenance_run: Path,
    feature_plan_run: Path,
    repo_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    return {
        "artifact_family": "v56_feature_matrix_leakage_audit_plan",
        "created_utc": timestamp,
        "status": "planned_feature_matrix_leakage_audit_recorded",
        "audit_plan_id": config["audit_plan_id"],
        "benchmark_name": benchmark["benchmark_name"],
        "program_version": benchmark["program_version"],
        "record_scope": benchmark["record_scope"],
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "claim_ready": False,
        "gate0_run": str(gate0_run),
        "split_registry_lock_run": str(split_lock_run),
        "feature_provenance_run": str(provenance_run),
        "feature_matrix_plan_run": str(feature_plan_run),
        "gate0_manifest_status": manifest["manifest_status"],
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "n_locked_folds": len(split_lock.get("folds", [])),
        "feature_matrix_plan_status": feature_plan["status"],
        "feature_matrix_plan_id": feature_plan["plan_id"],
        "fit_scope_policy": config["fit_scope_policy"],
        "planned_audit_checks": config["planned_audit_checks"],
        "artifact_boundary": config["artifact_boundary"],
        "test_time_inference": split_lock["test_time_inference"],
        "source_hashes": {
            "leakage_audit_plan_config": _sha256(repo_root / config_path),
            "split_registry_lock": _sha256(split_lock_run / "v56_split_registry_lock.json"),
            "feature_provenance": _sha256(provenance_run / "v56_feature_provenance_populated.json"),
            "feature_matrix_plan": _sha256(feature_plan_run / "v56_feature_matrix_plan.json"),
        },
        "validation_status": validation["status"],
        "scientific_boundary": {
            "feature_matrix_materialized": False,
            "runtime_comparator_logs_audited": False,
            "model_training_run": False,
            "comparator_execution_run": False,
            "efficacy_metrics_computed": False,
            "claim_ready": False,
            "allowed_interpretation": (
                "Leakage-audit plan is recorded for future feature materialization/comparator execution. "
                "No empirical model evidence is produced."
            ),
        },
        "claim_blockers": config["claim_blockers_after_success"],
        "repo": _repo_state(repo_root),
    }


def _build_summary(
    *,
    output_dir: Path,
    timestamp: str,
    benchmark: dict[str, Any],
    plan: dict[str, Any],
    validation: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "artifact_family": "v56_feature_matrix_leakage_audit_plan",
        "status": plan["status"],
        "validation_status": validation["status"],
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "claim_ready": False,
        "created_utc": timestamp,
        "output_dir": str(output_dir),
        "audit_plan_id": plan["audit_plan_id"],
        "n_locked_folds": plan["n_locked_folds"],
        "n_planned_audit_checks": len(plan["planned_audit_checks"]),
        "feature_matrix_materialized": False,
        "runtime_comparator_logs_audited": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "artifact_sha256": _sha256_json(plan),
        "repo": _repo_state(repo_root),
        "next_step": "manual_review_then_implement_feature_matrix_materializer_only_if_leakage_plan_passes",
    }


def _render_report(summary: dict[str, Any], validation: dict[str, Any], plan: dict[str, Any]) -> str:
    lines = [
        "# V5.6 Feature Matrix Leakage Audit Plan",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Validation: `{summary['validation_status']}`",
        f"- Claim closed: `{summary['claim_closed']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Locked folds: `{summary['n_locked_folds']}`",
        f"- Planned audit checks: `{summary['n_planned_audit_checks']}`",
        "",
        "## Integrity Boundary",
        "",
        "- This artifact is a leakage-audit plan only.",
        "- No feature values were materialized.",
        "- No runtime comparator logs were audited.",
        "- No model was trained.",
        "- No comparator was executed.",
        "- No efficacy metric was computed.",
        "- No claim is opened.",
        "",
        "## Test-Time Policy",
        "",
        f"- Modality: `{plan['test_time_inference'].get('modality')}`",
        f"- Allow iEEG: `{plan['test_time_inference'].get('allow_ieeg')}`",
        f"- Allow beamforming bridge: `{plan['test_time_inference'].get('allow_beamforming_bridge')}`",
        "",
        "## Claim Blockers",
        "",
    ]
    for blocker in plan["claim_blockers"]:
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
