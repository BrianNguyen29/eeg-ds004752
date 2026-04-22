"""Final Phase 1 reporting package.

This runner consumes an existing final governance reconciliation run and writes
a claim-closed reporting package. It is intentionally conservative: it records
the observed comparator/governance state, preserves upstream blockers, and
never fabricates missing controls, calibration, influence, or efficacy results.
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


class Phase1FinalReportingError(RuntimeError):
    """Raised when final reporting cannot be assembled."""


@dataclass(frozen=True)
class Phase1FinalReportingResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "reporting": "configs/phase1/final_reporting.json",
    "governance": "configs/phase1/final_governance_reconciliation.json",
}


def run_phase1_final_reporting(
    *,
    prereg_bundle: str | Path,
    final_governance_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalReportingResult:
    """Write final reporting artifacts while keeping all claims closed."""

    prereg_bundle = Path(prereg_bundle)
    final_governance_reconciliation_run = _resolve_run_dir(Path(final_governance_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    reporting_config = load_config(repo_root / config_paths["reporting"])
    governance_config = load_config(repo_root / config_paths["governance"])
    governance = _read_governance_reconciliation_run(final_governance_reconciliation_run)
    input_validation = _validate_inputs(
        governance=governance,
        reporting_config=reporting_config,
        governance_config=governance_config,
    )
    reports = _build_reporting_artifacts(
        governance=governance,
        input_validation=input_validation,
        required_artifacts=list(reporting_config.get("required_reporting_artifacts", [])),
    )
    manifest = _build_manifest(
        reports=reports,
        input_validation=input_validation,
        reporting_config=reporting_config,
    )
    claim_state = _build_claim_state(manifest=manifest, governance=governance, input_validation=input_validation)
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
        "status": "phase1_final_reporting_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_governance_reconciliation_run": str(final_governance_reconciliation_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        governance=governance,
        manifest=manifest,
        input_validation=input_validation,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_reporting_inputs.json"
    summary_path = output_dir / "phase1_final_reporting_summary.json"
    report_path = output_dir / "phase1_final_reporting_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_reporting_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_reporting_input_validation.json", input_validation)
    _write_json(output_dir / "final_comparator_completeness_table.json", reports["final_comparator_completeness_table"])
    _write_json(output_dir / "negative_controls_report.json", reports["negative_controls_report"])
    _write_json(output_dir / "calibration_package_report.json", reports["calibration_package_report"])
    _write_json(output_dir / "influence_package_report.json", reports["influence_package_report"])
    _write_json(output_dir / "final_fold_logs.json", reports["final_fold_logs"])
    _write_json(output_dir / "claim_state_report.json", reports["claim_state_report"])
    _write_json(output_dir / "phase1_final_reporting_claim_table.json", reports["phase1_final_reporting_claim_table"])
    _write_json(output_dir / "final_reporting_manifest.json", manifest)
    _write_json(output_dir / "phase1_final_reporting_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    main_report = _render_main_report(summary, manifest, governance, claim_state)
    (output_dir / "main_phase1_report.md").write_text(main_report, encoding="utf-8")
    report_path.write_text(_render_report(summary, manifest, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalReportingResult(
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
            raise Phase1FinalReportingError(f"Final governance reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    governance: dict[str, Any],
    reporting_config: dict[str, Any],
    governance_config: dict[str, Any],
) -> dict[str, Any]:
    summary = governance["summary"]
    claim_state = governance["claim_state"]
    required = dict(reporting_config.get("required_governance_inputs", {}))
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
        blockers.append("source_governance_reporting_attempted_to_open_claims")
    required_reporting_artifacts = list(
        reporting_config.get(
            "required_reporting_artifacts",
            governance_config.get("required_reporting_artifacts", []),
        )
    )
    if not required_reporting_artifacts:
        blockers.append("required_reporting_artifact_contract_missing")
    return {
        "status": "phase1_final_reporting_inputs_ready" if not blockers else "phase1_final_reporting_inputs_blocked",
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "observed": observed,
        "required": required,
        "required_reporting_artifacts": required_reporting_artifacts,
        "upstream_governance_status": summary.get("status"),
        "upstream_claim_blockers": list(summary.get("claim_blockers", [])),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks reporting prerequisites only; it is not efficacy evidence.",
    }


def _build_reporting_artifacts(
    *,
    governance: dict[str, Any],
    input_validation: dict[str, Any],
    required_artifacts: list[str],
) -> dict[str, Any]:
    summary = governance["summary"]
    controls = governance["controls"]
    calibration = governance["calibration"]
    influence = governance["influence"]
    claim_state = governance["claim_state"]
    source_links = governance["source_links"]
    claim_blockers = list(summary.get("claim_blockers", []))

    claim_rows = [
        _claim_row("decoder_efficacy", "decoder efficacy", claim_blockers),
        _claim_row("a2d_efficacy", "A2d efficacy", claim_blockers),
        _claim_row("a3_distillation_efficacy", "A3 distillation efficacy", claim_blockers),
        _claim_row("a4_privileged_transfer_efficacy", "A4 privileged-transfer efficacy", claim_blockers),
        _claim_row("a4_superiority", "A4 superiority over A2/A2b/A2c/A2d/A3", claim_blockers),
        _claim_row("full_phase1_neural_comparator_performance", "full Phase 1 neural comparator performance", claim_blockers),
    ]
    return {
        "final_comparator_completeness_table": {
            "status": "phase1_final_reporting_comparator_completeness_recorded",
            "comparator_outputs_complete": summary.get("comparator_outputs_complete"),
            "runtime_logs_audited_for_all_required_comparators": summary.get(
                "runtime_logs_audited_for_all_required_comparators"
            ),
            "comparator_reconciliation_run": source_links.get("comparator_reconciliation_run"),
            "scientific_limit": "This table records comparator artifact completeness only; it is not model evidence.",
        },
        "negative_controls_report": {
            "status": "phase1_final_reporting_negative_controls_recorded",
            "controls_claim_evaluable": controls.get("claim_evaluable"),
            "control_status": controls.get("status"),
            "blockers": list(controls.get("blockers", [])),
            "final_control_manifest_path": controls.get("final_control_manifest_path"),
            "scientific_limit": "This report records control package status only; it does not fabricate missing controls.",
        },
        "calibration_package_report": {
            "status": "phase1_final_reporting_calibration_recorded",
            "calibration_claim_evaluable": calibration.get("claim_evaluable"),
            "calibration_status": calibration.get("status"),
            "blockers": list(calibration.get("blockers", [])),
            "final_calibration_manifest_path": calibration.get("final_calibration_manifest_path"),
            "scientific_limit": "This report records calibration package status only; it does not alter thresholds or logits.",
        },
        "influence_package_report": {
            "status": "phase1_final_reporting_influence_recorded",
            "influence_claim_evaluable": influence.get("claim_evaluable"),
            "influence_status": influence.get("status"),
            "blockers": list(influence.get("blockers", [])),
            "final_influence_manifest_path": influence.get("final_influence_manifest_path"),
            "scientific_limit": "This report records influence package status only; it does not rerun influence diagnostics.",
        },
        "final_fold_logs": {
            "status": "phase1_final_reporting_fold_log_index_recorded",
            "runtime_logs_audited_for_all_required_comparators": summary.get(
                "runtime_logs_audited_for_all_required_comparators"
            ),
            "source_links": {
                "governance_reconciliation_run": str(governance["run_dir"]),
                "comparator_reconciliation_run": source_links.get("comparator_reconciliation_run"),
                "comparator_reconciliation_summary": source_links.get("comparator_reconciliation_summary"),
            },
            "scientific_limit": "This is an index to audited runtime logs, not a substitute for the original logs.",
        },
        "claim_state_report": {
            "status": "phase1_final_reporting_claim_state_recorded",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "upstream_governance_claim_state_status": claim_state.get("status"),
            "blockers": claim_blockers,
            "not_ok_to_claim": list(claim_state.get("not_ok_to_claim", [])),
            "scientific_limit": "The final reporting claim state is closed even when reporting artifacts are complete.",
        },
        "phase1_final_reporting_claim_table": {
            "status": "phase1_final_reporting_claim_table_ready_claims_closed",
            "claim_table_ready": True,
            "claims_opened": False,
            "rows": claim_rows,
            "scientific_limit": "Every listed claim remains closed; rows do not constitute evidence for the claims.",
        },
        "required_reporting_artifacts": required_artifacts,
    }


def _build_manifest(
    *,
    reports: dict[str, Any],
    input_validation: dict[str, Any],
    reporting_config: dict[str, Any],
) -> dict[str, Any]:
    required = list(reporting_config.get("required_reporting_artifacts", []))
    artifacts_written = [
        "final_comparator_completeness_table",
        "negative_controls_report",
        "calibration_package_report",
        "influence_package_report",
        "final_fold_logs",
        "claim_state_report",
        "main_phase1_report",
    ]
    missing = [item for item in required if item not in artifacts_written]
    blockers = list(input_validation.get("blockers", []))
    if missing:
        blockers.append("final_phase1_reporting_artifacts_missing")
    policy = reporting_config.get("claim_table_policy", {})
    if policy.get("claims_opened") is not False:
        blockers.append("reporting_config_claim_policy_not_closed")
    reporting_package_passed = not blockers
    return {
        "status": "phase1_final_reporting_manifest_recorded"
        if reporting_package_passed
        else "phase1_final_reporting_manifest_blocked",
        "reporting_package_passed": reporting_package_passed,
        "claim_evaluable": reporting_package_passed,
        "claim_ready": False,
        "claim_table_ready": reports["phase1_final_reporting_claim_table"].get("claim_table_ready"),
        "claims_opened": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "smoke_artifacts_promoted": False,
        "artifacts": artifacts_written,
        "required_reporting_artifacts": required,
        "missing_reporting_artifacts": missing,
        "upstream_governance_blocked": bool(input_validation.get("upstream_claim_blockers")),
        "upstream_claim_blockers": list(input_validation.get("upstream_claim_blockers", [])),
        "blockers": _unique(blockers),
        "scientific_limit": "A complete reporting manifest records closed claims; it does not make failed governance surfaces pass.",
    }


def _build_claim_state(
    *, manifest: dict[str, Any], governance: dict[str, Any], input_validation: dict[str, Any]
) -> dict[str, Any]:
    blockers = _unique(list(input_validation.get("upstream_claim_blockers", [])) + list(manifest.get("blockers", [])))
    return {
        "status": "phase1_final_reporting_claim_state_recorded",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "reporting_package_passed": manifest.get("reporting_package_passed"),
        "upstream_governance_status": governance["summary"].get("status"),
        "blockers": blockers,
        "not_ok_to_claim": list(governance["claim_state"].get("not_ok_to_claim", [])),
        "scientific_limit": "Reporting records the claim state; it does not open claims.",
    }


def _build_summary(
    *,
    output_dir: Path,
    governance: dict[str, Any],
    manifest: dict[str, Any],
    input_validation: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_reporting_complete_claim_closed"
        if manifest.get("reporting_package_passed") is True
        else "phase1_final_reporting_blocked_claim_closed",
        "output_dir": str(output_dir),
        "final_governance_reconciliation_run": str(governance["run_dir"]),
        "reporting_package_passed": manifest.get("reporting_package_passed"),
        "claim_table_ready": manifest.get("claim_table_ready"),
        "claims_opened": False,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "upstream_governance_status": governance["summary"].get("status"),
        "governance_surfaces": governance["summary"].get("governance_surfaces", {}),
        "upstream_governance_blocked": bool(input_validation.get("upstream_claim_blockers")),
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final reporting can be complete while claims remain closed. "
            "This package does not prove Phase 1 efficacy or privileged transfer."
        ),
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
        "status": "phase1_final_reporting_source_links_recorded",
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


def _claim_row(claim_id: str, label: str, blockers: list[str]) -> dict[str, Any]:
    return {
        "claim_id": claim_id,
        "claim": label,
        "claim_ready": False,
        "claim_open": False,
        "evidence_status": "not_claim_evaluable",
        "blocking_reasons": blockers,
    }


def _render_main_report(
    summary: dict[str, Any],
    manifest: dict[str, Any],
    governance: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Report",
        "",
        f"Reporting package passed: `{summary['reporting_package_passed']}`",
        f"Claims opened: `{summary['claims_opened']}`",
        f"Upstream governance status: `{summary['upstream_governance_status']}`",
        "",
        "## Governance Surfaces",
        "",
    ]
    for key, value in summary.get("governance_surfaces", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            f"Headline Phase 1 claim open: `{claim_state['headline_phase1_claim_open']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "## Scientific Limit",
            "",
            manifest["scientific_limit"],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_report(summary: dict[str, Any], manifest: dict[str, Any], claim_state: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Reporting Package",
            "",
            f"Status: `{summary['status']}`",
            f"Reporting package passed: `{summary['reporting_package_passed']}`",
            f"Claim table ready: `{summary['claim_table_ready']}`",
            f"Claims opened: `{summary['claims_opened']}`",
            "",
            "## Required Artifacts",
            "",
            *[f"- `{artifact}`" for artifact in manifest["artifacts"]],
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            f"Headline Phase 1 claim open: `{claim_state['headline_phase1_claim_open']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "NOT OK TO CLAIM: this reporting package does not prove decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
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
