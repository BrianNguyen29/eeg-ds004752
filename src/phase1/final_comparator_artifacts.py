"""Phase 1 final comparator artifact manifest/readiness plan.

This module records the artifact schema required before final comparator
outputs can feed controls, calibration, influence and reporting. It does not
run final comparators and it does not treat smoke outputs as evidence.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalComparatorArtifactError(RuntimeError):
    """Raised when final comparator artifact planning cannot proceed."""


@dataclass(frozen=True)
class Phase1FinalComparatorArtifactResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "artifact": "configs/phase1/final_comparator_artifacts.json",
    "claim_package": "configs/phase1/final_claim_package.json",
}


def run_phase1_final_comparator_artifact_plan(
    *,
    prereg_bundle: str | Path,
    claim_package_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalComparatorArtifactResult:
    """Write a fail-closed final comparator artifact manifest plan."""

    prereg_bundle = Path(prereg_bundle)
    claim_package_run = _resolve_run_dir(Path(claim_package_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    claim_package = _read_claim_package_run(claim_package_run)
    artifact_config = load_config(repo_root / config_paths["artifact"])
    claim_config = load_config(repo_root / config_paths["claim_package"])
    _validate_claim_package_boundary(claim_package)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    contract = _build_contract(artifact_config, claim_config, claim_package)
    manifest_status = _build_manifest_status(artifact_config, claim_package)
    missing_artifacts = _build_missing_artifacts(artifact_config, manifest_status)
    leakage_requirements = _build_leakage_requirements(artifact_config)
    claim_state = _build_claim_state(artifact_config, missing_artifacts)
    implementation_plan = _build_implementation_plan(artifact_config, missing_artifacts)
    summary = {
        "status": "phase1_final_comparator_artifact_plan_recorded",
        "output_dir": str(output_dir),
        "artifact_plan_status": artifact_config.get("status"),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_package_run": str(claim_package_run),
        "required_final_comparators": artifact_config.get("required_final_comparators", []),
        "all_final_comparator_manifests_present": False,
        "smoke_metrics_promoted": False,
        "blockers": claim_state["blockers"],
        "next_step": "implement_final_comparator_runners_against_this_manifest_contract",
        "scientific_limit": (
            "Final comparator artifact planning only. This run does not execute final comparators "
            "or support Phase 1 efficacy claims."
        ),
    }
    inputs = {
        "status": "phase1_final_comparator_artifact_plan_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "claim_package_run": str(claim_package_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_comparator_artifact_plan_inputs.json"
    summary_path = output_dir / "phase1_final_comparator_artifact_plan_summary.json"
    report_path = output_dir / "phase1_final_comparator_artifact_plan_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_comparator_artifact_contract.json", contract)
    _write_json(output_dir / "phase1_final_comparator_manifest_status.json", manifest_status)
    _write_json(output_dir / "phase1_final_comparator_missing_artifacts.json", missing_artifacts)
    _write_json(output_dir / "phase1_final_comparator_leakage_requirements.json", leakage_requirements)
    _write_json(output_dir / "phase1_final_comparator_claim_state.json", claim_state)
    _write_json(output_dir / "phase1_final_comparator_implementation_plan.json", implementation_plan)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, contract, manifest_status, missing_artifacts, leakage_requirements, claim_state),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalComparatorArtifactResult(
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


def _read_claim_package_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_claim_package_plan_summary.json",
        "contract": "phase1_final_claim_package_contract.json",
        "claim_state": "phase1_final_claim_state_plan.json",
        "blockers": "phase1_final_claim_blocker_inventory.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalComparatorArtifactError(f"Final claim-package artifact not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_claim_package_boundary(claim_package: dict[str, Any]) -> None:
    summary = claim_package["summary"]
    claim_state = claim_package["claim_state"]
    if summary.get("status") != "phase1_final_claim_package_plan_recorded":
        raise Phase1FinalComparatorArtifactError("Final comparator artifact planning requires a recorded claim-package plan")
    if summary.get("claim_ready") is not False:
        raise Phase1FinalComparatorArtifactError("Final claim-package plan must keep claim_ready=false")
    if summary.get("headline_phase1_claim_open") is not False:
        raise Phase1FinalComparatorArtifactError("Final claim-package plan must keep headline claims closed")
    if claim_state.get("full_phase1_claim_bearing_run_allowed") is not False:
        raise Phase1FinalComparatorArtifactError("Final claim-package plan must keep claim-bearing runs blocked")


def _build_contract(
    artifact_config: dict[str, Any],
    claim_config: dict[str, Any],
    claim_package: dict[str, Any],
) -> dict[str, Any]:
    claim_required = set(claim_config.get("required_final_comparators", []))
    artifact_required = set(artifact_config.get("required_final_comparators", []))
    comparator_mismatch = sorted(claim_required.symmetric_difference(artifact_required))
    artifact_required_items = set(artifact_config.get("required_artifacts_per_comparator", []))
    claim_required_items = set(claim_config.get("required_final_comparator_artifacts", [])) - set(
        artifact_config.get("shared_artifacts", [])
    )
    artifact_schema_mismatch = sorted(claim_required_items.symmetric_difference(artifact_required_items))
    return {
        "status": "phase1_final_comparator_artifact_contract_recorded",
        "artifact_plan_id": artifact_config.get("artifact_plan_id"),
        "artifact_plan_status": artifact_config.get("status"),
        "claim_scope": artifact_config.get("claim_scope"),
        "source_contract": artifact_config.get("source_contract"),
        "source_claim_package_run_status": claim_package["summary"].get("status"),
        "required_final_comparators": artifact_config.get("required_final_comparators", []),
        "required_artifacts_per_comparator": artifact_config.get("required_artifacts_per_comparator", []),
        "shared_artifacts": artifact_config.get("shared_artifacts", []),
        "manifest_schema": artifact_config.get("manifest_schema", {}),
        "comparator_contract_matches_claim_package": not comparator_mismatch,
        "artifact_schema_matches_claim_package": not artifact_schema_mismatch,
        "comparator_mismatch": comparator_mismatch,
        "artifact_schema_mismatch": artifact_schema_mismatch,
        "scientific_integrity_rule": artifact_config.get("scientific_integrity_rule"),
    }


def _build_manifest_status(
    artifact_config: dict[str, Any],
    claim_package: dict[str, Any],
) -> dict[str, Any]:
    required_artifacts = artifact_config.get("required_artifacts_per_comparator", [])
    rows = []
    for comparator_id in artifact_config.get("required_final_comparators", []):
        rows.append(
            {
                "comparator_id": comparator_id,
                "status": "final_comparator_manifest_missing",
                "claim_evaluable": False,
                "source_final_claim_package_plan_status": claim_package["summary"].get("status"),
                "missing_artifacts": list(required_artifacts),
                "smoke_metrics_promoted": False,
                "scientific_limit": (
                    f"{comparator_id} final artifact manifest is not present; smoke artifacts cannot substitute."
                ),
            }
        )
    return {
        "status": "phase1_final_comparator_manifests_missing",
        "claim_evaluable": False,
        "all_final_comparator_manifests_present": False,
        "comparators": rows,
        "scientific_limit": "This manifest status records missing final comparator artifacts; it does not run comparators.",
    }


def _build_missing_artifacts(
    artifact_config: dict[str, Any],
    manifest_status: dict[str, Any],
) -> dict[str, Any]:
    per_comparator = [
        {
            "comparator_id": row["comparator_id"],
            "missing_artifacts": row["missing_artifacts"],
        }
        for row in manifest_status["comparators"]
    ]
    return {
        "status": "phase1_final_comparator_missing_artifacts_recorded",
        "claim_evaluable": False,
        "shared_missing_artifacts": artifact_config.get("shared_artifacts", []),
        "per_comparator_missing_artifacts": per_comparator,
        "blockers": [
            "final_comparator_artifact_manifests_missing",
            "final_comparator_completeness_table_missing",
            "final_comparator_outputs_not_claim_evaluable",
        ],
        "scientific_limit": "Missing artifact inventory is an implementation checklist, not evidence.",
    }


def _build_leakage_requirements(artifact_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_leakage_requirements_recorded",
        "requirements": artifact_config.get("leakage_requirements", {}),
        "outer_test_subject_policy": "no_outer_test_subject_in_any_fit",
        "test_time_policy": "scalp_only_for_test_time_inference",
        "must_be_verified_per_final_comparator_manifest": True,
        "scientific_limit": "Leakage requirements are recorded; final leakage audits are still missing.",
    }


def _build_claim_state(
    artifact_config: dict[str, Any],
    missing_artifacts: dict[str, Any],
) -> dict[str, Any]:
    blockers = [
        "final_comparator_artifact_plan_not_locked"
        if artifact_config.get("status") != "final_comparator_artifacts_locked"
        else "",
        *missing_artifacts["blockers"],
        "claim_blocked_until_final_comparator_artifacts_exist",
    ]
    return {
        "status": "phase1_final_comparator_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "smoke_metrics_promoted": False,
        "blockers": [item for item in _unique(blockers) if item],
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": "Final comparator artifact schema is recorded; final comparator evidence is still absent.",
    }


def _build_implementation_plan(
    artifact_config: dict[str, Any],
    missing_artifacts: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_implementation_plan_recorded",
        "ordered_items": [
            {
                "item": "implement_final_split_and_feature_manifests",
                "purpose": "Freeze final LOSO fold definitions and feature provenance before final comparator fits.",
            },
            {
                "item": "implement_final_fold_logs_and_logits",
                "purpose": "Write per-comparator fold outputs without using outer-test subjects in any fit.",
            },
            {
                "item": "implement_final_subject_level_metrics",
                "purpose": "Compute subject-level metrics from final logits only, not smoke outputs.",
            },
            {
                "item": "implement_final_leakage_audits",
                "purpose": "Verify split, preprocessing, alignment, teacher, privileged, gate and calibration fit policies.",
            },
            {
                "item": "implement_final_comparator_completeness_table",
                "purpose": "Provide the shared table consumed by controls, calibration, influence and reporting.",
            },
        ],
        "required_final_comparators": artifact_config.get("required_final_comparators", []),
        "blocked_by": missing_artifacts["blockers"],
        "scientific_integrity_rule": "Do not mark any comparator claim-evaluable until every required artifact exists.",
    }


def _render_report(
    summary: dict[str, Any],
    contract: dict[str, Any],
    manifest_status: dict[str, Any],
    missing_artifacts: dict[str, Any],
    leakage_requirements: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Comparator Artifact Plan",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Artifact plan status: `{summary['artifact_plan_status']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Smoke metrics promoted: `{summary['smoke_metrics_promoted']}`",
        "",
        "## Required Final Comparators",
        "",
    ]
    for comparator_id in summary["required_final_comparators"]:
        lines.append(f"- {comparator_id}")
    lines.extend(["", "## Contract Checks", ""])
    lines.append(f"- Comparator contract matches claim package: `{contract['comparator_contract_matches_claim_package']}`")
    lines.append(f"- Artifact schema matches claim package: `{contract['artifact_schema_matches_claim_package']}`")
    lines.extend(["", "## Missing Final Manifests", ""])
    for row in manifest_status["comparators"]:
        lines.append(f"- {row['comparator_id']}: `{row['status']}`")
    lines.extend(["", "## Shared Missing Artifacts", ""])
    for item in missing_artifacts["shared_missing_artifacts"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Leakage Requirements", ""])
    lines.append(f"- Outer-test subject policy: `{leakage_requirements['outer_test_subject_policy']}`")
    lines.append(f"- Test-time policy: `{leakage_requirements['test_time_policy']}`")
    lines.extend(["", "## Blockers", ""])
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Scientific Integrity", ""])
    lines.append("- This plan does not run final comparators.")
    lines.append("- It does not compute final metrics, calibration, controls, influence or reporting.")
    lines.append("- Smoke metrics remain non-claim diagnostics and cannot satisfy this contract.")
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
