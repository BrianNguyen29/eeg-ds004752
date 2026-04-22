"""Phase 1 final metric-formula contract remediation plan.

This runner is intentionally limited to remediation planning after the
post-formula-decision governance update records an unresolved metric-formula
contract. It does not select a formula, change configs, alter thresholds, edit
logits or metrics, rerun controls, or open claims.
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


class Phase1FinalMetricFormulaContractRemediationPlanError(RuntimeError):
    """Raised when metric-formula contract remediation planning cannot be recorded."""


@dataclass(frozen=True)
class Phase1FinalMetricFormulaContractRemediationPlanResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "remediation": "configs/phase1/final_metric_formula_contract_remediation_plan.json",
    "post_formula_governance": "configs/phase1/final_post_formula_decision_governance_update.json",
    "formula_decision": "configs/phase1/final_controls_metric_formula_decision.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_metric_formula_contract_remediation_plan(
    *,
    prereg_bundle: str | Path,
    post_formula_decision_governance_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalMetricFormulaContractRemediationPlanResult:
    """Record claim-closed remediation plan for unresolved metric-formula contract."""

    prereg_bundle = Path(prereg_bundle)
    post_formula_decision_governance_run = _resolve_run_dir(Path(post_formula_decision_governance_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    remediation_config = load_config(repo_root / Path(config_paths["remediation"]))
    supporting_configs = _load_supporting_configs(repo_root, config_paths)
    governance = _read_post_formula_governance(post_formula_decision_governance_run)

    input_validation = _validate_inputs(governance=governance, remediation_config=remediation_config)
    scope = _build_scope(governance=governance, remediation_config=remediation_config, supporting_configs=supporting_configs)
    workplan = _build_workplan(scope=scope, remediation_config=remediation_config)
    guardrails = _build_guardrails(governance=governance, remediation_config=remediation_config)
    claim_state = _build_claim_state(input_validation=input_validation, scope=scope, remediation_config=remediation_config)
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        governance=governance,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    inputs = {
        "status": "phase1_final_metric_formula_contract_remediation_plan_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "post_formula_decision_governance_run": str(post_formula_decision_governance_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        input_validation=input_validation,
        scope=scope,
        workplan=workplan,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_metric_formula_contract_remediation_plan_inputs.json"
    summary_path = output_dir / "phase1_final_metric_formula_contract_remediation_plan_summary.json"
    report_path = output_dir / "phase1_final_metric_formula_contract_remediation_plan_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_metric_formula_contract_remediation_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_metric_formula_contract_remediation_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_metric_formula_contract_remediation_scope.json", scope)
    _write_json(output_dir / "phase1_final_metric_formula_contract_remediation_workplan.json", workplan)
    _write_json(output_dir / "phase1_final_metric_formula_contract_remediation_guardrails.json", guardrails)
    _write_json(output_dir / "phase1_final_metric_formula_contract_remediation_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, scope, workplan, guardrails), encoding="utf-8")
    (output_dir / "phase1_final_metric_formula_contract_remediation_decision_memo.md").write_text(
        _render_decision_memo(summary, scope, workplan),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalMetricFormulaContractRemediationPlanResult(
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


def _read_post_formula_governance(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_post_formula_decision_governance_update_summary.json",
        "input_validation": "phase1_final_post_formula_decision_governance_input_validation.json",
        "metric_formula_status": "phase1_final_metric_formula_contract_status.json",
        "claim_state": "phase1_final_post_formula_decision_governance_claim_state.json",
        "source_links": "phase1_final_post_formula_decision_governance_source_links.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalMetricFormulaContractRemediationPlanError(
                f"Post-formula-decision governance artifact not found: {path}"
            )
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(*, governance: dict[str, Any], remediation_config: dict[str, Any]) -> dict[str, Any]:
    required = dict(remediation_config.get("required_boundary", {}))
    observed = {
        "post_formula_claim_ready": governance["summary"].get("claim_ready"),
        "post_formula_headline_phase1_claim_open": governance["summary"].get("headline_phase1_claim_open"),
        "post_formula_claims_opened": governance["summary"].get("claims_opened"),
        "metric_formula_contract_claim_evaluable": governance["summary"].get("metric_formula_contract_claim_evaluable"),
        "formula_decision": governance["summary"].get("formula_decision"),
        "selected_formula": governance["summary"].get("selected_formula"),
    }
    blockers = [
        f"boundary_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) != expected
    ]
    if "metric_formula_contract:metric_formula_contract_unresolved" not in governance["claim_state"].get("blockers", []):
        blockers.append("metric_formula_contract_unresolved_blocker_missing")
    if governance["metric_formula_status"].get("next_step") != "do_not_rerun_controls_until_metric_formula_contract_is_resolved":
        blockers.append("metric_formula_next_step_not_fail_closed")
    return {
        "status": "phase1_final_metric_formula_contract_remediation_inputs_ready"
        if not blockers
        else "phase1_final_metric_formula_contract_remediation_inputs_blocked",
        "observed": observed,
        "required": required,
        "post_formula_decision_governance_run": str(governance["run_dir"]),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks only the claim-closed unresolved formula-contract boundary.",
    }


def _build_scope(
    *,
    governance: dict[str, Any],
    remediation_config: dict[str, Any],
    supporting_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_metric_formula_contract_remediation_scope_recorded",
        "remediation_scope": "metric_formula_contract_docs_config_planning_only",
        "formula_decision": governance["summary"].get("formula_decision"),
        "selected_formula": governance["summary"].get("selected_formula"),
        "metric_formula_contract_claim_evaluable": False,
        "allowed_remediation_targets": remediation_config.get("allowed_remediation_targets", []),
        "candidate_formula_semantics": remediation_config.get("candidate_formula_semantics", []),
        "config_paths_reviewed": {key: value["path"] for key, value in supporting_configs.items()},
        "code_change_allowed_now": False,
        "runtime_formula_change_allowed_now": False,
        "threshold_change_allowed_now": False,
        "controls_rerun_allowed_now": False,
        "claim_opening_allowed_now": False,
        "scientific_limit": "Scope authorizes planning only; no contract, code, or result is changed.",
    }


def _build_workplan(*, scope: dict[str, Any], remediation_config: dict[str, Any]) -> dict[str, Any]:
    work_items = [
        {
            "id": item.get("id"),
            "objective": item.get("objective"),
            "required_before_execution": item.get("required_before_execution", []),
            "allowed_outputs": item.get("allowed_outputs", []),
            "not_allowed": remediation_config.get("not_allowed_actions", []),
        }
        for item in remediation_config.get("work_items", [])
    ]
    return {
        "status": "phase1_final_metric_formula_contract_remediation_workplan_recorded",
        "work_items": work_items,
        "next_step": "draft_metric_formula_contract_revision_proposal",
        "claims_opened": False,
        "scientific_limit": "Workplan is a planning artifact only and does not authorize reruns.",
    }


def _build_guardrails(*, governance: dict[str, Any], remediation_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_metric_formula_contract_remediation_guardrails_recorded",
        "claims_opened": False,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "scientific_integrity_rule": remediation_config.get("scientific_integrity_rule"),
        "not_allowed_actions": remediation_config.get("not_allowed_actions", []),
        "source_claim_blockers": governance["summary"].get("claim_blockers", []),
        "not_ok_to_claim": remediation_config.get("not_ok_to_claim", []),
        "scientific_limit": "Guardrails preserve the unresolved contract blocker.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    scope: dict[str, Any],
    remediation_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + [
            "metric_formula_contract_unresolved",
            "metric_formula_contract_revision_proposal_pending",
            "controls_must_not_be_rerun_until_contract_is_resolved",
            "headline_claim_blocked_until_full_package_passes",
        ]
    )
    return {
        "status": "phase1_final_metric_formula_contract_remediation_claim_state_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": scope.get("formula_decision"),
        "selected_formula": scope.get("selected_formula"),
        "blockers": blockers,
        "not_ok_to_claim": remediation_config.get("not_ok_to_claim", []),
        "scientific_limit": "Remediation planning keeps all claims closed.",
    }


def _build_summary(
    *,
    output_dir: Path,
    input_validation: dict[str, Any],
    scope: dict[str, Any],
    workplan: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_metric_formula_contract_remediation_plan_recorded"
        if input_validation.get("status") == "phase1_final_metric_formula_contract_remediation_inputs_ready"
        else "phase1_final_metric_formula_contract_remediation_plan_blocked",
        "output_dir": str(output_dir),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": scope.get("formula_decision"),
        "selected_formula": scope.get("selected_formula"),
        "remediation_scope": scope.get("remediation_scope"),
        "code_change_allowed_now": scope.get("code_change_allowed_now"),
        "runtime_formula_change_allowed_now": scope.get("runtime_formula_change_allowed_now"),
        "threshold_change_allowed_now": scope.get("threshold_change_allowed_now"),
        "controls_rerun_allowed_now": scope.get("controls_rerun_allowed_now"),
        "claim_opening_allowed_now": scope.get("claim_opening_allowed_now"),
        "next_step": workplan.get("next_step"),
        "claim_blockers": claim_state.get("blockers", []),
        "scientific_limit": "This plan records remediation planning only; it does not resolve the formula contract.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    governance: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    summary_path = governance["run_dir"] / "phase1_final_post_formula_decision_governance_update_summary.json"
    return {
        "status": "phase1_final_metric_formula_contract_remediation_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "post_formula_decision_governance_run": str(governance["run_dir"]),
        "post_formula_decision_governance_summary": str(summary_path),
        "post_formula_decision_governance_summary_sha256": _sha256(summary_path),
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
    scope: dict[str, Any],
    workplan: dict[str, Any],
    guardrails: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Metric Formula Contract Remediation Plan",
        "",
        f"Status: `{summary['status']}`",
        f"Formula decision: `{summary['formula_decision']}`",
        f"Selected formula: `{summary['selected_formula']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        "",
        "## Scope",
        "",
        f"Remediation scope: `{scope['remediation_scope']}`",
        f"Code change allowed now: `{scope['code_change_allowed_now']}`",
        f"Controls rerun allowed now: `{scope['controls_rerun_allowed_now']}`",
        f"Threshold change allowed now: `{scope['threshold_change_allowed_now']}`",
        "",
        "## Work Items",
        "",
    ]
    for item in workplan.get("work_items", []):
        lines.append(f"- `{item['id']}`: {item['objective']}")
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            guardrails.get("scientific_integrity_rule", ""),
            "",
            "Not allowed:",
        ]
    )
    lines.extend(f"- `{item}`" for item in guardrails.get("not_allowed_actions", []))
    lines.extend(
        [
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_decision_memo(summary: dict[str, Any], scope: dict[str, Any], workplan: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 1 Metric Formula Contract Remediation Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            f"Formula decision: `{summary['formula_decision']}`",
            "",
            "## Decision",
            "",
            "Open only a claim-closed contract remediation plan. Do not select a formula, change runtime semantics, alter thresholds, rerun controls, or open claims from this plan.",
            "",
            "## Next Step",
            "",
            f"`{workplan['next_step']}`",
            "",
            "## Current Permissions",
            "",
            f"- Code change allowed now: `{scope['code_change_allowed_now']}`",
            f"- Runtime formula change allowed now: `{scope['runtime_formula_change_allowed_now']}`",
            f"- Controls rerun allowed now: `{scope['controls_rerun_allowed_now']}`",
            f"- Claim opening allowed now: `{scope['claim_opening_allowed_now']}`",
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
