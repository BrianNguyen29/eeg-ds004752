"""Phase 1 post-formula-decision governance update.

This runner links the final governance reconciliation state with the
claim-closed metric-formula decision. It does not rerun controls, calibration,
influence, reporting, or model comparators. Its job is to preserve the updated
claim boundary after a formula decision such as ``unresolved``.
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


class Phase1FinalPostFormulaDecisionGovernanceUpdateError(RuntimeError):
    """Raised when post-formula-decision governance update cannot be recorded."""


@dataclass(frozen=True)
class Phase1FinalPostFormulaDecisionGovernanceUpdateResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "update": "configs/phase1/final_post_formula_decision_governance_update.json",
    "formula_decision": "configs/phase1/final_controls_metric_formula_decision.json",
    "governance": "configs/phase1/final_governance_reconciliation.json",
}


def run_phase1_final_post_formula_decision_governance_update(
    *,
    prereg_bundle: str | Path,
    final_governance_reconciliation_run: str | Path,
    formula_decision_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalPostFormulaDecisionGovernanceUpdateResult:
    """Record updated fail-closed governance after metric-formula decision."""

    prereg_bundle = Path(prereg_bundle)
    final_governance_reconciliation_run = _resolve_run_dir(Path(final_governance_reconciliation_run))
    formula_decision_run = _resolve_run_dir(Path(formula_decision_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    update_config = load_config(repo_root / Path(config_paths["update"]))
    governance = _read_governance(final_governance_reconciliation_run)
    formula = _read_formula_decision(formula_decision_run)

    input_validation = _validate_inputs(governance=governance, formula=formula, update_config=update_config)
    metric_formula_status = _build_metric_formula_status(formula=formula)
    claim_state = _build_claim_state(
        governance=governance,
        formula=formula,
        metric_formula_status=metric_formula_status,
        input_validation=input_validation,
        update_config=update_config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        governance=governance,
        formula=formula,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_post_formula_decision_governance_update_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_governance_reconciliation_run": str(final_governance_reconciliation_run),
        "formula_decision_run": str(formula_decision_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        governance=governance,
        formula=formula,
        metric_formula_status=metric_formula_status,
        claim_state=claim_state,
        input_validation=input_validation,
    )

    inputs_path = output_dir / "phase1_final_post_formula_decision_governance_update_inputs.json"
    summary_path = output_dir / "phase1_final_post_formula_decision_governance_update_summary.json"
    report_path = output_dir / "phase1_final_post_formula_decision_governance_update_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_post_formula_decision_governance_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_post_formula_decision_governance_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_metric_formula_contract_status.json", metric_formula_status)
    _write_json(output_dir / "phase1_final_post_formula_decision_governance_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, claim_state, metric_formula_status), encoding="utf-8")
    (output_dir / "phase1_final_post_formula_decision_governance_decision_memo.md").write_text(
        _render_decision_memo(summary, claim_state, metric_formula_status),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalPostFormulaDecisionGovernanceUpdateResult(
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


def _read_governance(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_governance_reconciliation_summary.json",
        "claim_state": "phase1_final_governance_claim_state.json",
        "controls": "phase1_final_controls_reconciliation_status.json",
        "calibration": "phase1_final_calibration_reconciliation_status.json",
        "influence": "phase1_final_influence_reconciliation_status.json",
        "reporting": "phase1_final_reporting_reconciliation_status.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalPostFormulaDecisionGovernanceUpdateError(f"Governance artifact not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _read_formula_decision(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_controls_metric_formula_decision_summary.json",
        "record": "phase1_final_controls_metric_formula_decision_record.json",
        "boundary": "phase1_final_controls_metric_formula_implementation_boundary.json",
        "claim_state": "phase1_final_controls_metric_formula_decision_claim_state.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalPostFormulaDecisionGovernanceUpdateError(
                f"Metric-formula decision artifact not found: {path}"
            )
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(*, governance: dict[str, Any], formula: dict[str, Any], update_config: dict[str, Any]) -> dict[str, Any]:
    required = dict(update_config.get("required_boundary", {}))
    observed = {
        "governance_claim_ready": governance["summary"].get("claim_ready"),
        "governance_headline_phase1_claim_open": governance["summary"].get("headline_phase1_claim_open"),
        "formula_decision_claim_ready": formula["summary"].get("claim_ready"),
        "formula_decision_claims_opened": formula["summary"].get("claims_opened"),
        "formula_decision_thresholds_changed": formula["summary"].get("thresholds_changed"),
        "formula_decision_controls_rerun_by_runner": formula["summary"].get("controls_rerun_by_decision_runner"),
        "formula_decision_logits_or_metrics_edited": formula["summary"].get("logits_or_metrics_edited"),
    }
    blockers = [
        f"boundary_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) != expected
    ]
    if formula["summary"].get("status") != "phase1_final_controls_metric_formula_decision_recorded":
        blockers.append("formula_decision_not_recorded")
    if governance["claim_state"].get("headline_phase1_claim_open") is not False:
        blockers.append("upstream_governance_claim_state_not_closed")
    return {
        "status": "phase1_final_post_formula_decision_governance_inputs_ready"
        if not blockers
        else "phase1_final_post_formula_decision_governance_inputs_blocked",
        "observed": observed,
        "required": required,
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "formula_decision_run": str(formula["run_dir"]),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks claim-closed provenance only.",
    }


def _build_metric_formula_status(*, formula: dict[str, Any]) -> dict[str, Any]:
    decision = formula["summary"].get("formula_decision")
    if decision == "unresolved":
        blockers = ["metric_formula_contract_unresolved"]
        claim_evaluable = False
        next_step = "do_not_rerun_controls_until_metric_formula_contract_is_resolved"
    elif decision == "gain_over_chance_ratio":
        blockers = [
            "metric_formula_code_config_revision_pending",
            "controls_must_be_rerun_after_reviewed_formula_contract_update",
        ]
        claim_evaluable = False
        next_step = "implement_scoped_formula_contract_update_with_tests_before_control_rerun"
    else:
        blockers = ["existing_controls_remain_fail_closed"]
        claim_evaluable = False
        next_step = "keep_existing_runtime_formula_and_preserve_control_blockers"

    return {
        "status": "phase1_final_metric_formula_contract_not_claim_evaluable",
        "claim_evaluable": claim_evaluable,
        "formula_decision": decision,
        "selected_formula": formula["summary"].get("selected_formula"),
        "code_config_revision_required": formula["summary"].get("code_config_revision_required"),
        "code_change_allowed_by_decision_runner": formula["summary"].get("code_change_allowed_by_this_runner"),
        "controls_rerun_allowed_by_decision_runner": formula["summary"].get("controls_rerun_allowed_by_this_runner"),
        "thresholds_changed": formula["summary"].get("thresholds_changed"),
        "logits_or_metrics_edited": formula["summary"].get("logits_or_metrics_edited"),
        "blockers": blockers,
        "next_step": next_step,
        "scientific_limit": "Metric-formula contract status is governance only; it is not model evidence.",
    }


def _build_claim_state(
    *,
    governance: dict[str, Any],
    formula: dict[str, Any],
    metric_formula_status: dict[str, Any],
    input_validation: dict[str, Any],
    update_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + list(governance["summary"].get("claim_blockers", []))
        + _prefixed("metric_formula_contract", metric_formula_status.get("blockers", []))
        + list(update_config.get("standing_claim_blockers", []))
    )
    return {
        "status": "phase1_final_post_formula_decision_governance_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": formula["summary"].get("formula_decision"),
        "selected_formula": formula["summary"].get("selected_formula"),
        "governance_surfaces": governance["summary"].get("governance_surfaces", {}),
        "metric_formula_contract_claim_evaluable": metric_formula_status.get("claim_evaluable"),
        "blockers": blockers,
        "not_ok_to_claim": update_config.get("not_ok_to_claim", []),
        "scientific_limit": "Post-formula-decision governance remains fail-closed.",
    }


def _build_summary(
    *,
    output_dir: Path,
    governance: dict[str, Any],
    formula: dict[str, Any],
    metric_formula_status: dict[str, Any],
    claim_state: dict[str, Any],
    input_validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_post_formula_decision_governance_update_recorded"
        if input_validation.get("status") == "phase1_final_post_formula_decision_governance_inputs_ready"
        else "phase1_final_post_formula_decision_governance_update_blocked",
        "output_dir": str(output_dir),
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "formula_decision_run": str(formula["run_dir"]),
        "formula_decision": formula["summary"].get("formula_decision"),
        "selected_formula": formula["summary"].get("selected_formula"),
        "metric_formula_contract_claim_evaluable": metric_formula_status.get("claim_evaluable"),
        "metric_formula_next_step": metric_formula_status.get("next_step"),
        "governance_surfaces": governance["summary"].get("governance_surfaces", {}),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "claim_blockers": claim_state.get("blockers", []),
        "scientific_limit": "This update records the post-formula-decision claim boundary; it does not alter results.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    governance: dict[str, Any],
    formula: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    governance_summary = governance["run_dir"] / "phase1_final_governance_reconciliation_summary.json"
    formula_summary = formula["run_dir"] / "phase1_final_controls_metric_formula_decision_summary.json"
    return {
        "status": "phase1_final_post_formula_decision_governance_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "final_governance_reconciliation_summary": str(governance_summary),
        "final_governance_reconciliation_summary_sha256": _sha256(governance_summary),
        "formula_decision_run": str(formula["run_dir"]),
        "formula_decision_summary": str(formula_summary),
        "formula_decision_summary_sha256": _sha256(formula_summary),
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
    claim_state: dict[str, Any],
    metric_formula_status: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Post-Formula-Decision Governance Update",
        "",
        f"Status: `{summary['status']}`",
        f"Formula decision: `{summary['formula_decision']}`",
        f"Selected formula: `{summary['selected_formula']}`",
        f"Metric-formula contract claim-evaluable: `{summary['metric_formula_contract_claim_evaluable']}`",
        "",
        "## Metric Formula Contract",
        "",
        f"Next step: `{metric_formula_status['next_step']}`",
        "Blockers:",
        *[f"- `{blocker}`" for blocker in metric_formula_status.get("blockers", [])],
        "",
        "## Claim State",
        "",
        f"Claims opened: `{claim_state['claims_opened']}`",
        "Claim blockers:",
        *[f"- `{blocker}`" for blocker in claim_state.get("blockers", [])],
        "",
        "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
        "",
    ]
    return "\n".join(lines)


def _render_decision_memo(
    summary: dict[str, Any],
    claim_state: dict[str, Any],
    metric_formula_status: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Post-Formula-Decision Governance Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            f"Formula decision: `{summary['formula_decision']}`",
            "",
            "## Decision",
            "",
            "Keep Phase 1 fail-closed. Do not rerun controls or remediate code/config until the metric-formula contract is resolved under revision policy.",
            "",
            "## Metric Formula Next Step",
            "",
            f"`{metric_formula_status['next_step']}`",
            "",
            "## Claim Blockers",
            "",
            *[f"- `{blocker}`" for blocker in claim_state.get("blockers", [])],
            "",
        ]
    )


def _prefixed(prefix: str, items: list[str]) -> list[str]:
    return [f"{prefix}:{item}" for item in items]


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
