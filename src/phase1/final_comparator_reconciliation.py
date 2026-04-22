"""Reconcile final Phase 1 comparator outputs after the A2d runner.

This module links the feature-matrix comparator runner package with the final
A2d covariance/tangent package. It checks artifact presence and runtime
leakage logs, records a reconciled completeness table, and keeps claims closed.
It does not rerun models, edit logits, compute new metrics, or promote smoke
artifacts.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalComparatorReconciliationError(RuntimeError):
    """Raised when final comparator reconciliation cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalComparatorReconciliationResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "reconciliation": "configs/phase1/final_comparator_reconciliation.json",
}


def run_phase1_final_comparator_reconciliation(
    *,
    prereg_bundle: str | Path,
    feature_matrix_comparator_run: str | Path,
    final_a2d_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalComparatorReconciliationResult:
    """Reconcile final comparator output manifests while keeping claims closed."""

    prereg_bundle = Path(prereg_bundle)
    feature_matrix_comparator_run = _resolve_run_dir(Path(feature_matrix_comparator_run))
    final_a2d_run = _resolve_run_dir(Path(final_a2d_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {
        **DEFAULT_CONFIG_PATHS,
        **{key: str(value) for key, value in (config_paths or {}).items()},
    }

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    config = load_config(repo_root / config_paths["reconciliation"])
    feature_matrix_runner = _read_feature_matrix_runner_run(feature_matrix_comparator_run)
    a2d = _read_a2d_runner_run(final_a2d_run)

    input_validation = _validate_inputs(
        feature_matrix_runner=feature_matrix_runner,
        a2d=a2d,
        config=config,
    )
    completeness = _build_completeness_table(
        feature_matrix_runner=feature_matrix_runner,
        a2d=a2d,
        config=config,
        input_blockers=input_validation["blockers"],
    )
    runtime_leakage = _build_runtime_leakage_audit(completeness)
    output_manifest_index = _build_output_manifest_index(completeness)
    claim_state = _build_claim_state(
        input_validation=input_validation,
        completeness=completeness,
        runtime_leakage=runtime_leakage,
        config=config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        feature_matrix_runner=feature_matrix_runner,
        a2d=a2d,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_comparator_reconciliation_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "feature_matrix_comparator_run": str(feature_matrix_comparator_run),
        "final_a2d_run": str(final_a2d_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        feature_matrix_runner=feature_matrix_runner,
        a2d=a2d,
        completeness=completeness,
        runtime_leakage=runtime_leakage,
        input_validation=input_validation,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_comparator_reconciliation_inputs.json"
    summary_path = output_dir / "phase1_final_comparator_reconciliation_summary.json"
    report_path = output_dir / "phase1_final_comparator_reconciliation_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_comparator_reconciliation_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_comparator_reconciliation_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_comparator_reconciled_completeness_table.json", completeness)
    _write_json(output_dir / "phase1_final_comparator_reconciled_runtime_leakage_audit.json", runtime_leakage)
    _write_json(output_dir / "phase1_final_comparator_reconciled_output_manifest_index.json", output_manifest_index)
    _write_json(output_dir / "phase1_final_comparator_reconciled_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, completeness, runtime_leakage, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalComparatorReconciliationResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _resolve_run_dir(path: Path) -> Path:
    if path.is_file():
        return Path(path.read_text(encoding="utf-8").strip())
    return path


def _read_feature_matrix_runner_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "inputs": "phase1_final_comparator_runner_inputs.json",
        "summary": "phase1_final_comparator_runner_summary.json",
        "source_links": "phase1_final_comparator_runner_source_links.json",
        "input_validation": "phase1_final_comparator_runner_input_validation.json",
        "completeness": "phase1_final_comparator_completeness_table.json",
        "runtime_leakage": "phase1_final_comparator_runtime_leakage_audit.json",
        "claim_state": "phase1_final_comparator_runner_claim_state.json",
    }
    payload = _read_required_files(run_dir, required, "Final feature-matrix comparator runner")
    payload["run_dir"] = run_dir
    payload["manifests"] = _read_manifest_dir(run_dir / "comparator_output_manifests")
    return payload


def _read_a2d_runner_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "inputs": "phase1_final_a2d_runner_inputs.json",
        "summary": "phase1_final_a2d_runner_summary.json",
        "source_links": "phase1_final_a2d_runner_source_links.json",
        "input_validation": "phase1_final_a2d_runner_input_validation.json",
        "covariance_validation": "phase1_final_a2d_covariance_validation.json",
        "completeness_patch": "phase1_final_a2d_completeness_patch.json",
        "claim_state": "phase1_final_a2d_claim_state.json",
        "output_manifest": "comparator_output_manifests/A2d_riemannian_output_manifest.json",
        "runtime_leakage": "runtime_leakage_logs/A2d_riemannian_runtime_leakage_audit.json",
        "metrics": "final_subject_level_metrics/A2d_riemannian_subject_level_metrics.json",
        "logits": "final_logits/A2d_riemannian_final_logits.json",
    }
    payload = _read_required_files(run_dir, required, "Final A2d covariance/tangent runner")
    payload["run_dir"] = run_dir
    return payload


def _read_required_files(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalComparatorReconciliationError(f"{label} file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _read_manifest_dir(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        raise Phase1FinalComparatorReconciliationError(f"Comparator output manifest directory not found: {path}")
    manifests = {}
    for manifest_path in sorted(path.glob("*_output_manifest.json")):
        payload = _read_json(manifest_path)
        comparator_id = str(payload.get("comparator_id") or manifest_path.name.removesuffix("_output_manifest.json"))
        manifests[comparator_id] = payload
    return manifests


def _validate_inputs(
    *,
    feature_matrix_runner: dict[str, Any],
    a2d: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    required = list(config.get("required_final_comparators", []))
    feature_matrix_comparators = list(config.get("feature_matrix_runner_comparators", []))
    a2d_id = str(config.get("a2d_comparator_id", "A2d_riemannian"))
    blockers = []

    fm_summary = feature_matrix_runner["summary"]
    fm_claim_state = feature_matrix_runner["claim_state"]
    if fm_summary.get("claim_ready") is not False or fm_claim_state.get("claim_ready") is not False:
        blockers.append("feature_matrix_comparator_runner_claim_not_closed")
    if fm_summary.get("smoke_artifacts_promoted") is not False:
        blockers.append("feature_matrix_comparator_runner_promoted_smoke_artifacts")
    completed = set(fm_summary.get("completed_comparators", []))
    missing_completed = sorted(set(feature_matrix_comparators) - completed)
    if missing_completed:
        blockers.append("feature_matrix_comparator_outputs_missing")
    if a2d_id not in set(fm_summary.get("blocked_comparators", [])):
        blockers.append("feature_matrix_runner_did_not_record_a2d_blocker")
    if "final_comparator_outputs_incomplete" not in fm_summary.get("claim_blockers", []):
        blockers.append("feature_matrix_runner_missing_incomplete_output_blocker")

    a2d_summary = a2d["summary"]
    a2d_claim_state = a2d["claim_state"]
    if a2d_summary.get("status") != "phase1_final_a2d_covariance_tangent_runner_complete_claim_closed":
        blockers.append("final_a2d_runner_not_complete_claim_closed")
    if a2d_summary.get("a2d_final_output_present") is not True:
        blockers.append("final_a2d_output_missing")
    if a2d_summary.get("runtime_leakage_passed") is not True:
        blockers.append("final_a2d_runtime_leakage_not_passed")
    if a2d_summary.get("claim_ready") is not False or a2d_claim_state.get("claim_ready") is not False:
        blockers.append("final_a2d_claim_not_closed")
    if a2d_summary.get("smoke_artifacts_promoted") is not False:
        blockers.append("final_a2d_promoted_smoke_artifacts")
    if a2d["covariance_validation"].get("status") != "phase1_final_a2d_covariance_validation_passed":
        blockers.append("final_a2d_covariance_validation_not_passed")

    patch = a2d["completeness_patch"]
    resolved = set(patch.get("resolved_blockers_for_downstream_reconciliation", []))
    missing_resolved = sorted(set(config.get("required_resolved_a2d_blockers", [])) - resolved)
    if missing_resolved:
        blockers.append("final_a2d_patch_missing_required_resolved_blockers")
    previous_run = patch.get("previous_feature_matrix_comparator_run")
    if previous_run and _path_key(previous_run) != _path_key(feature_matrix_runner["run_dir"]):
        blockers.append("final_a2d_patch_points_to_different_feature_matrix_runner")
    a2d_input_previous = a2d["inputs"].get("feature_matrix_comparator_run")
    if a2d_input_previous and _path_key(a2d_input_previous) != _path_key(feature_matrix_runner["run_dir"]):
        blockers.append("final_a2d_inputs_point_to_different_feature_matrix_runner")

    fm_feature_matrix_run = feature_matrix_runner["summary"].get("feature_matrix_run")
    a2d_feature_matrix_run = a2d["summary"].get("feature_matrix_run")
    if fm_feature_matrix_run and a2d_feature_matrix_run and _path_key(fm_feature_matrix_run) != _path_key(a2d_feature_matrix_run):
        blockers.append("feature_matrix_source_mismatch_between_runners")

    for key, expected in config.get("required_claim_closed_fields", {}).items():
        if fm_summary.get(key) is not expected:
            blockers.append(f"feature_matrix_runner_{key}_mismatch")
        if a2d_summary.get(key) is not expected:
            blockers.append(f"final_a2d_runner_{key}_mismatch")

    return {
        "status": "phase1_final_comparator_reconciliation_inputs_ready" if not blockers else "phase1_final_comparator_reconciliation_inputs_blocked",
        "required_final_comparators": required,
        "feature_matrix_runner_comparators": feature_matrix_comparators,
        "a2d_comparator_id": a2d_id,
        "feature_matrix_runner_completed_comparators": sorted(completed),
        "feature_matrix_runner_blocked_comparators": sorted(fm_summary.get("blocked_comparators", [])),
        "a2d_final_output_present": a2d_summary.get("a2d_final_output_present"),
        "a2d_runtime_leakage_passed": a2d_summary.get("runtime_leakage_passed"),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks artifact linkage and claim-closed boundaries only; it is not model evidence.",
    }


def _build_completeness_table(
    *,
    feature_matrix_runner: dict[str, Any],
    a2d: dict[str, Any],
    config: dict[str, Any],
    input_blockers: list[str],
) -> dict[str, Any]:
    rows = []
    for comparator_id in config.get("required_final_comparators", []):
        if comparator_id == config.get("a2d_comparator_id", "A2d_riemannian"):
            rows.append(_completeness_row_from_a2d(comparator_id, a2d))
        else:
            rows.append(_completeness_row_from_feature_matrix_runner(comparator_id, feature_matrix_runner))
    blockers = list(input_blockers)
    for row in rows:
        blockers.extend(row.get("blockers", []))
    all_outputs = not blockers and all(
        row["output_manifest_present"]
        and row["logits_present"]
        and row["subject_metrics_present"]
        and row["runtime_leakage_log_present"]
        and row["runtime_leakage_passed"]
        for row in rows
    )
    return {
        "status": "phase1_final_comparator_reconciled_completeness_recorded"
        if all_outputs
        else "phase1_final_comparator_reconciled_completeness_blocked",
        "all_final_comparator_outputs_present": all_outputs,
        "all_comparator_output_manifests_present": all(row["output_manifest_present"] for row in rows),
        "runtime_comparator_logs_audited_for_all_required_comparators": all(
            row["runtime_leakage_log_present"] for row in rows
        ),
        "claim_ready": False,
        "claim_evaluable": False,
        "smoke_artifacts_promoted": False,
        "rows": rows,
        "blockers": _unique(blockers),
        "scientific_limit": "Completeness is an artifact-presence record only; it is not efficacy evidence.",
    }


def _completeness_row_from_feature_matrix_runner(comparator_id: str, run: dict[str, Any]) -> dict[str, Any]:
    run_dir = run["run_dir"]
    manifest = run["manifests"].get(comparator_id)
    blockers = []
    if not manifest:
        blockers.append(f"{comparator_id}_output_manifest_missing")
        return _missing_row(comparator_id, "feature_matrix_runner", blockers)
    files = manifest.get("files", {})
    logits = run_dir / files.get("logits", "")
    metrics = run_dir / files.get("subject_level_metrics", "")
    leakage_path = run_dir / files.get("runtime_leakage_audit", "")
    leakage = _read_json(leakage_path) if leakage_path.exists() else {}
    leakage_passed = leakage.get("outer_test_subject_used_for_any_fit") is False and leakage.get(
        "test_time_privileged_or_teacher_outputs_allowed"
    ) is False
    if manifest.get("status") != "phase1_final_comparator_output_manifest_recorded":
        blockers.append(f"{comparator_id}_output_manifest_status_not_recorded")
    if manifest.get("claim_ready") is not False or manifest.get("claim_evaluable") is not False:
        blockers.append(f"{comparator_id}_manifest_claim_not_closed")
    if manifest.get("smoke_artifacts_promoted") is not False:
        blockers.append(f"{comparator_id}_manifest_promoted_smoke_artifacts")
    if not logits.exists():
        blockers.append(f"{comparator_id}_logits_missing")
    if not metrics.exists():
        blockers.append(f"{comparator_id}_subject_metrics_missing")
    if not leakage_path.exists():
        blockers.append(f"{comparator_id}_runtime_leakage_log_missing")
    if leakage_path.exists() and not leakage_passed:
        blockers.append(f"{comparator_id}_runtime_leakage_not_passed")
    return {
        "comparator_id": comparator_id,
        "source_package": "feature_matrix_comparator_runner",
        "source_run": str(run_dir),
        "output_manifest_present": True,
        "logits_present": logits.exists(),
        "subject_metrics_present": metrics.exists(),
        "runtime_leakage_log_present": leakage_path.exists(),
        "runtime_leakage_passed": leakage_passed,
        "claim_evaluable": False,
        "status": "completed_claim_closed" if not blockers else "blocked",
        "blockers": blockers,
        "files": {
            "output_manifest": str(run_dir / "comparator_output_manifests" / f"{comparator_id}_output_manifest.json"),
            "logits": str(logits),
            "subject_level_metrics": str(metrics),
            "runtime_leakage_audit": str(leakage_path),
        },
    }


def _completeness_row_from_a2d(comparator_id: str, run: dict[str, Any]) -> dict[str, Any]:
    run_dir = run["run_dir"]
    manifest = run["output_manifest"]
    files = manifest.get("files", {})
    logits = run_dir / files.get("logits", "")
    metrics = run_dir / files.get("subject_level_metrics", "")
    leakage_path = run_dir / files.get("runtime_leakage_audit", "")
    covariance = run_dir / files.get("covariance_manifest", "")
    tangent = run_dir / files.get("tangent_manifest", "")
    leakage = run["runtime_leakage"]
    blockers = []
    leakage_passed = leakage.get("outer_test_subject_used_for_any_fit") is False and leakage.get(
        "test_time_privileged_or_teacher_outputs_allowed"
    ) is False
    if manifest.get("status") != "phase1_final_a2d_output_manifest_recorded":
        blockers.append("A2d_riemannian_output_manifest_status_not_recorded")
    if manifest.get("claim_ready") is not False or manifest.get("claim_evaluable") is not False:
        blockers.append("A2d_riemannian_manifest_claim_not_closed")
    if manifest.get("smoke_artifacts_promoted") is not False:
        blockers.append("A2d_riemannian_manifest_promoted_smoke_artifacts")
    if not logits.exists():
        blockers.append("A2d_riemannian_logits_missing")
    if not metrics.exists():
        blockers.append("A2d_riemannian_subject_metrics_missing")
    if not leakage_path.exists():
        blockers.append("A2d_riemannian_runtime_leakage_log_missing")
    if leakage_path.exists() and not leakage_passed:
        blockers.append("A2d_riemannian_runtime_leakage_not_passed")
    if not covariance.exists():
        blockers.append("A2d_riemannian_covariance_manifest_missing")
    if not tangent.exists():
        blockers.append("A2d_riemannian_tangent_manifest_missing")
    return {
        "comparator_id": comparator_id,
        "source_package": "final_a2d_covariance_tangent_runner",
        "source_run": str(run_dir),
        "output_manifest_present": True,
        "logits_present": logits.exists(),
        "subject_metrics_present": metrics.exists(),
        "runtime_leakage_log_present": leakage_path.exists(),
        "runtime_leakage_passed": leakage_passed,
        "claim_evaluable": False,
        "status": "completed_claim_closed" if not blockers else "blocked",
        "blockers": blockers,
        "files": {
            "output_manifest": str(run_dir / "comparator_output_manifests" / f"{comparator_id}_output_manifest.json"),
            "logits": str(logits),
            "subject_level_metrics": str(metrics),
            "runtime_leakage_audit": str(leakage_path),
            "covariance_manifest": str(covariance),
            "tangent_manifest": str(tangent),
        },
    }


def _missing_row(comparator_id: str, source_package: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "comparator_id": comparator_id,
        "source_package": source_package,
        "source_run": None,
        "output_manifest_present": False,
        "logits_present": False,
        "subject_metrics_present": False,
        "runtime_leakage_log_present": False,
        "runtime_leakage_passed": False,
        "claim_evaluable": False,
        "status": "blocked",
        "blockers": blockers,
        "files": {},
    }


def _build_runtime_leakage_audit(completeness: dict[str, Any]) -> dict[str, Any]:
    rows = completeness["rows"]
    blockers = list(completeness.get("blockers", []))
    return {
        "status": "phase1_final_comparator_reconciled_runtime_leakage_audit_recorded"
        if not blockers
        else "phase1_final_comparator_reconciled_runtime_leakage_audit_blocked",
        "runtime_logs_audited_for_all_required_comparators": all(
            row["runtime_leakage_log_present"] for row in rows
        ),
        "outer_test_subject_used_for_any_fit": False if not blockers else None,
        "test_time_privileged_or_teacher_outputs_allowed": False if not blockers else None,
        "claim_ready": False,
        "claim_evaluable": False,
        "comparator_logs": [
            {
                "comparator_id": row["comparator_id"],
                "source_package": row["source_package"],
                "runtime_leakage_log_present": row["runtime_leakage_log_present"],
                "runtime_leakage_passed": row["runtime_leakage_passed"],
                "runtime_leakage_audit": row.get("files", {}).get("runtime_leakage_audit"),
                "blockers": row.get("blockers", []),
            }
            for row in rows
        ],
        "blockers": blockers,
        "scientific_limit": "Runtime leakage reconciliation checks logs only; it is not efficacy evidence.",
    }


def _build_output_manifest_index(completeness: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_reconciled_output_manifest_index_recorded",
        "claim_ready": False,
        "claim_evaluable": False,
        "manifests": [
            {
                "comparator_id": row["comparator_id"],
                "source_package": row["source_package"],
                "output_manifest": row.get("files", {}).get("output_manifest"),
                "status": row["status"],
                "blockers": row.get("blockers", []),
            }
            for row in completeness["rows"]
        ],
        "scientific_limit": "Manifest index records file locations only; it is not model evidence.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    completeness: dict[str, Any],
    runtime_leakage: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", []))
    blockers.extend(completeness.get("blockers", []))
    blockers.extend(runtime_leakage.get("blockers", []))
    if completeness.get("all_final_comparator_outputs_present") is not True:
        blockers.append("final_comparator_outputs_incomplete")
    blockers.extend(config.get("claim_blockers_after_reconciliation", []))
    return {
        "status": "phase1_final_comparator_reconciled_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "all_final_comparator_outputs_present": completeness.get("all_final_comparator_outputs_present"),
        "runtime_comparator_logs_audited_for_all_required_comparators": runtime_leakage.get(
            "runtime_logs_audited_for_all_required_comparators"
        ),
        "smoke_artifacts_promoted": False,
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A2d efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "scientific_limit": "Comparator output completeness does not open claims without controls, calibration, influence and reporting.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    feature_matrix_runner: dict[str, Any],
    a2d: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_reconciliation_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "feature_matrix_comparator_run": str(feature_matrix_runner["run_dir"]),
        "feature_matrix_comparator_summary": str(
            feature_matrix_runner["run_dir"] / "phase1_final_comparator_runner_summary.json"
        ),
        "feature_matrix_comparator_summary_sha256": _sha256(
            feature_matrix_runner["run_dir"] / "phase1_final_comparator_runner_summary.json"
        ),
        "final_a2d_run": str(a2d["run_dir"]),
        "final_a2d_summary": str(a2d["run_dir"] / "phase1_final_a2d_runner_summary.json"),
        "final_a2d_summary_sha256": _sha256(a2d["run_dir"] / "phase1_final_a2d_runner_summary.json"),
        "feature_matrix_runner_source_links": feature_matrix_runner["source_links"],
        "final_a2d_source_links": a2d["source_links"],
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not model evidence.",
    }


def _build_summary(
    *,
    output_dir: Path,
    feature_matrix_runner: dict[str, Any],
    a2d: dict[str, Any],
    completeness: dict[str, Any],
    runtime_leakage: dict[str, Any],
    input_validation: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    completed = [
        row["comparator_id"]
        for row in completeness["rows"]
        if row["status"] == "completed_claim_closed"
    ]
    return {
        "status": "phase1_final_comparator_reconciliation_complete_claim_closed"
        if completeness.get("all_final_comparator_outputs_present") and not input_validation.get("blockers")
        else "phase1_final_comparator_reconciliation_blocked",
        "output_dir": str(output_dir),
        "feature_matrix_comparator_run": str(feature_matrix_runner["run_dir"]),
        "final_a2d_run": str(a2d["run_dir"]),
        "completed_comparators": completed,
        "blocked_comparators": [
            row["comparator_id"] for row in completeness["rows"] if row["status"] != "completed_claim_closed"
        ],
        "all_final_comparator_outputs_present": completeness.get("all_final_comparator_outputs_present"),
        "all_comparator_output_manifests_present": completeness.get("all_comparator_output_manifests_present"),
        "runtime_comparator_logs_audited_for_all_required_comparators": runtime_leakage.get(
            "runtime_logs_audited_for_all_required_comparators"
        ),
        "a2d_missing_output_blocker_resolved_at_artifact_level": "A2d_riemannian_final_covariance_runner_missing"
        not in completeness.get("blockers", []),
        "smoke_artifacts_promoted": False,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "This reconciliation records final comparator artifact completeness only. It does not prove efficacy "
            "or open Phase 1 claims."
        ),
    }


def _render_report(
    summary: dict[str, Any],
    completeness: dict[str, Any],
    runtime_leakage: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Comparator Reconciliation",
            "",
            f"Status: `{summary['status']}`",
            f"Feature-matrix comparator run: `{summary['feature_matrix_comparator_run']}`",
            f"Final A2d run: `{summary['final_a2d_run']}`",
            f"Completed comparators: `{', '.join(summary['completed_comparators']) or 'none'}`",
            f"Blocked comparators: `{', '.join(summary['blocked_comparators']) or 'none'}`",
            "",
            "## Completeness",
            "",
            f"All final comparator outputs present: `{completeness['all_final_comparator_outputs_present']}`",
            f"All output manifests present: `{completeness['all_comparator_output_manifests_present']}`",
            "",
            "## Runtime Leakage",
            "",
            f"Runtime logs audited for all required comparators: `{runtime_leakage['runtime_logs_audited_for_all_required_comparators']}`",
            f"Outer-test subject used for any fit: `{runtime_leakage['outer_test_subject_used_for_any_fit']}`",
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )


def _path_key(value: str | Path) -> str:
    return str(Path(value)).replace("\\", "/").rstrip("/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_record(repo_root: Path) -> dict[str, Any]:
    def git(args: list[str]) -> str:
        return subprocess.check_output(args, cwd=repo_root, text=True).strip()

    try:
        status = git(["git", "status", "--short"])
        return {
            "branch": git(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "commit": git(["git", "rev-parse", "HEAD"]),
            "working_tree_clean": status == "",
            "git_status_short": status,
        }
    except Exception as exc:  # pragma: no cover - non-git execution environment
        return {"status": "git_unavailable", "reason": str(exc)}


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
