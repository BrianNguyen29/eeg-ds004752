"""Final manifest-level leakage audit for Phase 1.

This module audits final split and feature manifest fit-scope rules before
final comparator execution. It does not train models, inspect comparator
runtime logs, compute metrics, or open claims.
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


class Phase1FinalLeakageAuditError(RuntimeError):
    """Raised when final leakage audit generation cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalLeakageAuditResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "audit": "configs/phase1/final_leakage_audit.json",
    "readiness": "configs/phase1/final_split_feature_leakage.json",
}


def run_phase1_final_leakage_audit(
    *,
    prereg_bundle: str | Path,
    final_split_run: str | Path,
    final_feature_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalLeakageAuditResult:
    """Write a final manifest-level leakage audit or fail before doing so."""

    prereg_bundle = Path(prereg_bundle)
    final_split_run = _resolve_run_dir(Path(final_split_run))
    final_feature_run = _resolve_run_dir(Path(final_feature_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    split = _read_final_split_run(final_split_run)
    feature = _read_final_feature_run(final_feature_run)
    _validate_final_split_boundary(split)
    _validate_final_feature_boundary(feature)

    audit_config = load_config(repo_root / config_paths["audit"])
    readiness_config = load_config(repo_root / config_paths["readiness"])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    input_validation = _validate_inputs(split, feature, audit_config)
    leakage_audit = _build_leakage_audit(
        timestamp=timestamp,
        audit_config=audit_config,
        readiness_config=readiness_config,
        split=split,
        feature=feature,
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
    )
    validation = _validate_leakage_audit(leakage_audit, audit_config)
    leakage_ready = not input_validation["blockers"] and not validation["blockers"]
    claim_state = _build_claim_state(audit_config, leakage_ready, input_validation["blockers"] + validation["blockers"])
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
        config_paths=config_paths,
        repo_root=repo_root,
    )

    summary = {
        "status": "phase1_final_leakage_audit_recorded" if leakage_ready else "phase1_final_leakage_audit_with_blockers",
        "output_dir": str(output_dir),
        "leakage_audit_ready": leakage_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "audit_id": audit_config.get("audit_id"),
        "audit_boundary": audit_config.get("audit_boundary", {}),
        "final_split_run": str(final_split_run),
        "final_feature_run": str(final_feature_run),
        "n_folds": len(leakage_audit["folds"]),
        "n_stages": len(audit_config.get("stages", [])),
        "outer_test_subject_used_in_any_fit": leakage_audit["outer_test_subject_used_in_any_fit"],
        "test_time_privileged_or_teacher_outputs_allowed": leakage_audit[
            "test_time_privileged_or_teacher_outputs_allowed"
        ],
        "runtime_comparator_logs_audited": leakage_audit["runtime_comparator_logs_audited"],
        "contains_model_outputs": leakage_audit["contains_model_outputs"],
        "contains_metrics": leakage_audit["contains_metrics"],
        "leakage_blockers": _unique(input_validation["blockers"] + validation["blockers"]),
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final manifest-level leakage audit only. This run records fit-scope leakage guards from manifests; "
            "it does not audit final comparator runtime logs, train models, compute metrics, or support claims."
        ),
    }
    inputs = {
        "status": "phase1_final_leakage_audit_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_feature_run": str(final_feature_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_leakage_audit_inputs.json"
    summary_path = output_dir / "phase1_final_leakage_audit_summary.json"
    report_path = output_dir / "phase1_final_leakage_audit_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_leakage_audit_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_leakage_audit_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_leakage_audit_validation.json", validation)
    _write_json(output_dir / "phase1_final_leakage_audit_claim_state.json", claim_state)
    _write_json(output_dir / "final_leakage_audit.json", leakage_audit)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, input_validation, validation, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalLeakageAuditResult(
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


def _read_final_split_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_split_manifest_summary.json",
        "manifest": "final_split_manifest.json",
        "validation": "phase1_final_split_manifest_validation.json",
        "claim_state": "phase1_final_split_manifest_claim_state.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalLeakageAuditError(f"Final split manifest file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _read_final_feature_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_feature_manifest_summary.json",
        "manifest": "final_feature_manifest.json",
        "validation": "phase1_final_feature_manifest_validation.json",
        "claim_state": "phase1_final_feature_manifest_claim_state.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalLeakageAuditError(f"Final feature manifest file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_final_split_boundary(split: dict[str, Any]) -> None:
    if split["summary"].get("status") != "phase1_final_split_manifest_recorded":
        raise Phase1FinalLeakageAuditError("Final leakage audit requires a recorded final split manifest")
    if split["summary"].get("split_manifest_ready") is not True:
        raise Phase1FinalLeakageAuditError("Final split manifest must be ready")
    if split["validation"].get("status") != "phase1_final_split_manifest_validation_passed":
        raise Phase1FinalLeakageAuditError("Final split validation must pass")
    if split["validation"].get("no_subject_overlap_between_train_and_test") is not True:
        raise Phase1FinalLeakageAuditError("Final split must have no train/test subject overlap")
    if split["manifest"].get("claim_ready") is not False or split["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalLeakageAuditError("Final split manifest must keep claim_ready=false")


def _validate_final_feature_boundary(feature: dict[str, Any]) -> None:
    if feature["summary"].get("status") != "phase1_final_feature_manifest_recorded":
        raise Phase1FinalLeakageAuditError("Final leakage audit requires a recorded final feature manifest")
    if feature["summary"].get("feature_manifest_ready") is not True:
        raise Phase1FinalLeakageAuditError("Final feature manifest must be ready")
    if feature["validation"].get("status") != "phase1_final_feature_manifest_validation_passed":
        raise Phase1FinalLeakageAuditError("Final feature validation must pass")
    if feature["manifest"].get("contains_feature_matrix") is not False:
        raise Phase1FinalLeakageAuditError("Final feature manifest must not contain feature matrix")
    if feature["manifest"].get("contains_model_outputs") is not False:
        raise Phase1FinalLeakageAuditError("Final feature manifest must not contain model outputs")
    if feature["manifest"].get("contains_metrics") is not False:
        raise Phase1FinalLeakageAuditError("Final feature manifest must not contain metrics")
    if feature["manifest"].get("claim_ready") is not False or feature["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalLeakageAuditError("Final feature manifest must keep claim_ready=false")


def _validate_inputs(split: dict[str, Any], feature: dict[str, Any], audit_config: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    required = audit_config.get("required_inputs", {})
    if split["summary"].get("split_manifest_ready") is not required.get("final_split_manifest_ready"):
        blockers.append("final_split_manifest_not_ready")
    if feature["summary"].get("feature_manifest_ready") is not required.get("final_feature_manifest_ready"):
        blockers.append("final_feature_manifest_not_ready")
    manifest = feature["manifest"]
    if manifest.get("contains_feature_matrix") is not required.get("feature_manifest_contains_feature_matrix"):
        blockers.append("feature_manifest_boundary_contains_feature_matrix")
    if manifest.get("contains_model_outputs") is not required.get("feature_manifest_contains_model_outputs"):
        blockers.append("feature_manifest_boundary_contains_model_outputs")
    if manifest.get("contains_metrics") is not required.get("feature_manifest_contains_metrics"):
        blockers.append("feature_manifest_boundary_contains_metrics")
    return {
        "status": "phase1_final_leakage_audit_input_validation_passed" if not blockers else "phase1_final_leakage_audit_input_validation_blocked",
        "split_manifest_ready": split["summary"].get("split_manifest_ready"),
        "feature_manifest_ready": feature["summary"].get("feature_manifest_ready"),
        "feature_manifest_contains_feature_matrix": manifest.get("contains_feature_matrix"),
        "feature_manifest_contains_model_outputs": manifest.get("contains_model_outputs"),
        "feature_manifest_contains_metrics": manifest.get("contains_metrics"),
        "blockers": blockers,
    }


def _build_leakage_audit(
    *,
    timestamp: str,
    audit_config: dict[str, Any],
    readiness_config: dict[str, Any],
    split: dict[str, Any],
    feature: dict[str, Any],
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    final_feature_run: Path,
) -> dict[str, Any]:
    stage_names = list(audit_config.get("stages", []))
    stage_policies = audit_config.get("stage_policies", {})
    folds = []
    outer_used = False
    for fold in split["manifest"].get("folds", []):
        outer = fold["outer_test_subject"]
        train_subjects = list(fold.get("train_subjects", []))
        test_subjects = list(fold.get("test_subjects", [outer]))
        stage_records = []
        for stage in stage_names:
            fit_subjects = list(train_subjects)
            transform_subjects = _transform_subjects_for_stage(stage, train_subjects, test_subjects)
            no_outer = outer not in set(fit_subjects)
            outer_used = outer_used or not no_outer
            stage_records.append(
                {
                    "stage": stage,
                    "policy": stage_policies.get(stage),
                    "fit_subjects": fit_subjects,
                    "transform_subjects": transform_subjects,
                    "outer_test_subject": outer,
                    "outer_test_subject_in_fit": not no_outer,
                    "no_outer_test_subject_in_fit": no_outer,
                    "fit_subjects_recorded": True,
                    "transform_subjects_recorded": True,
                }
            )
        folds.append(
            {
                "fold_id": fold["fold_id"],
                "outer_test_subject": outer,
                "train_subjects": train_subjects,
                "test_subjects": test_subjects,
                "stages": stage_records,
                "no_outer_test_subject_in_any_fit": all(stage["no_outer_test_subject_in_fit"] for stage in stage_records),
                "test_time_inference_policy": audit_config.get("fit_scope_policy", {}).get("test_time_inference_policy"),
                "test_time_privileged_or_teacher_outputs_allowed": False,
            }
        )
    return {
        "status": "phase1_final_leakage_audit_recorded",
        "created_utc": timestamp,
        "audit_id": audit_config.get("audit_id"),
        "audit_scope": audit_config.get("claim_scope"),
        "source_prereg_bundle": str(prereg_bundle),
        "source_prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "source_final_split_run": str(final_split_run),
        "source_final_feature_run": str(final_feature_run),
        "source_split_manifest_status": split["manifest"].get("status"),
        "source_feature_manifest_status": feature["manifest"].get("status"),
        "feature_set_id": feature["manifest"].get("feature_set_id"),
        "feature_count": feature["manifest"].get("feature_count"),
        "fit_scope_policy": audit_config.get("fit_scope_policy", {}),
        "stage_policies": stage_policies,
        "readiness_required_schema": readiness_config.get("leakage_audit_schema", {}),
        "n_folds": len(folds),
        "folds": folds,
        "outer_test_subject_used_in_any_fit": outer_used,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "runtime_comparator_logs_audited": False,
        "contains_model_outputs": False,
        "contains_metrics": False,
        "claim_ready": False,
        "standalone_claim_ready": False,
        "scientific_limit": (
            "This is a manifest-level leakage audit from split and feature manifests. It does not audit final "
            "comparator runtime logs, train models, compute metrics, or support claims."
        ),
    }


def _transform_subjects_for_stage(stage: str, train_subjects: list[str], test_subjects: list[str]) -> list[str]:
    if stage in {"teacher", "privileged"}:
        return list(train_subjects)
    return sorted(set(train_subjects) | set(test_subjects))


def _validate_leakage_audit(audit: dict[str, Any], audit_config: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    policy = audit_config.get("fit_scope_policy", {})
    if audit.get("outer_test_subject_used_in_any_fit") is not False:
        blockers.append("outer_test_subject_used_in_fit")
    if audit.get("test_time_privileged_or_teacher_outputs_allowed") is not policy.get(
        "test_time_privileged_or_teacher_outputs_allowed"
    ):
        blockers.append("test_time_privileged_or_teacher_outputs_allowed")
    if audit.get("contains_model_outputs") is not False:
        blockers.append("leakage_audit_contains_model_outputs")
    if audit.get("contains_metrics") is not False:
        blockers.append("leakage_audit_contains_metrics")
    if audit.get("claim_ready") is not False:
        blockers.append("leakage_audit_claim_ready_not_false")
    for fold in audit["folds"]:
        if not fold["no_outer_test_subject_in_any_fit"]:
            blockers.append(f"{fold['fold_id']}:outer_test_subject_used_in_any_fit")
        for stage in fold["stages"]:
            if policy.get("transform_subjects_must_be_recorded") and not stage["transform_subjects_recorded"]:
                blockers.append(f"{fold['fold_id']}:{stage['stage']}:transform_subjects_not_recorded")
            if not stage["fit_subjects_recorded"]:
                blockers.append(f"{fold['fold_id']}:{stage['stage']}:fit_subjects_not_recorded")
    return {
        "status": "phase1_final_leakage_audit_validation_passed" if not blockers else "phase1_final_leakage_audit_validation_failed",
        "leakage_audit_ready": not blockers,
        "n_folds": audit["n_folds"],
        "outer_test_subject_used_in_any_fit": audit["outer_test_subject_used_in_any_fit"],
        "test_time_privileged_or_teacher_outputs_allowed": audit["test_time_privileged_or_teacher_outputs_allowed"],
        "runtime_comparator_logs_audited": audit["runtime_comparator_logs_audited"],
        "contains_model_outputs": audit["contains_model_outputs"],
        "contains_metrics": audit["contains_metrics"],
        "blockers": _unique(blockers),
        "scientific_limit": "Validation covers manifest-level leakage guards only; it is not model evidence.",
    }


def _build_claim_state(audit_config: dict[str, Any], leakage_ready: bool, leakage_blockers: list[str]) -> dict[str, Any]:
    blockers = list(leakage_blockers)
    if leakage_ready:
        blockers.extend(
            [
                "final_comparator_outputs_not_claim_evaluable",
                "runtime_comparator_leakage_logs_missing_until_final_runners_execute",
                "headline_claim_blocked_until_full_package_passes",
            ]
        )
    else:
        blockers.append("final_leakage_audit_missing_or_blocked")
        blockers.append("claim_blocked_until_final_leakage_audit_passes")
    return {
        "status": "phase1_final_leakage_audit_claim_state_blocked",
        "leakage_audit_ready": leakage_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "standalone_claim_ready": audit_config.get("audit_boundary", {}).get("standalone_claim_ready", False),
        "runtime_comparator_logs_audited": audit_config.get("audit_boundary", {}).get(
            "runtime_comparator_logs_audited", False
        ),
        "smoke_artifacts_promoted": False,
        "remaining_required_after_leakage": audit_config.get("remaining_required_after_leakage", []),
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": (
            "A manifest-level leakage audit exists for planned final split/feature fit scopes."
            if leakage_ready
            else "Final leakage audit has blockers and cannot be used by final comparator runners."
        ),
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    final_feature_run: Path,
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    split_path = final_split_run / "final_split_manifest.json"
    feature_path = final_feature_run / "final_feature_manifest.json"
    return {
        "status": "phase1_final_leakage_audit_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_split_manifest": str(split_path),
        "final_split_manifest_sha256": _sha256(split_path),
        "final_feature_run": str(final_feature_run),
        "final_feature_manifest": str(feature_path),
        "final_feature_manifest_sha256": _sha256(feature_path),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links document provenance for the manifest-level leakage audit only.",
    }


def _render_report(
    summary: dict[str, Any],
    input_validation: dict[str, Any],
    validation: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Leakage Audit",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Leakage audit ready: `{summary['leakage_audit_ready']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Folds: `{summary['n_folds']}`",
        f"- Stages: `{summary['n_stages']}`",
        f"- Outer-test subject used in any fit: `{summary['outer_test_subject_used_in_any_fit']}`",
        f"- Test-time privileged or teacher outputs allowed: `{summary['test_time_privileged_or_teacher_outputs_allowed']}`",
        f"- Runtime comparator logs audited: `{summary['runtime_comparator_logs_audited']}`",
        "",
        "## Validation",
        "",
        f"- Input validation: `{input_validation['status']}`",
        f"- Leakage validation: `{validation['status']}`",
        f"- Contains model outputs: `{validation['contains_model_outputs']}`",
        f"- Contains metrics: `{validation['contains_metrics']}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Scientific Integrity", ""])
    lines.append("- This audit is manifest-level only; it does not inspect final comparator runtime logs.")
    lines.append("- It does not train models, compute metrics, run controls, calibration, influence or reporting.")
    lines.append("- It cannot support decoder efficacy or privileged-transfer claims.")
    lines.extend(["", "## Not OK To Claim", ""])
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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
