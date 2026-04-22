"""Phase 1 final controls remediation audit.

This runner reads failed final controls and dedicated-control artifacts after
the final remediation plan. It records why controls remain blocked and which
technical contract items need revision review. It does not recompute controls,
edit thresholds, alter logits, or open claims.
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


class Phase1FinalControlsRemediationAuditError(RuntimeError):
    """Raised when final controls remediation audit cannot be assembled."""


@dataclass(frozen=True)
class Phase1FinalControlsRemediationAuditResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "audit": "configs/phase1/final_controls_remediation_audit.json",
    "final_controls": "configs/phase1/final_controls.json",
    "dedicated_controls": "configs/phase1/final_dedicated_controls.json",
    "control_suite": "configs/controls/control_suite_spec.yaml",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_controls_remediation_audit(
    *,
    prereg_bundle: str | Path,
    final_remediation_plan_run: str | Path,
    final_controls_run: str | Path,
    final_dedicated_controls_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalControlsRemediationAuditResult:
    """Record a claim-closed audit of failed final controls."""

    prereg_bundle = Path(prereg_bundle)
    final_remediation_plan_run = _resolve_run_dir(Path(final_remediation_plan_run))
    final_controls_run = _resolve_run_dir(Path(final_controls_run))
    final_dedicated_controls_run = _resolve_run_dir(Path(final_dedicated_controls_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    audit_config = load_config(repo_root / config_paths["audit"])
    supporting_configs = _load_supporting_configs(repo_root, config_paths)
    remediation = _read_remediation_plan(final_remediation_plan_run)
    final_controls = _read_final_controls_run(final_controls_run)
    dedicated_controls = _read_dedicated_controls_run(final_dedicated_controls_run)

    input_validation = _validate_inputs(
        remediation=remediation,
        final_controls=final_controls,
        dedicated_controls=dedicated_controls,
        audit_config=audit_config,
    )
    threshold_review = _build_threshold_source_review(
        supporting_configs=supporting_configs,
        dedicated_controls=dedicated_controls,
    )
    control_failure_table = _build_control_failure_table(
        final_controls=final_controls,
        dedicated_controls=dedicated_controls,
        threshold_review=threshold_review,
        audit_config=audit_config,
    )
    implementation_review = _build_implementation_review(
        final_controls=final_controls,
        dedicated_controls=dedicated_controls,
        threshold_review=threshold_review,
    )
    remediation_work_items = _build_remediation_work_items(
        control_failure_table=control_failure_table,
        implementation_review=implementation_review,
        audit_config=audit_config,
    )
    claim_state = _build_claim_state(
        remediation=remediation,
        final_controls=final_controls,
        dedicated_controls=dedicated_controls,
        control_failure_table=control_failure_table,
        input_validation=input_validation,
        audit_config=audit_config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        remediation=remediation,
        final_controls=final_controls,
        dedicated_controls=dedicated_controls,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    inputs = {
        "status": "phase1_final_controls_remediation_audit_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_remediation_plan_run": str(final_remediation_plan_run),
        "final_controls_run": str(final_controls_run),
        "final_dedicated_controls_run": str(final_dedicated_controls_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        input_validation=input_validation,
        control_failure_table=control_failure_table,
        implementation_review=implementation_review,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_controls_remediation_audit_inputs.json"
    summary_path = output_dir / "phase1_final_controls_remediation_audit_summary.json"
    report_path = output_dir / "phase1_final_controls_remediation_audit_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_controls_remediation_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_controls_remediation_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_controls_failure_table.json", control_failure_table)
    _write_json(output_dir / "phase1_final_controls_threshold_source_review.json", threshold_review)
    _write_json(output_dir / "phase1_final_controls_implementation_review.json", implementation_review)
    _write_json(output_dir / "phase1_final_controls_remediation_work_items.json", remediation_work_items)
    _write_json(output_dir / "phase1_final_controls_remediation_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, control_failure_table, implementation_review, remediation_work_items),
        encoding="utf-8",
    )
    (output_dir / "phase1_final_controls_remediation_decision_memo.md").write_text(
        _render_decision_memo(summary, control_failure_table, implementation_review),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalControlsRemediationAuditResult(
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


def _load_supporting_configs(repo_root: Path, config_paths: dict[str, str | Path]) -> dict[str, dict[str, Any]]:
    configs = {}
    for key, relative in config_paths.items():
        if key == "audit":
            continue
        path = repo_root / Path(relative)
        configs[key] = {"path": str(path), "data": load_config(path)}
    return configs


def _read_remediation_plan(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_remediation_plan_summary.json",
        "blocker_review": "phase1_final_remediation_blocker_review.json",
        "workplan": "phase1_final_remediation_workplan.json",
        "guardrails": "phase1_final_remediation_guardrails.json",
        "claim_state": "phase1_final_remediation_claim_state.json",
    }
    return _read_run_payload(run_dir, required, "Final remediation plan")


def _read_final_controls_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_controls_summary.json",
        "input_validation": "phase1_final_controls_input_validation.json",
        "logit_controls": "phase1_final_logit_level_control_results.json",
        "dedicated_requirements": "phase1_final_dedicated_control_requirements.json",
        "dedicated_manifest_review": "phase1_final_dedicated_control_manifest_review.json",
        "manifest": "final_control_manifest.json",
        "claim_state": "phase1_final_controls_claim_state.json",
    }
    return _read_run_payload(run_dir, required, "Final controls")


def _read_dedicated_controls_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_dedicated_controls_summary.json",
        "input_validation": "phase1_final_dedicated_controls_input_validation.json",
        "nuisance_shared_control": "nuisance_shared_control.json",
        "spatial_control": "spatial_control.json",
        "shuffled_teacher": "shuffled_teacher_control.json",
        "time_shifted_teacher": "time_shifted_teacher_control.json",
        "runtime_leakage": "phase1_final_dedicated_controls_runtime_leakage_audit.json",
        "manifest": "final_dedicated_control_manifest.json",
        "claim_state": "phase1_final_dedicated_controls_claim_state.json",
    }
    return _read_run_payload(run_dir, required, "Final dedicated controls")


def _read_run_payload(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalControlsRemediationAuditError(f"{label} artifact not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    remediation: dict[str, Any],
    final_controls: dict[str, Any],
    dedicated_controls: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    required = dict(audit_config.get("required_boundary", {}))
    observed = {
        "remediation_claims_opened": remediation["summary"].get("claims_opened"),
        "remediation_final_claim_blocked": remediation["summary"].get("final_claim_blocked"),
        "final_controls_claim_ready": final_controls["summary"].get("claim_ready"),
        "final_dedicated_controls_claim_ready": dedicated_controls["summary"].get("claim_ready"),
    }
    blockers = [
        f"boundary_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    if "controls" not in remediation["summary"].get("blocking_surfaces", []):
        blockers.append("remediation_plan_does_not_mark_controls_blocking")
    if final_controls["manifest"].get("control_suite_passed") is True:
        blockers.append("final_controls_already_passed_no_remediation_audit_needed")
    if dedicated_controls["manifest"].get("dedicated_control_suite_passed") is True:
        blockers.append("dedicated_controls_already_passed_no_failure_to_audit")
    return {
        "status": "phase1_final_controls_remediation_inputs_ready"
        if not blockers
        else "phase1_final_controls_remediation_inputs_blocked",
        "observed": observed,
        "required": required,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation confirms only the claim-closed controls remediation boundary.",
    }


def _build_threshold_source_review(
    *,
    supporting_configs: dict[str, dict[str, Any]],
    dedicated_controls: dict[str, Any],
) -> dict[str, Any]:
    gate2 = supporting_configs["gate2"]["data"]
    final_controls_config = supporting_configs["final_controls"]["data"]
    dedicated_config = supporting_configs["dedicated_controls"]["data"]
    expected = {
        "negative_control_max_abs_gain": gate2.get("pass_criteria", {}).get("negative_control_max_abs_gain"),
        "nuisance_relative_ceiling": gate2.get("frozen_threshold_defaults", {}).get("nuisance_relative_ceiling"),
        "nuisance_absolute_ceiling": gate2.get("frozen_threshold_defaults", {}).get("nuisance_absolute_ceiling"),
        "spatial_relative_ceiling": gate2.get("frozen_threshold_defaults", {}).get("spatial_relative_ceiling"),
        "shuffled_teacher_max_gain_over_a3": gate2.get("negative_controls", {}).get("shuffled_teacher_max_gain_over_a3"),
        "time_shifted_teacher_max_gain_over_a3": gate2.get("negative_controls", {}).get("time_shifted_teacher_max_gain_over_a3"),
    }
    runtime = {
        "nuisance_relative_ceiling": dedicated_controls["nuisance_shared_control"].get("threshold", {}).get(
            "nuisance_relative_ceiling"
        ),
        "nuisance_absolute_ceiling": dedicated_controls["nuisance_shared_control"].get("threshold", {}).get(
            "nuisance_absolute_ceiling"
        ),
        "spatial_relative_ceiling": dedicated_controls["spatial_control"].get("threshold", {}).get(
            "spatial_relative_ceiling"
        ),
        "shuffled_teacher_max_gain_over_a3": dedicated_controls["shuffled_teacher"].get("threshold", {}).get(
            "max_gain_over_a3"
        ),
        "time_shifted_teacher_max_gain_over_a3": dedicated_controls["time_shifted_teacher"].get("threshold", {}).get(
            "max_gain_over_a3"
        ),
    }
    gate2_control_suite = gate2.get("control_suite", {})
    source_findings = []
    for key, expected_value in expected.items():
        runtime_value = runtime.get(key)
        missing_runtime = runtime_value is None
        source_findings.append(
            {
                "threshold_id": key,
                "expected_from_locked_config": expected_value,
                "runtime_artifact_value": runtime_value,
                "runtime_threshold_missing": missing_runtime,
                "config_source_present": expected_value is not None,
                "matches_locked_config": (runtime_value == expected_value) if runtime_value is not None else False,
            }
        )
    teacher_path_mismatch = (
        bool(gate2.get("negative_controls"))
        and "shuffled_teacher_max_gain_over_a3" not in gate2_control_suite
        and (
            runtime.get("shuffled_teacher_max_gain_over_a3") is None
            or runtime.get("time_shifted_teacher_max_gain_over_a3") is None
        )
    )
    return {
        "status": "phase1_final_controls_threshold_source_review_recorded",
        "locked_gate2_thresholds": expected,
        "runtime_artifact_thresholds": runtime,
        "final_controls_threshold_sources": final_controls_config.get("threshold_sources", {}),
        "dedicated_controls_threshold_sources": dedicated_config.get("threshold_sources", {}),
        "teacher_threshold_path_mismatch_suspected": teacher_path_mismatch,
        "findings": source_findings,
        "scientific_limit": "Threshold source review identifies contract consistency only; it does not change thresholds.",
    }


def _build_control_failure_table(
    *,
    final_controls: dict[str, Any],
    dedicated_controls: dict[str, Any],
    threshold_review: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    required = list(audit_config.get("required_controls", []))
    required_dedicated = list(audit_config.get("required_dedicated_controls", []))
    final_manifest = final_controls["manifest"]
    dedicated_manifest = dedicated_controls["manifest"]
    rows = []
    for control_id in required:
        if control_id in required_dedicated:
            payload = dedicated_controls[control_id]
            rows.append(_dedicated_control_row(control_id, payload, threshold_review))
        else:
            rows.append(
                {
                    "control_id": control_id,
                    "control_type": "logit_level",
                    "present": control_id in final_manifest.get("results", []),
                    "passed": control_id in final_manifest.get("results", [])
                    and control_id not in final_manifest.get("missing_results", []),
                    "blocking": control_id in final_manifest.get("missing_results", []),
                    "failure_reasons": ["missing_logit_level_control_result"]
                    if control_id in final_manifest.get("missing_results", [])
                    else [],
                    "scientific_limit": "Logit-level control presence is not efficacy evidence.",
                }
            )
    return {
        "status": "phase1_final_controls_failure_table_recorded",
        "control_suite_passed": final_manifest.get("control_suite_passed"),
        "dedicated_control_suite_passed": dedicated_manifest.get("dedicated_control_suite_passed"),
        "failed_dedicated_controls": dedicated_manifest.get("failed_results", []),
        "rows": rows,
        "blocking_controls": [row["control_id"] for row in rows if row.get("blocking")],
        "claim_ready": False,
        "claims_opened": False,
        "scientific_limit": "Failure table records observed control status only; failed controls remain failed.",
    }


def _dedicated_control_row(
    control_id: str,
    payload: dict[str, Any],
    threshold_review: dict[str, Any],
) -> dict[str, Any]:
    threshold = payload.get("threshold", {})
    metrics = payload.get("metrics", {})
    failure_reasons = []
    if payload.get("runtime_leakage_passed") is not True:
        failure_reasons.append("runtime_leakage_not_passed")
    if payload.get("passed") is not True:
        failure_reasons.append("control_threshold_not_passed")
    if control_id == "nuisance_shared_control":
        if threshold.get("nuisance_relative_ceiling") is None:
            failure_reasons.append("nuisance_relative_ceiling_missing")
        elif threshold.get("relative_to_baseline") is not None and float(threshold["relative_to_baseline"]) > float(
            threshold["nuisance_relative_ceiling"]
        ):
            failure_reasons.append("nuisance_relative_ceiling_exceeded")
        if threshold.get("nuisance_absolute_ceiling") is None:
            failure_reasons.append("nuisance_absolute_ceiling_missing")
        elif threshold.get("absolute_gain_over_chance") is not None and float(
            threshold["absolute_gain_over_chance"]
        ) > float(threshold["nuisance_absolute_ceiling"]):
            failure_reasons.append("nuisance_absolute_ceiling_exceeded")
    elif control_id == "spatial_control":
        if threshold.get("spatial_relative_ceiling") is None:
            failure_reasons.append("spatial_relative_ceiling_missing")
        elif threshold.get("relative_to_baseline") is not None and float(threshold["relative_to_baseline"]) > float(
            threshold["spatial_relative_ceiling"]
        ):
            failure_reasons.append("spatial_relative_ceiling_exceeded")
    elif control_id in {"shuffled_teacher", "time_shifted_teacher"}:
        if threshold.get("max_gain_over_a3") is None:
            failure_reasons.append("teacher_control_gain_threshold_missing")
        elif threshold.get("gain_over_a3") is not None and float(threshold["gain_over_a3"]) > float(
            threshold["max_gain_over_a3"]
        ):
            failure_reasons.append("teacher_control_gain_threshold_exceeded")
        if threshold_review.get("teacher_threshold_path_mismatch_suspected"):
            failure_reasons.append("teacher_threshold_source_path_mismatch_suspected")
    return {
        "control_id": control_id,
        "control_type": "dedicated",
        "present": True,
        "passed": payload.get("passed"),
        "blocking": payload.get("passed") is not True,
        "runtime_leakage_passed": payload.get("runtime_leakage_passed"),
        "metrics": metrics,
        "threshold": threshold,
        "failure_reasons": _unique(failure_reasons),
        "scientific_limit": payload.get("scientific_limit"),
    }


def _build_implementation_review(
    *,
    final_controls: dict[str, Any],
    dedicated_controls: dict[str, Any],
    threshold_review: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if threshold_review.get("teacher_threshold_path_mismatch_suspected"):
        blockers.append("teacher_control_threshold_source_path_requires_review")
    if dedicated_controls["runtime_leakage"].get("outer_test_subject_used_for_any_fit") is True:
        blockers.append("dedicated_control_runtime_leakage_detected")
    if final_controls["manifest"].get("missing_results"):
        blockers.append("final_controls_missing_required_results")
    if dedicated_controls["manifest"].get("failed_results"):
        blockers.append("dedicated_controls_failed_locked_thresholds")
    return {
        "status": "phase1_final_controls_implementation_review_recorded",
        "final_controls_status": final_controls["summary"].get("status"),
        "dedicated_controls_status": dedicated_controls["summary"].get("status"),
        "all_required_controls_present": not bool(final_controls["manifest"].get("missing_results")),
        "runtime_leakage_detected": dedicated_controls["runtime_leakage"].get("outer_test_subject_used_for_any_fit"),
        "teacher_threshold_path_mismatch_suspected": threshold_review.get("teacher_threshold_path_mismatch_suspected"),
        "blockers": _unique(blockers),
        "scientific_limit": "Implementation review can identify audit targets only; it does not repair controls.",
    }


def _build_remediation_work_items(
    *,
    control_failure_table: dict[str, Any],
    implementation_review: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    items = []
    if implementation_review.get("teacher_threshold_path_mismatch_suspected"):
        items.append(
            {
                "item_id": "review_teacher_control_threshold_source_contract",
                "priority": 1,
                "scope": "code_config_contract",
                "reason": "Teacher-control runtime artifacts have missing gain thresholds while locked Gate 2 config contains teacher-control thresholds under negative_controls.",
                "allowed_action": "prepare a revision-scoped code/config contract fix if review confirms the source-path mismatch",
                "not_allowed": audit_config.get("not_allowed_actions", []),
            }
        )
    for row in control_failure_table.get("rows", []):
        if row.get("control_type") != "dedicated" or not row.get("blocking"):
            continue
        priority = 2 if row["control_id"] in {"nuisance_shared_control", "spatial_control"} else 3
        items.append(
            {
                "item_id": f"audit_{row['control_id']}_failure",
                "priority": priority,
                "scope": "observed_control_failure",
                "reason": ", ".join(row.get("failure_reasons", [])) or "control_failed",
                "allowed_action": "inspect observed metric and threshold fields without changing thresholds or labels",
                "not_allowed": audit_config.get("not_allowed_actions", []),
            }
        )
    return {
        "status": "phase1_final_controls_remediation_work_items_recorded",
        "work_items": sorted(items, key=lambda item: int(item.get("priority", 99))),
        "next_step": items[0]["item_id"] if items else "manual_review_no_controls_remediation_item_detected",
        "claims_opened": False,
        "scientific_limit": "Work items are audit targets only and do not authorize claim opening.",
    }


def _build_claim_state(
    *,
    remediation: dict[str, Any],
    final_controls: dict[str, Any],
    dedicated_controls: dict[str, Any],
    control_failure_table: dict[str, Any],
    input_validation: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + list(final_controls["summary"].get("claim_blockers", []))
        + list(dedicated_controls["summary"].get("claim_blockers", []))
        + list(control_failure_table.get("blocking_controls", []))
    )
    return {
        "status": "phase1_final_controls_remediation_claim_state_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": True,
        "source_remediation_plan": str(remediation["run_dir"]),
        "blocking_controls": control_failure_table.get("blocking_controls", []),
        "blockers": blockers,
        "not_ok_to_claim": audit_config.get("not_ok_to_claim", []),
        "scientific_limit": "Controls remediation audit keeps claims closed.",
    }


def _build_summary(
    *,
    output_dir: Path,
    input_validation: dict[str, Any],
    control_failure_table: dict[str, Any],
    implementation_review: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_remediation_audit_recorded"
        if input_validation.get("status") == "phase1_final_controls_remediation_inputs_ready"
        else "phase1_final_controls_remediation_audit_blocked",
        "output_dir": str(output_dir),
        "input_validation_status": input_validation.get("status"),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": True,
        "control_suite_passed": control_failure_table.get("control_suite_passed"),
        "dedicated_control_suite_passed": control_failure_table.get("dedicated_control_suite_passed"),
        "failed_dedicated_controls": control_failure_table.get("failed_dedicated_controls", []),
        "blocking_controls": control_failure_table.get("blocking_controls", []),
        "teacher_threshold_path_mismatch_suspected": implementation_review.get(
            "teacher_threshold_path_mismatch_suspected"
        ),
        "claim_blockers": claim_state.get("blockers", []),
        "scientific_limit": "Controls remediation audit records observed blockers only; it does not prove Phase 1 efficacy.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    remediation: dict[str, Any],
    final_controls: dict[str, Any],
    dedicated_controls: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_remediation_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_remediation_plan_run": str(remediation["run_dir"]),
        "final_controls_run": str(final_controls["run_dir"]),
        "final_dedicated_controls_run": str(dedicated_controls["run_dir"]),
        "final_control_manifest": str(final_controls["run_dir"] / "final_control_manifest.json"),
        "final_control_manifest_sha256": _sha256(final_controls["run_dir"] / "final_control_manifest.json"),
        "final_dedicated_control_manifest": str(dedicated_controls["run_dir"] / "final_dedicated_control_manifest.json"),
        "final_dedicated_control_manifest_sha256": _sha256(
            dedicated_controls["run_dir"] / "final_dedicated_control_manifest.json"
        ),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not control evidence.",
    }


def _render_report(
    summary: dict[str, Any],
    control_failure_table: dict[str, Any],
    implementation_review: dict[str, Any],
    remediation_work_items: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Controls Remediation Audit",
        "",
        f"Status: `{summary['status']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Control suite passed: `{summary['control_suite_passed']}`",
        f"Dedicated control suite passed: `{summary['dedicated_control_suite_passed']}`",
        f"Teacher threshold path mismatch suspected: `{summary['teacher_threshold_path_mismatch_suspected']}`",
        "",
        "## Blocking Controls",
        "",
    ]
    lines.extend(f"- `{control}`" for control in summary.get("blocking_controls", []))
    lines.extend(["", "## Failure Reasons", ""])
    for row in control_failure_table.get("rows", []):
        if row.get("blocking"):
            reasons = ", ".join(row.get("failure_reasons", [])) or "blocked"
            lines.append(f"- `{row['control_id']}`: {reasons}")
    lines.extend(["", "## Implementation Review", ""])
    for blocker in implementation_review.get("blockers", []):
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Work Items", ""])
    for item in remediation_work_items.get("work_items", []):
        lines.append(f"- `{item['item_id']}`: {item['reason']}")
    lines.extend(
        [
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_memo(
    summary: dict[str, Any],
    control_failure_table: dict[str, Any],
    implementation_review: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Controls Remediation Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            "",
            "## Decision",
            "",
            "Proceed only with claim-closed controls remediation audit. Do not change locked thresholds, edit logits or metrics, drop subjects post hoc, or reinterpret failed controls as pass.",
            "",
            "## Blocking Controls",
            "",
            *[f"- `{control}`" for control in control_failure_table.get("blocking_controls", [])],
            "",
            "## Technical Review Flags",
            "",
            *[f"- `{blocker}`" for blocker in implementation_review.get("blockers", [])],
            "",
        ]
    )


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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
