"""Final split, feature provenance and leakage readiness plan for Phase 1.

This module records the manifest contract needed before final comparator
runners can write claim-evaluable artifacts. It does not construct final
folds, extract final features, run leakage audits, train models, or promote
smoke artifacts.
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


class Phase1FinalSplitFeatureLeakageError(RuntimeError):
    """Raised when final split/feature/leakage readiness cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalSplitFeatureLeakageResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "readiness": "configs/phase1/final_split_feature_leakage.json",
    "artifact": "configs/phase1/final_comparator_artifacts.json",
    "split": "configs/split/loso_subject.yaml",
    "dataset": "configs/data/snapshot.yaml",
}


def run_phase1_final_split_feature_leakage_plan(
    *,
    prereg_bundle: str | Path,
    comparator_artifact_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalSplitFeatureLeakageResult:
    """Write a fail-closed final split/feature/leakage readiness plan."""

    prereg_bundle = Path(prereg_bundle)
    comparator_artifact_run = _resolve_run_dir(Path(comparator_artifact_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    comparator_artifact = _read_comparator_artifact_run(comparator_artifact_run)
    _validate_comparator_artifact_boundary(comparator_artifact)

    readiness_config = load_config(repo_root / config_paths["readiness"])
    artifact_config = load_config(repo_root / config_paths["artifact"])
    split_config = load_config(repo_root / config_paths["split"])
    dataset_config = load_config(repo_root / config_paths["dataset"])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    contract = _build_contract(readiness_config, artifact_config, split_config, dataset_config, comparator_artifact)
    split_readiness = _build_split_readiness(readiness_config, split_config, bundle)
    feature_readiness = _build_feature_readiness(readiness_config, dataset_config)
    leakage_readiness = _build_leakage_readiness(readiness_config, comparator_artifact)
    source_links = _build_source_links(readiness_config, bundle, comparator_artifact_run, comparator_artifact)
    missing = _build_missing_manifest_inventory(readiness_config)
    claim_state = _build_claim_state(readiness_config, missing)
    implementation_plan = _build_implementation_plan(readiness_config, missing)

    summary = {
        "status": "phase1_final_split_feature_leakage_plan_recorded",
        "output_dir": str(output_dir),
        "readiness_status": readiness_config.get("status"),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "comparator_artifact_run": str(comparator_artifact_run),
        "required_manifests": readiness_config.get("required_manifests", []),
        "all_required_manifests_present": False,
        "smoke_artifacts_promoted": False,
        "blockers": claim_state["blockers"],
        "next_step": "implement_final_split_feature_leakage_manifests_before_final_comparator_runners",
        "scientific_limit": (
            "Final split/feature/leakage readiness only. This run does not create final folds, "
            "extract final features, run leakage audits, or support Phase 1 claims."
        ),
    }
    inputs = {
        "status": "phase1_final_split_feature_leakage_plan_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "comparator_artifact_run": str(comparator_artifact_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_split_feature_leakage_plan_inputs.json"
    summary_path = output_dir / "phase1_final_split_feature_leakage_plan_summary.json"
    report_path = output_dir / "phase1_final_split_feature_leakage_plan_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_split_feature_leakage_contract.json", contract)
    _write_json(output_dir / "phase1_final_split_manifest_readiness.json", split_readiness)
    _write_json(output_dir / "phase1_final_feature_manifest_readiness.json", feature_readiness)
    _write_json(output_dir / "phase1_final_leakage_audit_readiness.json", leakage_readiness)
    _write_json(output_dir / "phase1_final_split_feature_leakage_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_split_feature_leakage_missing_manifests.json", missing)
    _write_json(output_dir / "phase1_final_split_feature_leakage_claim_state.json", claim_state)
    _write_json(output_dir / "phase1_final_split_feature_leakage_implementation_plan.json", implementation_plan)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, contract, split_readiness, feature_readiness, leakage_readiness, missing, claim_state),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalSplitFeatureLeakageResult(
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


def _read_comparator_artifact_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_comparator_artifact_plan_summary.json",
        "contract": "phase1_final_comparator_artifact_contract.json",
        "manifest_status": "phase1_final_comparator_manifest_status.json",
        "missing": "phase1_final_comparator_missing_artifacts.json",
        "leakage": "phase1_final_comparator_leakage_requirements.json",
        "claim_state": "phase1_final_comparator_claim_state.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalSplitFeatureLeakageError(f"Final comparator artifact plan file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_comparator_artifact_boundary(comparator_artifact: dict[str, Any]) -> None:
    summary = comparator_artifact["summary"]
    claim_state = comparator_artifact["claim_state"]
    if summary.get("status") != "phase1_final_comparator_artifact_plan_recorded":
        raise Phase1FinalSplitFeatureLeakageError("Split/feature/leakage planning requires a recorded comparator artifact plan")
    if summary.get("claim_ready") is not False:
        raise Phase1FinalSplitFeatureLeakageError("Comparator artifact plan must keep claim_ready=false")
    if summary.get("smoke_metrics_promoted") is not False:
        raise Phase1FinalSplitFeatureLeakageError("Comparator artifact plan must not promote smoke metrics")
    if claim_state.get("full_phase1_claim_bearing_run_allowed") is not False:
        raise Phase1FinalSplitFeatureLeakageError("Comparator artifact plan must keep claim-bearing runs blocked")


def _build_contract(
    readiness_config: dict[str, Any],
    artifact_config: dict[str, Any],
    split_config: dict[str, Any],
    dataset_config: dict[str, Any],
    comparator_artifact: dict[str, Any],
) -> dict[str, Any]:
    required_from_artifact = set(artifact_config.get("required_artifacts_per_comparator", []))
    required_here = set(readiness_config.get("required_manifests", []))
    schema_matches_artifact_plan = required_here.issubset(required_from_artifact)
    return {
        "status": "phase1_final_split_feature_leakage_contract_recorded",
        "readiness_id": readiness_config.get("readiness_id"),
        "readiness_status": readiness_config.get("status"),
        "claim_scope": readiness_config.get("claim_scope"),
        "source_contract": readiness_config.get("source_contract"),
        "source_comparator_artifact_plan_status": comparator_artifact["summary"].get("status"),
        "required_manifests": readiness_config.get("required_manifests", []),
        "split_manifest_schema": readiness_config.get("split_manifest_schema", {}),
        "feature_manifest_schema": readiness_config.get("feature_manifest_schema", {}),
        "leakage_audit_schema": readiness_config.get("leakage_audit_schema", {}),
        "schema_matches_comparator_artifact_plan": schema_matches_artifact_plan,
        "split_config": split_config,
        "dataset_config_snapshot": {
            "snapshot_id": dataset_config.get("snapshot_id"),
            "allow_metadata_only": dataset_config.get("allow_metadata_only"),
            "require_materialized_payloads_for_signal_audit": dataset_config.get(
                "require_materialized_payloads_for_signal_audit"
            ),
        },
        "scientific_integrity_rule": readiness_config.get("scientific_integrity_rule"),
    }


def _build_split_readiness(
    readiness_config: dict[str, Any],
    split_config: dict[str, Any],
    bundle: dict[str, Any],
) -> dict[str, Any]:
    blockers = ["final_split_manifest_missing"]
    if split_config.get("split_id") != readiness_config.get("split_manifest_schema", {}).get("split_id"):
        blockers.append("split_config_does_not_match_contract")
    return {
        "status": "phase1_final_split_manifest_not_ready",
        "claim_evaluable": False,
        "split_config_status": "configured",
        "split_id": split_config.get("split_id"),
        "group_key": split_config.get("group_key"),
        "leakage_policy": split_config.get("leakage_policy"),
        "source_gate0_run": bundle.get("source_runs", {}).get("gate0"),
        "required_schema": readiness_config.get("split_manifest_schema", {}),
        "blockers": blockers,
        "scientific_limit": "Split readiness records the final split contract; it does not create final folds.",
    }


def _build_feature_readiness(
    readiness_config: dict[str, Any],
    dataset_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = ["final_feature_manifest_missing", "materialized_payload_signal_audit_for_final_scope_missing"]
    return {
        "status": "phase1_final_feature_manifest_not_ready",
        "claim_evaluable": False,
        "dataset_snapshot_id": dataset_config.get("snapshot_id"),
        "dataset_root": dataset_config.get("dataset_root"),
        "allow_metadata_only": dataset_config.get("allow_metadata_only"),
        "payload_materialization_required_for_final": readiness_config.get("feature_manifest_schema", {}).get(
            "payload_materialization_required_for_final"
        ),
        "smoke_feature_rows_allowed_as_final": readiness_config.get("feature_manifest_schema", {}).get(
            "smoke_feature_rows_allowed_as_final"
        ),
        "required_schema": readiness_config.get("feature_manifest_schema", {}),
        "blockers": blockers,
        "scientific_limit": "Feature readiness records provenance requirements; it does not extract final features.",
    }


def _build_leakage_readiness(
    readiness_config: dict[str, Any],
    comparator_artifact: dict[str, Any],
) -> dict[str, Any]:
    blockers = ["final_leakage_audit_missing"]
    return {
        "status": "phase1_final_leakage_audit_not_ready",
        "claim_evaluable": False,
        "required_schema": readiness_config.get("leakage_audit_schema", {}),
        "comparator_artifact_leakage_requirements": comparator_artifact["leakage"].get("requirements", {}),
        "outer_test_subject_policy": "no_outer_test_subject_in_any_fit",
        "test_time_policy": "scalp_only_for_test_time_inference",
        "blockers": blockers,
        "scientific_limit": "Leakage readiness records required audit fields; it does not execute final leakage audits.",
    }


def _build_source_links(
    readiness_config: dict[str, Any],
    bundle: dict[str, Any],
    comparator_artifact_run: Path,
    comparator_artifact: dict[str, Any],
) -> dict[str, Any]:
    links = {
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "gate0_run": bundle.get("source_runs", {}).get("gate0"),
        "final_comparator_artifact_plan": str(comparator_artifact_run),
        "final_comparator_artifact_contract_status": comparator_artifact["contract"].get("status"),
    }
    missing = [
        item
        for item in readiness_config.get("required_source_links", [])
        if item == "cohort_lock" or (item == "final_claim_package_plan" and not comparator_artifact["contract"].get("source_claim_package_run_status"))
    ]
    return {
        "status": "phase1_final_split_feature_leakage_source_links_recorded",
        "source_links": links,
        "required_source_links": readiness_config.get("required_source_links", []),
        "missing_source_links": missing,
        "scientific_limit": "Source links document provenance requirements; missing links remain blockers.",
    }


def _build_missing_manifest_inventory(readiness_config: dict[str, Any]) -> dict[str, Any]:
    missing = list(readiness_config.get("blocking_if_missing", []))
    return {
        "status": "phase1_final_split_feature_leakage_missing_manifests_recorded",
        "claim_evaluable": False,
        "missing_manifests": missing,
        "blockers": [
            "final_split_manifest_missing",
            "final_feature_manifest_missing",
            "final_leakage_audit_missing",
            "materialized_payload_signal_audit_for_final_scope_missing",
        ],
        "scientific_limit": "Missing manifest inventory is an implementation checklist, not evidence.",
    }


def _build_claim_state(readiness_config: dict[str, Any], missing: dict[str, Any]) -> dict[str, Any]:
    blockers = [
        "final_split_feature_leakage_plan_not_locked"
        if readiness_config.get("status") != "final_split_feature_leakage_locked"
        else "",
        *missing["blockers"],
        "claim_blocked_until_final_split_feature_leakage_manifests_exist",
    ]
    return {
        "status": "phase1_final_split_feature_leakage_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "smoke_artifacts_promoted": False,
        "blockers": [item for item in _unique(blockers) if item],
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": "Final split/feature/leakage schema is recorded; final manifests are still absent.",
    }


def _build_implementation_plan(readiness_config: dict[str, Any], missing: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_split_feature_leakage_implementation_plan_recorded",
        "ordered_items": [
            {
                "item": "write_final_split_manifest",
                "purpose": "Create LOSO subject folds from locked cohort without train/test subject overlap.",
            },
            {
                "item": "write_final_feature_manifest",
                "purpose": "Record final feature provenance, payload materialization scope and feature extraction policy.",
            },
            {
                "item": "write_final_leakage_audit_template",
                "purpose": "Record fit and transform subjects per preprocessing, normalization, alignment, teacher, privileged, gate and calibration stage.",
            },
            {
                "item": "wire_manifests_into_final_comparator_runners",
                "purpose": "Require every final comparator manifest to link these split/feature/leakage artifacts.",
            },
        ],
        "required_manifests": readiness_config.get("required_manifests", []),
        "blocked_by": missing["blockers"],
        "scientific_integrity_rule": "Do not run claim-bearing comparator fits until these final manifests exist.",
    }


def _render_report(
    summary: dict[str, Any],
    contract: dict[str, Any],
    split_readiness: dict[str, Any],
    feature_readiness: dict[str, Any],
    leakage_readiness: dict[str, Any],
    missing: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Split/Feature/Leakage Readiness",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Readiness status: `{summary['readiness_status']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Smoke artifacts promoted: `{summary['smoke_artifacts_promoted']}`",
        "",
        "## Contract",
        "",
        f"- Schema matches comparator artifact plan: `{contract['schema_matches_comparator_artifact_plan']}`",
        f"- Split ID: `{split_readiness['split_id']}`",
        f"- Dataset snapshot: `{feature_readiness['dataset_snapshot_id']}`",
        "",
        "## Required Manifests",
        "",
    ]
    for item in summary["required_manifests"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Readiness Surfaces", ""])
    lines.append(f"- Split manifest: `{split_readiness['status']}`")
    lines.append(f"- Feature manifest: `{feature_readiness['status']}`")
    lines.append(f"- Leakage audit: `{leakage_readiness['status']}`")
    lines.extend(["", "## Missing Manifests", ""])
    for item in missing["missing_manifests"]:
        lines.append(f"- `{item}`")
    lines.extend(["", "## Blockers", ""])
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Scientific Integrity", ""])
    lines.append("- This readiness plan does not create final folds, features or leakage audits.")
    lines.append("- It does not run final comparators or compute final metrics.")
    lines.append("- Smoke artifacts remain non-claim diagnostics and cannot satisfy this contract.")
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
