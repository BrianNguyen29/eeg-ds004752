"""Phase 1 comparator-suite gap review.

This module does not train a model. It records the implementation and
scientific-governance gap between completed non-claim smoke checks and any
future claim-bearing Phase 1 run.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .smoke import (
    Phase1SmokeError,
    _read_json,
    _readiness_path,
    _validate_readiness,
    _write_json,
    _write_latest_pointer,
)


class Phase1GapReviewError(RuntimeError):
    """Raised when Phase 1 gap review cannot proceed."""


@dataclass(frozen=True)
class Phase1GapReviewResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


EXPECTED_REVIEW_NOTES = {
    "A2_A2b": {
        "filename": "phase1_a2_a2b_model_smoke_review_note.json",
        "status": "phase1_a2_a2b_model_smoke_review_pass_non_claim",
    },
    "A2c_CORAL": {
        "filename": "phase1_a2c_coral_smoke_review_note.json",
        "status": "phase1_a2c_coral_smoke_review_pass_non_claim",
    },
    "A2d_riemannian": {
        "filename": "phase1_a2d_riemannian_smoke_review_note.json",
        "status": "phase1_a2d_riemannian_smoke_review_pass_non_claim",
    },
    "A3_distillation": {
        "filename": "phase1_a3_distillation_smoke_review_note.json",
        "status": "phase1_a3_distillation_smoke_review_pass_non_claim",
    },
    "A4_privileged": {
        "filename": "phase1_a4_privileged_smoke_review_note.json",
        "status": "phase1_a4_privileged_smoke_review_pass_non_claim",
    },
}


DEFAULT_CONFIG_PATHS = {
    "a3": "configs/models/distill_a3.yaml",
    "a4": "configs/models/privileged_a4.yaml",
    "controls": "configs/controls/control_suite_spec.yaml",
    "claim_mapping": "configs/eval/claim_mapping.yaml",
    "metrics": "configs/eval/metrics.yaml",
    "inference": "configs/eval/inference_defaults.yaml",
    "gate1": "configs/gate1/decision_simulation.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_gap_review(
    *,
    prereg_bundle: str | Path,
    readiness_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    reviewed_runs: dict[str, str | Path | None] | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1GapReviewResult:
    """Review remaining Phase 1 comparator/control gaps without launching training."""

    prereg_bundle = Path(prereg_bundle)
    readiness_run = Path(readiness_run)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    reviewed_runs = reviewed_runs or {}
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    readiness_path = _readiness_path(readiness_run)
    readiness = _read_json(readiness_path)
    try:
        _validate_readiness(readiness, bundle)
    except Phase1SmokeError as exc:
        raise Phase1GapReviewError(str(exc)) from exc

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    config_review = _review_configs(repo_root, config_paths)
    source_review = _review_source_surface(repo_root)
    smoke_review = _review_smoke_notes(reviewed_runs)
    backlog = _build_backlog(config_review, source_review, smoke_review)
    blockers = _build_blockers(config_review, source_review, smoke_review)
    claim_state = {
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "reason": (
            "A3/A4 smoke reviews may be complete, but final claim-bearing comparator implementations, "
            "full controls, calibration, influence and reporting package are not complete."
        ),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
    }
    inputs = {
        "status": "phase1_comparator_suite_gap_review_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "readiness_run": str(readiness_run),
        "readiness_path": str(readiness_path),
        "reviewed_runs": {key: str(value) if value is not None else None for key, value in reviewed_runs.items()},
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = {
        "status": "phase1_comparator_suite_gap_review_complete",
        "output_dir": str(output_dir),
        "blockers": blockers,
        "completed_non_claim_smoke_reviews": [
            item["comparator_id"] for item in smoke_review["items"] if item["review_passed"]
        ],
        "missing_or_not_final_comparators": config_review["missing_or_not_final_comparators"],
        "draft_governance_surfaces": config_review["draft_governance_surfaces"],
        "missing_source_modules": source_review["missing_source_modules"],
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "scientific_limit": "Gap review only; it does not train models or estimate comparator efficacy.",
        "next_step": "implement_full_control_calibration_influence_reporting_package_and_final_comparator_readiness_under_revision_policy",
    }

    inputs_path = output_dir / "phase1_comparator_suite_gap_review_inputs.json"
    summary_path = output_dir / "phase1_comparator_suite_gap_review_summary.json"
    report_path = output_dir / "phase1_comparator_suite_gap_review_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "comparator_suite_status.json", {
        "status": "phase1_comparator_suite_status_reviewed",
        "smoke_review": smoke_review,
        "config_review": config_review,
        "source_review": source_review,
    })
    _write_json(output_dir / "claim_readiness_blockers.json", {
        "status": "phase1_claim_readiness_blocked",
        "blockers": blockers,
        "claim_state": claim_state,
    })
    _write_json(output_dir / "implementation_backlog.json", backlog)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, smoke_review, config_review, source_review, backlog), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1GapReviewResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _review_smoke_notes(reviewed_runs: dict[str, str | Path | None]) -> dict[str, Any]:
    items = []
    for comparator_id, expected in EXPECTED_REVIEW_NOTES.items():
        run_value = reviewed_runs.get(comparator_id)
        note_path = Path(run_value) / expected["filename"] if run_value else None
        exists = bool(note_path and note_path.exists())
        status = None
        if exists and note_path is not None:
            status = _read_json(note_path).get("status")
        items.append(
            {
                "comparator_id": comparator_id,
                "review_note": str(note_path) if note_path else None,
                "expected_status": expected["status"],
                "observed_status": status,
                "review_passed": exists and status == expected["status"],
                "claim_scope": "non_claim_smoke_only",
            }
        )
    return {
        "status": "phase1_completed_smoke_reviews_checked",
        "items": items,
        "all_required_non_claim_smoke_reviews_passed": all(item["review_passed"] for item in items),
    }


def _review_configs(repo_root: Path, config_paths: dict[str, str | Path]) -> dict[str, Any]:
    configs = {}
    missing_or_not_final = []
    draft_surfaces = []
    for key, relative in config_paths.items():
        path = repo_root / Path(relative)
        data = load_config(path)
        configs[key] = {"path": str(path), "data": data}
        status = _config_status(data, key)
        if key in {"a3", "a4"} and ("placeholder" in status or data.get("final_comparator_ready") is False):
            missing_or_not_final.append(
                {
                    "comparator": "A3_distillation" if key == "a3" else "A4_privileged",
                    "config": str(path),
                    "status": status,
                    "reason": "Comparator config is placeholder or explicitly marked not final; smoke runners do not clear final comparator readiness.",
                }
            )
        if key in {"controls", "claim_mapping", "metrics", "inference"} and "draft" in status:
            draft_surfaces.append({"surface": key, "config": str(path), "status": status})
    return {
        "status": "phase1_config_gap_reviewed",
        "missing_or_not_final_comparators": missing_or_not_final,
        "draft_governance_surfaces": draft_surfaces,
        "gate_threshold_sources": {
            "gate1_config": configs["gate1"]["path"],
            "gate2_config": configs["gate2"]["path"],
        },
    }


def _config_status(data: dict[str, Any], key: str) -> str:
    status_keys = {
        "controls": "control_suite_status",
        "claim_mapping": "claim_mapping_status",
        "metrics": "metrics_status",
        "inference": "inference_status",
    }
    return str(data.get("status") or data.get(status_keys.get(key, f"{key}_status")) or "")


def _review_source_surface(repo_root: Path) -> dict[str, Any]:
    expected = {
        "A3_distillation": [repo_root / "src" / "phase1" / "a3_smoke.py", repo_root / "src" / "phase1" / "a3.py"],
        "A4_privileged": [repo_root / "src" / "phase1" / "a4_smoke.py", repo_root / "src" / "phase1" / "a4.py"],
        "full_controls": [repo_root / "src" / "phase1" / "controls.py"],
        "full_calibration": [repo_root / "src" / "phase1" / "calibration.py"],
        "full_influence": [repo_root / "src" / "phase1" / "influence.py"],
    }
    missing = []
    for surface, alternatives in expected.items():
        if not any(path.exists() for path in alternatives):
            missing.append({"surface": surface, "expected_any_of": [str(path) for path in alternatives]})
    return {
        "status": "phase1_source_surface_gap_reviewed",
        "missing_source_modules": missing,
    }


def _build_blockers(
    config_review: dict[str, Any],
    source_review: dict[str, Any],
    smoke_review: dict[str, Any],
) -> list[str]:
    blockers = []
    if not smoke_review["all_required_non_claim_smoke_reviews_passed"]:
        blockers.append("required_non_claim_smoke_reviews_not_all_passed")
    if config_review["missing_or_not_final_comparators"]:
        blockers.append("a3_a4_final_comparator_configs_or_runners_missing")
    if config_review["draft_governance_surfaces"]:
        blockers.append("phase1_control_claim_metric_inference_surfaces_still_draft")
    if source_review["missing_source_modules"]:
        blockers.append("phase1_final_runner_control_calibration_influence_modules_missing")
    blockers.append("headline_claim_blocked_until_full_comparator_suite_controls_calibration_influence_reporting_pass")
    return blockers


def _build_backlog(
    config_review: dict[str, Any],
    source_review: dict[str, Any],
    smoke_review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_implementation_backlog_recorded",
        "completed_non_claim_items": [
            item["comparator_id"] for item in smoke_review["items"] if item["review_passed"]
        ],
        "next_engineering_items": [
            "Keep A3/A4 smoke reviews non-claim; do not promote smoke proxy metrics to final comparator evidence.",
            "Define or refreeze final A3/A4 claim-bearing comparator specifications before any substantive claim run.",
            "Promote control suite from draft to executable Phase 1 controls.",
            "Run and reconcile the final calibration package from final logits; do not treat executable config as evidence.",
            "Implement full influence package and leave-one-subject-out claim-state checks.",
            "Implement reporting/claim-state package that refuses headline claims until all blockers clear.",
        ],
        "config_blockers": config_review["missing_or_not_final_comparators"] + config_review["draft_governance_surfaces"],
        "source_blockers": source_review["missing_source_modules"],
        "scientific_integrity_rule": "Do not use smoke metrics as efficacy evidence.",
    }


def _render_report(
    summary: dict[str, Any],
    smoke_review: dict[str, Any],
    config_review: dict[str, Any],
    source_review: dict[str, Any],
    backlog: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Comparator-Suite Gap Review",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        "",
        "## Completed Non-Claim Smoke Reviews",
        "",
    ]
    for item in smoke_review["items"]:
        lines.append(f"- {item['comparator_id']}: review_passed=`{item['review_passed']}` status=`{item['observed_status']}`")
    lines.extend(["", "## Blocking Gaps", ""])
    for blocker in summary["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Config Gaps", ""])
    for item in config_review["missing_or_not_final_comparators"]:
        lines.append(f"- {item['comparator']}: `{item['status']}`")
    for item in config_review["draft_governance_surfaces"]:
        lines.append(f"- {item['surface']}: `{item['status']}`")
    lines.extend(["", "## Source Gaps", ""])
    for item in source_review["missing_source_modules"]:
        lines.append(f"- {item['surface']}")
    lines.extend(["", "## Backlog", ""])
    for item in backlog["next_engineering_items"]:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Scientific Integrity",
            "",
            "- This review does not train models.",
            "- It does not estimate A3, A4, decoder, or privileged-transfer efficacy.",
            "- Completed A2/A2b/A2c/A2d/A3/A4 smoke metrics remain implementation diagnostics only.",
            "- Headline claims remain blocked until the full comparator suite, controls, calibration, influence and reporting package are implemented and run under prereg/revision policy.",
        ]
    )
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
