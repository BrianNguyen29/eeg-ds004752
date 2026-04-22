"""Phase 1 final controls metric-formula decision.

This module records the manual decision required after the metric-formula
revision plan. It does not change thresholds, edit logits or metrics, rerun
controls, or open claims. If a formula change is selected, this runner only
authorizes a future scoped code/config revision with tests.
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


class Phase1FinalControlsMetricFormulaDecisionError(RuntimeError):
    """Raised when the metric-formula decision cannot be recorded."""


@dataclass(frozen=True)
class Phase1FinalControlsMetricFormulaDecisionResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "decision": "configs/phase1/final_controls_metric_formula_decision.json",
    "revision_plan": "configs/phase1/final_controls_metric_formula_revision_plan.json",
    "metric_contract": "configs/phase1/final_controls_metric_contract_audit.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_controls_metric_formula_decision(
    *,
    prereg_bundle: str | Path,
    formula_revision_plan_run: str | Path,
    formula_decision: str,
    decision_rationale: str,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalControlsMetricFormulaDecisionResult:
    """Record a claim-closed manual metric-formula decision."""

    prereg_bundle = Path(prereg_bundle)
    formula_revision_plan_run = _resolve_run_dir(Path(formula_revision_plan_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    decision_config = load_config(repo_root / Path(config_paths["decision"]))
    supporting_configs = _load_supporting_configs(repo_root, config_paths)
    revision = _read_formula_revision_plan(formula_revision_plan_run)

    formula_decision = str(formula_decision).strip()
    decision_rationale = str(decision_rationale).strip()
    input_validation = _validate_inputs(
        revision=revision,
        formula_decision=formula_decision,
        decision_rationale=decision_rationale,
        decision_config=decision_config,
    )
    decision_record = _build_decision_record(
        revision=revision,
        formula_decision=formula_decision,
        decision_rationale=decision_rationale,
        input_validation=input_validation,
        decision_config=decision_config,
    )
    implementation_boundary = _build_implementation_boundary(
        decision_record=decision_record,
        decision_config=decision_config,
        supporting_configs=supporting_configs,
    )
    claim_state = _build_claim_state(
        input_validation=input_validation,
        decision_record=decision_record,
        implementation_boundary=implementation_boundary,
        decision_config=decision_config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        revision=revision,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_controls_metric_formula_decision_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "formula_revision_plan_run": str(formula_revision_plan_run),
        "formula_decision": formula_decision,
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        input_validation=input_validation,
        decision_record=decision_record,
        implementation_boundary=implementation_boundary,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_controls_metric_formula_decision_inputs.json"
    summary_path = output_dir / "phase1_final_controls_metric_formula_decision_summary.json"
    report_path = output_dir / "phase1_final_controls_metric_formula_decision_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_controls_metric_formula_decision_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_controls_metric_formula_decision_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_controls_metric_formula_decision_record.json", decision_record)
    _write_json(output_dir / "phase1_final_controls_metric_formula_implementation_boundary.json", implementation_boundary)
    _write_json(output_dir / "phase1_final_controls_metric_formula_decision_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, decision_record, implementation_boundary), encoding="utf-8")
    (output_dir / "phase1_final_controls_metric_formula_decision_memo.md").write_text(
        _render_decision_memo(summary, decision_record, implementation_boundary),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalControlsMetricFormulaDecisionResult(
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


def _read_formula_revision_plan(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_controls_metric_formula_revision_plan_summary.json",
        "scope": "phase1_final_controls_metric_formula_revision_scope.json",
        "options": "phase1_final_controls_metric_formula_options.json",
        "requirements": "phase1_final_controls_metric_formula_decision_requirements.json",
        "claim_state": "phase1_final_controls_metric_formula_revision_claim_state.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalControlsMetricFormulaDecisionError(f"Formula revision-plan artifact not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    revision: dict[str, Any],
    formula_decision: str,
    decision_rationale: str,
    decision_config: dict[str, Any],
) -> dict[str, Any]:
    allowed = set(decision_config.get("allowed_formula_decisions", []))
    required = dict(decision_config.get("required_boundary", {}))
    observed = {
        "revision_plan_claims_opened": revision["summary"].get("claims_opened"),
        "revision_plan_claim_ready": revision["summary"].get("claim_ready"),
        "revision_plan_manual_decision_required": revision["summary"].get("manual_decision_required"),
        "revision_plan_selected_formula": revision["summary"].get("selected_formula"),
        "revision_plan_headline_claim_open": revision["claim_state"].get("headline_phase1_claim_open"),
        "revision_plan_code_change_allowed_now": revision["summary"].get("code_change_allowed_now"),
        "revision_plan_rerun_controls_allowed_now": revision["summary"].get("rerun_controls_allowed_now"),
        "revision_plan_threshold_change_allowed_now": revision["summary"].get("threshold_change_allowed_now"),
    }
    blockers = [
        f"boundary_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) != expected
    ]
    if formula_decision not in allowed:
        blockers.append("formula_decision_not_allowed")
    if len(decision_rationale) < int(decision_config.get("minimum_rationale_characters", 40)):
        blockers.append("decision_rationale_too_short")
    if not revision["summary"].get("controls_in_scope"):
        blockers.append("no_controls_in_scope_for_formula_decision")
    return {
        "status": "phase1_final_controls_metric_formula_decision_inputs_ready"
        if not blockers
        else "phase1_final_controls_metric_formula_decision_inputs_blocked",
        "observed": observed,
        "required": required,
        "formula_decision": formula_decision,
        "allowed_formula_decisions": sorted(allowed),
        "source_formula_revision_plan": str(revision["run_dir"]),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation confirms only the claim-closed decision boundary.",
    }


def _build_decision_record(
    *,
    revision: dict[str, Any],
    formula_decision: str,
    decision_rationale: str,
    input_validation: dict[str, Any],
    decision_config: dict[str, Any],
) -> dict[str, Any]:
    selected_formula = None if formula_decision == "unresolved" else formula_decision
    status = (
        "phase1_final_controls_metric_formula_decision_recorded"
        if input_validation.get("status") == "phase1_final_controls_metric_formula_decision_inputs_ready"
        else "phase1_final_controls_metric_formula_decision_blocked"
    )
    return {
        "status": status,
        "formula_decision": formula_decision,
        "selected_formula": selected_formula,
        "decision_rationale": decision_rationale,
        "controls_in_scope": revision["summary"].get("controls_in_scope", []),
        "runtime_formula_ids_before_decision": revision["summary"].get("runtime_formula_ids", []),
        "candidate_formula_options": revision["options"].get("candidate_formulas", []),
        "decision_is_claim_closed": True,
        "existing_artifacts_reclassified": False,
        "thresholds_changed": False,
        "logits_or_metrics_edited": False,
        "controls_rerun_by_decision_runner": False,
        "not_allowed_actions": decision_config.get("not_allowed_actions", []),
        "scientific_limit": "This decision records a formula-contract disposition only; it does not change analysis outputs.",
    }


def _build_implementation_boundary(
    *,
    decision_record: dict[str, Any],
    decision_config: dict[str, Any],
    supporting_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    formula_decision = decision_record.get("formula_decision")
    if formula_decision == "gain_over_chance_ratio":
        next_step = "implement_scoped_metric_formula_contract_update_with_tests"
        code_config_revision_required = True
        controls_rerun_allowed_next = False
        reason = "A formula change requires a separate code/config patch, tests, and review before any control rerun."
    elif formula_decision == "raw_ba_ratio":
        next_step = "keep_existing_runtime_formula_and_fail_closed_controls"
        code_config_revision_required = False
        controls_rerun_allowed_next = False
        reason = "The current runtime formula is retained; existing control blockers remain."
    else:
        next_step = "keep_controls_fail_closed_until_metric_formula_contract_is_resolved"
        code_config_revision_required = False
        controls_rerun_allowed_next = False
        reason = "No formula is selected; governance remains blocked."

    return {
        "status": "phase1_final_controls_metric_formula_implementation_boundary_recorded",
        "formula_decision": formula_decision,
        "next_step": next_step,
        "code_config_revision_required": code_config_revision_required,
        "code_change_allowed_by_this_runner": False,
        "controls_rerun_allowed_by_this_runner": controls_rerun_allowed_next,
        "threshold_change_allowed": False,
        "claim_opening_allowed": False,
        "required_before_any_control_rerun": decision_config.get("required_before_any_control_rerun", []),
        "config_paths_reviewed": {key: value["path"] for key, value in supporting_configs.items()},
        "reason": reason,
        "scientific_limit": "This boundary may identify a future engineering path; it does not execute that path.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    decision_record: dict[str, Any],
    implementation_boundary: dict[str, Any],
    decision_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + [
            "controls_calibration_influence_governance_still_not_claim_evaluable",
            "headline_claim_blocked_until_full_package_passes",
        ]
    )
    if decision_record.get("formula_decision") == "gain_over_chance_ratio":
        blockers.append("metric_formula_code_config_revision_pending")
        blockers.append("controls_must_be_rerun_after_reviewed_formula_contract_update")
    elif decision_record.get("formula_decision") == "raw_ba_ratio":
        blockers.append("existing_controls_remain_fail_closed")
    else:
        blockers.append("metric_formula_contract_unresolved")

    return {
        "status": "phase1_final_controls_metric_formula_decision_claim_state_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": decision_record.get("formula_decision"),
        "selected_formula": decision_record.get("selected_formula"),
        "next_step": implementation_boundary.get("next_step"),
        "blockers": _unique(blockers),
        "not_ok_to_claim": decision_config.get("not_ok_to_claim", []),
        "scientific_limit": "Metric-formula decision keeps all claims closed.",
    }


def _build_summary(
    *,
    output_dir: Path,
    input_validation: dict[str, Any],
    decision_record: dict[str, Any],
    implementation_boundary: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_metric_formula_decision_recorded"
        if input_validation.get("status") == "phase1_final_controls_metric_formula_decision_inputs_ready"
        else "phase1_final_controls_metric_formula_decision_blocked",
        "output_dir": str(output_dir),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": decision_record.get("formula_decision"),
        "selected_formula": decision_record.get("selected_formula"),
        "controls_in_scope": decision_record.get("controls_in_scope", []),
        "existing_artifacts_reclassified": decision_record.get("existing_artifacts_reclassified"),
        "thresholds_changed": decision_record.get("thresholds_changed"),
        "logits_or_metrics_edited": decision_record.get("logits_or_metrics_edited"),
        "controls_rerun_by_decision_runner": decision_record.get("controls_rerun_by_decision_runner"),
        "code_config_revision_required": implementation_boundary.get("code_config_revision_required"),
        "code_change_allowed_by_this_runner": implementation_boundary.get("code_change_allowed_by_this_runner"),
        "controls_rerun_allowed_by_this_runner": implementation_boundary.get("controls_rerun_allowed_by_this_runner"),
        "next_step": implementation_boundary.get("next_step"),
        "claim_blockers": claim_state.get("blockers", []),
        "scientific_limit": "This decision does not prove efficacy or alter any previous results.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    revision: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    summary_path = revision["run_dir"] / "phase1_final_controls_metric_formula_revision_plan_summary.json"
    return {
        "status": "phase1_final_controls_metric_formula_decision_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "formula_revision_plan_run": str(revision["run_dir"]),
        "formula_revision_plan_summary": str(summary_path),
        "formula_revision_plan_summary_sha256": _sha256(summary_path),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / Path(value))
            for key, value in config_paths.items()
            if (repo_root / Path(value)).exists()
        },
        "scientific_limit": "Source links record provenance only.",
    }


def _render_report(
    summary: dict[str, Any],
    decision_record: dict[str, Any],
    implementation_boundary: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Controls Metric Formula Decision",
        "",
        f"Status: `{summary['status']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Formula decision: `{summary['formula_decision']}`",
        f"Selected formula: `{summary['selected_formula']}`",
        "",
        "## Controls In Scope",
        "",
    ]
    lines.extend(f"- `{control}`" for control in decision_record.get("controls_in_scope", []))
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            f"Existing artifacts reclassified: `{summary['existing_artifacts_reclassified']}`",
            f"Thresholds changed: `{summary['thresholds_changed']}`",
            f"Logits or metrics edited: `{summary['logits_or_metrics_edited']}`",
            f"Controls rerun by this runner: `{summary['controls_rerun_by_decision_runner']}`",
            f"Code change allowed by this runner: `{summary['code_change_allowed_by_this_runner']}`",
            "",
            "## Next Step",
            "",
            f"`{implementation_boundary['next_step']}`",
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_memo(
    summary: dict[str, Any],
    decision_record: dict[str, Any],
    implementation_boundary: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Controls Metric Formula Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            "",
            "## Decision",
            "",
            f"Formula decision: `{decision_record['formula_decision']}`",
            f"Selected formula: `{decision_record['selected_formula']}`",
            "",
            "## Rationale",
            "",
            decision_record.get("decision_rationale", ""),
            "",
            "## Boundary",
            "",
            f"Next step: `{implementation_boundary['next_step']}`",
            "This decision does not rerun controls, edit metrics, change thresholds, or open claims.",
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
