"""Final comparator runner readiness and output-manifest contract.

This module links final split, feature and manifest-level leakage artifacts to
the final comparator output contract. It deliberately does not run final
comparators or create model outputs.
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


class Phase1FinalComparatorRunnerReadinessError(RuntimeError):
    """Raised when final comparator runner readiness cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalComparatorRunnerReadinessResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "runner": "configs/phase1/final_comparator_runner_readiness.json",
    "artifact": "configs/phase1/final_comparator_artifacts.json",
}


def run_phase1_final_comparator_runner_readiness(
    *,
    prereg_bundle: str | Path,
    final_split_run: str | Path,
    final_feature_run: str | Path,
    final_leakage_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalComparatorRunnerReadinessResult:
    """Record final comparator output-manifest readiness without running models."""

    prereg_bundle = Path(prereg_bundle)
    final_split_run = _resolve_run_dir(Path(final_split_run))
    final_feature_run = _resolve_run_dir(Path(final_feature_run))
    final_leakage_run = _resolve_run_dir(Path(final_leakage_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    split = _read_final_split_run(final_split_run)
    feature = _read_final_feature_run(final_feature_run)
    leakage = _read_final_leakage_run(final_leakage_run)
    runner_config = load_config(repo_root / config_paths["runner"])
    artifact_config = load_config(repo_root / config_paths["artifact"])

    _validate_final_split_boundary(split)
    _validate_final_feature_boundary(feature)
    _validate_final_leakage_boundary(leakage)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    input_validation = _validate_upstream_inputs(split, feature, leakage, runner_config)
    contract = _build_contract(runner_config, artifact_config, input_validation)
    manifest_status = _build_manifest_status(
        runner_config=runner_config,
        artifact_config=artifact_config,
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
        final_leakage_run=final_leakage_run,
    )
    missing_outputs = _build_missing_outputs(runner_config, manifest_status)
    runtime_leakage_requirements = _build_runtime_leakage_requirements(runner_config, artifact_config)
    completeness_table = _build_completeness_table(manifest_status)
    claim_state = _build_claim_state(runner_config, input_validation, missing_outputs)
    implementation_plan = _build_implementation_plan(runner_config, missing_outputs)
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
        final_leakage_run=final_leakage_run,
        config_paths=config_paths,
        repo_root=repo_root,
    )

    upstream_ready = input_validation["status"] == "phase1_final_comparator_runner_inputs_ready"
    summary = {
        "status": "phase1_final_comparator_runner_readiness_recorded",
        "output_dir": str(output_dir),
        "runner_readiness_status": runner_config.get("status"),
        "upstream_manifests_ready": upstream_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "required_final_comparators": runner_config.get("required_final_comparators", []),
        "final_comparator_outputs_present": False,
        "all_comparator_output_manifests_present": False,
        "runtime_comparator_logs_audited": False,
        "smoke_artifacts_promoted": False,
        "contract_matches_artifact_plan": contract["comparator_contract_matches_artifact_plan"],
        "output_schema_matches_artifact_plan": contract["output_schema_matches_artifact_plan"],
        "manifest_status": manifest_status["status"],
        "n_required_comparators": len(runner_config.get("required_final_comparators", [])),
        "n_comparator_output_manifests_present": 0,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final comparator runner readiness and output-manifest contract only. This run does not execute "
            "final comparators, create logits or metrics, audit runtime comparator logs, or support claims."
        ),
    }
    inputs = {
        "status": "phase1_final_comparator_runner_readiness_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_feature_run": str(final_feature_run),
        "final_leakage_run": str(final_leakage_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_comparator_runner_readiness_inputs.json"
    summary_path = output_dir / "phase1_final_comparator_runner_readiness_summary.json"
    report_path = output_dir / "phase1_final_comparator_runner_readiness_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_comparator_runner_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_comparator_runner_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_comparator_runner_output_contract.json", contract)
    _write_json(output_dir / "phase1_final_comparator_runner_manifest_status.json", manifest_status)
    _write_json(output_dir / "phase1_final_comparator_missing_outputs.json", missing_outputs)
    _write_json(output_dir / "phase1_final_comparator_runtime_leakage_requirements.json", runtime_leakage_requirements)
    _write_json(output_dir / "phase1_final_comparator_completeness_table.json", completeness_table)
    _write_json(output_dir / "phase1_final_comparator_runner_claim_state.json", claim_state)
    _write_json(output_dir / "phase1_final_comparator_runner_implementation_plan.json", implementation_plan)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(
            summary,
            input_validation,
            contract,
            manifest_status,
            missing_outputs,
            runtime_leakage_requirements,
            claim_state,
        ),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalComparatorRunnerReadinessResult(
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


def _read_final_split_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_split_manifest_summary.json",
        "manifest": "final_split_manifest.json",
        "validation": "phase1_final_split_manifest_validation.json",
        "claim_state": "phase1_final_split_manifest_claim_state.json",
    }
    return _read_required_files(run_dir, required, "Final split manifest")


def _read_final_feature_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_feature_manifest_summary.json",
        "manifest": "final_feature_manifest.json",
        "validation": "phase1_final_feature_manifest_validation.json",
        "claim_state": "phase1_final_feature_manifest_claim_state.json",
    }
    return _read_required_files(run_dir, required, "Final feature manifest")


def _read_final_leakage_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_leakage_audit_summary.json",
        "audit": "final_leakage_audit.json",
        "input_validation": "phase1_final_leakage_audit_input_validation.json",
        "validation": "phase1_final_leakage_audit_validation.json",
        "claim_state": "phase1_final_leakage_audit_claim_state.json",
    }
    return _read_required_files(run_dir, required, "Final leakage audit")


def _read_required_files(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalComparatorRunnerReadinessError(f"{label} file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_final_split_boundary(split: dict[str, Any]) -> None:
    if split["summary"].get("status") != "phase1_final_split_manifest_recorded":
        raise Phase1FinalComparatorRunnerReadinessError("Final comparator readiness requires a recorded final split manifest")
    if split["summary"].get("split_manifest_ready") is not True:
        raise Phase1FinalComparatorRunnerReadinessError("Final split manifest must be ready")
    if split["validation"].get("status") != "phase1_final_split_manifest_validation_passed":
        raise Phase1FinalComparatorRunnerReadinessError("Final split manifest validation must pass")
    if split["validation"].get("no_subject_overlap_between_train_and_test") is not True:
        raise Phase1FinalComparatorRunnerReadinessError("Final split manifest must have no train/test subject overlap")
    if split["manifest"].get("claim_ready") is not False or split["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final split manifest must keep claim_ready=false")
    if split["manifest"].get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final split manifest must not promote smoke artifacts")


def _validate_final_feature_boundary(feature: dict[str, Any]) -> None:
    if feature["summary"].get("status") != "phase1_final_feature_manifest_recorded":
        raise Phase1FinalComparatorRunnerReadinessError("Final comparator readiness requires a recorded final feature manifest")
    if feature["summary"].get("feature_manifest_ready") is not True:
        raise Phase1FinalComparatorRunnerReadinessError("Final feature manifest must be ready")
    if feature["validation"].get("status") != "phase1_final_feature_manifest_validation_passed":
        raise Phase1FinalComparatorRunnerReadinessError("Final feature manifest validation must pass")
    manifest = feature["manifest"]
    if manifest.get("contains_feature_matrix") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final feature manifest must not contain feature matrix")
    if manifest.get("contains_model_outputs") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final feature manifest must not contain model outputs")
    if manifest.get("contains_metrics") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final feature manifest must not contain metrics")
    if manifest.get("claim_ready") is not False or feature["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final feature manifest must keep claim_ready=false")


def _validate_final_leakage_boundary(leakage: dict[str, Any]) -> None:
    if leakage["summary"].get("status") != "phase1_final_leakage_audit_recorded":
        raise Phase1FinalComparatorRunnerReadinessError("Final comparator readiness requires a recorded final leakage audit")
    if leakage["summary"].get("leakage_audit_ready") is not True:
        raise Phase1FinalComparatorRunnerReadinessError("Final leakage audit must be ready")
    if leakage["validation"].get("status") != "phase1_final_leakage_audit_validation_passed":
        raise Phase1FinalComparatorRunnerReadinessError("Final leakage audit validation must pass")
    if leakage["audit"].get("outer_test_subject_used_in_any_fit") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Manifest-level leakage audit found outer-test subject in fit")
    if leakage["audit"].get("test_time_privileged_or_teacher_outputs_allowed") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Manifest-level leakage audit must disallow test-time privileged/teacher outputs")
    if leakage["audit"].get("runtime_comparator_logs_audited") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("This readiness step must run before runtime comparator logs exist")
    if leakage["audit"].get("contains_model_outputs") is not False or leakage["audit"].get("contains_metrics") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Manifest-level leakage audit must not contain model outputs or metrics")
    if leakage["audit"].get("claim_ready") is not False or leakage["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalComparatorRunnerReadinessError("Final leakage audit must keep claim_ready=false")


def _validate_upstream_inputs(
    split: dict[str, Any],
    feature: dict[str, Any],
    leakage: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    required = runner_config.get("required_upstream_inputs", {})
    observed = {
        "final_split_manifest_ready": split["summary"].get("split_manifest_ready"),
        "final_feature_manifest_ready": feature["summary"].get("feature_manifest_ready"),
        "final_leakage_audit_ready": leakage["summary"].get("leakage_audit_ready"),
        "runtime_comparator_logs_audited": leakage["audit"].get("runtime_comparator_logs_audited"),
        "feature_manifest_contains_feature_matrix": feature["manifest"].get("contains_feature_matrix"),
        "feature_manifest_contains_model_outputs": feature["manifest"].get("contains_model_outputs"),
        "feature_manifest_contains_metrics": feature["manifest"].get("contains_metrics"),
        "manifest_level_outer_test_subject_used_in_any_fit": leakage["audit"].get("outer_test_subject_used_in_any_fit"),
        "test_time_privileged_or_teacher_outputs_allowed": leakage["audit"].get(
            "test_time_privileged_or_teacher_outputs_allowed"
        ),
        "smoke_artifacts_promoted": bool(
            split["manifest"].get("smoke_artifacts_promoted")
            or feature["manifest"].get("smoke_feature_rows_allowed_as_final")
        ),
    }
    blockers = [
        f"{key}_mismatch"
        for key, expected in required.items()
        if observed.get(key) is not expected
    ]
    return {
        "status": "phase1_final_comparator_runner_inputs_ready" if not blockers else "phase1_final_comparator_runner_inputs_blocked",
        "observed": observed,
        "required": required,
        "blockers": blockers,
        "scientific_limit": "Input validation checks readiness manifests only; it is not model evidence.",
    }


def _build_contract(
    runner_config: dict[str, Any],
    artifact_config: dict[str, Any],
    input_validation: dict[str, Any],
) -> dict[str, Any]:
    runner_comparators = set(runner_config.get("required_final_comparators", []))
    artifact_comparators = set(artifact_config.get("required_final_comparators", []))
    comparator_mismatch = sorted(runner_comparators.symmetric_difference(artifact_comparators))
    runner_outputs = set(runner_config.get("required_outputs_per_comparator", []))
    artifact_outputs = set(artifact_config.get("required_artifacts_per_comparator", []))
    mapped_artifact_outputs = artifact_outputs - {"final_split_manifest", "final_feature_manifest", "final_leakage_audit"}
    mapped_runner_outputs = runner_outputs - {"runtime_leakage_logs", "comparator_output_manifest"}
    output_schema_mismatch = sorted(mapped_runner_outputs.symmetric_difference(mapped_artifact_outputs))
    return {
        "status": "phase1_final_comparator_runner_output_contract_recorded",
        "readiness_id": runner_config.get("readiness_id"),
        "readiness_status": runner_config.get("status"),
        "claim_scope": runner_config.get("claim_scope"),
        "required_final_comparators": runner_config.get("required_final_comparators", []),
        "required_outputs_per_comparator": runner_config.get("required_outputs_per_comparator", []),
        "shared_required_outputs": runner_config.get("shared_required_outputs", []),
        "output_manifest_schema": runner_config.get("output_manifest_schema", {}),
        "fit_scope_rules": runner_config.get("fit_scope_rules", {}),
        "source_contracts": runner_config.get("source_contracts", {}),
        "input_validation_status": input_validation["status"],
        "comparator_contract_matches_artifact_plan": not comparator_mismatch,
        "output_schema_matches_artifact_plan": not output_schema_mismatch,
        "comparator_mismatch": comparator_mismatch,
        "output_schema_mismatch": output_schema_mismatch,
        "scientific_integrity_rule": runner_config.get("scientific_integrity_rule"),
    }


def _build_manifest_status(
    *,
    runner_config: dict[str, Any],
    artifact_config: dict[str, Any],
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    final_feature_run: Path,
    final_leakage_run: Path,
) -> dict[str, Any]:
    missing = list(runner_config.get("required_outputs_per_comparator", []))
    rows = []
    for comparator_id in runner_config.get("required_final_comparators", []):
        rows.append(
            {
                "comparator_id": comparator_id,
                "status": "final_comparator_outputs_missing",
                "claim_evaluable": False,
                "source_prereg_bundle": str(prereg_bundle),
                "source_prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
                "source_final_split_manifest": str(final_split_run / "final_split_manifest.json"),
                "source_final_feature_manifest": str(final_feature_run / "final_feature_manifest.json"),
                "source_manifest_level_leakage_audit": str(final_leakage_run / "final_leakage_audit.json"),
                "final_fold_logs": "missing",
                "final_logits": "missing",
                "final_subject_level_metrics": "missing",
                "runtime_leakage_logs": "missing",
                "comparator_output_manifest": "missing",
                "missing_outputs": missing,
                "outer_test_subject_policy": artifact_config.get("manifest_schema", {}).get(
                    "outer_test_subject_policy", "no_outer_test_subject_in_any_fit"
                ),
                "test_time_inference_policy": runner_config.get("output_manifest_schema", {}).get(
                    "test_time_inference_policy", "scalp_only"
                ),
                "teacher_or_privileged_test_time_outputs_allowed": False,
                "smoke_metrics_promoted": False,
                "scientific_limit": (
                    f"{comparator_id} final comparator outputs are absent; no metric, logit or claim evidence is recorded."
                ),
            }
        )
    return {
        "status": "phase1_final_comparator_outputs_missing",
        "claim_evaluable": False,
        "all_comparator_output_manifests_present": False,
        "final_comparator_outputs_present": False,
        "runtime_comparator_logs_audited": False,
        "smoke_artifacts_promoted": False,
        "comparators": rows,
        "scientific_limit": "This manifest status records missing final comparator outputs; it does not run comparators.",
    }


def _build_missing_outputs(
    runner_config: dict[str, Any],
    manifest_status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_missing_outputs_recorded",
        "claim_evaluable": False,
        "shared_missing_outputs": runner_config.get("shared_required_outputs", []),
        "per_comparator_missing_outputs": [
            {"comparator_id": row["comparator_id"], "missing_outputs": row["missing_outputs"]}
            for row in manifest_status["comparators"]
        ],
        "blockers": [
            "final_comparator_outputs_missing",
            "runtime_comparator_leakage_logs_missing_until_final_runners_execute",
            "final_comparator_completeness_table_not_claim_evaluable",
        ],
        "scientific_limit": "Missing output inventory is an implementation checklist, not evidence.",
    }


def _build_runtime_leakage_requirements(
    runner_config: dict[str, Any],
    artifact_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_runtime_leakage_requirements_recorded",
        "claim_evaluable": False,
        "fit_scope_rules": runner_config.get("fit_scope_rules", {}),
        "artifact_plan_leakage_requirements": artifact_config.get("leakage_requirements", {}),
        "per_comparator_runtime_logs_required": [
            {
                "comparator_id": comparator_id,
                "runtime_leakage_logs": "missing",
                "must_verify_outer_test_not_used_in_any_fit": True,
                "must_verify_test_time_inference_scalp_only": True,
                "claim_evaluable": False,
            }
            for comparator_id in runner_config.get("required_final_comparators", [])
        ],
        "scientific_limit": "Runtime leakage requirements are recorded; runtime comparator logs are still missing.",
    }


def _build_completeness_table(manifest_status: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in manifest_status["comparators"]:
        rows.append(
            {
                "comparator_id": row["comparator_id"],
                "final_fold_logs_present": False,
                "final_logits_present": False,
                "final_subject_level_metrics_present": False,
                "runtime_leakage_logs_present": False,
                "comparator_output_manifest_present": False,
                "claim_evaluable": False,
                "smoke_metrics_promoted": False,
            }
        )
    return {
        "status": "phase1_final_comparator_completeness_table_not_claim_evaluable",
        "claim_evaluable": False,
        "all_required_outputs_present": False,
        "rows": rows,
        "scientific_limit": "Completeness table contains absence records only; it is not model evidence.",
    }


def _build_claim_state(
    runner_config: dict[str, Any],
    input_validation: dict[str, Any],
    missing_outputs: dict[str, Any],
) -> dict[str, Any]:
    blockers = list(input_validation["blockers"])
    blockers.extend(missing_outputs["blockers"])
    blockers.extend(runner_config.get("claim_blockers_until_outputs_exist", []))
    if runner_config.get("status") != "final_comparator_runner_readiness_locked":
        blockers.append("final_comparator_runner_readiness_config_not_locked")
    return {
        "status": "phase1_final_comparator_runner_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "upstream_manifests_ready": input_validation["status"] == "phase1_final_comparator_runner_inputs_ready",
        "final_comparator_outputs_present": False,
        "runtime_comparator_logs_audited": False,
        "smoke_artifacts_promoted": False,
        "blockers": [item for item in _unique(blockers) if item],
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": (
            "Final split, feature and manifest-level leakage artifacts are linked to a final comparator "
            "output contract, but final comparator outputs and runtime leakage logs are absent."
        ),
    }


def _build_implementation_plan(
    runner_config: dict[str, Any],
    missing_outputs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_comparator_runner_implementation_plan_recorded",
        "ordered_items": [
            {
                "item": "implement_final_feature_matrix_materialization",
                "purpose": "Materialize feature values from the final feature manifest without changing the locked split.",
            },
            {
                "item": "implement_final_comparator_runner_for_each_required_comparator",
                "purpose": "Write final fold logs, logits and subject-level metrics for A2/A2b/A2c/A2d/A3/A4.",
            },
            {
                "item": "write_runtime_leakage_logs_per_comparator",
                "purpose": "Verify every fit stage excludes the outer-test subject and every test-time path is scalp-only.",
            },
            {
                "item": "write_comparator_output_manifest_per_comparator",
                "purpose": "Link final outputs to split, feature, leakage and prereg sources without using smoke artifacts.",
            },
            {
                "item": "promote_downstream_governance_only_after_outputs_exist",
                "purpose": "Feed controls, calibration, influence and reporting only from final outputs, not smoke diagnostics.",
            },
        ],
        "required_final_comparators": runner_config.get("required_final_comparators", []),
        "blocked_by": missing_outputs["blockers"],
        "scientific_integrity_rule": "No final comparator is claim-evaluable until all output and runtime leakage artifacts exist.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    final_feature_run: Path,
    final_leakage_run: Path,
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    split_path = final_split_run / "final_split_manifest.json"
    feature_path = final_feature_run / "final_feature_manifest.json"
    leakage_path = final_leakage_run / "final_leakage_audit.json"
    return {
        "status": "phase1_final_comparator_runner_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_split_manifest": str(split_path),
        "final_split_manifest_sha256": _sha256(split_path),
        "final_feature_run": str(final_feature_run),
        "final_feature_manifest": str(feature_path),
        "final_feature_manifest_sha256": _sha256(feature_path),
        "final_leakage_run": str(final_leakage_run),
        "final_leakage_audit": str(leakage_path),
        "final_leakage_audit_sha256": _sha256(leakage_path),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links document provenance for readiness/output-manifest planning only.",
    }


def _render_report(
    summary: dict[str, Any],
    input_validation: dict[str, Any],
    contract: dict[str, Any],
    manifest_status: dict[str, Any],
    missing_outputs: dict[str, Any],
    runtime_leakage_requirements: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    lines = [
        "# Phase 1 Final Comparator Runner Readiness",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Runner readiness status: `{summary['runner_readiness_status']}`",
        f"- Upstream manifests ready: `{summary['upstream_manifests_ready']}`",
        f"- Final comparator outputs present: `{summary['final_comparator_outputs_present']}`",
        f"- Runtime comparator logs audited: `{summary['runtime_comparator_logs_audited']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        "",
        "## Input Validation",
        "",
        f"- Input validation status: `{input_validation['status']}`",
        f"- Contract matches artifact plan: `{contract['comparator_contract_matches_artifact_plan']}`",
        f"- Output schema matches artifact plan: `{contract['output_schema_matches_artifact_plan']}`",
        "",
        "## Required Final Comparators",
        "",
    ]
    for comparator_id in summary["required_final_comparators"]:
        lines.append(f"- {comparator_id}")
    lines.extend(["", "## Missing Comparator Outputs", ""])
    for row in missing_outputs["per_comparator_missing_outputs"]:
        lines.append(f"- {row['comparator_id']}: `{', '.join(row['missing_outputs'])}`")
    lines.extend(["", "## Runtime Leakage Boundary", ""])
    lines.append(
        f"- Runtime leakage requirements status: `{runtime_leakage_requirements['status']}`"
    )
    lines.append("- Runtime comparator logs are required later; this readiness step does not create them.")
    lines.extend(["", "## Blockers", ""])
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Scientific Integrity", ""])
    lines.append("- This run records output-manifest readiness only.")
    lines.append("- It does not create logits, metrics, fold logs or runtime leakage logs.")
    lines.append("- Smoke artifacts remain non-claim diagnostics and cannot satisfy this contract.")
    lines.extend(["", "## Not OK To Claim", ""])
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
