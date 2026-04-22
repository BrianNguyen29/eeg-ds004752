"""Phase 1 final controls metric-contract audit.

This runner audits the relative-metric contract behind failed final controls.
It reads already-generated controls artifacts, compares observed
``relative_to_baseline`` values against candidate formulas, and records whether
the locked configs/docs explicitly identify the intended formula. It does not
rerun controls, edit thresholds, alter logits, or open claims.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .final_comparator_runner import _classification_metrics
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalControlsMetricContractAuditError(RuntimeError):
    """Raised when metric-contract audit inputs cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalControlsMetricContractAuditResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "metric_contract": "configs/phase1/final_controls_metric_contract_audit.json",
    "dedicated_controls": "configs/phase1/final_dedicated_controls.json",
    "control_suite": "configs/controls/control_suite_spec.yaml",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_controls_metric_contract_audit(
    *,
    prereg_bundle: str | Path,
    controls_remediation_audit_run: str | Path,
    final_dedicated_controls_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalControlsMetricContractAuditResult:
    """Record a claim-closed audit of final-control relative metric formulas."""

    prereg_bundle = Path(prereg_bundle)
    controls_remediation_audit_run = _resolve_run_dir(Path(controls_remediation_audit_run))
    final_dedicated_controls_run = _resolve_run_dir(Path(final_dedicated_controls_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    audit_config = load_config(repo_root / Path(config_paths["metric_contract"]))
    supporting_configs = _load_supporting_configs(repo_root, config_paths)
    remediation_audit = _read_controls_remediation_audit(controls_remediation_audit_run)
    dedicated = _read_final_dedicated_controls(final_dedicated_controls_run)

    input_validation = _validate_inputs(
        remediation_audit=remediation_audit,
        dedicated=dedicated,
        audit_config=audit_config,
    )
    baseline_metrics = _baseline_metrics_from_dedicated_source_links(dedicated)
    formula_review = _build_relative_formula_review(
        remediation_audit=remediation_audit,
        dedicated=dedicated,
        baseline_metrics=baseline_metrics,
        audit_config=audit_config,
        supporting_configs=supporting_configs,
    )
    threshold_contract_review = _build_threshold_contract_review(
        formula_review=formula_review,
        supporting_configs=supporting_configs,
    )
    recommendation = _build_remediation_recommendation(
        formula_review=formula_review,
        threshold_contract_review=threshold_contract_review,
        input_validation=input_validation,
        audit_config=audit_config,
    )
    claim_state = _build_claim_state(
        input_validation=input_validation,
        formula_review=formula_review,
        recommendation=recommendation,
        audit_config=audit_config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        controls_remediation_audit=remediation_audit,
        dedicated=dedicated,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    inputs = {
        "status": "phase1_final_controls_metric_contract_audit_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "controls_remediation_audit_run": str(controls_remediation_audit_run),
        "final_dedicated_controls_run": str(final_dedicated_controls_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        input_validation=input_validation,
        formula_review=formula_review,
        recommendation=recommendation,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_controls_metric_contract_audit_inputs.json"
    summary_path = output_dir / "phase1_final_controls_metric_contract_audit_summary.json"
    report_path = output_dir / "phase1_final_controls_metric_contract_audit_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_controls_metric_contract_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_controls_metric_contract_input_validation.json", input_validation)
    _write_json(output_dir / "relative_metric_formula_review.json", formula_review)
    _write_json(output_dir / "controls_threshold_contract_review.json", threshold_contract_review)
    _write_json(output_dir / "controls_metric_contract_remediation_recommendation.json", recommendation)
    _write_json(output_dir / "phase1_final_controls_metric_contract_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, formula_review, recommendation), encoding="utf-8")
    (output_dir / "phase1_final_controls_metric_contract_decision_memo.md").write_text(
        _render_decision_memo(summary, formula_review, recommendation),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalControlsMetricContractAuditResult(
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
        path = repo_root / Path(relative)
        configs[key] = {"path": str(path), "data": load_config(path)}
    return configs


def _read_controls_remediation_audit(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_controls_remediation_audit_summary.json",
        "failure_table": "phase1_final_controls_failure_table.json",
        "threshold_review": "phase1_final_controls_threshold_source_review.json",
        "implementation_review": "phase1_final_controls_implementation_review.json",
        "claim_state": "phase1_final_controls_remediation_claim_state.json",
    }
    payload = _read_run_payload(run_dir, required, "Final controls remediation audit")
    return payload


def _read_final_dedicated_controls(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_dedicated_controls_summary.json",
        "source_links": "phase1_final_dedicated_controls_source_links.json",
        "nuisance_shared_control": "nuisance_shared_control.json",
        "spatial_control": "spatial_control.json",
        "runtime_leakage": "phase1_final_dedicated_controls_runtime_leakage_audit.json",
        "manifest": "final_dedicated_control_manifest.json",
        "claim_state": "phase1_final_dedicated_controls_claim_state.json",
    }
    payload = _read_run_payload(run_dir, required, "Final dedicated controls")
    return payload


def _read_run_payload(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalControlsMetricContractAuditError(f"{label} artifact not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    remediation_audit: dict[str, Any],
    dedicated: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    required = dict(audit_config.get("required_boundary", {}))
    observed = {
        "remediation_claims_opened": remediation_audit["summary"].get("claims_opened"),
        "remediation_claim_ready": remediation_audit["summary"].get("claim_ready"),
        "dedicated_controls_claim_ready": dedicated["summary"].get("claim_ready"),
        "dedicated_controls_claims_opened": dedicated["summary"].get(
            "claims_opened",
            dedicated["claim_state"].get("headline_phase1_claim_open"),
        ),
    }
    blockers = [
        f"boundary_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    blocking = set(remediation_audit["summary"].get("blocking_controls", []))
    required_controls = set(audit_config.get("relative_controls_under_review", []))
    if not blocking.intersection(required_controls):
        blockers.append("no_relative_control_blocker_to_audit")
    if dedicated["runtime_leakage"].get("outer_test_subject_used_for_any_fit") is True:
        blockers.append("dedicated_control_runtime_leakage_detected")
    if remediation_audit["claim_state"].get("headline_phase1_claim_open") is not False:
        blockers.append("remediation_audit_claim_state_not_closed")
    return {
        "status": "phase1_final_controls_metric_contract_inputs_ready"
        if not blockers
        else "phase1_final_controls_metric_contract_inputs_blocked",
        "observed": observed,
        "required": required,
        "blocking_controls_under_review": sorted(blocking.intersection(required_controls)),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks only the claim-closed metric-contract audit boundary.",
    }


def _baseline_metrics_from_dedicated_source_links(dedicated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    run_value = dedicated["source_links"].get("comparator_reconciliation_run")
    if not run_value:
        return {}
    run_dir = Path(run_value)
    completeness_path = run_dir / "phase1_final_comparator_reconciled_completeness_table.json"
    if not completeness_path.exists():
        return {}
    completeness = _read_json(completeness_path)
    baselines: dict[str, dict[str, Any]] = {}
    for row in completeness.get("rows", []):
        comparator_id = str(row.get("comparator_id"))
        logits_value = row.get("files", {}).get("logits")
        if not logits_value:
            continue
        logits_path = Path(logits_value)
        if not logits_path.exists():
            continue
        logits = _read_json(logits_path).get("rows", [])
        if not logits:
            continue
        y_true = [float(item["y_true"]) for item in logits]
        prob = [float(item["prob_load8"]) for item in logits]
        pred = [int(item.get("y_pred", 1 if float(item["prob_load8"]) >= 0.5 else 0)) for item in logits]
        baselines[comparator_id] = _classification_metrics(y_true, prob, pred)
    return baselines


def _build_relative_formula_review(
    *,
    remediation_audit: dict[str, Any],
    dedicated: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
    audit_config: dict[str, Any],
    supporting_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    formula_contract = _locked_formula_contract(supporting_configs)
    rows = []
    for control_id in audit_config.get("relative_controls_under_review", []):
        payload = dedicated[control_id]
        threshold = payload.get("threshold", {})
        metrics = payload.get("metrics", {})
        baseline_id = str(threshold.get("baseline_comparator") or audit_config.get("default_baseline_comparator", "A2"))
        baseline_ba = _baseline_ba(baseline_metrics, baseline_id)
        runtime_relative = _float_or_none(threshold.get("relative_to_baseline"))
        control_ba = _float_or_none(metrics.get("balanced_accuracy"))
        if baseline_ba is None and control_ba is not None and runtime_relative not in (None, 0.0):
            baseline_ba = control_ba / runtime_relative
        raw_ratio = _ratio(control_ba, baseline_ba)
        gain_ratio = _gain_ratio(control_ba, baseline_ba)
        runtime_formula = _matching_formula(runtime_relative, raw_ratio, gain_ratio, float(audit_config.get("formula_tolerance", 1e-5)))
        ceiling = _relative_ceiling(control_id, threshold)
        runtime_pass = bool(payload.get("passed"))
        raw_pass = raw_ratio is not None and ceiling is not None and raw_ratio <= ceiling
        gain_pass = gain_ratio is not None and ceiling is not None and gain_ratio <= ceiling
        pass_differs = raw_pass != gain_pass
        rows.append(
            {
                "control_id": control_id,
                "control_passed_in_artifact": runtime_pass,
                "blocking_in_remediation_audit": control_id in remediation_audit["summary"].get("blocking_controls", []),
                "balanced_accuracy": _round_or_none(control_ba),
                "baseline_comparator": baseline_id,
                "baseline_balanced_accuracy": _round_or_none(baseline_ba),
                "runtime_relative_to_baseline": _round_or_none(runtime_relative),
                "candidate_formulas": {
                    "raw_ba_ratio": _round_or_none(raw_ratio),
                    "gain_over_chance_ratio": _round_or_none(gain_ratio),
                },
                "relative_ceiling": ceiling,
                "runtime_formula_matches": runtime_formula,
                "pass_under_raw_ba_ratio": raw_pass,
                "pass_under_gain_over_chance_ratio": gain_pass,
                "candidate_formula_changes_pass_status": pass_differs,
                "scientific_limit": "Candidate formulas are diagnostic only; this audit does not reclassify controls.",
            }
        )
    ambiguous_rows = [
        row["control_id"]
        for row in rows
        if row["candidate_formula_changes_pass_status"] and not formula_contract["relative_formula_locked"]
    ]
    return {
        "status": "phase1_final_controls_relative_metric_formula_review_recorded",
        "relative_formula_locked": formula_contract["relative_formula_locked"],
        "locked_formula_source": formula_contract["locked_formula_source"],
        "locked_formula_id": formula_contract["locked_formula_id"],
        "current_runtime_formula_ids": sorted({row["runtime_formula_matches"] for row in rows}),
        "formula_ambiguity_detected": bool(ambiguous_rows),
        "controls_with_formula_dependent_pass_status": ambiguous_rows,
        "rows": rows,
        "scientific_limit": (
            "This review compares formulas without changing thresholds, logits, metrics, or claim state."
        ),
    }


def _locked_formula_contract(supporting_configs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    locations = []
    for key, payload in supporting_configs.items():
        data = payload["data"]
        for field in (
            "relative_metric_formula",
            "relative_to_baseline_formula",
            "control_relative_metric_formula",
        ):
            if field in data:
                locations.append({"config": key, "path": payload["path"], "field": field, "value": data[field]})
    if locations:
        return {
            "relative_formula_locked": True,
            "locked_formula_source": locations,
            "locked_formula_id": str(locations[0]["value"]),
        }
    return {
        "relative_formula_locked": False,
        "locked_formula_source": [],
        "locked_formula_id": None,
    }


def _build_threshold_contract_review(
    *,
    formula_review: dict[str, Any],
    supporting_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    gate2 = supporting_configs["gate2"]["data"]
    locked = {
        "nuisance_relative_ceiling": gate2.get("frozen_threshold_defaults", {}).get("nuisance_relative_ceiling"),
        "nuisance_absolute_ceiling": gate2.get("frozen_threshold_defaults", {}).get("nuisance_absolute_ceiling"),
        "spatial_relative_ceiling": gate2.get("frozen_threshold_defaults", {}).get("spatial_relative_ceiling"),
    }
    rows = []
    for row in formula_review.get("rows", []):
        threshold_id = "nuisance_relative_ceiling" if row["control_id"] == "nuisance_shared_control" else "spatial_relative_ceiling"
        rows.append(
            {
                "control_id": row["control_id"],
                "threshold_id": threshold_id,
                "locked_threshold": locked.get(threshold_id),
                "runtime_threshold": row.get("relative_ceiling"),
                "matches_locked_threshold": row.get("relative_ceiling") == locked.get(threshold_id),
                "threshold_changed_by_audit": False,
            }
        )
    return {
        "status": "phase1_final_controls_threshold_contract_review_recorded",
        "locked_thresholds": locked,
        "rows": rows,
        "all_runtime_thresholds_match_locked_config": all(row["matches_locked_threshold"] for row in rows),
        "scientific_limit": "Threshold review checks source consistency only; it does not alter thresholds.",
    }


def _build_remediation_recommendation(
    *,
    formula_review: dict[str, Any],
    threshold_contract_review: dict[str, Any],
    input_validation: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", []))
    if formula_review.get("formula_ambiguity_detected"):
        blockers.append("relative_metric_formula_contract_ambiguous")
    if not threshold_contract_review.get("all_runtime_thresholds_match_locked_config"):
        blockers.append("runtime_thresholds_do_not_match_locked_config")
    if formula_review.get("relative_formula_locked") is False:
        next_step = "open_revision_scoped_metric_formula_contract_review"
        allowed_action = "Clarify the locked metric formula before any code change or rerun."
    else:
        next_step = "compare_runtime_formula_to_locked_formula"
        allowed_action = "Only fix code if runtime formula conflicts with the locked contract."
    return {
        "status": "phase1_final_controls_metric_contract_recommendation_recorded",
        "claims_opened": False,
        "claim_ready": False,
        "blockers": _unique(blockers),
        "next_step": next_step,
        "allowed_action": allowed_action,
        "not_allowed_actions": audit_config.get("not_allowed_actions", []),
        "do_not_change_thresholds": True,
        "do_not_edit_logits_or_metrics": True,
        "do_not_reclassify_existing_controls": True,
        "scientific_limit": "Recommendation is a revision-planning artifact only; it is not control evidence.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    formula_review: dict[str, Any],
    recommendation: dict[str, Any],
    audit_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + list(recommendation.get("blockers", []))
        + ["headline_claim_blocked_until_metric_contract_and_governance_pass"]
    )
    return {
        "status": "phase1_final_controls_metric_contract_claim_state_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_ambiguity_detected": formula_review.get("formula_ambiguity_detected"),
        "blockers": blockers,
        "not_ok_to_claim": audit_config.get("not_ok_to_claim", []),
        "scientific_limit": "Metric-contract audit cannot open claims.",
    }


def _build_summary(
    *,
    output_dir: Path,
    input_validation: dict[str, Any],
    formula_review: dict[str, Any],
    recommendation: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_metric_contract_audit_recorded"
        if input_validation.get("status") == "phase1_final_controls_metric_contract_inputs_ready"
        else "phase1_final_controls_metric_contract_audit_blocked",
        "output_dir": str(output_dir),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "relative_formula_locked": formula_review.get("relative_formula_locked"),
        "formula_ambiguity_detected": formula_review.get("formula_ambiguity_detected"),
        "controls_with_formula_dependent_pass_status": formula_review.get(
            "controls_with_formula_dependent_pass_status", []
        ),
        "current_runtime_formula_ids": formula_review.get("current_runtime_formula_ids", []),
        "next_step": recommendation.get("next_step"),
        "claim_blockers": claim_state.get("blockers", []),
        "scientific_limit": "This audit reviews metric contracts only; it does not prove or disprove Phase 1 efficacy.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    controls_remediation_audit: dict[str, Any],
    dedicated: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_metric_contract_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "controls_remediation_audit_run": str(controls_remediation_audit["run_dir"]),
        "final_dedicated_controls_run": str(dedicated["run_dir"]),
        "controls_failure_table": str(controls_remediation_audit["run_dir"] / "phase1_final_controls_failure_table.json"),
        "controls_failure_table_sha256": _sha256(
            controls_remediation_audit["run_dir"] / "phase1_final_controls_failure_table.json"
        ),
        "final_dedicated_control_manifest": str(dedicated["run_dir"] / "final_dedicated_control_manifest.json"),
        "final_dedicated_control_manifest_sha256": _sha256(dedicated["run_dir"] / "final_dedicated_control_manifest.json"),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / Path(value))
            for key, value in config_paths.items()
            if (repo_root / Path(value)).exists()
        },
        "scientific_limit": "Source links provide provenance only.",
    }


def _render_report(summary: dict[str, Any], formula_review: dict[str, Any], recommendation: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 Final Controls Metric Contract Audit",
        "",
        f"Status: `{summary['status']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Relative formula locked: `{summary['relative_formula_locked']}`",
        f"Formula ambiguity detected: `{summary['formula_ambiguity_detected']}`",
        "",
        "## Formula Rows",
        "",
    ]
    for row in formula_review.get("rows", []):
        lines.append(
            f"- `{row['control_id']}`: runtime `{row['runtime_formula_matches']}`, "
            f"raw pass `{row['pass_under_raw_ba_ratio']}`, "
            f"gain-over-chance pass `{row['pass_under_gain_over_chance_ratio']}`"
        )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"Next step: `{recommendation['next_step']}`",
            f"Allowed action: {recommendation['allowed_action']}",
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_memo(
    summary: dict[str, Any],
    formula_review: dict[str, Any],
    recommendation: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Controls Metric Contract Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            "",
            "## Decision",
            "",
            "Keep claims closed. Do not change locked thresholds, edit logits or metrics, or reclassify existing controls based on this audit.",
            "",
            "## Controls With Formula-Dependent Pass Status",
            "",
            *[f"- `{control}`" for control in formula_review.get("controls_with_formula_dependent_pass_status", [])],
            "",
            "## Next Step",
            "",
            f"`{recommendation['next_step']}`",
            "",
        ]
    )


def _relative_ceiling(control_id: str, threshold: dict[str, Any]) -> float | None:
    if control_id == "nuisance_shared_control":
        return _float_or_none(threshold.get("nuisance_relative_ceiling"))
    if control_id == "spatial_control":
        return _float_or_none(threshold.get("spatial_relative_ceiling"))
    return None


def _baseline_ba(baselines: dict[str, dict[str, Any]], comparator_id: str) -> float | None:
    value = baselines.get(comparator_id, {}).get("balanced_accuracy")
    return _float_or_none(value)


def _ratio(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or abs(float(baseline)) < 1e-12:
        return None
    return float(value) / float(baseline)


def _gain_ratio(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    denom = abs(float(baseline) - 0.5)
    if denom < 1e-12:
        return math.inf
    return abs(float(value) - 0.5) / denom


def _matching_formula(
    runtime: float | None,
    raw_ratio: float | None,
    gain_ratio: float | None,
    tolerance: float,
) -> str:
    if runtime is None:
        return "runtime_relative_missing"
    candidates = {
        "raw_ba_ratio": raw_ratio,
        "gain_over_chance_ratio": gain_ratio,
    }
    for name, value in candidates.items():
        if value is None or not math.isfinite(value):
            continue
        if abs(float(runtime) - float(value)) <= tolerance:
            return name
    return "unknown_formula"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return round(float(value), 6)


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
