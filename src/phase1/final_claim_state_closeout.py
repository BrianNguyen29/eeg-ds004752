"""Final Phase 1 claim-state closeout.

This runner consumes a reviewed final governance reconciliation run and writes
a fail-closed claim-state disposition. It does not recompute model outputs,
controls, calibration, influence, or reporting. Its job is to preserve the
observed governance state and make the claim boundary explicit.
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


class Phase1FinalClaimStateCloseoutError(RuntimeError):
    """Raised when final claim-state closeout cannot be assembled."""


@dataclass(frozen=True)
class Phase1FinalClaimStateCloseoutResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "closeout": "configs/phase1/final_claim_state_closeout.json",
}


def run_phase1_final_claim_state_closeout(
    *,
    prereg_bundle: str | Path,
    final_governance_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalClaimStateCloseoutResult:
    """Write a final fail-closed claim-state disposition."""

    prereg_bundle = Path(prereg_bundle)
    final_governance_reconciliation_run = _resolve_run_dir(Path(final_governance_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    closeout_config = load_config(repo_root / config_paths["closeout"])
    governance = _read_governance_reconciliation_run(final_governance_reconciliation_run)
    input_validation = _validate_inputs(governance=governance, closeout_config=closeout_config)
    blocker_table = _build_blocker_table(governance=governance, input_validation=input_validation)
    disposition = _build_claim_disposition(
        governance=governance,
        closeout_config=closeout_config,
        blocker_table=blocker_table,
        input_validation=input_validation,
    )
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
        "status": "phase1_final_claim_state_closeout_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_governance_reconciliation_run": str(final_governance_reconciliation_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    manifest = _build_manifest(
        disposition=disposition,
        blocker_table=blocker_table,
        input_validation=input_validation,
    )
    summary = _build_summary(
        output_dir=output_dir,
        governance=governance,
        disposition=disposition,
        blocker_table=blocker_table,
        input_validation=input_validation,
    )

    inputs_path = output_dir / "phase1_final_claim_state_closeout_inputs.json"
    summary_path = output_dir / "phase1_final_claim_state_closeout_summary.json"
    report_path = output_dir / "phase1_final_claim_state_closeout_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_claim_state_closeout_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_claim_state_closeout_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_blocker_table.json", blocker_table)
    _write_json(output_dir / "phase1_final_claim_disposition.json", disposition)
    _write_json(output_dir / "phase1_final_claim_state_closeout_manifest.json", manifest)
    _write_json(summary_path, summary)
    (output_dir / "phase1_final_revision_decision_memo.md").write_text(
        _render_revision_memo(summary, disposition, blocker_table),
        encoding="utf-8",
    )
    report_path.write_text(_render_report(summary, disposition, blocker_table), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalClaimStateCloseoutResult(
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


def _read_governance_reconciliation_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_governance_reconciliation_summary.json",
        "input_validation": "phase1_final_governance_reconciliation_input_validation.json",
        "controls": "phase1_final_controls_reconciliation_status.json",
        "calibration": "phase1_final_calibration_reconciliation_status.json",
        "influence": "phase1_final_influence_reconciliation_status.json",
        "reporting": "phase1_final_reporting_reconciliation_status.json",
        "claim_state": "phase1_final_governance_claim_state.json",
        "source_links": "phase1_final_governance_reconciliation_source_links.json",
    }
    payload: dict[str, Any] = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalClaimStateCloseoutError(f"Final governance reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(*, governance: dict[str, Any], closeout_config: dict[str, Any]) -> dict[str, Any]:
    summary = governance["summary"]
    claim_state = governance["claim_state"]
    required = dict(closeout_config.get("required_governance_boundary", {}))
    observed = {
        "comparator_outputs_complete": summary.get("comparator_outputs_complete"),
        "runtime_logs_audited_for_all_required_comparators": summary.get(
            "runtime_logs_audited_for_all_required_comparators"
        ),
        "claim_ready": summary.get("claim_ready"),
        "headline_phase1_claim_open": summary.get("headline_phase1_claim_open"),
        "full_phase1_claim_bearing_run_allowed": summary.get("full_phase1_claim_bearing_run_allowed"),
    }
    blockers = [
        f"governance_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    if claim_state.get("claim_ready") is not False:
        blockers.append("governance_claim_state_not_closed")
    if claim_state.get("headline_phase1_claim_open") is not False:
        blockers.append("governance_headline_claim_open")
    if claim_state.get("full_phase1_claim_bearing_run_allowed") is not False:
        blockers.append("governance_full_phase1_claim_bearing_run_allowed")
    if governance["reporting"].get("claims_opened") is True:
        blockers.append("governance_reporting_attempted_to_open_claims")
    return {
        "status": "phase1_final_claim_state_closeout_inputs_ready"
        if not blockers
        else "phase1_final_claim_state_closeout_inputs_blocked",
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "observed": observed,
        "required": required,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks closeout prerequisites only; it is not efficacy evidence.",
    }


def _build_blocker_table(*, governance: dict[str, Any], input_validation: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for surface_name, payload in [
        ("controls", governance["controls"]),
        ("calibration", governance["calibration"]),
        ("influence", governance["influence"]),
        ("reporting", governance["reporting"]),
    ]:
        blockers = list(payload.get("blockers", []))
        rows.append(
            {
                "surface": surface_name,
                "claim_evaluable": payload.get("claim_evaluable"),
                "status": payload.get("status"),
                "blockers": blockers,
                "blocking": payload.get("claim_evaluable") is not True or bool(blockers),
            }
        )
    global_blockers = [
        blocker
        for blocker in governance["summary"].get("claim_blockers", [])
        if ":" not in str(blocker)
    ]
    for blocker in input_validation.get("blockers", []):
        global_blockers.append(f"input_validation:{blocker}")
    return {
        "status": "phase1_final_blocker_table_recorded",
        "rows": rows,
        "global_blockers": _unique(global_blockers),
        "blocking_surfaces": [row["surface"] for row in rows if row["blocking"]],
        "scientific_limit": "Blocker table records governance state only; it does not rank scientific importance.",
    }


def _build_claim_disposition(
    *,
    governance: dict[str, Any],
    closeout_config: dict[str, Any],
    blocker_table: dict[str, Any],
    input_validation: dict[str, Any],
) -> dict[str, Any]:
    blocking_surfaces = list(blocker_table.get("blocking_surfaces", []))
    blockers = _unique(
        list(input_validation.get("blockers", []))
        + list(governance["summary"].get("claim_blockers", []))
    )
    final_claim_blocked = bool(blockers) or bool(blocking_surfaces)
    return {
        "status": "phase1_final_claim_blocked_fail_closed"
        if final_claim_blocked
        else "phase1_final_claim_ready_but_closed_for_manual_review",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": final_claim_blocked,
        "blocking_surfaces": blocking_surfaces,
        "comparator_outputs_complete": governance["summary"].get("comparator_outputs_complete"),
        "runtime_logs_audited_for_all_required_comparators": governance["summary"].get(
            "runtime_logs_audited_for_all_required_comparators"
        ),
        "governance_surfaces": governance["summary"].get("governance_surfaces", {}),
        "blockers": blockers,
        "not_ok_to_claim": list(closeout_config.get("not_ok_to_claim", [])),
        "revision_required_for_remediation": closeout_config.get("claim_disposition_policy", {}).get(
            "revision_required_for_remediation", True
        ),
        "allowed_interpretation": (
            "Final comparator and reporting artifacts can be described as completed if their source artifacts say so; "
            "Phase 1 efficacy and privileged-transfer claims must remain closed because governance blockers remain."
        ),
        "not_allowed_interpretation": (
            "Do not use comparator metrics, reporting completeness, or partial governance progress as evidence for "
            "decoder efficacy, privileged-transfer efficacy, A4 superiority, or full Phase 1 performance."
        ),
        "scientific_limit": "This disposition is a governance closeout, not a model-efficacy result.",
    }


def _build_manifest(
    *,
    disposition: dict[str, Any],
    blocker_table: dict[str, Any],
    input_validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_claim_state_closeout_manifest_recorded",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": disposition.get("final_claim_blocked"),
        "blocking_surfaces": blocker_table.get("blocking_surfaces", []),
        "input_validation_status": input_validation.get("status"),
        "blockers": disposition.get("blockers", []),
        "scientific_limit": "Manifest records closeout only and does not authorize claims.",
    }


def _build_summary(
    *,
    output_dir: Path,
    governance: dict[str, Any],
    disposition: dict[str, Any],
    blocker_table: dict[str, Any],
    input_validation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": disposition["status"],
        "output_dir": str(output_dir),
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "input_validation_status": input_validation.get("status"),
        "comparator_outputs_complete": disposition.get("comparator_outputs_complete"),
        "runtime_logs_audited_for_all_required_comparators": disposition.get(
            "runtime_logs_audited_for_all_required_comparators"
        ),
        "governance_surfaces": disposition.get("governance_surfaces", {}),
        "blocking_surfaces": blocker_table.get("blocking_surfaces", []),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "final_claim_blocked": disposition.get("final_claim_blocked"),
        "claim_blockers": disposition.get("blockers", []),
        "revision_required_for_remediation": disposition.get("revision_required_for_remediation"),
        "scientific_limit": "Final closeout records the claim boundary; it does not prove Phase 1 efficacy.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    governance: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    governance_run = governance["run_dir"]
    return {
        "status": "phase1_final_claim_state_closeout_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_governance_reconciliation_run": str(governance_run),
        "final_governance_reconciliation_summary": str(governance_run / "phase1_final_governance_reconciliation_summary.json"),
        "final_governance_reconciliation_summary_sha256": _sha256(
            governance_run / "phase1_final_governance_reconciliation_summary.json"
        ),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not model evidence.",
    }


def _render_revision_memo(
    summary: dict[str, Any],
    disposition: dict[str, Any],
    blocker_table: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Revision Decision Memo",
            "",
            f"Disposition: `{summary['status']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            f"Revision required for remediation: `{summary['revision_required_for_remediation']}`",
            "",
            "## Blocking Surfaces",
            "",
            *[f"- `{surface}`" for surface in blocker_table.get("blocking_surfaces", [])],
            "",
            "## Decision",
            "",
            "Do not open headline Phase 1 claims from this run. Any remediation must follow the locked preregistration revision policy and must not be implemented by changing thresholds or omitting failed governance results after seeing outcomes.",
            "",
            "## Not OK To Claim",
            "",
            *[f"- {claim}" for claim in disposition.get("not_ok_to_claim", [])],
            "",
        ]
    )


def _render_report(
    summary: dict[str, Any],
    disposition: dict[str, Any],
    blocker_table: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Claim-State Closeout",
        "",
        f"Status: `{summary['status']}`",
        f"Comparator outputs complete: `{summary['comparator_outputs_complete']}`",
        f"Runtime logs audited: `{summary['runtime_logs_audited_for_all_required_comparators']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Final claim blocked: `{summary['final_claim_blocked']}`",
        "",
        "## Governance Surfaces",
        "",
    ]
    for key, value in summary.get("governance_surfaces", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Blockers",
            "",
            *[f"- `{blocker}`" for blocker in summary["claim_blockers"]],
            "",
            "## Interpretation",
            "",
            disposition["allowed_interpretation"],
            "",
            disposition["not_allowed_interpretation"],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )
    return "\n".join(lines)


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
