"""Phase 1 final claim-package specification and readiness plan.

This runner records the contract for a future claim-bearing Phase 1 package.
It is intentionally non-claim and fail-closed: it validates prerequisite
readiness surfaces and lists missing final artifacts, but it does not train
models, execute controls, estimate calibration, estimate influence, or promote
smoke diagnostics into efficacy evidence.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .claim_state import EXPECTED_NON_CLAIM_SMOKE_REVIEWS
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalClaimPackageError(RuntimeError):
    """Raised when the final claim-package plan cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalClaimPackageResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "package": "configs/phase1/final_claim_package.json",
    "a3_model": "configs/models/distill_a3.yaml",
    "a4_model": "configs/models/privileged_a4.yaml",
    "controls": "configs/controls/control_suite_spec.yaml",
    "claim_mapping": "configs/eval/claim_mapping.yaml",
    "metrics": "configs/eval/metrics.yaml",
    "inference": "configs/eval/inference_defaults.yaml",
    "gate1": "configs/gate1/decision_simulation.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_claim_package_plan(
    *,
    prereg_bundle: str | Path,
    governance_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalClaimPackageResult:
    """Write a non-claim final claim-package plan and blocker inventory."""

    prereg_bundle = Path(prereg_bundle)
    governance_run = _resolve_run_dir(Path(governance_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    governance = _read_governance_package(governance_run)
    package_config = load_config(repo_root / config_paths["package"])
    supporting_configs = _load_supporting_configs(repo_root, config_paths)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    contract = _build_contract(package_config, supporting_configs)
    comparator_readiness = _review_comparator_readiness(package_config, supporting_configs)
    governance_review = _review_governance_boundary(governance, package_config)
    blocker_inventory = _build_blocker_inventory(
        package_config=package_config,
        contract=contract,
        comparator_readiness=comparator_readiness,
        governance_review=governance_review,
    )
    claim_state = _build_claim_state(package_config, blocker_inventory, governance_review)
    implementation_plan = _build_implementation_plan(blocker_inventory)
    summary = {
        "status": "phase1_final_claim_package_plan_recorded",
        "output_dir": str(output_dir),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "package_status": package_config.get("status"),
        "completed_non_claim_smoke_reviews": governance_review["completed_non_claim_smoke_reviews"],
        "required_final_comparators": package_config.get("required_final_comparators", []),
        "blockers": blocker_inventory["blockers"],
        "next_step": "implement_final_comparator_control_calibration_influence_reporting_artifacts_under_this_contract",
        "scientific_limit": (
            "Final claim-package plan only. It does not produce final Phase 1 evidence "
            "and cannot support efficacy or privileged-transfer claims."
        ),
    }
    inputs = {
        "status": "phase1_final_claim_package_plan_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "governance_run": str(governance_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_claim_package_plan_inputs.json"
    summary_path = output_dir / "phase1_final_claim_package_plan_summary.json"
    report_path = output_dir / "phase1_final_claim_package_plan_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_claim_package_contract.json", contract)
    _write_json(output_dir / "phase1_final_comparator_readiness.json", comparator_readiness)
    _write_json(output_dir / "phase1_final_governance_boundary_review.json", governance_review)
    _write_json(output_dir / "phase1_final_claim_blocker_inventory.json", blocker_inventory)
    _write_json(output_dir / "phase1_final_claim_state_plan.json", claim_state)
    _write_json(output_dir / "phase1_final_implementation_plan.json", implementation_plan)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, contract, comparator_readiness, governance_review, blocker_inventory, claim_state),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalClaimPackageResult(
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


def _read_governance_package(governance_run: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_governance_readiness_summary.json",
        "claim_state": "phase1_claim_state.json",
        "controls": "phase1_control_suite_status.json",
        "calibration": "phase1_calibration_package_status.json",
        "influence": "phase1_influence_status.json",
        "reporting": "phase1_reporting_readiness.json",
    }
    payload = {}
    for key, filename in required.items():
        path = governance_run / filename
        if not path.exists():
            raise Phase1FinalClaimPackageError(f"Governance artifact not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _load_supporting_configs(repo_root: Path, config_paths: dict[str, str | Path]) -> dict[str, dict[str, Any]]:
    configs = {}
    for key, relative in config_paths.items():
        if key == "package":
            continue
        path = repo_root / Path(relative)
        configs[key] = {"path": str(path), "data": load_config(path)}
    return configs


def _build_contract(package_config: dict[str, Any], supporting_configs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    gate1 = supporting_configs["gate1"]["data"]
    gate2 = supporting_configs["gate2"]["data"]
    return {
        "status": "phase1_final_claim_package_contract_recorded",
        "package_id": package_config.get("package_id"),
        "package_status": package_config.get("status"),
        "claim_scope": package_config.get("claim_scope"),
        "primary_endpoint": package_config.get("primary_endpoint", {}),
        "required_final_comparators": package_config.get("required_final_comparators", []),
        "required_non_claim_smoke_reviews": package_config.get("required_non_claim_smoke_reviews", []),
        "required_final_comparator_artifacts": package_config.get("required_final_comparator_artifacts", []),
        "required_final_control_results": package_config.get("required_final_control_results", []),
        "required_final_calibration_artifacts": package_config.get("required_final_calibration_artifacts", []),
        "required_final_influence_artifacts": package_config.get("required_final_influence_artifacts", []),
        "required_final_reporting_artifacts": package_config.get("required_final_reporting_artifacts", []),
        "claim_opening_rules": package_config.get("claim_opening_rules", {}),
        "locked_threshold_references": {
            "subject_level_sesoi_delta_ba": gate1.get("subject_level_sesoi_delta_ba"),
            "max_allowed_delta_ece": gate1.get("max_allowed_delta_ece"),
            "gate1_influence_ceiling": gate1.get("influence_ceiling"),
            "negative_control_max_abs_gain": gate2.get("pass_criteria", {}).get("negative_control_max_abs_gain"),
            "gate2_influence_ceiling": gate2.get("frozen_threshold_defaults", {}).get("influence_ceiling"),
            "nuisance_absolute_ceiling": gate2.get("frozen_threshold_defaults", {}).get("nuisance_absolute_ceiling"),
            "nuisance_relative_ceiling": gate2.get("frozen_threshold_defaults", {}).get("nuisance_relative_ceiling"),
            "spatial_relative_ceiling": gate2.get("frozen_threshold_defaults", {}).get("spatial_relative_ceiling"),
        },
        "scientific_integrity_rule": package_config.get("scientific_integrity_rule"),
    }


def _review_comparator_readiness(
    package_config: dict[str, Any],
    supporting_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    a3 = supporting_configs["a3_model"]["data"]
    a4 = supporting_configs["a4_model"]["data"]
    items = [
        {
            "comparator_id": "A3_distillation",
            "config_path": supporting_configs["a3_model"]["path"],
            "config_status": a3.get("status"),
            "final_comparator_ready": bool(a3.get("final_comparator_ready")),
            "claim_scope": a3.get("claim_scope"),
            "blocker": None if a3.get("final_comparator_ready") is True else "a3_final_comparator_not_ready",
        },
        {
            "comparator_id": "A4_privileged",
            "config_path": supporting_configs["a4_model"]["path"],
            "config_status": a4.get("status"),
            "final_comparator_ready": bool(a4.get("final_comparator_ready")),
            "claim_scope": a4.get("claim_scope"),
            "blocker": None if a4.get("final_comparator_ready") is True else "a4_final_comparator_not_ready",
        },
    ]
    missing_artifact_manifests = [
        {
            "comparator_id": comparator,
            "missing": package_config.get("required_final_comparator_artifacts", []),
        }
        for comparator in package_config.get("required_final_comparators", [])
    ]
    blockers = [item["blocker"] for item in items if item["blocker"]]
    blockers.append("final_comparator_artifact_manifests_missing")
    return {
        "status": "phase1_final_comparator_readiness_blocked",
        "claim_evaluable": False,
        "items": items,
        "required_final_comparators": package_config.get("required_final_comparators", []),
        "missing_final_comparator_artifact_manifests": missing_artifact_manifests,
        "blockers": blockers,
        "scientific_limit": "A3/A4 smoke configs remain non-claim and cannot satisfy final comparator readiness.",
    }


def _review_governance_boundary(
    governance: dict[str, Any],
    package_config: dict[str, Any],
) -> dict[str, Any]:
    summary = governance["summary"]
    claim_state = governance["claim_state"]
    completed = summary.get("completed_non_claim_smoke_reviews", [])
    expected = package_config.get("required_non_claim_smoke_reviews", EXPECTED_NON_CLAIM_SMOKE_REVIEWS)
    missing_smokes = [item for item in expected if item not in completed]
    violations = []
    if summary.get("status") != "phase1_governance_readiness_blocked":
        violations.append("governance_readiness_not_blocked")
    if summary.get("claim_ready") is not False:
        violations.append("governance_claim_ready_not_false")
    if summary.get("headline_phase1_claim_open") is not False:
        violations.append("governance_headline_claim_open_not_false")
    if claim_state.get("full_phase1_claim_bearing_run_allowed") is not False:
        violations.append("governance_full_claim_bearing_run_allowed_not_false")
    return {
        "status": "phase1_final_governance_boundary_review_complete",
        "governance_status": summary.get("status"),
        "claim_ready": summary.get("claim_ready"),
        "headline_phase1_claim_open": summary.get("headline_phase1_claim_open"),
        "full_phase1_claim_bearing_run_allowed": claim_state.get("full_phase1_claim_bearing_run_allowed"),
        "completed_non_claim_smoke_reviews": completed,
        "missing_required_non_claim_smoke_reviews": missing_smokes,
        "boundary_violations": violations,
        "governance_surfaces": summary.get("governance_surfaces", {}),
        "scientific_limit": "A passing boundary review only confirms that claims remain closed before final artifacts exist.",
    }


def _build_blocker_inventory(
    *,
    package_config: dict[str, Any],
    contract: dict[str, Any],
    comparator_readiness: dict[str, Any],
    governance_review: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if package_config.get("status") != "final_claim_package_locked":
        blockers.append("final_claim_package_config_not_locked")
    blockers.extend(comparator_readiness["blockers"])
    if governance_review["missing_required_non_claim_smoke_reviews"]:
        blockers.append("required_non_claim_smoke_reviews_missing")
    if governance_review["boundary_violations"]:
        blockers.append("governance_boundary_violation")
    blockers.extend(
        [
            "final_control_results_missing",
            "final_calibration_package_missing",
            "final_influence_package_missing",
            "final_reporting_package_missing",
            "claim_opening_rules_not_evaluable_without_final_artifacts",
        ]
    )
    return {
        "status": "phase1_final_claim_blocker_inventory_recorded",
        "claim_ready": False,
        "blockers": _unique(blockers),
        "missing_final_artifact_groups": {
            "comparators": contract["required_final_comparator_artifacts"],
            "controls": contract["required_final_control_results"],
            "calibration": contract["required_final_calibration_artifacts"],
            "influence": contract["required_final_influence_artifacts"],
            "reporting": contract["required_final_reporting_artifacts"],
        },
        "scientific_limit": "This inventory lists missing evidence; it does not substitute for evidence.",
    }


def _build_claim_state(
    package_config: dict[str, Any],
    blocker_inventory: dict[str, Any],
    governance_review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_claim_state_plan_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "package_status": package_config.get("status"),
        "completed_non_claim_smoke_reviews": governance_review["completed_non_claim_smoke_reviews"],
        "blockers": blocker_inventory["blockers"],
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": (
            "This plan may be used as an engineering checklist for final artifact implementation. "
            "It is not scientific evidence for any Phase 1 claim."
        ),
    }


def _build_implementation_plan(blocker_inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_implementation_plan_recorded",
        "ordered_items": [
            {
                "item": "lock_final_comparator_contracts",
                "purpose": "Define final A2/A2b/A2c/A2d/A3/A4 claim-bearing run manifests and leak guards.",
            },
            {
                "item": "implement_executable_control_suite",
                "purpose": "Produce final negative-control manifests and pass/fail decisions from locked thresholds.",
            },
            {
                "item": "implement_final_calibration_package",
                "purpose": "Compute ECE, Brier, NLL, reliability and risk-coverage from final logits only.",
            },
            {
                "item": "implement_final_influence_package",
                "purpose": "Run leave-one-subject-out deltas and claim-state flip checks against the locked ceiling.",
            },
            {
                "item": "implement_final_reporting_package",
                "purpose": "Compile final fold logs, comparator completeness, control, calibration, influence and claim-state reports.",
            },
        ],
        "blocked_by": blocker_inventory["blockers"],
        "scientific_integrity_rule": "Each implementation item must remain fail-closed until its real artifact evidence exists.",
    }


def _render_report(
    summary: dict[str, Any],
    contract: dict[str, Any],
    comparator_readiness: dict[str, Any],
    governance_review: dict[str, Any],
    blocker_inventory: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Claim-Package Plan",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Package status: `{summary['package_status']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        "",
        "## Contract",
        "",
        f"- Package ID: `{contract['package_id']}`",
        f"- Primary metric: `{contract['primary_endpoint'].get('primary_metric')}`",
        f"- Unit of inference: `{contract['primary_endpoint'].get('unit_of_inference')}`",
        "",
        "## Required Final Comparators",
        "",
    ]
    for comparator in contract["required_final_comparators"]:
        lines.append(f"- {comparator}")
    lines.extend(["", "## Comparator Readiness", ""])
    for item in comparator_readiness["items"]:
        lines.append(
            f"- {item['comparator_id']}: final_ready=`{item['final_comparator_ready']}` "
            f"status=`{item['config_status']}`"
        )
    lines.extend(["", "## Governance Boundary", ""])
    lines.append(f"- Governance status: `{governance_review['governance_status']}`")
    lines.append(f"- Claim ready: `{governance_review['claim_ready']}`")
    lines.append(f"- Boundary violations: `{governance_review['boundary_violations']}`")
    lines.extend(["", "## Blockers", ""])
    for blocker in blocker_inventory["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Scientific Integrity", ""])
    lines.append("- This plan does not train models or execute final controls.")
    lines.append("- It does not estimate calibration, influence, or final comparator performance.")
    lines.append("- Smoke metrics remain implementation diagnostics only.")
    lines.append("- Headline claims remain closed until every final artifact group exists and passes locked rules.")
    lines.extend(["", "## Not OK To Claim", ""])
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


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
