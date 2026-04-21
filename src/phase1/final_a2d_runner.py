"""Final A2d covariance/tangent runner for Phase 1.

This runner closes the specific A2d missing-output gap left by the
feature-matrix comparator runner. It uses the final feature matrix row index as
the row/provenance contract, extracts scalp covariance matrices from the final
EDF payloads, projects them into a training-only log-Euclidean tangent space,
and writes A2d output manifests and runtime leakage logs. Claims remain closed.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from ..phase05.estimators import Phase05EstimatorError, _optional_signal_imports, _read_edf
from .a2d_smoke import (
    _fit_logistic_np,
    _logeuclidean_reference,
    _sample_weights_np,
    _sigmoid_np,
    _stack_covariances,
    _standardize_np,
    _tangent_project,
)
from .final_feature_matrix import _expected_channels_from_feature_names, _feature_aliases_for_raw_channels
from .model_smoke import _classification_metrics, _mean, _median, _round_or_none
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalA2dRunnerError(RuntimeError):
    """Raised when final A2d runner execution cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalA2dRunnerResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "runner": "configs/phase1/final_a2d_runner.json",
}


def run_phase1_final_a2d_runner(
    *,
    prereg_bundle: str | Path,
    final_split_run: str | Path,
    final_feature_run: str | Path,
    final_leakage_run: str | Path,
    feature_matrix_run: str | Path,
    dataset_root: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
    feature_matrix_comparator_run: str | Path | None = None,
    max_outer_folds: int | None = None,
    precomputed_rows: dict[str, Any] | None = None,
) -> Phase1FinalA2dRunnerResult:
    """Run final claim-closed A2d covariance/tangent outputs."""

    prereg_bundle = Path(prereg_bundle)
    final_split_run = _resolve_run_dir(Path(final_split_run))
    final_feature_run = _resolve_run_dir(Path(final_feature_run))
    final_leakage_run = _resolve_run_dir(Path(final_leakage_run))
    feature_matrix_run = _resolve_run_dir(Path(feature_matrix_run))
    feature_matrix_comparator_run = (
        _resolve_run_dir(Path(feature_matrix_comparator_run)) if feature_matrix_comparator_run is not None else None
    )
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    split = _read_final_split_run(final_split_run)
    feature = _read_final_feature_run(final_feature_run)
    leakage = _read_final_leakage_run(final_leakage_run)
    matrix = _read_feature_matrix_run(feature_matrix_run)
    previous_runner = (
        _read_feature_matrix_comparator_run(feature_matrix_comparator_run)
        if feature_matrix_comparator_run is not None
        else None
    )
    runner_config = load_config(repo_root / config_paths["runner"])

    _validate_final_split_boundary(split)
    _validate_final_feature_boundary(feature)
    _validate_final_leakage_boundary(leakage)
    _validate_feature_matrix_boundary(matrix)
    _validate_source_chain(
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
        final_leakage_run=final_leakage_run,
        split=split,
        matrix=matrix,
        previous_runner=previous_runner,
    )
    _validate_previous_runner_boundary(previous_runner)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    for dirname in ["fold_logs", "final_logits", "final_subject_level_metrics", "runtime_leakage_logs", "comparator_output_manifests"]:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)

    input_validation = _validate_inputs(
        split=split,
        feature=feature,
        leakage=leakage,
        matrix=matrix,
        previous_runner=previous_runner,
        dataset_root=dataset_root,
        runner_config=runner_config,
        precomputed_rows=precomputed_rows,
        max_outer_folds=max_outer_folds,
    )
    extracted = _extract_or_block(
        dataset_root=dataset_root,
        feature=feature,
        matrix=matrix,
        runner_config=runner_config,
        precomputed_rows=precomputed_rows,
    )
    covariance_validation = _validate_covariance_rows(
        extracted=extracted,
        split=split,
        matrix=matrix,
        input_blockers=input_validation["blockers"],
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
        final_leakage_run=final_leakage_run,
        feature_matrix_run=feature_matrix_run,
        feature_matrix_comparator_run=feature_matrix_comparator_run,
        config_paths=config_paths,
        repo_root=repo_root,
    )
    inputs = {
        "status": "phase1_final_a2d_runner_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_feature_run": str(final_feature_run),
        "final_leakage_run": str(final_leakage_run),
        "feature_matrix_run": str(feature_matrix_run),
        "feature_matrix_comparator_run": str(feature_matrix_comparator_run) if feature_matrix_comparator_run else None,
        "dataset_root": str(dataset_root),
        "config_paths": config_paths,
        "max_outer_folds": max_outer_folds,
        "precomputed_rows_used": precomputed_rows is not None,
        "git": _git_record(repo_root),
    }

    if covariance_validation["covariance_rows_ready"]:
        fold_specs = _selected_folds(split["manifest"], max_outer_folds)
        run_outputs = _run_a2d_outputs(
            output_dir=output_dir,
            rows=extracted["rows"],
            fold_specs=fold_specs,
            runner_config=runner_config,
        )
    else:
        fold_specs = []
        run_outputs = _blocked_outputs(output_dir, covariance_validation)

    covariance_manifest = _build_covariance_manifest(extracted, covariance_validation, runner_config)
    tangent_manifest = _build_tangent_manifest(run_outputs, covariance_manifest, runner_config)
    claim_state = _build_claim_state(covariance_validation, run_outputs, runner_config)
    reconciliation = _build_reconciliation_patch(previous_runner, run_outputs, claim_state)
    summary = _build_summary(
        output_dir=output_dir,
        inputs=inputs,
        extracted=extracted,
        covariance_validation=covariance_validation,
        fold_specs=fold_specs,
        run_outputs=run_outputs,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_a2d_runner_inputs.json"
    summary_path = output_dir / "phase1_final_a2d_runner_summary.json"
    report_path = output_dir / "phase1_final_a2d_runner_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_a2d_runner_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_a2d_runner_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_a2d_covariance_validation.json", covariance_validation)
    _write_json(output_dir / "a2d_final_covariance_manifest.json", covariance_manifest)
    _write_json(output_dir / "a2d_final_tangent_manifest.json", tangent_manifest)
    _write_json(output_dir / "phase1_final_a2d_completeness_patch.json", reconciliation)
    _write_json(output_dir / "phase1_final_a2d_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, covariance_validation, run_outputs, claim_state, reconciliation),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalA2dRunnerResult(
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
    return _read_required_files(
        run_dir,
        {
            "summary": "phase1_final_split_manifest_summary.json",
            "manifest": "final_split_manifest.json",
            "validation": "phase1_final_split_manifest_validation.json",
            "claim_state": "phase1_final_split_manifest_claim_state.json",
        },
        "Final split manifest",
    )


def _read_final_feature_run(run_dir: Path) -> dict[str, Any]:
    return _read_required_files(
        run_dir,
        {
            "summary": "phase1_final_feature_manifest_summary.json",
            "manifest": "final_feature_manifest.json",
            "validation": "phase1_final_feature_manifest_validation.json",
            "claim_state": "phase1_final_feature_manifest_claim_state.json",
        },
        "Final feature manifest",
    )


def _read_final_leakage_run(run_dir: Path) -> dict[str, Any]:
    return _read_required_files(
        run_dir,
        {
            "summary": "phase1_final_leakage_audit_summary.json",
            "audit": "final_leakage_audit.json",
            "validation": "phase1_final_leakage_audit_validation.json",
            "claim_state": "phase1_final_leakage_audit_claim_state.json",
        },
        "Final leakage audit",
    )


def _read_feature_matrix_run(run_dir: Path) -> dict[str, Any]:
    payload = _read_required_files(
        run_dir,
        {
            "summary": "phase1_final_feature_matrix_summary.json",
            "validation": "phase1_final_feature_matrix_validation.json",
            "schema": "phase1_final_feature_matrix_schema.json",
            "row_index": "final_feature_row_index.json",
            "source_links": "phase1_final_feature_matrix_source_links.json",
            "claim_state": "phase1_final_feature_matrix_claim_state.json",
        },
        "Final feature matrix",
    )
    payload["run_dir"] = run_dir
    return payload


def _read_feature_matrix_comparator_run(run_dir: Path) -> dict[str, Any]:
    payload = _read_required_files(
        run_dir,
        {
            "summary": "phase1_final_comparator_runner_summary.json",
            "claim_state": "phase1_final_comparator_runner_claim_state.json",
            "completeness": "phase1_final_comparator_completeness_table.json",
        },
        "Feature-matrix final comparator runner",
    )
    payload["run_dir"] = run_dir
    return payload


def _read_required_files(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalA2dRunnerError(f"{label} file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_final_split_boundary(split: dict[str, Any]) -> None:
    if split["summary"].get("status") != "phase1_final_split_manifest_recorded":
        raise Phase1FinalA2dRunnerError("Final A2d requires a recorded final split manifest")
    if split["summary"].get("split_manifest_ready") is not True:
        raise Phase1FinalA2dRunnerError("Final split manifest must be ready")
    if split["validation"].get("status") != "phase1_final_split_manifest_validation_passed":
        raise Phase1FinalA2dRunnerError("Final split manifest validation must pass")
    if split["validation"].get("no_subject_overlap_between_train_and_test") is not True:
        raise Phase1FinalA2dRunnerError("Final split manifest must have no train/test subject overlap")
    if split["manifest"].get("claim_ready") is not False or split["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalA2dRunnerError("Final split manifest must keep claim_ready=false")
    if split["manifest"].get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalA2dRunnerError("Final split manifest must not promote smoke artifacts")


def _validate_final_feature_boundary(feature: dict[str, Any]) -> None:
    if feature["summary"].get("status") != "phase1_final_feature_manifest_recorded":
        raise Phase1FinalA2dRunnerError("Final A2d requires a recorded final feature manifest")
    if feature["summary"].get("feature_manifest_ready") is not True:
        raise Phase1FinalA2dRunnerError("Final feature manifest must be ready")
    if feature["validation"].get("status") != "phase1_final_feature_manifest_validation_passed":
        raise Phase1FinalA2dRunnerError("Final feature manifest validation must pass")
    manifest = feature["manifest"]
    for key in ["contains_model_outputs", "contains_metrics"]:
        if manifest.get(key) is not False:
            raise Phase1FinalA2dRunnerError(f"Final feature manifest must not contain {key}")
    if manifest.get("claim_ready") is not False or feature["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalA2dRunnerError("Final feature manifest must keep claim_ready=false")


def _validate_final_leakage_boundary(leakage: dict[str, Any]) -> None:
    if leakage["summary"].get("status") != "phase1_final_leakage_audit_recorded":
        raise Phase1FinalA2dRunnerError("Final A2d requires a recorded final leakage audit")
    if leakage["summary"].get("leakage_audit_ready") is not True:
        raise Phase1FinalA2dRunnerError("Final leakage audit must be ready")
    if leakage["validation"].get("status") != "phase1_final_leakage_audit_validation_passed":
        raise Phase1FinalA2dRunnerError("Final leakage audit validation must pass")
    if leakage["audit"].get("outer_test_subject_used_in_any_fit") is not False:
        raise Phase1FinalA2dRunnerError("Manifest-level leakage audit found outer-test subject in fit")
    if leakage["audit"].get("test_time_privileged_or_teacher_outputs_allowed") is not False:
        raise Phase1FinalA2dRunnerError("Manifest-level leakage audit must disallow test-time privileged/teacher outputs")
    if leakage["audit"].get("runtime_comparator_logs_audited") is not False:
        raise Phase1FinalA2dRunnerError("Final A2d runner expects runtime audit to be pending before execution")
    if leakage["audit"].get("claim_ready") is not False or leakage["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalA2dRunnerError("Final leakage audit must keep claim_ready=false")


def _validate_feature_matrix_boundary(matrix: dict[str, Any]) -> None:
    if matrix["summary"].get("status") != "phase1_final_feature_matrix_materialized":
        raise Phase1FinalA2dRunnerError("Final A2d requires a materialized final feature matrix row contract")
    if matrix["summary"].get("feature_matrix_ready") is not True:
        raise Phase1FinalA2dRunnerError("Final feature matrix must be ready")
    if matrix["validation"].get("status") != "phase1_final_feature_matrix_validation_passed":
        raise Phase1FinalA2dRunnerError("Final feature matrix validation must pass")
    for key in ["contains_model_outputs", "contains_logits", "contains_metrics"]:
        if matrix["summary"].get(key) is not False or matrix["schema"].get(key) is not False:
            raise Phase1FinalA2dRunnerError(f"Final feature matrix must not contain {key}")
    if matrix["row_index"].get("status") != "phase1_final_feature_row_index_recorded":
        raise Phase1FinalA2dRunnerError("Final feature row index must be recorded")
    if matrix["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalA2dRunnerError("Final feature matrix must keep claim_ready=false")


def _validate_source_chain(
    *,
    final_split_run: Path,
    final_feature_run: Path,
    final_leakage_run: Path,
    split: dict[str, Any],
    matrix: dict[str, Any],
    previous_runner: dict[str, Any] | None,
) -> None:
    source = matrix["source_links"]
    expected = {
        "final_split_manifest": final_split_run / "final_split_manifest.json",
        "final_feature_manifest": final_feature_run / "final_feature_manifest.json",
        "final_leakage_audit": final_leakage_run / "final_leakage_audit.json",
    }
    for key, path in expected.items():
        linked = source.get(key)
        if linked and _path_key(linked) != _path_key(path):
            raise Phase1FinalA2dRunnerError(f"Feature matrix source link {key} does not match selected run")
    feature_run = matrix["summary"].get("final_feature_run")
    if feature_run and _path_key(feature_run) != _path_key(final_feature_run):
        raise Phase1FinalA2dRunnerError("Feature matrix summary final_feature_run does not match selected run")
    if split["manifest"].get("split_id") != "loso_subject":
        raise Phase1FinalA2dRunnerError("Final A2d currently requires LOSO subject split")
    if previous_runner is not None:
        previous_matrix_run = previous_runner["summary"].get("feature_matrix_run")
        if previous_matrix_run and _path_key(previous_matrix_run) != _path_key(matrix["run_dir"]):
            raise Phase1FinalA2dRunnerError("Previous feature-matrix comparator run uses a different feature matrix")


def _validate_previous_runner_boundary(previous_runner: dict[str, Any] | None) -> None:
    if previous_runner is None:
        return
    summary = previous_runner["summary"]
    if summary.get("claim_ready") is not False:
        raise Phase1FinalA2dRunnerError("Previous comparator runner must keep claim_ready=false")
    if "A2d_riemannian" not in summary.get("blocked_comparators", []):
        raise Phase1FinalA2dRunnerError("Previous comparator runner does not record A2d as blocked")


def _validate_inputs(
    *,
    split: dict[str, Any],
    feature: dict[str, Any],
    leakage: dict[str, Any],
    matrix: dict[str, Any],
    previous_runner: dict[str, Any] | None,
    dataset_root: Path,
    runner_config: dict[str, Any],
    precomputed_rows: dict[str, Any] | None,
    max_outer_folds: int | None,
) -> dict[str, Any]:
    observed = {
        "final_split_manifest_ready": split["summary"].get("split_manifest_ready"),
        "final_feature_manifest_ready": feature["summary"].get("feature_manifest_ready"),
        "final_leakage_audit_ready": leakage["summary"].get("leakage_audit_ready"),
        "final_feature_matrix_ready": matrix["summary"].get("feature_matrix_ready"),
        "feature_matrix_contains_model_outputs": matrix["summary"].get("contains_model_outputs"),
        "feature_matrix_contains_logits": matrix["summary"].get("contains_logits"),
        "feature_matrix_contains_metrics": matrix["summary"].get("contains_metrics"),
        "manifest_level_outer_test_subject_used_in_any_fit": leakage["audit"].get("outer_test_subject_used_in_any_fit"),
        "manifest_level_runtime_comparator_logs_audited": leakage["audit"].get("runtime_comparator_logs_audited"),
        "smoke_artifacts_promoted": bool(
            split["manifest"].get("smoke_artifacts_promoted")
            or feature["manifest"].get("smoke_feature_rows_allowed_as_final")
            or (previous_runner or {}).get("summary", {}).get("smoke_artifacts_promoted")
        ),
    }
    blockers = [
        f"{key}_mismatch"
        for key, expected in runner_config.get("required_inputs", {}).items()
        if observed.get(key) is not expected
    ]
    expected_subjects = sorted(split["manifest"].get("eligible_subjects", []))
    row_subjects = sorted({row.get("participant_id") for row in matrix["row_index"].get("rows", [])})
    if row_subjects != expected_subjects:
        blockers.append("feature_matrix_row_subjects_do_not_match_split_manifest")
    if not dataset_root.exists() and precomputed_rows is None:
        blockers.append("dataset_root_missing")
    channels = _expected_channels_from_feature_names(list(feature["manifest"].get("feature_names", [])))
    if len(channels) < 2:
        blockers.append("fewer_than_two_final_scalp_channels_for_covariance")
    if max_outer_folds is not None and max_outer_folds < len(split["manifest"].get("folds", [])):
        blockers.append("bounded_fold_subset_not_full_final_run")
    return {
        "status": "phase1_final_a2d_runner_inputs_ready" if not blockers else "phase1_final_a2d_runner_inputs_blocked",
        "observed": observed,
        "required": runner_config.get("required_inputs", {}),
        "dataset_root": str(dataset_root),
        "precomputed_rows_used": precomputed_rows is not None,
        "expected_subjects": expected_subjects,
        "row_subjects": row_subjects,
        "final_covariance_channels": channels,
        "n_row_index_rows": len(matrix["row_index"].get("rows", [])),
        "max_outer_folds": max_outer_folds,
        "previous_runner_linked": previous_runner is not None,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks final A2d prerequisites only; it is not model evidence.",
    }


def _extract_or_block(
    *,
    dataset_root: Path,
    feature: dict[str, Any],
    matrix: dict[str, Any],
    runner_config: dict[str, Any],
    precomputed_rows: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        if precomputed_rows is not None:
            return _coerce_precomputed_rows(precomputed_rows)
        return _extract_covariances_from_final_rows(dataset_root, feature, matrix, runner_config)
    except (Phase05EstimatorError, Phase1FinalA2dRunnerError, FileNotFoundError, ModuleNotFoundError) as exc:
        return {
            "status": "phase1_final_a2d_covariance_extraction_blocked",
            "rows": [],
            "subjects": [],
            "sessions": [],
            "channel_names": [],
            "skipped_sessions": [{"reason": str(exc)}],
            "read_fallbacks": [],
            "invalid_window_rows": [],
            "missing_source_channels": [],
            "nonfinite_signal_rows": [],
            "blockers": ["a2d_covariance_extraction_failed"],
            "error": str(exc),
        }


def _coerce_precomputed_rows(precomputed_rows: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for index, row in enumerate(precomputed_rows.get("rows", []), start=1):
        rows.append(
            {
                "row_id": str(row.get("row_id") or f"row_{index:06d}"),
                "subject": str(row.get("subject") or row.get("participant_id")),
                "session": str(row.get("session") or row.get("session_id")),
                "trial_id": str(row.get("trial_id", index)),
                "set_size": int(row.get("set_size", 8 if int(row["label"]) else 4)),
                "label": int(row["label"]),
                "event_onset_sample": int(row.get("event_onset_sample", 0)),
                "source_eeg_file": str(row.get("source_eeg_file", "precomputed")),
                "covariance": row["covariance"],
                "channel_names": list(row.get("channel_names", ["C1", "C2"])),
            }
        )
    return _finalize_extracted_rows(
        rows=rows,
        skipped_sessions=[],
        read_fallbacks=[],
        invalid_window_rows=[],
        missing_source_channels=[],
        nonfinite_signal_rows=[],
        source="precomputed_rows_test_fixture",
    )


def _extract_covariances_from_final_rows(
    dataset_root: Path,
    feature: dict[str, Any],
    matrix: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    np, mne = _optional_signal_imports()
    feature_manifest = feature["manifest"]
    expected_channels = _expected_channels_from_feature_names(list(feature_manifest.get("feature_names", [])))
    task_window = tuple(feature_manifest.get("signal_windows_sec", {}).get("task_maintenance") or runner_config["signal_windows_sec"]["task_maintenance"])
    if len(task_window) != 2:
        raise Phase1FinalA2dRunnerError("Final feature manifest must define task_maintenance signal window")
    min_window_samples = int(runner_config["covariance"].get("min_window_samples", 8))
    row_index = list(matrix["row_index"].get("rows", []))
    if not row_index:
        raise Phase1FinalA2dRunnerError("Final feature row index is empty")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in row_index:
        source = str(row.get("source_eeg_file", ""))
        grouped.setdefault(source, []).append(row)

    rows = []
    skipped_sessions = []
    read_fallbacks = []
    invalid_window_rows = []
    missing_source_channels = []
    nonfinite_signal_rows = []
    for source_eeg_file, source_rows in sorted(grouped.items()):
        eeg_path = Path(source_eeg_file)
        if not eeg_path.is_absolute():
            eeg_path = dataset_root / source_eeg_file
        if not eeg_path.exists():
            skipped_sessions.append({"source_eeg_file": source_eeg_file, "reason": "missing_eeg_file"})
            continue
        try:
            raw = _read_edf(mne, eeg_path)
        except Phase05EstimatorError as exc:
            skipped_sessions.append({"source_eeg_file": source_eeg_file, "reason": str(exc)})
            continue
        fallback = getattr(raw, "_phase05_read_fallback", None)
        if fallback:
            read_fallbacks.append({"source_eeg_file": source_eeg_file, "modality": "eeg", **fallback})
        data = raw.get_data()
        sfreq = float(raw.info["sfreq"])
        raw_channels = [str(name) for name in raw.ch_names]
        aliases = _feature_aliases_for_raw_channels(expected_channels, raw_channels)
        missing = [channel for channel, raw_channel in aliases.items() if raw_channel is None]
        if missing:
            for row in source_rows:
                missing_source_channels.append(
                    {
                        "row_id": row.get("row_id"),
                        "participant_id": row.get("participant_id"),
                        "session_id": row.get("session_id"),
                        "source_eeg_file": source_eeg_file,
                        "missing_channels": missing,
                    }
                )
            continue
        raw_index_by_channel = {name: idx for idx, name in enumerate(raw_channels)}
        channel_indices = [raw_index_by_channel[str(aliases[channel])] for channel in expected_channels]
        for row in source_rows:
            trial_start = int(row.get("event_onset_sample", 0))
            start = trial_start + int(round(float(task_window[0]) * sfreq))
            stop = min(trial_start + int(round(float(task_window[1]) * sfreq)), int(data.shape[1]))
            if stop <= start or stop - start < min_window_samples:
                invalid_window_rows.append(
                    {
                        "row_id": row.get("row_id"),
                        "participant_id": row.get("participant_id"),
                        "session_id": row.get("session_id"),
                        "trial_id": row.get("trial_id"),
                        "event_onset_sample": trial_start,
                        "window_start_sample": start,
                        "window_stop_sample": stop,
                        "data_n_samples": int(data.shape[1]),
                    }
                )
                continue
            segment = data[channel_indices, start:stop]
            if not bool(np.isfinite(segment).all()):
                nonfinite_signal_rows.append(
                    {
                        "row_id": row.get("row_id"),
                        "participant_id": row.get("participant_id"),
                        "session_id": row.get("session_id"),
                        "trial_id": row.get("trial_id"),
                        "source_eeg_file": source_eeg_file,
                    }
                )
                continue
            cov = np.cov(segment)
            rows.append(
                {
                    "row_id": str(row.get("row_id")),
                    "subject": str(row.get("participant_id")),
                    "session": str(row.get("session_id")),
                    "trial_id": str(row.get("trial_id")),
                    "set_size": int(row.get("set_size")),
                    "label": int(row.get("label")),
                    "event_onset_sample": trial_start,
                    "source_eeg_file": source_eeg_file,
                    "covariance": cov.tolist(),
                    "channel_names": expected_channels,
                }
            )
    return _finalize_extracted_rows(
        rows=rows,
        skipped_sessions=skipped_sessions,
        read_fallbacks=read_fallbacks,
        invalid_window_rows=invalid_window_rows,
        missing_source_channels=missing_source_channels,
        nonfinite_signal_rows=nonfinite_signal_rows,
        source="final_row_index_edf_covariance_extraction",
    )


def _finalize_extracted_rows(
    *,
    rows: list[dict[str, Any]],
    skipped_sessions: list[dict[str, Any]],
    read_fallbacks: list[dict[str, Any]],
    invalid_window_rows: list[dict[str, Any]],
    missing_source_channels: list[dict[str, Any]],
    nonfinite_signal_rows: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    return {
        "status": "phase1_final_a2d_covariance_rows_extracted",
        "source": source,
        "rows": rows,
        "subjects": sorted({row["subject"] for row in rows}),
        "sessions": sorted({f"{row['subject']}/{row['session']}" for row in rows}),
        "channel_names": list(rows[0]["channel_names"]) if rows else [],
        "skipped_sessions": skipped_sessions,
        "read_fallbacks": read_fallbacks,
        "invalid_window_rows": invalid_window_rows,
        "missing_source_channels": missing_source_channels,
        "nonfinite_signal_rows": nonfinite_signal_rows,
        "blockers": [],
    }


def _validate_covariance_rows(
    *,
    extracted: dict[str, Any],
    split: dict[str, Any],
    matrix: dict[str, Any],
    input_blockers: list[str],
) -> dict[str, Any]:
    rows = extracted.get("rows", [])
    blockers = list(input_blockers) + list(extracted.get("blockers", []))
    expected_rows = int(matrix["summary"].get("n_rows", 0))
    expected_subjects = sorted(split["manifest"].get("eligible_subjects", []))
    subjects = sorted({row.get("subject") for row in rows})
    shapes = sorted({f"{len(row['covariance'])}x{len(row['covariance'][0])}" for row in rows if row.get("covariance")})
    labels = sorted({int(row.get("label")) for row in rows}) if rows else []
    nonfinite_covariance_count = 0
    bad_shape_count = 0
    for row in rows:
        cov = row.get("covariance", [])
        if not cov or len(cov) != len(cov[0]):
            bad_shape_count += 1
            continue
        for cov_row in cov:
            for value in cov_row:
                if not math.isfinite(float(value)):
                    nonfinite_covariance_count += 1
    if len(rows) != expected_rows:
        blockers.append("a2d_covariance_row_count_does_not_match_final_feature_matrix")
    if subjects != expected_subjects:
        blockers.append("a2d_covariance_subjects_do_not_match_split_manifest")
    if labels != [0, 1]:
        blockers.append("a2d_covariance_rows_do_not_contain_both_binary_classes")
    if bad_shape_count:
        blockers.append("a2d_covariance_matrices_not_square")
    if nonfinite_covariance_count:
        blockers.append("a2d_covariance_nonfinite_values_present")
    if extracted.get("skipped_sessions"):
        blockers.append("a2d_covariance_source_sessions_skipped")
    if extracted.get("invalid_window_rows"):
        blockers.append("a2d_covariance_invalid_windows_present")
    if extracted.get("missing_source_channels"):
        blockers.append("a2d_covariance_source_channels_missing")
    if extracted.get("nonfinite_signal_rows"):
        blockers.append("a2d_covariance_nonfinite_signal_rows_present")
    if not rows:
        blockers.append("no_a2d_covariance_rows_extracted")
    return {
        "status": "phase1_final_a2d_covariance_validation_passed" if not blockers else "phase1_final_a2d_covariance_validation_blocked",
        "covariance_rows_ready": not blockers,
        "n_rows": len(rows),
        "n_expected_rows": expected_rows,
        "subjects": subjects,
        "expected_subjects": expected_subjects,
        "labels": labels,
        "matrix_shapes": shapes,
        "channel_names": extracted.get("channel_names", []),
        "skipped_sessions_count": len(extracted.get("skipped_sessions", [])),
        "read_fallbacks_count": len(extracted.get("read_fallbacks", [])),
        "invalid_window_rows_count": len(extracted.get("invalid_window_rows", [])),
        "missing_source_channels_count": len(extracted.get("missing_source_channels", [])),
        "nonfinite_signal_rows_count": len(extracted.get("nonfinite_signal_rows", [])),
        "nonfinite_covariance_values": nonfinite_covariance_count,
        "blockers": _unique(blockers),
        "scientific_limit": "Covariance validation checks A2d input materialization only; it is not model evidence.",
    }


def _selected_folds(split_manifest: dict[str, Any], max_outer_folds: int | None) -> list[dict[str, Any]]:
    folds = list(split_manifest.get("folds", []))
    if max_outer_folds is not None:
        folds = folds[:max_outer_folds]
    if not folds:
        raise Phase1FinalA2dRunnerError("No final LOSO folds available")
    return folds


def _run_a2d_outputs(
    *,
    output_dir: Path,
    rows: list[dict[str, Any]],
    fold_specs: list[dict[str, Any]],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    fold_logs = []
    fold_metrics = []
    all_logits = []
    for fold in fold_specs:
        fold_result = _run_a2d_fold(rows=rows, fold=fold, runner_config=runner_config)
        fold_logs.append(fold_result["fold_log"])
        fold_metrics.append(fold_result["metrics"])
        all_logits.extend(fold_result["logits"])
        _write_json(output_dir / "fold_logs" / f"{fold_result['fold_log']['fold_id']}.json", fold_result["fold_log"])

    metric_summary = {
        "status": "phase1_final_a2d_subject_metrics_recorded",
        "comparator_id": "A2d_riemannian",
        "n_folds": len(fold_metrics),
        "median_balanced_accuracy": _median([row["balanced_accuracy"] for row in fold_metrics]),
        "mean_ece_10_bins": _mean([row["ece_10_bins"] for row in fold_metrics]),
        "mean_brier": _mean([row["brier"] for row in fold_metrics]),
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": "A2d final-runner diagnostics only; not standalone efficacy evidence.",
        "folds": fold_metrics,
    }
    logits_payload = {
        "status": "phase1_final_a2d_logits_recorded",
        "comparator_id": "A2d_riemannian",
        "n_rows": len(all_logits),
        "contains_covariance_values": False,
        "contains_tangent_features": False,
        "claim_ready": False,
        "claim_evaluable": False,
        "rows": all_logits,
        "scientific_limit": "Logits are comparator outputs only; claims remain closed until the full package passes.",
    }
    leakage = _runtime_leakage_audit(fold_logs)
    output_manifest = {
        "status": "phase1_final_a2d_output_manifest_recorded",
        "comparator_id": "A2d_riemannian",
        "claim_ready": False,
        "claim_evaluable": False,
        "smoke_artifacts_promoted": False,
        "n_folds": len(fold_logs),
        "n_logit_rows": len(all_logits),
        "runtime_leakage_passed": leakage["outer_test_subject_used_for_any_fit"] is False,
        "files": {
            "logits": "final_logits/A2d_riemannian_final_logits.json",
            "subject_level_metrics": "final_subject_level_metrics/A2d_riemannian_subject_level_metrics.json",
            "runtime_leakage_audit": "runtime_leakage_logs/A2d_riemannian_runtime_leakage_audit.json",
            "fold_logs_dir": "fold_logs",
            "covariance_manifest": "a2d_final_covariance_manifest.json",
            "tangent_manifest": "a2d_final_tangent_manifest.json",
        },
        "scientific_limit": "A2d output manifest records files only; it is not by itself claim evidence.",
    }
    _write_json(output_dir / "final_logits" / "A2d_riemannian_final_logits.json", logits_payload)
    _write_json(output_dir / "final_subject_level_metrics" / "A2d_riemannian_subject_level_metrics.json", metric_summary)
    _write_json(output_dir / "runtime_leakage_logs" / "A2d_riemannian_runtime_leakage_audit.json", leakage)
    _write_json(output_dir / "comparator_output_manifests" / "A2d_riemannian_output_manifest.json", output_manifest)
    return {
        "status": "phase1_final_a2d_outputs_recorded",
        "completed": True,
        "fold_logs": fold_logs,
        "metrics_summary": metric_summary,
        "logits": logits_payload,
        "runtime_leakage": leakage,
        "output_manifest": output_manifest,
        "blockers": [],
    }


def _run_a2d_fold(*, rows: list[dict[str, Any]], fold: dict[str, Any], runner_config: dict[str, Any]) -> dict[str, Any]:
    np = _numpy()
    fold_id = str(fold.get("fold_id"))
    outer_subject = str(fold.get("outer_test_subject") or fold.get("test_subjects", [""])[0])
    train_subjects = set(str(value) for value in fold.get("train_subjects", []))
    test_subjects = set(str(value) for value in fold.get("test_subjects", [outer_subject]))
    train_rows = [row for row in rows if row["subject"] in train_subjects]
    test_rows = [row for row in rows if row["subject"] in test_subjects]
    if not train_rows or not test_rows:
        raise Phase1FinalA2dRunnerError(f"Fold {fold_id} has empty train/test covariance rows")
    _validate_binary_classes(train_rows, f"training fold {fold_id}")
    _validate_binary_classes(test_rows, f"outer-test fold {fold_id}")

    train_cov = _stack_covariances(train_rows)
    test_cov = _stack_covariances(test_rows)
    reference = _logeuclidean_reference(train_cov, runner_config)
    x_train = _tangent_project(train_cov, reference, runner_config)
    x_test = _tangent_project(test_cov, reference, runner_config)
    x_train, x_test = _standardize_np(x_train, x_test)
    y_train = np.asarray([float(row["label"]) for row in train_rows], dtype=float)
    y_test = [float(row["label"]) for row in test_rows]
    weights = _sample_weights_np(train_rows, bool(runner_config["logistic_probe"].get("subject_balanced", True)))
    model = _fit_logistic_np(x_train, y_train, weights, runner_config["logistic_probe"])
    prob_arr = _sigmoid_np(x_test @ model["coef"] + model["intercept"])
    prob = [float(value) for value in prob_arr.tolist()]
    pred = [1 if value >= 0.5 else 0 for value in prob]
    metrics = _classification_metrics(y_test, prob, pred)
    metrics.update(
        {
            "comparator_id": "A2d_riemannian",
            "fold_id": fold_id,
            "outer_test_subject": outer_subject,
            "n_train_rows": len(train_rows),
            "n_test_rows": len(test_rows),
            "n_tangent_features": int(x_train.shape[1]),
            "claim_ready": False,
            "claim_evaluable": False,
            "scientific_limit": "A2d fold diagnostic only; not standalone Phase 1 evidence.",
        }
    )
    logits = [
        {
            "row_id": row["row_id"],
            "participant_id": row["subject"],
            "session_id": row["session"],
            "trial_id": row["trial_id"],
            "outer_test_subject": outer_subject,
            "y_true": int(row["label"]),
            "prob_load8": round(float(value), 8),
            "y_pred": int(guess),
        }
        for row, value, guess in zip(test_rows, prob, pred)
    ]
    fold_log = {
        "status": "phase1_final_a2d_fold_complete",
        "fold_id": fold_id,
        "comparator_id": "A2d_riemannian",
        "outer_test_subject": outer_subject,
        "train_subjects": sorted(train_subjects),
        "test_subjects": sorted(test_subjects),
        "no_outer_test_subject_in_any_fit": outer_subject not in train_subjects,
        "covariance_reference_fit_subjects": sorted(train_subjects),
        "tangent_reference_fit_subjects": sorted(train_subjects),
        "normalization_fit_subjects": sorted(train_subjects),
        "classifier_fit_subjects": sorted(train_subjects),
        "calibration_fit_subjects": [],
        "outer_test_subject_used_for_covariance_reference_fit": outer_subject in train_subjects,
        "outer_test_subject_used_for_tangent_reference_fit": outer_subject in train_subjects,
        "outer_test_subject_used_for_normalization_fit": outer_subject in train_subjects,
        "outer_test_subject_used_for_classifier_fit": outer_subject in train_subjects,
        "outer_test_subject_used_for_calibration_fit": False,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "student_inference_uses_scalp_only": True,
        "training_policy": "training_subjects_only_logeuclidean_tangent_l2_logistic_probe",
        "n_tangent_features": int(x_train.shape[1]),
        "reference_matrix_trace": _round_or_none(float(np.trace(reference))),
        "metrics": metrics,
        "logit_rows": len(logits),
        "claim_ready": False,
        "claim_evaluable": False,
    }
    return {"fold_log": fold_log, "metrics": metrics, "logits": logits}


def _validate_binary_classes(rows: list[dict[str, Any]], label: str) -> None:
    labels = {int(row["label"]) for row in rows}
    if labels != {0, 1}:
        raise Phase1FinalA2dRunnerError(f"A2d final runner requires both load classes in {label}; got {sorted(labels)}")


def _runtime_leakage_audit(fold_logs: list[dict[str, Any]]) -> dict[str, Any]:
    outer_used = any(
        not fold.get("no_outer_test_subject_in_any_fit")
        or fold.get("outer_test_subject_used_for_covariance_reference_fit")
        or fold.get("outer_test_subject_used_for_tangent_reference_fit")
        or fold.get("outer_test_subject_used_for_normalization_fit")
        or fold.get("outer_test_subject_used_for_classifier_fit")
        or fold.get("outer_test_subject_used_for_calibration_fit")
        for fold in fold_logs
    )
    return {
        "status": "phase1_final_a2d_runtime_leakage_audit_passed" if not outer_used else "phase1_final_a2d_runtime_leakage_audit_blocked",
        "comparator_id": "A2d_riemannian",
        "claim_ready": False,
        "claim_evaluable": False,
        "n_folds": len(fold_logs),
        "outer_test_subject_used_for_any_fit": outer_used,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "folds": [
            {
                "fold_id": fold["fold_id"],
                "outer_test_subject": fold["outer_test_subject"],
                "no_outer_test_subject_in_any_fit": fold["no_outer_test_subject_in_any_fit"],
                "student_inference_uses_scalp_only": fold["student_inference_uses_scalp_only"],
            }
            for fold in fold_logs
        ],
        "scientific_limit": "Runtime leakage audit covers final A2d runner logs only; it is not efficacy evidence.",
    }


def _blocked_outputs(output_dir: Path, covariance_validation: dict[str, Any]) -> dict[str, Any]:
    record = {
        "status": "phase1_final_a2d_outputs_blocked",
        "completed": False,
        "comparator_id": "A2d_riemannian",
        "claim_ready": False,
        "claim_evaluable": False,
        "smoke_artifacts_promoted": False,
        "blockers": list(covariance_validation.get("blockers", [])),
        "scientific_limit": "Final A2d outputs were not written because covariance validation did not pass.",
    }
    _write_json(output_dir / "phase1_final_a2d_runner_blocked.json", record)
    return record


def _build_covariance_manifest(
    extracted: dict[str, Any],
    covariance_validation: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_a2d_covariance_manifest_recorded"
        if covariance_validation["covariance_rows_ready"]
        else "phase1_final_a2d_covariance_manifest_blocked",
        "backend": runner_config.get("backend"),
        "n_rows": covariance_validation.get("n_rows"),
        "subjects": covariance_validation.get("subjects"),
        "sessions": extracted.get("sessions", []),
        "channel_names": covariance_validation.get("channel_names"),
        "matrix_shapes": covariance_validation.get("matrix_shapes"),
        "contains_covariance_values": False,
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "invalid_window_rows": extracted.get("invalid_window_rows", [])[:100],
        "missing_source_channels": extracted.get("missing_source_channels", [])[:100],
        "nonfinite_signal_rows": extracted.get("nonfinite_signal_rows", [])[:100],
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": "Covariance manifest records provenance and shape only; it does not store covariance matrices or prove efficacy.",
    }


def _build_tangent_manifest(
    run_outputs: dict[str, Any],
    covariance_manifest: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    tangent_features = None
    if run_outputs.get("completed") and run_outputs.get("fold_logs"):
        tangent_features = run_outputs["fold_logs"][0].get("n_tangent_features")
    return {
        "status": "phase1_final_a2d_tangent_manifest_recorded" if run_outputs.get("completed") else "phase1_final_a2d_tangent_manifest_blocked",
        "backend": runner_config.get("backend"),
        "comparator_id": "A2d_riemannian",
        "n_channels": len(covariance_manifest.get("channel_names") or []),
        "n_tangent_features": tangent_features,
        "contains_tangent_values": False,
        "reference_fit_scope": "training_subjects_only_per_fold",
        "normalization_fit_scope": "training_subjects_only_per_fold",
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": "Tangent manifest records projection contract only; it is not model evidence.",
    }


def _build_claim_state(
    covariance_validation: dict[str, Any],
    run_outputs: dict[str, Any],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = list(covariance_validation.get("blockers", []))
    if run_outputs.get("completed"):
        blockers.extend(runner_config.get("claim_blockers_after_success", []))
    else:
        blockers.append("A2d_riemannian_final_outputs_missing_or_blocked")
    return {
        "status": "phase1_final_a2d_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "a2d_final_output_present": bool(run_outputs.get("completed")),
        "smoke_artifacts_promoted": False,
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A2d final comparator efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "scientific_limit": "A2d output presence does not open claims without full controls/calibration/influence/reporting.",
    }


def _build_reconciliation_patch(
    previous_runner: dict[str, Any] | None,
    run_outputs: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    resolved = []
    if run_outputs.get("completed"):
        resolved = [
            "A2d_riemannian_not_executable_from_final_feature_matrix",
            "A2d_riemannian_final_covariance_runner_missing",
        ]
    return {
        "status": "phase1_final_a2d_completeness_patch_recorded",
        "previous_feature_matrix_comparator_run": str(previous_runner.get("run_dir")) if previous_runner else None,
        "a2d_final_output_present": bool(run_outputs.get("completed")),
        "resolved_blockers_for_downstream_reconciliation": resolved,
        "remaining_claim_blockers": claim_state["blockers"],
        "claim_ready": False,
        "scientific_limit": (
            "This patch documents how downstream comparator-package reconciliation may clear A2d missing-output "
            "blockers. It does not itself open claims."
        ),
    }


def _build_summary(
    *,
    output_dir: Path,
    inputs: dict[str, Any],
    extracted: dict[str, Any],
    covariance_validation: dict[str, Any],
    fold_specs: list[dict[str, Any]],
    run_outputs: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_a2d_covariance_tangent_runner_complete_claim_closed"
        if run_outputs.get("completed")
        else "phase1_final_a2d_covariance_tangent_runner_blocked",
        "output_dir": str(output_dir),
        "comparator": "A2d_riemannian",
        "feature_matrix_run": inputs["feature_matrix_run"],
        "dataset_root": inputs["dataset_root"],
        "n_covariance_rows": covariance_validation.get("n_rows"),
        "n_expected_rows": covariance_validation.get("n_expected_rows"),
        "n_folds": len(fold_specs),
        "subjects": covariance_validation.get("subjects"),
        "matrix_shapes": covariance_validation.get("matrix_shapes"),
        "channel_names": covariance_validation.get("channel_names"),
        "skipped_sessions_count": covariance_validation.get("skipped_sessions_count"),
        "read_fallbacks_count": covariance_validation.get("read_fallbacks_count"),
        "invalid_window_rows_count": covariance_validation.get("invalid_window_rows_count"),
        "a2d_final_output_present": bool(run_outputs.get("completed")),
        "runtime_leakage_passed": run_outputs.get("runtime_leakage", {}).get("outer_test_subject_used_for_any_fit") is False
        if run_outputs.get("completed")
        else False,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "smoke_artifacts_promoted": False,
        "blockers": covariance_validation.get("blockers", []),
        "claim_blockers": claim_state["blockers"],
        "metrics_summary": run_outputs.get("metrics_summary"),
        "scientific_limit": (
            "Final A2d covariance/tangent runner output only. It resolves the A2d missing-output engineering gap "
            "when complete, but it does not prove efficacy or open Phase 1 claims."
        ),
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    final_feature_run: Path,
    final_leakage_run: Path,
    feature_matrix_run: Path,
    feature_matrix_comparator_run: Path | None,
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase1_final_a2d_runner_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_manifest": str(final_split_run / "final_split_manifest.json"),
        "final_split_manifest_sha256": _sha256(final_split_run / "final_split_manifest.json"),
        "final_feature_manifest": str(final_feature_run / "final_feature_manifest.json"),
        "final_feature_manifest_sha256": _sha256(final_feature_run / "final_feature_manifest.json"),
        "final_leakage_audit": str(final_leakage_run / "final_leakage_audit.json"),
        "final_leakage_audit_sha256": _sha256(final_leakage_run / "final_leakage_audit.json"),
        "feature_matrix_run": str(feature_matrix_run),
        "feature_matrix_summary": str(feature_matrix_run / "phase1_final_feature_matrix_summary.json"),
        "feature_matrix_summary_sha256": _sha256(feature_matrix_run / "phase1_final_feature_matrix_summary.json"),
        "feature_matrix_comparator_run": str(feature_matrix_comparator_run) if feature_matrix_comparator_run else None,
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
    covariance_validation: dict[str, Any],
    run_outputs: dict[str, Any],
    claim_state: dict[str, Any],
    reconciliation: dict[str, Any],
) -> str:
    metrics = run_outputs.get("metrics_summary") or {}
    return "\n".join(
        [
            "# Phase 1 Final A2d Covariance/Tangent Runner",
            "",
            f"Status: `{summary['status']}`",
            f"Comparator: `{summary['comparator']}`",
            f"Covariance rows: `{summary['n_covariance_rows']}` / `{summary['n_expected_rows']}`",
            f"Folds: `{summary['n_folds']}`",
            f"A2d output present: `{summary['a2d_final_output_present']}`",
            f"Claim ready: `{summary['claim_ready']}`",
            "",
            "## Metrics Diagnostics",
            "",
            f"- Median BA: `{metrics.get('median_balanced_accuracy')}`",
            f"- Mean ECE: `{metrics.get('mean_ece_10_bins')}`",
            f"- Mean Brier: `{metrics.get('mean_brier')}`",
            "",
            "These diagnostics are not efficacy evidence while claim blockers remain.",
            "",
            "## Covariance Validation",
            "",
            f"Status: `{covariance_validation['status']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in covariance_validation.get("blockers", [])],
            "",
            "## Reconciliation",
            "",
            "Resolved blockers for downstream reconciliation:",
            *[f"- `{blocker}`" for blocker in reconciliation.get("resolved_blockers_for_downstream_reconciliation", [])],
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            "Remaining blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )


def _path_key(value: str | Path) -> str:
    return str(Path(value)).replace("\\", "/").rstrip("/")


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


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _numpy():
    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - numpy is present in target runtimes
        raise Phase1FinalA2dRunnerError("Final A2d runner requires numpy.") from exc
    return np
