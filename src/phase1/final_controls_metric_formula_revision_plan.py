"""Phase 1 final controls metric-formula revision plan.

This module records the next governance step after the metric-contract audit
finds formula ambiguity. It does not choose a formula, edit configs, alter
thresholds, rerun controls, or open claims. Its output is a claim-closed plan
for a revision-scoped decision.
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


class Phase1FinalControlsMetricFormulaRevisionPlanError(RuntimeError):
    """Raised when the metric-formula revision plan cannot be recorded."""


@dataclass(frozen=True)
class Phase1FinalControlsMetricFormulaRevisionPlanResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "revision_plan": "configs/phase1/final_controls_metric_formula_revision_plan.json",
    "metric_contract": "configs/phase1/final_controls_metric_contract_audit.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_controls_metric_formula_revision_plan(
    *,
    prereg_bundle: str | Path,
    metric_contract_audit_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalControlsMetricFormulaRevisionPlanResult:
    """Record a fail-closed revision plan for relative-metric formula ambiguity."""

    prereg_bundle = Path(prereg_bundle)
    metric_contract_audit_run = _resolve_run_dir(Path(metric_contract_audit_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    revision_config = load_config(repo_root / Path(config_paths["revision_plan"]))
    supporting_configs = _load_supporting_configs(repo_root, config_paths)
    metric_audit = _read_metric_contract_audit(metric_contract_audit_run)

    input_validation = _validate_inputs(metric_audit=metric_audit, revision_config=revision_config)
    formula_options = _build_formula_options(metric_audit=metric_audit, revision_config=revision_config)
    revision_scope = _build_revision_scope(
        metric_audit=metric_audit,
        input_validation=input_validation,
        formula_options=formula_options,
        revision_config=revision_config,
        supporting_configs=supporting_configs,
    )
    decision_requirements = _build_decision_requirements(
        metric_audit=metric_audit,
        revision_scope=revision_scope,
        revision_config=revision_config,
    )
    claim_state = _build_claim_state(
        input_validation=input_validation,
        revision_scope=revision_scope,
        decision_requirements=decision_requirements,
        revision_config=revision_config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        metric_audit=metric_audit,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_controls_metric_formula_revision_plan_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "metric_contract_audit_run": str(metric_contract_audit_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        input_validation=input_validation,
        revision_scope=revision_scope,
        decision_requirements=decision_requirements,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_controls_metric_formula_revision_plan_inputs.json"
    summary_path = output_dir / "phase1_final_controls_metric_formula_revision_plan_summary.json"
    report_path = output_dir / "phase1_final_controls_metric_formula_revision_plan_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_controls_metric_formula_revision_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_controls_metric_formula_revision_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_controls_metric_formula_options.json", formula_options)
    _write_json(output_dir / "phase1_final_controls_metric_formula_revision_scope.json", revision_scope)
    _write_json(output_dir / "phase1_final_controls_metric_formula_decision_requirements.json", decision_requirements)
    _write_json(output_dir / "phase1_final_controls_metric_formula_revision_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, revision_scope, decision_requirements),
        encoding="utf-8",
    )
    (output_dir / "phase1_final_controls_metric_formula_revision_decision_memo.md").write_text(
        _render_decision_memo(summary, formula_options, decision_requirements),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalControlsMetricFormulaRevisionPlanResult(
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


def _read_metric_contract_audit(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_controls_metric_contract_audit_summary.json",
        "formula_review": "relative_metric_formula_review.json",
        "threshold_review": "controls_threshold_contract_review.json",
        "recommendation": "controls_metric_contract_remediation_recommendation.json",
        "claim_state": "phase1_final_controls_metric_contract_claim_state.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalControlsMetricFormulaRevisionPlanError(f"Metric-contract audit artifact not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(*, metric_audit: dict[str, Any], revision_config: dict[str, Any]) -> dict[str, Any]:
    required = dict(revision_config.get("required_boundary", {}))
    observed = {
        "metric_audit_claims_opened": metric_audit["summary"].get("claims_opened"),
        "metric_audit_claim_ready": metric_audit["summary"].get("claim_ready"),
        "metric_audit_formula_ambiguity_detected": metric_audit["summary"].get("formula_ambiguity_detected"),
        "metric_audit_headline_claim_open": metric_audit["claim_state"].get("headline_phase1_claim_open"),
    }
    blockers = [
        f"boundary_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    if metric_audit["summary"].get("relative_formula_locked") is True:
        blockers.append("relative_formula_already_locked_no_revision_plan_needed")
    if not metric_audit["summary"].get("controls_with_formula_dependent_pass_status"):
        blockers.append("no_formula_dependent_control_detected")
    return {
        "status": "phase1_final_controls_metric_formula_revision_inputs_ready"
        if not blockers
        else "phase1_final_controls_metric_formula_revision_inputs_blocked",
        "observed": observed,
        "required": required,
        "source_metric_contract_audit": str(metric_audit["run_dir"]),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation confirms only the revision-planning boundary.",
    }


def _build_formula_options(*, metric_audit: dict[str, Any], revision_config: dict[str, Any]) -> dict[str, Any]:
    options = []
    candidate_names = set(revision_config.get("candidate_relative_formulas", []))
    for formula_id in sorted(candidate_names):
        rows = []
        for row in metric_audit["formula_review"].get("rows", []):
            candidate_value = row.get("candidate_formulas", {}).get(formula_id)
            pass_key = "pass_under_raw_ba_ratio" if formula_id == "raw_ba_ratio" else "pass_under_gain_over_chance_ratio"
            rows.append(
                {
                    "control_id": row.get("control_id"),
                    "candidate_value": candidate_value,
                    "would_pass_existing_threshold": row.get(pass_key),
                    "changes_runtime_pass_status": (
                        bool(row.get("candidate_formula_changes_pass_status"))
                        and formula_id != row.get("runtime_formula_matches")
                    ),
                }
            )
        options.append(
            {
                "formula_id": formula_id,
                "status": "candidate_for_revision_review",
                "rows": rows,
                "not_selected_by_this_plan": True,
            }
        )
    return {
        "status": "phase1_final_controls_metric_formula_options_recorded",
        "runtime_formula_ids": metric_audit["summary"].get("current_runtime_formula_ids", []),
        "candidate_formulas": options,
        "selected_formula": None,
        "scientific_limit": "Formula options are recorded for revision review only; this plan does not select one.",
    }


def _build_revision_scope(
    *,
    metric_audit: dict[str, Any],
    input_validation: dict[str, Any],
    formula_options: dict[str, Any],
    revision_config: dict[str, Any],
    supporting_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    ambiguity = bool(metric_audit["summary"].get("formula_ambiguity_detected"))
    dependent = list(metric_audit["summary"].get("controls_with_formula_dependent_pass_status", []))
    return {
        "status": "phase1_final_controls_metric_formula_revision_scope_recorded",
        "revision_required": ambiguity and not input_validation.get("blockers"),
        "revision_scope": "metric_formula_contract_only",
        "controls_in_scope": dependent,
        "runtime_formula_ids": metric_audit["summary"].get("current_runtime_formula_ids", []),
        "relative_formula_locked_before_revision": metric_audit["summary"].get("relative_formula_locked"),
        "selected_formula": formula_options.get("selected_formula"),
        "code_change_allowed_now": False,
        "rerun_controls_allowed_now": False,
        "threshold_change_allowed_now": False,
        "required_sources_to_review": revision_config.get("required_sources_to_review", []),
        "config_paths": {key: value["path"] for key, value in supporting_configs.items()},
        "scientific_limit": "Scope records a revision decision boundary only; it does not modify analysis outputs.",
    }


def _build_decision_requirements(
    *,
    metric_audit: dict[str, Any],
    revision_scope: dict[str, Any],
    revision_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_metric_formula_decision_requirements_recorded",
        "manual_decision_required": bool(revision_scope.get("revision_required")),
        "decision_must_be_made_before_code_change": True,
        "decision_must_be_made_before_control_rerun": True,
        "decision_must_document_formula_choice": True,
        "decision_must_document_scientific_rationale": True,
        "decision_must_preserve_locked_threshold_values": True,
        "decision_must_preserve_existing_artifacts": True,
        "source_metric_audit_next_step": metric_audit["summary"].get("next_step"),
        "allowed_outcomes": revision_config.get("allowed_revision_outcomes", []),
        "not_allowed_actions": revision_config.get("not_allowed_actions", []),
        "scientific_limit": "Decision requirements do not authorize claims or code changes by themselves.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    revision_scope: dict[str, Any],
    decision_requirements: dict[str, Any],
    revision_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + [
            "metric_formula_revision_decision_pending",
            "controls_calibration_influence_governance_still_not_claim_evaluable",
            "headline_claim_blocked_until_full_package_passes",
        ]
    )
    return {
        "status": "phase1_final_controls_metric_formula_revision_claim_state_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "revision_required": revision_scope.get("revision_required"),
        "manual_decision_required": decision_requirements.get("manual_decision_required"),
        "blockers": blockers,
        "not_ok_to_claim": revision_config.get("not_ok_to_claim", []),
        "scientific_limit": "Metric-formula revision planning keeps all claims closed.",
    }


def _build_summary(
    *,
    output_dir: Path,
    input_validation: dict[str, Any],
    revision_scope: dict[str, Any],
    decision_requirements: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_controls_metric_formula_revision_plan_recorded"
        if input_validation.get("status") == "phase1_final_controls_metric_formula_revision_inputs_ready"
        else "phase1_final_controls_metric_formula_revision_plan_blocked",
        "output_dir": str(output_dir),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "revision_required": revision_scope.get("revision_required"),
        "manual_decision_required": decision_requirements.get("manual_decision_required"),
        "controls_in_scope": revision_scope.get("controls_in_scope", []),
        "runtime_formula_ids": revision_scope.get("runtime_formula_ids", []),
        "selected_formula": revision_scope.get("selected_formula"),
        "code_change_allowed_now": revision_scope.get("code_change_allowed_now"),
        "rerun_controls_allowed_now": revision_scope.get("rerun_controls_allowed_now"),
        "threshold_change_allowed_now": revision_scope.get("threshold_change_allowed_now"),
        "next_step": "manual_metric_formula_revision_decision",
        "claim_blockers": claim_state.get("blockers", []),
        "scientific_limit": "This plan records a revision decision boundary only; it does not choose a formula or prove efficacy.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    metric_audit: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    summary_path = metric_audit["run_dir"] / "phase1_final_controls_metric_contract_audit_summary.json"
    return {
        "status": "phase1_final_controls_metric_formula_revision_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "metric_contract_audit_run": str(metric_audit["run_dir"]),
        "metric_contract_audit_summary": str(summary_path),
        "metric_contract_audit_summary_sha256": _sha256(summary_path),
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
    revision_scope: dict[str, Any],
    decision_requirements: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Controls Metric Formula Revision Plan",
        "",
        f"Status: `{summary['status']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Revision required: `{summary['revision_required']}`",
        f"Manual decision required: `{summary['manual_decision_required']}`",
        f"Selected formula: `{summary['selected_formula']}`",
        "",
        "## Controls In Scope",
        "",
    ]
    lines.extend(f"- `{control}`" for control in revision_scope.get("controls_in_scope", []))
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            f"Code change allowed now: `{summary['code_change_allowed_now']}`",
            f"Rerun controls allowed now: `{summary['rerun_controls_allowed_now']}`",
            f"Threshold change allowed now: `{summary['threshold_change_allowed_now']}`",
            "",
            "## Decision Requirements",
            "",
        ]
    )
    for key, value in decision_requirements.items():
        if key.startswith("decision_must_"):
            lines.append(f"- `{key}`: `{value}`")
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
    formula_options: dict[str, Any],
    decision_requirements: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Controls Metric Formula Revision Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            "",
            "## Decision",
            "",
            "Open only a claim-closed metric-formula revision decision. No formula is selected by this plan.",
            "",
            "## Candidate Formula Options",
            "",
            *[f"- `{option['formula_id']}`" for option in formula_options.get("candidate_formulas", [])],
            "",
            "## Required Before Any Code Change Or Control Rerun",
            "",
            *[
                f"- `{key}`"
                for key, value in decision_requirements.items()
                if key.startswith("decision_must_") and value is True
            ],
            "",
            "## Guardrail",
            "",
            "Do not choose a formula post hoc to improve results. Any formula choice must be justified from the locked scientific contract or a documented revision policy.",
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
