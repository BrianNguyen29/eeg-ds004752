"""V5.6 Tranche 2.2 feature-matrix planning artifacts.

This runner records the contract for future feature-matrix materialization. It
does not materialize feature values, train models, run comparators, compute
statistics, or open claims.
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


class V56FeatureMatrixPlanError(RuntimeError):
    """Raised when the V5.6 feature-matrix plan cannot be recorded."""


@dataclass(frozen=True)
class V56FeatureMatrixPlanResult:
    output_dir: Path
    plan_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


def run_v56_feature_matrix_plan(
    *,
    gate0_run: str | Path,
    split_registry_lock_run: str | Path,
    feature_provenance_run: str | Path,
    benchmark_spec: str | Path = "configs/v56/benchmark_spec.json",
    feature_matrix_plan_config: str | Path = "configs/v56/feature_matrix_plan.json",
    output_root: str | Path = "artifacts/v56_feature_matrix_plan",
    repo_root: str | Path | None = None,
) -> V56FeatureMatrixPlanResult:
    """Write a claim-closed V5.6 feature-matrix plan artifact."""

    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    gate0_path = _resolve_path(Path(gate0_run), must_be_dir=True)
    split_lock_run = _resolve_path(Path(split_registry_lock_run), must_be_dir=True)
    provenance_run = _resolve_path(Path(feature_provenance_run), must_be_dir=True)
    output_root = Path(output_root)

    benchmark = load_benchmark_spec(repo / benchmark_spec if not Path(benchmark_spec).is_absolute() else benchmark_spec)
    config = load_config(
        repo / feature_matrix_plan_config
        if not Path(feature_matrix_plan_config).is_absolute()
        else feature_matrix_plan_config
    )
    manifest = _read_json(gate0_path / "manifest.json")
    cohort_lock = _read_json(gate0_path / "cohort_lock.json")
    split_lock = _read_json(split_lock_run / "v56_split_registry_lock.json")
    provenance = _read_json(provenance_run / "v56_feature_provenance_populated.json")

    assert_signal_ready_gate0(manifest, cohort_lock, benchmark)
    validation = _validate_inputs(
        benchmark=benchmark,
        config=config,
        manifest=manifest,
        cohort_lock=cohort_lock,
        split_lock=split_lock,
        provenance=provenance,
    )
    if validation["blocking_errors"]:
        raise V56FeatureMatrixPlanError(f"Feature-matrix plan prerequisites failed: {validation['blocking_errors']}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    plan = _build_plan(
        timestamp=timestamp,
        benchmark=benchmark,
        config=config,
        manifest=manifest,
        cohort_lock=cohort_lock,
        split_lock=split_lock,
        provenance=provenance,
        validation=validation,
        gate0_run=gate0_path,
        split_registry_lock_run=split_lock_run,
        feature_provenance_run=provenance_run,
        repo_root=repo,
        config_path=Path(feature_matrix_plan_config),
    )
    summary = _build_summary(
        output_dir=output_dir,
        timestamp=timestamp,
        benchmark=benchmark,
        plan=plan,
        validation=validation,
        repo_root=repo,
    )

    plan_path = output_dir / "v56_feature_matrix_plan.json"
    summary_path = output_dir / "v56_feature_matrix_plan_summary.json"
    validation_path = output_dir / "v56_feature_matrix_plan_validation.json"
    report_path = output_dir / "v56_feature_matrix_plan_report.md"

    _write_json(plan_path, plan)
    _write_json(summary_path, summary)
    _write_json(validation_path, validation)
    report_path.write_text(_render_report(summary, validation, plan), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return V56FeatureMatrixPlanResult(
        output_dir=output_dir,
        plan_path=plan_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _resolve_path(path: Path, *, must_be_dir: bool) -> Path:
    if path.is_file() and path.name == "latest.txt":
        path = Path(path.read_text(encoding="utf-8").strip())
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if must_be_dir and not path.is_dir():
        raise V56FeatureMatrixPlanError(f"Expected directory path, got: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise V56FeatureMatrixPlanError(f"JSON root must be an object: {path}")
    return data


def _validate_inputs(
    *,
    benchmark: dict[str, Any],
    config: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    split_lock: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    errors = []
    warnings = []
    if config.get("scientific_integrity_rule") is None:
        errors.append("feature_matrix_plan_missing_scientific_integrity_rule")
    if split_lock.get("status") != "locked_subject_level_split_registry":
        errors.append("split_registry_not_locked")
    if split_lock.get("claim_closed") is not True:
        errors.append("split_registry_lock_not_claim_closed")
    if split_lock.get("subject_isolation_enforced") is not True:
        errors.append("subject_isolation_not_enforced")
    inference = split_lock.get("test_time_inference", {})
    if inference.get("modality") != "scalp_eeg_only":
        errors.append("test_time_modality_not_scalp_only")
    if inference.get("allow_ieeg") is not False:
        errors.append("test_time_ieeg_allowed")
    if inference.get("allow_beamforming_bridge") is not False:
        errors.append("test_time_beamforming_bridge_allowed")
    if provenance.get("status") != "populated_source_hashes_and_split_links":
        errors.append("feature_provenance_not_populated")
    if provenance.get("claim_closed") is not True:
        errors.append("feature_provenance_not_claim_closed")
    if provenance.get("missing_sources"):
        errors.append("feature_provenance_has_missing_sources")
    links = provenance.get("required_links_satisfied", {})
    for key in ("split_registry", "source_hashes", "manifest"):
        if links.get(key) is not True:
            errors.append(f"feature_provenance_link_not_satisfied:{key}")
    if benchmark["implementation_policy"].get("heavy_modeling_allowed_in_tranche2") is not False:
        errors.append("heavy_modeling_allowed_in_tranche2_not_false")
    if manifest.get("manifest_status") != benchmark["gate_requirements"]["gate0_manifest_status"]:
        errors.append("gate0_manifest_not_signal_ready")
    if cohort_lock.get("cohort_lock_status") != benchmark["gate_requirements"]["cohort_lock_status"]:
        errors.append("cohort_lock_not_signal_ready")

    primary_sets = config.get("primary_feature_sets", [])
    if not primary_sets:
        errors.append("no_primary_feature_sets_declared")
    for feature_set in primary_sets:
        if feature_set.get("allowed_at_test_time") is True and feature_set.get("source_modality") != "scalp_eeg":
            errors.append(f"non_scalp_feature_set_allowed_at_test_time:{feature_set.get('id')}")
        if feature_set.get("materialization_status") != "planned_not_materialized":
            errors.append(f"primary_feature_set_already_materialized:{feature_set.get('id')}")
    for source in config.get("privileged_train_time_sources", []):
        if source.get("allowed_at_test_time") is not False:
            errors.append(f"privileged_source_allowed_at_test_time:{source.get('id')}")
        if source.get("requires_train_fold_fit_only") is not True:
            warnings.append(f"privileged_source_missing_train_fold_fit_only:{source.get('id')}")

    return {
        "status": "v56_feature_matrix_plan_validation_passed" if not errors else "v56_feature_matrix_plan_validation_failed",
        "blocking_errors": errors,
        "warnings": warnings,
        "claim_closed": True,
        "feature_matrix_materialized": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "test_time_inference": inference,
        "n_folds": len(split_lock.get("folds", [])),
        "n_primary_eligible": cohort_lock.get("n_primary_eligible"),
        "scientific_limit": "Validation covers feature-matrix planning only; it is not model evidence.",
    }


def _build_plan(
    *,
    timestamp: str,
    benchmark: dict[str, Any],
    config: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    split_lock: dict[str, Any],
    provenance: dict[str, Any],
    validation: dict[str, Any],
    gate0_run: Path,
    split_registry_lock_run: Path,
    feature_provenance_run: Path,
    repo_root: Path,
    config_path: Path,
) -> dict[str, Any]:
    return {
        "artifact_family": "v56_feature_matrix_plan",
        "created_utc": timestamp,
        "status": "planned_feature_matrix_contract_recorded",
        "plan_id": config["plan_id"],
        "benchmark_name": benchmark["benchmark_name"],
        "program_version": benchmark["program_version"],
        "record_scope": benchmark["record_scope"],
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "claim_ready": False,
        "gate0_run": str(gate0_run),
        "split_registry_lock_run": str(split_registry_lock_run),
        "feature_provenance_run": str(feature_provenance_run),
        "gate0_manifest_status": manifest["manifest_status"],
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "n_locked_folds": validation["n_folds"],
        "test_time_inference": split_lock["test_time_inference"],
        "row_identity_columns": config["row_identity_columns"],
        "primary_feature_sets": config["primary_feature_sets"],
        "privileged_train_time_sources": config.get("privileged_train_time_sources", []),
        "future_materialization_requirements": config["future_materialization_requirements"],
        "validation_rules": config["validation_rules"],
        "source_hashes": {
            "feature_matrix_plan_config": _sha256(repo_root / config_path),
            "split_registry_lock": _sha256(split_registry_lock_run / "v56_split_registry_lock.json"),
            "feature_provenance": _sha256(feature_provenance_run / "v56_feature_provenance_populated.json"),
        },
        "scientific_boundary": {
            "feature_matrix_materialized": False,
            "model_training_run": False,
            "comparator_execution_run": False,
            "efficacy_metrics_computed": False,
            "claim_ready": False,
            "allowed_interpretation": (
                "Feature-matrix contract is planned and linked to locked split/provenance artifacts. "
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
        "artifact_family": "v56_feature_matrix_plan",
        "status": plan["status"],
        "validation_status": validation["status"],
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "claim_ready": False,
        "created_utc": timestamp,
        "output_dir": str(output_dir),
        "plan_id": plan["plan_id"],
        "n_primary_feature_sets": len(plan["primary_feature_sets"]),
        "n_privileged_train_time_sources": len(plan["privileged_train_time_sources"]),
        "n_locked_folds": plan["n_locked_folds"],
        "feature_matrix_materialized": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "artifact_sha256": _sha256_json(plan),
        "repo": _repo_state(repo_root),
        "next_step": "manual_review_then_implement_feature_matrix_materializer_only_if_plan_passes",
    }


def _render_report(summary: dict[str, Any], validation: dict[str, Any], plan: dict[str, Any]) -> str:
    lines = [
        "# V5.6 Feature Matrix Plan",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Validation: `{summary['validation_status']}`",
        f"- Claim closed: `{summary['claim_closed']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Locked folds: `{summary['n_locked_folds']}`",
        f"- Primary feature sets: `{summary['n_primary_feature_sets']}`",
        f"- Privileged train-time sources: `{summary['n_privileged_train_time_sources']}`",
        "",
        "## Integrity Boundary",
        "",
        "- This artifact is a feature-matrix plan only.",
        "- No feature values were materialized.",
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
        "## Blockers",
        "",
    ]
    for blocker in plan["claim_blockers"]:
        lines.append(f"- `{blocker}`")
    if validation["warnings"]:
        lines.extend(["", "## Warnings", ""])
        for warning in validation["warnings"]:
            lines.append(f"- `{warning}`")
    lines.extend(
        [
            "",
            "## Next Step",
            "",
            f"- {summary['next_step']}",
            "",
        ]
    )
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
