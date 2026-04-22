"""Phase 1 final remediation plan after fail-closed closeout.

This runner consumes a reviewed final claim-state closeout and writes a
claim-closed remediation plan. It does not recompute model outputs, controls,
calibration, influence, or reporting. It also does not relax thresholds or
remove failed results. Its purpose is to make the next engineering work
auditable under the revision policy.
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


class Phase1FinalRemediationPlanError(RuntimeError):
    """Raised when final remediation planning cannot be assembled."""


@dataclass(frozen=True)
class Phase1FinalRemediationPlanResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "remediation": "configs/phase1/final_remediation_plan.json",
}


def run_phase1_final_remediation_plan(
    *,
    prereg_bundle: str | Path,
    final_claim_state_closeout_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalRemediationPlanResult:
    """Write a claim-closed remediation plan from a fail-closed closeout."""

    prereg_bundle = Path(prereg_bundle)
    final_claim_state_closeout_run = _resolve_run_dir(Path(final_claim_state_closeout_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    remediation_config = load_config(repo_root / config_paths["remediation"])
    closeout = _read_closeout_run(final_claim_state_closeout_run)
    input_validation = _validate_inputs(closeout=closeout, remediation_config=remediation_config)
    blocker_review = _build_blocker_review(closeout=closeout, remediation_config=remediation_config)
    workplan = _build_remediation_workplan(blocker_review=blocker_review, remediation_config=remediation_config)
    guardrails = _build_guardrails(remediation_config=remediation_config, closeout=closeout)
    revision_checklist = _build_revision_checklist(blocker_review=blocker_review)
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        closeout=closeout,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    inputs = {
        "status": "phase1_final_remediation_plan_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_claim_state_closeout_run": str(final_claim_state_closeout_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        closeout=closeout,
        input_validation=input_validation,
        blocker_review=blocker_review,
        workplan=workplan,
    )

    inputs_path = output_dir / "phase1_final_remediation_plan_inputs.json"
    summary_path = output_dir / "phase1_final_remediation_plan_summary.json"
    report_path = output_dir / "phase1_final_remediation_plan_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_remediation_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_remediation_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_remediation_blocker_review.json", blocker_review)
    _write_json(output_dir / "phase1_final_remediation_workplan.json", workplan)
    _write_json(output_dir / "phase1_final_remediation_guardrails.json", guardrails)
    _write_json(output_dir / "phase1_final_remediation_revision_checklist.json", revision_checklist)
    _write_json(output_dir / "phase1_final_remediation_claim_state.json", _build_claim_state(closeout, blocker_review))
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, blocker_review, workplan, guardrails), encoding="utf-8")
    (output_dir / "phase1_final_remediation_decision_memo.md").write_text(
        _render_decision_memo(summary, blocker_review, revision_checklist),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalRemediationPlanResult(
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


def _read_closeout_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_claim_state_closeout_summary.json",
        "input_validation": "phase1_final_claim_state_closeout_input_validation.json",
        "blocker_table": "phase1_final_blocker_table.json",
        "disposition": "phase1_final_claim_disposition.json",
        "manifest": "phase1_final_claim_state_closeout_manifest.json",
        "source_links": "phase1_final_claim_state_closeout_source_links.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalRemediationPlanError(f"Final claim-state closeout file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(*, closeout: dict[str, Any], remediation_config: dict[str, Any]) -> dict[str, Any]:
    summary = closeout["summary"]
    disposition = closeout["disposition"]
    required = dict(remediation_config.get("required_closeout_boundary", {}))
    observed = {
        "final_claim_blocked": summary.get("final_claim_blocked"),
        "claims_opened": summary.get("claims_opened"),
        "claim_ready": summary.get("claim_ready"),
        "headline_phase1_claim_open": summary.get("headline_phase1_claim_open"),
        "full_phase1_claim_bearing_run_allowed": summary.get("full_phase1_claim_bearing_run_allowed"),
        "revision_required_for_remediation": summary.get("revision_required_for_remediation"),
    }
    blockers = [
        f"closeout_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    if disposition.get("claims_opened") is not False:
        blockers.append("closeout_disposition_claims_opened")
    if not summary.get("claim_blockers"):
        blockers.append("closeout_has_no_claim_blockers_to_remediate")
    return {
        "status": "phase1_final_remediation_inputs_ready"
        if not blockers
        else "phase1_final_remediation_inputs_blocked",
        "final_claim_state_closeout_run": str(closeout["run_dir"]),
        "observed": observed,
        "required": required,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation confirms only the fail-closed closeout boundary; it is not efficacy evidence.",
    }


def _build_blocker_review(*, closeout: dict[str, Any], remediation_config: dict[str, Any]) -> dict[str, Any]:
    surface_order = list(remediation_config.get("surface_order", []))
    rows_by_surface = {row.get("surface"): row for row in closeout["blocker_table"].get("rows", [])}
    rows = []
    for surface in surface_order:
        source = dict(rows_by_surface.get(surface, {}))
        blockers = list(source.get("blockers", []))
        rows.append(
            {
                "surface": surface,
                "closeout_status": source.get("status"),
                "claim_evaluable": source.get("claim_evaluable"),
                "blocking": source.get("blocking") is True or bool(blockers),
                "observed_blockers": blockers,
                "remediation_priority": _priority_for_surface(surface),
                "allowed_remediation_classes": list(
                    remediation_config.get("allowed_remediation_classes", {}).get(surface, [])
                ),
                "not_allowed": list(remediation_config.get("not_allowed_remediation_classes", [])),
            }
        )
    unclassified = [
        blocker
        for blocker in closeout["summary"].get("claim_blockers", [])
        if ":" not in str(blocker) and blocker not in closeout["blocker_table"].get("global_blockers", [])
    ]
    return {
        "status": "phase1_final_remediation_blocker_review_recorded",
        "closeout_status": closeout["summary"].get("status"),
        "rows": rows,
        "blocking_surfaces": [row["surface"] for row in rows if row["blocking"]],
        "global_blockers": list(closeout["blocker_table"].get("global_blockers", [])),
        "unclassified_blockers": unclassified,
        "scientific_limit": "Blocker review classifies observed governance blockers; it does not judge efficacy.",
    }


def _build_remediation_workplan(
    *,
    blocker_review: dict[str, Any],
    remediation_config: dict[str, Any],
) -> dict[str, Any]:
    work_items = []
    for row in blocker_review.get("rows", []):
        if not row.get("blocking"):
            continue
        work_items.append(
            {
                "surface": row["surface"],
                "priority": row["remediation_priority"],
                "objective": _objective_for_surface(row["surface"]),
                "observed_blockers": row["observed_blockers"],
                "allowed_actions": row["allowed_remediation_classes"],
                "required_before_rerun": [
                    "write_revision_decision_or_preregistered_remediation_scope",
                    "commit_and_push_code_config_changes",
                    "rerun_unit_tests",
                    "rerun_affected_artifact_family_from_reviewed_sources",
                    "rerun_final_governance_reconciliation_and_claim_state_closeout",
                ],
                "must_not_do": remediation_config.get("not_allowed_remediation_classes", []),
                "claim_state_after_item": "claim_closed_until_governance_passes_and_manual_review_occurs",
            }
        )
    return {
        "status": "phase1_final_remediation_workplan_recorded",
        "work_items": work_items,
        "next_step": _next_step(work_items),
        "claims_opened": False,
        "scientific_limit": "Workplan is a remediation scaffold only; it does not authorize claims or reruns by itself.",
    }


def _build_guardrails(*, remediation_config: dict[str, Any], closeout: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_remediation_guardrails_recorded",
        "claims_opened": False,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "scientific_integrity_rule": remediation_config.get("scientific_integrity_rule"),
        "not_allowed_remediation_classes": remediation_config.get("not_allowed_remediation_classes", []),
        "not_ok_to_claim": remediation_config.get("not_ok_to_claim", []),
        "source_closeout_claim_blockers": closeout["summary"].get("claim_blockers", []),
        "scientific_limit": "Guardrails preserve the fail-closed boundary during remediation planning.",
    }


def _build_revision_checklist(*, blocker_review: dict[str, Any]) -> dict[str, Any]:
    checklist = [
        {
            "item": "preserve_failed_artifacts",
            "required": True,
            "status": "pending_manual_review",
            "description": "Keep failed controls/calibration/influence artifacts linked; do not overwrite them as pass.",
        },
        {
            "item": "no_posthoc_threshold_relaxation",
            "required": True,
            "status": "pending_manual_review",
            "description": "Any threshold or endpoint change after observed failure requires revision policy handling.",
        },
        {
            "item": "define_affected_surface_scope",
            "required": True,
            "status": "pending_manual_review",
            "description": "Name the exact governance surface to remediate before rerunning artifacts.",
        },
        {
            "item": "rerun_dependency_chain",
            "required": True,
            "status": "pending_manual_review",
            "description": "Rerun all dependent manifests/reconciliations after any substantive code or config change.",
        },
    ]
    return {
        "status": "phase1_final_remediation_revision_checklist_recorded",
        "blocking_surfaces": blocker_review.get("blocking_surfaces", []),
        "checklist": checklist,
        "scientific_limit": "Checklist records governance requirements only; it is not evidence that remediation succeeded.",
    }


def _build_claim_state(closeout: dict[str, Any], blocker_review: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_remediation_claim_state_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": True,
        "blocking_surfaces": blocker_review.get("blocking_surfaces", []),
        "source_closeout_run": str(closeout["run_dir"]),
        "source_closeout_status": closeout["summary"].get("status"),
        "scientific_limit": "Remediation planning keeps claims closed.",
    }


def _build_summary(
    *,
    output_dir: Path,
    closeout: dict[str, Any],
    input_validation: dict[str, Any],
    blocker_review: dict[str, Any],
    workplan: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_remediation_plan_recorded"
        if input_validation.get("status") == "phase1_final_remediation_inputs_ready"
        else "phase1_final_remediation_plan_blocked",
        "output_dir": str(output_dir),
        "final_claim_state_closeout_run": str(closeout["run_dir"]),
        "source_closeout_status": closeout["summary"].get("status"),
        "input_validation_status": input_validation.get("status"),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": True,
        "revision_required_for_remediation": True,
        "blocking_surfaces": blocker_review.get("blocking_surfaces", []),
        "claim_blockers": closeout["summary"].get("claim_blockers", []),
        "next_step": workplan.get("next_step"),
        "scientific_limit": "Remediation plan records next engineering work only; it does not prove Phase 1 efficacy.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    closeout: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    closeout_run = closeout["run_dir"]
    return {
        "status": "phase1_final_remediation_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_claim_state_closeout_run": str(closeout_run),
        "final_claim_state_closeout_summary": str(closeout_run / "phase1_final_claim_state_closeout_summary.json"),
        "final_claim_state_closeout_summary_sha256": _sha256(
            closeout_run / "phase1_final_claim_state_closeout_summary.json"
        ),
        "final_blocker_table": str(closeout_run / "phase1_final_blocker_table.json"),
        "final_blocker_table_sha256": _sha256(closeout_run / "phase1_final_blocker_table.json"),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not model evidence.",
    }


def _render_report(
    summary: dict[str, Any],
    blocker_review: dict[str, Any],
    workplan: dict[str, Any],
    guardrails: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Remediation Plan",
        "",
        f"Status: `{summary['status']}`",
        f"Source closeout status: `{summary['source_closeout_status']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Final claim blocked: `{summary['final_claim_blocked']}`",
        f"Revision required for remediation: `{summary['revision_required_for_remediation']}`",
        "",
        "## Blocking Surfaces",
        "",
    ]
    lines.extend(f"- `{surface}`" for surface in summary.get("blocking_surfaces", []))
    lines.extend(["", "## Work Items", ""])
    for item in workplan.get("work_items", []):
        lines.append(f"- `{item['surface']}`: {item['objective']}")
    lines.extend(["", "## Observed Blockers", ""])
    for blocker in summary.get("claim_blockers", []):
        lines.append(f"- `{blocker}`")
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
    lines.extend(f"- `{item}`" for item in guardrails.get("not_allowed_remediation_classes", []))
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
    blocker_review: dict[str, Any],
    revision_checklist: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Remediation Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            "",
            "## Decision",
            "",
            "Proceed only with claim-closed remediation planning. Do not change locked thresholds, omit failed governance results, drop subjects post hoc, or open headline Phase 1 claims from this closeout.",
            "",
            "## Blocking Surfaces",
            "",
            *[f"- `{surface}`" for surface in blocker_review.get("blocking_surfaces", [])],
            "",
            "## Required Checklist",
            "",
            *[f"- `{item['item']}`: {item['status']}" for item in revision_checklist.get("checklist", [])],
            "",
        ]
    )


def _objective_for_surface(surface: str) -> str:
    objectives = {
        "controls": "Review failed final controls and dedicated controls against locked control specifications without editing thresholds.",
        "calibration": "Review final calibration threshold failure from observed logits without recalibrating existing predictions.",
        "influence": "Review subject-level influence veto and leave-one-subject-out diagnostics without excluding subjects post hoc.",
    }
    return objectives.get(surface, "Review observed governance blocker under revision policy.")


def _priority_for_surface(surface: str) -> int:
    priorities = {"controls": 1, "calibration": 2, "influence": 3}
    return priorities.get(surface, 99)


def _next_step(work_items: list[dict[str, Any]]) -> str:
    if not work_items:
        return "manual_review_no_blocking_surface_detected"
    first = sorted(work_items, key=lambda item: int(item.get("priority", 99)))[0]
    return f"start_revision_scoped_{first['surface']}_remediation_audit"


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
