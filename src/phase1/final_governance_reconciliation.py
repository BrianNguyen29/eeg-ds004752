"""Final Phase 1 governance reconciliation.

This runner links a completed final comparator reconciliation package with
final controls, calibration, influence and reporting manifests. It is
deliberately claim-closed: it records readiness and blockers, but it does not
fabricate missing governance artifacts, recompute comparator metrics, or open
headline claims.
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
from .calibration import evaluate_calibration_package
from .controls import evaluate_control_suite
from .influence import evaluate_influence_package
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalGovernanceReconciliationError(RuntimeError):
    """Raised when final governance reconciliation cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalGovernanceReconciliationResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "governance": "configs/phase1/final_governance_reconciliation.json",
    "controls": "configs/controls/control_suite_spec.yaml",
    "nuisance": "configs/controls/nuisance_block_spec.yaml",
    "metrics": "configs/eval/metrics.yaml",
    "inference": "configs/eval/inference_defaults.yaml",
    "gate1": "configs/gate1/decision_simulation.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_governance_reconciliation(
    *,
    prereg_bundle: str | Path,
    comparator_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
    final_control_manifest: str | Path | None = None,
    final_calibration_manifest: str | Path | None = None,
    final_influence_manifest: str | Path | None = None,
    final_reporting_manifest: str | Path | None = None,
) -> Phase1FinalGovernanceReconciliationResult:
    """Write final governance reconciliation artifacts while keeping claims closed."""

    prereg_bundle = Path(prereg_bundle)
    comparator_reconciliation_run = _resolve_run_dir(Path(comparator_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    config = load_config(repo_root / config_paths["governance"])
    comparator = _read_comparator_reconciliation_run(comparator_reconciliation_run)
    input_validation = _validate_comparator_reconciliation(comparator=comparator, config=config)

    controls = evaluate_control_suite(
        control_config_path=repo_root / config_paths["controls"],
        nuisance_config_path=repo_root / config_paths["nuisance"],
        gate2_config_path=repo_root / config_paths["gate2"],
        final_control_manifest_path=final_control_manifest,
    )
    calibration = evaluate_calibration_package(
        metrics_config_path=repo_root / config_paths["metrics"],
        inference_config_path=repo_root / config_paths["inference"],
        gate1_config_path=repo_root / config_paths["gate1"],
        final_calibration_manifest_path=final_calibration_manifest,
    )
    influence = evaluate_influence_package(
        gate1_config_path=repo_root / config_paths["gate1"],
        gate2_config_path=repo_root / config_paths["gate2"],
        final_influence_manifest_path=final_influence_manifest,
    )
    reporting = _evaluate_reporting_manifest(
        final_reporting_manifest=final_reporting_manifest,
        required_artifacts=config.get("required_reporting_artifacts", []),
    )
    claim_state = _build_claim_state(
        input_validation=input_validation,
        controls=controls,
        calibration=calibration,
        influence=influence,
        reporting=reporting,
        config=config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        comparator=comparator,
        final_control_manifest=final_control_manifest,
        final_calibration_manifest=final_calibration_manifest,
        final_influence_manifest=final_influence_manifest,
        final_reporting_manifest=final_reporting_manifest,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_governance_reconciliation_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "comparator_reconciliation_run": str(comparator_reconciliation_run),
        "final_control_manifest": str(final_control_manifest) if final_control_manifest else None,
        "final_calibration_manifest": str(final_calibration_manifest) if final_calibration_manifest else None,
        "final_influence_manifest": str(final_influence_manifest) if final_influence_manifest else None,
        "final_reporting_manifest": str(final_reporting_manifest) if final_reporting_manifest else None,
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        comparator=comparator,
        input_validation=input_validation,
        controls=controls,
        calibration=calibration,
        influence=influence,
        reporting=reporting,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_governance_reconciliation_inputs.json"
    summary_path = output_dir / "phase1_final_governance_reconciliation_summary.json"
    report_path = output_dir / "phase1_final_governance_reconciliation_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_governance_reconciliation_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_governance_reconciliation_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_controls_reconciliation_status.json", controls)
    _write_json(output_dir / "phase1_final_calibration_reconciliation_status.json", calibration)
    _write_json(output_dir / "phase1_final_influence_reconciliation_status.json", influence)
    _write_json(output_dir / "phase1_final_reporting_reconciliation_status.json", reporting)
    _write_json(output_dir / "phase1_final_governance_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, claim_state, controls, calibration, influence, reporting), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalGovernanceReconciliationResult(
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


def _read_comparator_reconciliation_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_comparator_reconciliation_summary.json",
        "input_validation": "phase1_final_comparator_reconciliation_input_validation.json",
        "completeness": "phase1_final_comparator_reconciled_completeness_table.json",
        "runtime_leakage": "phase1_final_comparator_reconciled_runtime_leakage_audit.json",
        "claim_state": "phase1_final_comparator_reconciled_claim_state.json",
        "source_links": "phase1_final_comparator_reconciliation_source_links.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalGovernanceReconciliationError(f"Comparator reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_comparator_reconciliation(
    *, comparator: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    summary = comparator["summary"]
    completeness = comparator["completeness"]
    runtime_leakage = comparator["runtime_leakage"]
    claim_state = comparator["claim_state"]
    required = config.get("required_comparator_reconciliation", {})
    observed = {
        "all_final_comparator_outputs_present": summary.get("all_final_comparator_outputs_present"),
        "runtime_comparator_logs_audited_for_all_required_comparators": summary.get(
            "runtime_comparator_logs_audited_for_all_required_comparators"
        ),
        "claim_ready": summary.get("claim_ready"),
        "headline_phase1_claim_open": summary.get("headline_phase1_claim_open"),
        "full_phase1_claim_bearing_run_allowed": summary.get("full_phase1_claim_bearing_run_allowed"),
        "smoke_artifacts_promoted": summary.get("smoke_artifacts_promoted"),
    }
    blockers = [
        f"comparator_reconciliation_{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    if summary.get("status") != "phase1_final_comparator_reconciliation_complete_claim_closed":
        blockers.append("comparator_reconciliation_not_complete_claim_closed")
    if completeness.get("status") != "phase1_final_comparator_reconciled_completeness_recorded":
        blockers.append("comparator_reconciled_completeness_not_recorded")
    if runtime_leakage.get("status") != "phase1_final_comparator_reconciled_runtime_leakage_audit_recorded":
        blockers.append("comparator_reconciled_runtime_leakage_not_recorded")
    if claim_state.get("claim_ready") is not False:
        blockers.append("comparator_reconciliation_claim_state_not_closed")
    if len(completeness.get("rows", [])) != 6:
        blockers.append("comparator_reconciliation_missing_required_comparator_rows")
    return {
        "status": "phase1_final_governance_comparator_inputs_ready" if not blockers else "phase1_final_governance_comparator_inputs_blocked",
        "observed": observed,
        "required": required,
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "completed_comparators": summary.get("completed_comparators", []),
        "blocked_comparators": summary.get("blocked_comparators", []),
        "blockers": _unique(blockers),
        "scientific_limit": "Comparator reconciliation validation checks upstream artifact completeness only; it is not efficacy evidence.",
    }


def _evaluate_reporting_manifest(
    *, final_reporting_manifest: str | Path | None, required_artifacts: list[str]
) -> dict[str, Any]:
    manifest_path = Path(final_reporting_manifest) if final_reporting_manifest else None
    manifest = _load_optional_manifest(manifest_path)
    provided = sorted(manifest.get("artifacts", [])) if isinstance(manifest.get("artifacts"), list) else []
    missing = [item for item in required_artifacts if item not in provided]
    blockers = []
    if manifest_path is None or not manifest_path.exists():
        blockers.append("final_phase1_reporting_manifest_missing")
    if missing:
        blockers.append("final_phase1_reporting_artifacts_missing")
    if manifest.get("claim_table_ready") is not True:
        blockers.append("final_phase1_claim_table_missing_or_not_ready")
    if manifest.get("claims_opened") is True:
        blockers.append("final_phase1_reporting_manifest_attempts_to_open_claims")
    return {
        "status": "phase1_final_reporting_claim_evaluable" if not blockers else "phase1_final_reporting_not_claim_evaluable",
        "reporting_package_executable": not blockers,
        "claim_evaluable": not blockers,
        "claim_blocker": bool(blockers),
        "blockers": blockers,
        "final_reporting_manifest_path": str(manifest_path) if manifest_path else None,
        "provided_artifacts": provided,
        "required_reporting_artifacts": required_artifacts,
        "missing_reporting_artifacts": missing,
        "claim_table_ready": manifest.get("claim_table_ready"),
        "claims_opened": manifest.get("claims_opened", False),
        "scientific_limit": "Reporting readiness does not itself open claims; it records whether reporting artifacts exist.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    controls: dict[str, Any],
    calibration: dict[str, Any],
    influence: dict[str, Any],
    reporting: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    blockers = (
        list(input_validation.get("blockers", []))
        + _prefixed("controls", controls.get("blockers", []))
        + _prefixed("calibration", calibration.get("blockers", []))
        + _prefixed("influence", influence.get("blockers", []))
        + _prefixed("reporting", reporting.get("blockers", []))
    )
    if not all(
        surface.get("claim_evaluable") is True
        for surface in [controls, calibration, influence, reporting]
    ):
        blockers.extend(config.get("claim_blockers_when_incomplete", []))
    blockers = _unique(blockers)
    return {
        "status": "phase1_final_governance_claim_state_blocked"
        if blockers
        else "phase1_final_governance_claim_state_ready_claim_closed",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "governance_surfaces_claim_evaluable": {
            "controls": controls.get("claim_evaluable"),
            "calibration": calibration.get("claim_evaluable"),
            "influence": influence.get("claim_evaluable"),
            "reporting": reporting.get("claim_evaluable"),
        },
        "blockers": blockers,
        "not_ok_to_claim": [
            "decoder efficacy",
            "A2d efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "scientific_limit": "This claim state remains closed. Reconciliation can support later review but does not open claims.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    comparator: dict[str, Any],
    final_control_manifest: str | Path | None,
    final_calibration_manifest: str | Path | None,
    final_influence_manifest: str | Path | None,
    final_reporting_manifest: str | Path | None,
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    optional_paths = {
        "final_control_manifest": Path(final_control_manifest) if final_control_manifest else None,
        "final_calibration_manifest": Path(final_calibration_manifest) if final_calibration_manifest else None,
        "final_influence_manifest": Path(final_influence_manifest) if final_influence_manifest else None,
        "final_reporting_manifest": Path(final_reporting_manifest) if final_reporting_manifest else None,
    }
    return {
        "status": "phase1_final_governance_reconciliation_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "comparator_reconciliation_summary": str(comparator["run_dir"] / "phase1_final_comparator_reconciliation_summary.json"),
        "comparator_reconciliation_summary_sha256": _sha256(
            comparator["run_dir"] / "phase1_final_comparator_reconciliation_summary.json"
        ),
        "optional_manifest_paths": {key: str(path) if path else None for key, path in optional_paths.items()},
        "optional_manifest_hashes": {
            key: _sha256(path)
            for key, path in optional_paths.items()
            if path is not None and path.exists()
        },
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not model evidence.",
    }


def _build_summary(
    *,
    output_dir: Path,
    comparator: dict[str, Any],
    input_validation: dict[str, Any],
    controls: dict[str, Any],
    calibration: dict[str, Any],
    influence: dict[str, Any],
    reporting: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    surfaces_ready = all(
        surface.get("claim_evaluable") is True
        for surface in [controls, calibration, influence, reporting]
    )
    input_ready = not input_validation.get("blockers")
    return {
        "status": "phase1_final_governance_reconciliation_ready_claim_closed"
        if input_ready and surfaces_ready
        else "phase1_final_governance_reconciliation_blocked",
        "output_dir": str(output_dir),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "comparator_outputs_complete": input_validation["observed"].get("all_final_comparator_outputs_present"),
        "runtime_logs_audited_for_all_required_comparators": input_validation["observed"].get(
            "runtime_comparator_logs_audited_for_all_required_comparators"
        ),
        "governance_surfaces": {
            "controls_claim_evaluable": controls.get("claim_evaluable"),
            "calibration_claim_evaluable": calibration.get("claim_evaluable"),
            "influence_claim_evaluable": influence.get("claim_evaluable"),
            "reporting_claim_evaluable": reporting.get("claim_evaluable"),
        },
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final governance reconciliation records whether governance surfaces are present. "
            "It does not open claims or prove Phase 1 efficacy."
        ),
    }


def _render_report(
    summary: dict[str, Any],
    claim_state: dict[str, Any],
    controls: dict[str, Any],
    calibration: dict[str, Any],
    influence: dict[str, Any],
    reporting: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Governance Reconciliation",
            "",
            f"Status: `{summary['status']}`",
            f"Comparator reconciliation run: `{summary['comparator_reconciliation_run']}`",
            f"Comparator outputs complete: `{summary['comparator_outputs_complete']}`",
            f"Runtime logs audited for all comparators: `{summary['runtime_logs_audited_for_all_required_comparators']}`",
            "",
            "## Governance Surfaces",
            "",
            f"- Controls claim-evaluable: `{controls['claim_evaluable']}`",
            f"- Calibration claim-evaluable: `{calibration['claim_evaluable']}`",
            f"- Influence claim-evaluable: `{influence['claim_evaluable']}`",
            f"- Reporting claim-evaluable: `{reporting['claim_evaluable']}`",
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )


def _load_optional_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    data = load_config(path)
    return data if isinstance(data, dict) else {}


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
