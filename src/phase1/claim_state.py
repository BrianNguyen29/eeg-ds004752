"""Phase 1 governance readiness and claim-state package.

The runner aggregates the post-A4 gap review with executable governance
surfaces for controls, calibration, influence and reporting. It is deliberately
fail-closed: the presence of smoke runs can document engineering progress, but
cannot open headline claims.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..guards import assert_real_phase_allowed
from .calibration import evaluate_calibration_package
from .controls import evaluate_control_suite
from .influence import evaluate_influence_package
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1GovernanceReadinessError(RuntimeError):
    """Raised when Phase 1 governance readiness cannot be evaluated."""


@dataclass(frozen=True)
class Phase1GovernanceReadinessResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "controls": "configs/controls/control_suite_spec.yaml",
    "nuisance": "configs/controls/nuisance_block_spec.yaml",
    "metrics": "configs/eval/metrics.yaml",
    "inference": "configs/eval/inference_defaults.yaml",
    "gate1": "configs/gate1/decision_simulation.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}

REQUIRED_REPORTING_ARTIFACTS = [
    "final_comparator_completeness_table",
    "negative_controls_report",
    "calibration_package_report",
    "influence_package_report",
    "final_fold_logs",
    "claim_state_report",
    "main_phase1_report",
]

EXPECTED_NON_CLAIM_SMOKE_REVIEWS = [
    "A2_A2b",
    "A2c_CORAL",
    "A2d_riemannian",
    "A3_distillation",
    "A4_privileged",
]


def run_phase1_governance_readiness(
    *,
    prereg_bundle: str | Path,
    gap_review_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1GovernanceReadinessResult:
    """Write a fail-closed Phase 1 governance readiness package."""

    prereg_bundle = Path(prereg_bundle)
    gap_review_run = _resolve_run_dir(Path(gap_review_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    gap_summary_path = gap_review_run / "phase1_comparator_suite_gap_review_summary.json"
    gap_blockers_path = gap_review_run / "claim_readiness_blockers.json"
    if not gap_summary_path.exists():
        raise Phase1GovernanceReadinessError(f"Gap review summary not found: {gap_summary_path}")
    if not gap_blockers_path.exists():
        raise Phase1GovernanceReadinessError(f"Gap review blockers not found: {gap_blockers_path}")
    gap_summary = _read_json(gap_summary_path)
    gap_blockers = _read_json(gap_blockers_path)
    _validate_gap_review_boundary(gap_summary, gap_blockers)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    controls = evaluate_control_suite(
        control_config_path=repo_root / config_paths["controls"],
        nuisance_config_path=repo_root / config_paths["nuisance"],
        gate2_config_path=repo_root / config_paths["gate2"],
    )
    calibration = evaluate_calibration_package(
        metrics_config_path=repo_root / config_paths["metrics"],
        inference_config_path=repo_root / config_paths["inference"],
        gate1_config_path=repo_root / config_paths["gate1"],
    )
    influence = evaluate_influence_package(
        gate1_config_path=repo_root / config_paths["gate1"],
        gate2_config_path=repo_root / config_paths["gate2"],
    )
    reporting = _evaluate_reporting_readiness()
    claim_state = _build_claim_state(
        gap_summary=gap_summary,
        gap_blockers=gap_blockers,
        controls=controls,
        calibration=calibration,
        influence=influence,
        reporting=reporting,
    )
    summary = {
        "status": "phase1_governance_readiness_blocked",
        "output_dir": str(output_dir),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "completed_non_claim_smoke_reviews": gap_summary.get("completed_non_claim_smoke_reviews", []),
        "blockers": claim_state["blockers"],
        "governance_surfaces": {
            "controls_claim_evaluable": controls["claim_evaluable"],
            "calibration_claim_evaluable": calibration["claim_evaluable"],
            "influence_claim_evaluable": influence["claim_evaluable"],
            "reporting_claim_evaluable": reporting["claim_evaluable"],
        },
        "scientific_limit": (
            "Governance readiness only. This run does not train models, execute controls, "
            "estimate calibration/influence, or support Phase 1 headline claims."
        ),
        "next_step": (
            "promote_controls_calibration_influence_reporting_from_readiness_surfaces_to_"
            "final_claim_evaluable_implementations_under_prereg_revision_policy"
        ),
    }
    inputs = {
        "status": "phase1_governance_readiness_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "gap_review_run": str(gap_review_run),
        "gap_review_summary": str(gap_summary_path),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_governance_readiness_inputs.json"
    summary_path = output_dir / "phase1_governance_readiness_summary.json"
    report_path = output_dir / "phase1_governance_readiness_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_control_suite_status.json", controls)
    _write_json(output_dir / "phase1_calibration_package_status.json", calibration)
    _write_json(output_dir / "phase1_influence_status.json", influence)
    _write_json(output_dir / "phase1_reporting_readiness.json", reporting)
    _write_json(output_dir / "phase1_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, claim_state, controls, calibration, influence, reporting),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1GovernanceReadinessResult(
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


def _evaluate_reporting_readiness() -> dict[str, Any]:
    missing = list(REQUIRED_REPORTING_ARTIFACTS)
    return {
        "status": "phase1_reporting_not_claim_evaluable",
        "claim_evaluable": False,
        "claim_blocker": True,
        "blockers": ["final_phase1_reporting_package_missing"],
        "required_reporting_artifacts": REQUIRED_REPORTING_ARTIFACTS,
        "missing_reporting_artifacts": missing,
        "scientific_limit": (
            "This readiness artifact does not write a final Phase 1 report or claim table. "
            "It records that the final reporting package is still absent."
        ),
    }


def _validate_gap_review_boundary(gap_summary: dict[str, Any], gap_blockers: dict[str, Any]) -> None:
    if gap_summary.get("status") != "phase1_comparator_suite_gap_review_complete":
        raise Phase1GovernanceReadinessError("Governance readiness requires a completed Phase 1 gap review")
    if gap_summary.get("claim_ready") is not False:
        raise Phase1GovernanceReadinessError("Gap review must have claim_ready=false")
    if gap_summary.get("headline_phase1_claim_open") is not False:
        raise Phase1GovernanceReadinessError("Gap review must keep headline_phase1_claim_open=false")
    blocker_claim_state = gap_blockers.get("claim_state", {})
    if blocker_claim_state.get("full_phase1_claim_bearing_run_allowed") is not False:
        raise Phase1GovernanceReadinessError("Gap review blockers must keep full claim-bearing runs blocked")
    completed = set(gap_summary.get("completed_non_claim_smoke_reviews", []))
    missing = [item for item in EXPECTED_NON_CLAIM_SMOKE_REVIEWS if item not in completed]
    if missing:
        raise Phase1GovernanceReadinessError(
            "Governance readiness requires post-A4 non-claim smoke reviews; missing: " + ", ".join(missing)
        )


def _build_claim_state(
    *,
    gap_summary: dict[str, Any],
    gap_blockers: dict[str, Any],
    controls: dict[str, Any],
    calibration: dict[str, Any],
    influence: dict[str, Any],
    reporting: dict[str, Any],
) -> dict[str, Any]:
    blockers = _unique(
        list(gap_summary.get("blockers", []))
        + list(gap_blockers.get("blockers", []))
        + _prefixed("controls", controls["blockers"])
        + _prefixed("calibration", calibration["blockers"])
        + _prefixed("influence", influence["blockers"])
        + _prefixed("reporting", reporting["blockers"])
        + ["headline_claim_blocked_until_final_governance_package_passes"]
    )
    return {
        "status": "phase1_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "completed_non_claim_smoke_reviews": gap_summary.get("completed_non_claim_smoke_reviews", []),
        "blockers": blockers,
        "reason": (
            "A2/A2b/A2c/A2d/A3/A4 smoke reviews can document implementation mechanics only. "
            "Headline Phase 1 claims remain closed until final comparator readiness, executable "
            "controls, full calibration, full influence, and reporting all pass."
        ),
        "claim_state_table": [
            {
                "state": "blocked",
                "condition": "current repository state",
                "claim_ready": False,
                "allowed_interpretation": "engineering readiness and non-claim smoke provenance only",
            },
            {
                "state": "eligible_for_review",
                "condition": (
                    "final comparator suite, negative controls, calibration, influence, and reporting "
                    "artifacts are all present and pass locked thresholds"
                ),
                "claim_ready": "not_reached",
                "allowed_interpretation": "may be reviewed against preregistered claim rules",
            },
        ],
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
    }


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


def _render_report(
    summary: dict[str, Any],
    claim_state: dict[str, Any],
    controls: dict[str, Any],
    calibration: dict[str, Any],
    influence: dict[str, Any],
    reporting: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Governance Readiness",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Full claim-bearing run allowed: `{summary['full_phase1_claim_bearing_run_allowed']}`",
        "",
        "## Completed Non-Claim Smoke Reviews",
        "",
    ]
    for item in summary["completed_non_claim_smoke_reviews"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Blocking Conditions", ""])
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(
        [
            "",
            "## Governance Surfaces",
            "",
            f"- Controls claim-evaluable: `{controls['claim_evaluable']}`",
            f"- Calibration claim-evaluable: `{calibration['claim_evaluable']}`",
            f"- Influence claim-evaluable: `{influence['claim_evaluable']}`",
            f"- Reporting claim-evaluable: `{reporting['claim_evaluable']}`",
            "",
            "## Scientific Integrity",
            "",
            "- This readiness package does not train a model.",
            "- It does not execute negative controls, calibration, influence, or final reporting.",
            "- It does not convert smoke metrics into efficacy evidence.",
            "- Headline claims remain closed until the final governance package passes preregistered thresholds.",
            "",
            "## Not OK To Claim",
            "",
        ]
    )
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


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
