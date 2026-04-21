"""Final feature matrix materialization for Phase 1.

This module materializes feature values from the reviewed final feature
manifest and final LOSO split. It does not train comparators or compute
performance metrics.
"""

from __future__ import annotations

import csv
import hashlib
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from ..phase05.estimators import (
    Phase05EstimatorError,
    _band_log_power,
    _optional_signal_imports,
    _read_edf,
    _read_tsv,
    _safe_float,
)
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalFeatureMatrixError(RuntimeError):
    """Raised when final feature matrix materialization cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalFeatureMatrixResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "matrix": "configs/phase1/final_feature_matrix.json",
}


def run_phase1_final_feature_matrix(
    *,
    prereg_bundle: str | Path,
    final_split_run: str | Path,
    final_feature_run: str | Path,
    final_leakage_run: str | Path,
    runner_readiness_run: str | Path,
    dataset_root: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
    precomputed_rows: dict[str, Any] | None = None,
) -> Phase1FinalFeatureMatrixResult:
    """Materialize final scalp feature matrix or write a blocked record."""

    prereg_bundle = Path(prereg_bundle)
    final_split_run = _resolve_run_dir(Path(final_split_run))
    final_feature_run = _resolve_run_dir(Path(final_feature_run))
    final_leakage_run = _resolve_run_dir(Path(final_leakage_run))
    runner_readiness_run = _resolve_run_dir(Path(runner_readiness_run))
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    split = _read_final_split_run(final_split_run)
    feature = _read_final_feature_run(final_feature_run)
    leakage = _read_final_leakage_run(final_leakage_run)
    runner_readiness = _read_runner_readiness_run(runner_readiness_run)
    matrix_config = load_config(repo_root / config_paths["matrix"])

    _validate_final_split_boundary(split)
    _validate_final_feature_boundary(feature)
    _validate_final_leakage_boundary(leakage)
    _validate_runner_readiness_boundary(runner_readiness)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    input_validation = _validate_inputs(
        split=split,
        feature=feature,
        leakage=leakage,
        runner_readiness=runner_readiness,
        dataset_root=dataset_root,
        matrix_config=matrix_config,
        precomputed_rows=precomputed_rows,
    )
    extracted = _extract_or_block(
        dataset_root=dataset_root,
        split=split,
        feature=feature,
        matrix_config=matrix_config,
        precomputed_rows=precomputed_rows,
    )
    validation = _validate_matrix(
        extracted=extracted,
        feature=feature,
        matrix_config=matrix_config,
        input_blockers=input_validation["blockers"],
    )
    matrix_ready = validation["feature_matrix_ready"]
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        final_feature_run=final_feature_run,
        final_leakage_run=final_leakage_run,
        runner_readiness_run=runner_readiness_run,
        config_paths=config_paths,
        repo_root=repo_root,
    )
    claim_state = _build_claim_state(matrix_config, matrix_ready, validation["blockers"])
    schema = _build_schema(matrix_config, feature, extracted, matrix_ready)
    row_index = _build_row_index(extracted, matrix_ready)

    matrix_path = output_dir / "final_feature_matrix.csv"
    if matrix_ready:
        _write_matrix_csv(matrix_path, extracted["rows"], extracted["feature_names"], matrix_config)
        source_links["final_feature_matrix"] = str(matrix_path)
        source_links["final_feature_matrix_sha256"] = _sha256(matrix_path)
    else:
        _write_json(output_dir / "phase1_final_feature_matrix_blocked.json", _build_blocked_record(extracted, validation))

    summary = {
        "status": "phase1_final_feature_matrix_materialized" if matrix_ready else "phase1_final_feature_matrix_blocked",
        "output_dir": str(output_dir),
        "feature_matrix_ready": matrix_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "feature_set_id": feature["manifest"].get("feature_set_id"),
        "dataset_root": str(dataset_root),
        "final_split_run": str(final_split_run),
        "final_feature_run": str(final_feature_run),
        "final_leakage_run": str(final_leakage_run),
        "runner_readiness_run": str(runner_readiness_run),
        "n_rows": len(extracted["rows"]) if matrix_ready else 0,
        "n_candidate_rows": len(extracted["rows"]),
        "n_expected_rows": feature["manifest"].get("n_event_rows_planned"),
        "n_features": len(extracted.get("feature_names", [])),
        "n_expected_features": feature["manifest"].get("feature_count"),
        "subjects": extracted.get("subjects", []),
        "sessions": extracted.get("sessions", []),
        "skipped_sessions_count": len(extracted.get("skipped_sessions", [])),
        "read_fallbacks_count": len(extracted.get("read_fallbacks", [])),
        "invalid_window_rows_count": len(extracted.get("invalid_window_rows", [])),
        "nonfinite_feature_values": validation.get("nonfinite_feature_values", 0),
        "nonfinite_feature_examples": validation.get("nonfinite_feature_examples", []),
        "missing_source_channels": validation.get("missing_source_channels", []),
        "missing_source_channels_count": validation.get("missing_source_channels_count", 0),
        "nonfinite_signal_rows_count": validation.get("nonfinite_signal_rows_count", 0),
        "bandpower_nonfinite_feature_count": len(validation.get("bandpower_nonfinite_counts", {})),
        "matrix_path": str(matrix_path) if matrix_ready else None,
        "feature_matrix_blockers": validation["blockers"],
        "claim_blockers": claim_state["blockers"],
        "contains_model_outputs": False,
        "contains_logits": False,
        "contains_metrics": False,
        "scientific_limit": (
            "Final feature matrix materialization only. This run writes scalp EEG feature values and row provenance; "
            "it does not train models, compute comparator metrics, create logits, audit runtime comparator logs, "
            "or support claims."
        ),
    }
    inputs = {
        "status": "phase1_final_feature_matrix_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_feature_run": str(final_feature_run),
        "final_leakage_run": str(final_leakage_run),
        "runner_readiness_run": str(runner_readiness_run),
        "dataset_root": str(dataset_root),
        "config_paths": config_paths,
        "precomputed_rows_used": precomputed_rows is not None,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_feature_matrix_inputs.json"
    summary_path = output_dir / "phase1_final_feature_matrix_summary.json"
    report_path = output_dir / "phase1_final_feature_matrix_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_feature_matrix_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_feature_matrix_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_feature_matrix_schema.json", schema)
    _write_json(output_dir / "final_feature_row_index.json", row_index)
    _write_json(output_dir / "phase1_final_feature_matrix_validation.json", validation)
    _write_json(output_dir / "phase1_final_feature_matrix_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, validation, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalFeatureMatrixResult(
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
        "validation": "phase1_final_leakage_audit_validation.json",
        "claim_state": "phase1_final_leakage_audit_claim_state.json",
    }
    return _read_required_files(run_dir, required, "Final leakage audit")


def _read_runner_readiness_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_comparator_runner_readiness_summary.json",
        "input_validation": "phase1_final_comparator_runner_input_validation.json",
        "manifest_status": "phase1_final_comparator_runner_manifest_status.json",
        "claim_state": "phase1_final_comparator_runner_claim_state.json",
    }
    return _read_required_files(run_dir, required, "Final comparator runner readiness")


def _read_required_files(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalFeatureMatrixError(f"{label} file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_final_split_boundary(split: dict[str, Any]) -> None:
    if split["summary"].get("status") != "phase1_final_split_manifest_recorded":
        raise Phase1FinalFeatureMatrixError("Final feature matrix requires a recorded final split manifest")
    if split["summary"].get("split_manifest_ready") is not True:
        raise Phase1FinalFeatureMatrixError("Final split manifest must be ready")
    if split["validation"].get("status") != "phase1_final_split_manifest_validation_passed":
        raise Phase1FinalFeatureMatrixError("Final split manifest validation must pass")
    if split["validation"].get("no_subject_overlap_between_train_and_test") is not True:
        raise Phase1FinalFeatureMatrixError("Final split manifest must have no train/test subject overlap")
    if split["manifest"].get("claim_ready") is not False or split["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalFeatureMatrixError("Final split manifest must keep claim_ready=false")
    if split["manifest"].get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalFeatureMatrixError("Final split manifest must not promote smoke artifacts")


def _validate_final_feature_boundary(feature: dict[str, Any]) -> None:
    if feature["summary"].get("status") != "phase1_final_feature_manifest_recorded":
        raise Phase1FinalFeatureMatrixError("Final feature matrix requires a recorded final feature manifest")
    if feature["summary"].get("feature_manifest_ready") is not True:
        raise Phase1FinalFeatureMatrixError("Final feature manifest must be ready")
    if feature["validation"].get("status") != "phase1_final_feature_manifest_validation_passed":
        raise Phase1FinalFeatureMatrixError("Final feature manifest validation must pass")
    manifest = feature["manifest"]
    if manifest.get("contains_feature_matrix") is not False:
        raise Phase1FinalFeatureMatrixError("Final feature manifest must not already contain feature matrix values")
    if manifest.get("contains_model_outputs") is not False:
        raise Phase1FinalFeatureMatrixError("Final feature manifest must not contain model outputs")
    if manifest.get("contains_metrics") is not False:
        raise Phase1FinalFeatureMatrixError("Final feature manifest must not contain metrics")
    if manifest.get("claim_ready") is not False or feature["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalFeatureMatrixError("Final feature manifest must keep claim_ready=false")


def _validate_final_leakage_boundary(leakage: dict[str, Any]) -> None:
    if leakage["summary"].get("status") != "phase1_final_leakage_audit_recorded":
        raise Phase1FinalFeatureMatrixError("Final feature matrix requires a recorded final leakage audit")
    if leakage["summary"].get("leakage_audit_ready") is not True:
        raise Phase1FinalFeatureMatrixError("Final leakage audit must be ready")
    if leakage["validation"].get("status") != "phase1_final_leakage_audit_validation_passed":
        raise Phase1FinalFeatureMatrixError("Final leakage audit validation must pass")
    if leakage["audit"].get("outer_test_subject_used_in_any_fit") is not False:
        raise Phase1FinalFeatureMatrixError("Manifest-level leakage audit found outer-test subject in fit")
    if leakage["audit"].get("test_time_privileged_or_teacher_outputs_allowed") is not False:
        raise Phase1FinalFeatureMatrixError("Manifest-level leakage audit must disallow test-time privileged/teacher outputs")
    if leakage["audit"].get("runtime_comparator_logs_audited") is not False:
        raise Phase1FinalFeatureMatrixError("Feature matrix materialization must occur before runtime comparator logs exist")
    if leakage["audit"].get("contains_model_outputs") is not False or leakage["audit"].get("contains_metrics") is not False:
        raise Phase1FinalFeatureMatrixError("Manifest-level leakage audit must not contain model outputs or metrics")
    if leakage["audit"].get("claim_ready") is not False or leakage["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalFeatureMatrixError("Final leakage audit must keep claim_ready=false")


def _validate_runner_readiness_boundary(readiness: dict[str, Any]) -> None:
    if readiness["summary"].get("status") != "phase1_final_comparator_runner_readiness_recorded":
        raise Phase1FinalFeatureMatrixError("Final feature matrix requires recorded final comparator runner readiness")
    if readiness["summary"].get("upstream_manifests_ready") is not True:
        raise Phase1FinalFeatureMatrixError("Final comparator runner readiness must have upstream_manifests_ready=true")
    if readiness["summary"].get("final_comparator_outputs_present") is not False:
        raise Phase1FinalFeatureMatrixError("Final comparator outputs must not exist before feature matrix materialization")
    if readiness["summary"].get("runtime_comparator_logs_audited") is not False:
        raise Phase1FinalFeatureMatrixError("Runtime comparator logs must not be audited before final runners execute")
    if readiness["summary"].get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalFeatureMatrixError("Runner readiness must not promote smoke artifacts")
    if readiness["summary"].get("claim_ready") is not False or readiness["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalFeatureMatrixError("Runner readiness must keep claim_ready=false")


def _validate_inputs(
    *,
    split: dict[str, Any],
    feature: dict[str, Any],
    leakage: dict[str, Any],
    runner_readiness: dict[str, Any],
    dataset_root: Path,
    matrix_config: dict[str, Any],
    precomputed_rows: dict[str, Any] | None,
) -> dict[str, Any]:
    required = matrix_config.get("required_inputs", {})
    observed = {
        "final_split_manifest_ready": split["summary"].get("split_manifest_ready"),
        "final_feature_manifest_ready": feature["summary"].get("feature_manifest_ready"),
        "final_leakage_audit_ready": leakage["summary"].get("leakage_audit_ready"),
        "final_comparator_runner_upstream_manifests_ready": runner_readiness["summary"].get("upstream_manifests_ready"),
        "dataset_root_exists": dataset_root.exists() or precomputed_rows is not None,
        "feature_manifest_contains_feature_matrix": feature["manifest"].get("contains_feature_matrix"),
        "feature_manifest_contains_model_outputs": feature["manifest"].get("contains_model_outputs"),
        "feature_manifest_contains_metrics": feature["manifest"].get("contains_metrics"),
        "manifest_level_outer_test_subject_used_in_any_fit": leakage["audit"].get("outer_test_subject_used_in_any_fit"),
        "test_time_privileged_or_teacher_outputs_allowed": leakage["audit"].get(
            "test_time_privileged_or_teacher_outputs_allowed"
        ),
        "runtime_comparator_logs_audited": leakage["audit"].get("runtime_comparator_logs_audited"),
        "smoke_artifacts_promoted": bool(
            split["manifest"].get("smoke_artifacts_promoted")
            or feature["manifest"].get("smoke_feature_rows_allowed_as_final")
            or runner_readiness["summary"].get("smoke_artifacts_promoted")
        ),
    }
    blockers = [f"{key}_mismatch" for key, expected in required.items() if observed.get(key) is not expected]
    return {
        "status": "phase1_final_feature_matrix_inputs_ready" if not blockers else "phase1_final_feature_matrix_inputs_blocked",
        "observed": observed,
        "required": required,
        "blockers": blockers,
        "precomputed_rows_used": precomputed_rows is not None,
        "scientific_limit": "Input validation checks materialization prerequisites only; it is not model evidence.",
    }


def _extract_or_block(
    *,
    dataset_root: Path,
    split: dict[str, Any],
    feature: dict[str, Any],
    matrix_config: dict[str, Any],
    precomputed_rows: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        if precomputed_rows is not None:
            return _coerce_precomputed_rows(precomputed_rows, feature, matrix_config)
        return _extract_rows_from_signal(dataset_root, split, feature, matrix_config)
    except (Phase05EstimatorError, Phase1FinalFeatureMatrixError, FileNotFoundError) as exc:
        return {
            "status": "phase1_final_feature_matrix_extraction_blocked",
            "rows": [],
            "feature_names": list(feature["manifest"].get("feature_names", [])),
            "subjects": [],
            "sessions": [],
            "skipped_sessions": [{"reason": str(exc)}],
            "read_fallbacks": [],
            "channel_aliases": [],
            "blockers": ["feature_matrix_extraction_failed"],
            "error": str(exc),
            "invalid_window_rows": [],
            "missing_source_channels": [],
            "missing_feature_counts": {},
            "nonfinite_signal_rows": [],
            "bandpower_nonfinite_counts": {},
        }


def _coerce_precomputed_rows(
    precomputed_rows: dict[str, Any],
    feature: dict[str, Any],
    matrix_config: dict[str, Any],
) -> dict[str, Any]:
    feature_names = list(precomputed_rows.get("feature_names") or feature["manifest"].get("feature_names", []))
    rows = []
    for index, row in enumerate(precomputed_rows.get("rows", []), start=1):
        features = row.get("features", {})
        if isinstance(features, dict):
            values = [float(features.get(name, float("nan"))) for name in feature_names]
        else:
            values = [float(value) for value in features]
        rows.append(
            {
                "row_id": str(row.get("row_id") or f"row_{index:06d}"),
                "participant_id": str(row.get("participant_id") or row.get("subject")),
                "session_id": str(row.get("session_id") or row.get("session")),
                "trial_id": str(row.get("trial_id", index)),
                "label": int(row["label"]),
                "set_size": int(row.get("set_size", 8 if int(row["label"]) else 4)),
                "event_onset_sample": int(row.get("event_onset_sample", 0)),
                "event_onset_sec": float(row.get("event_onset_sec", 0.0)),
                "source_eeg_file": str(row.get("source_eeg_file", "precomputed")),
                "source_events_file": str(row.get("source_events_file", "precomputed")),
                "features": values,
                "nonfinite_feature_count": sum(1 for value in values if not math.isfinite(float(value))),
            }
        )
    return _finalize_extracted_rows(
        rows=rows,
        feature_names=feature_names,
        skipped_sessions=[],
        read_fallbacks=[],
        source="precomputed_rows_test_fixture",
        matrix_config=matrix_config,
        channel_aliases=[],
        invalid_window_rows=[],
        missing_source_channels=[],
        missing_feature_counts={},
        nonfinite_signal_rows=[],
        bandpower_nonfinite_counts={},
    )


def _extract_rows_from_signal(
    dataset_root: Path,
    split: dict[str, Any],
    feature: dict[str, Any],
    matrix_config: dict[str, Any],
) -> dict[str, Any]:
    np, mne = _optional_signal_imports()
    manifest = feature["manifest"]
    feature_names = list(manifest.get("feature_names", []))
    bands = {name: tuple(values) for name, values in sorted(manifest.get("frequency_bands_hz", {}).items())}
    expected_channels = _expected_channels_from_feature_names(feature_names)
    task_window = tuple(manifest.get("signal_windows_sec", {}).get("task_maintenance", []))
    if len(task_window) != 2:
        raise Phase1FinalFeatureMatrixError("Final feature manifest must define task_maintenance signal window")
    rows = []
    skipped_sessions = []
    read_fallbacks = []
    channel_alias_records = []
    invalid_window_rows = []
    missing_source_channels = []
    nonfinite_signal_rows = []
    bandpower_nonfinite_counts: dict[str, int] = {}
    missing_feature_counts: dict[str, int] = {}
    row_index = 1
    for session_label in manifest.get("sessions", []):
        subject, session = _split_session_label(str(session_label))
        eeg_dir = dataset_root / subject / session / "eeg"
        stem = f"{subject}_{session}_task-verbalWM_run-01"
        eeg_path = eeg_dir / f"{stem}_eeg.edf"
        events_path = eeg_dir / f"{stem}_events.tsv"
        if not eeg_path.exists() or not events_path.exists():
            skipped_sessions.append({"subject": subject, "session": session, "reason": "missing_eeg_or_events"})
            continue
        events = _load_binary_load_events(events_path, manifest)
        if not events:
            skipped_sessions.append({"subject": subject, "session": session, "reason": "no_clean_load_4_or_8_events"})
            continue
        try:
            raw = _read_edf(mne, eeg_path)
        except Phase05EstimatorError as exc:
            skipped_sessions.append({"subject": subject, "session": session, "reason": str(exc)})
            continue
        fallback = getattr(raw, "_phase05_read_fallback", None)
        if fallback:
            read_fallbacks.append({"subject": subject, "session": session, "modality": "eeg", **fallback})
        data = raw.get_data()
        sfreq = float(raw.info["sfreq"])
        channel_names = [str(name) for name in raw.ch_names]
        channel_aliases = _feature_aliases_for_raw_channels(expected_channels, channel_names)
        channel_alias_records.append(
            {
                "subject": subject,
                "session": session,
                "raw_channel_count": len(channel_names),
                "expected_channel_count": len(expected_channels),
                "aliases": channel_aliases,
            }
        )
        raw_index_by_channel = {name: index for index, name in enumerate(channel_names)}
        for event in events:
            trial_start = max(int(float(event.get("begSample", 1))) - 1, 0)
            window_start = trial_start + int(round(float(task_window[0]) * sfreq))
            window_stop = min(trial_start + int(round(float(task_window[1]) * sfreq)), int(data.shape[1]))
            invalid_window = window_stop <= window_start or (window_stop - window_start) < 4
            segment = data[:, window_start:window_stop] if not invalid_window else None
            if invalid_window:
                invalid_window_rows.append(
                    {
                        "row_id": f"row_{row_index:06d}",
                        "participant_id": subject,
                        "session_id": session,
                        "trial_id": str(event.get("nTrial", row_index)),
                        "event_onset_sample": trial_start,
                        "window_start_sample": window_start,
                        "window_stop_sample": window_stop,
                        "data_n_samples": int(data.shape[1]),
                    }
                )
            feature_map: dict[str, float] = {}
            for expected_channel in expected_channels:
                raw_channel = channel_aliases.get(expected_channel)
                if raw_channel is None:
                    missing_source_channels.append(
                        {
                            "row_id": f"row_{row_index:06d}",
                            "participant_id": subject,
                            "session_id": session,
                            "trial_id": str(event.get("nTrial", row_index)),
                            "expected_channel": expected_channel,
                            "available_raw_channels": channel_names,
                        }
                    )
                    for band_name in bands:
                        missing_feature_counts[f"{expected_channel}:{band_name}"] = (
                            missing_feature_counts.get(f"{expected_channel}:{band_name}", 0) + 1
                        )
                    continue
                for band_name, band in bands.items():
                    feature_name = f"{expected_channel}:{band_name}"
                    if invalid_window or segment is None:
                        feature_map[feature_name] = float("nan")
                    else:
                        signal = segment[raw_index_by_channel[raw_channel]]
                        nonfinite_samples = _nonfinite_sample_count(np, signal)
                        if nonfinite_samples:
                            if not any(
                                item.get("row_id") == f"row_{row_index:06d}"
                                and item.get("expected_channel") == expected_channel
                                for item in nonfinite_signal_rows
                            ):
                                nonfinite_signal_rows.append(
                                    {
                                        "row_id": f"row_{row_index:06d}",
                                        "participant_id": subject,
                                        "session_id": session,
                                        "trial_id": str(event.get("nTrial", row_index)),
                                        "expected_channel": expected_channel,
                                        "raw_channel": raw_channel,
                                        "nonfinite_samples": nonfinite_samples,
                                        "window_start_sample": window_start,
                                        "window_stop_sample": window_stop,
                                        "event_onset_sample": trial_start,
                                        "source_eeg_file": eeg_path.relative_to(dataset_root).as_posix(),
                                    }
                                )
                            feature_map[feature_name] = float("nan")
                        else:
                            value = _band_log_power(np, signal, sfreq, band)
                            if not math.isfinite(float(value)):
                                bandpower_nonfinite_counts[feature_name] = (
                                    bandpower_nonfinite_counts.get(feature_name, 0) + 1
                                )
                            feature_map[feature_name] = value
            set_size = int(float(event["SetSize"]))
            feature_values = [feature_map.get(name, float("nan")) for name in feature_names]
            for name, value in zip(feature_names, feature_values):
                if not math.isfinite(float(value)):
                    missing_feature_counts[name] = missing_feature_counts.get(name, 0) + 1
            rows.append(
                {
                    "row_id": f"row_{row_index:06d}",
                    "participant_id": subject,
                    "session_id": session,
                    "trial_id": str(event.get("nTrial", row_index)),
                    "label": 1 if set_size == 8 else 0,
                    "set_size": set_size,
                    "event_onset_sample": trial_start,
                    "event_onset_sec": float(trial_start / sfreq),
                    "source_eeg_file": eeg_path.relative_to(dataset_root).as_posix(),
                    "source_events_file": events_path.relative_to(dataset_root).as_posix(),
                    "features": feature_values,
                    "nonfinite_feature_count": sum(1 for value in feature_values if not math.isfinite(float(value))),
                }
            )
            row_index += 1
    return _finalize_extracted_rows(
        rows=rows,
        feature_names=feature_names,
        skipped_sessions=skipped_sessions,
        read_fallbacks=read_fallbacks,
        source="edf_signal_payloads",
        matrix_config=matrix_config,
        channel_aliases=channel_alias_records,
        invalid_window_rows=invalid_window_rows,
        missing_source_channels=missing_source_channels,
        missing_feature_counts=missing_feature_counts,
        nonfinite_signal_rows=nonfinite_signal_rows,
        bandpower_nonfinite_counts=bandpower_nonfinite_counts,
    )


def _finalize_extracted_rows(
    *,
    rows: list[dict[str, Any]],
    feature_names: list[str],
    skipped_sessions: list[dict[str, Any]],
    read_fallbacks: list[dict[str, Any]],
    source: str,
    matrix_config: dict[str, Any],
    channel_aliases: list[dict[str, Any]] | None = None,
    invalid_window_rows: list[dict[str, Any]] | None = None,
    missing_source_channels: list[dict[str, Any]] | None = None,
    missing_feature_counts: dict[str, int] | None = None,
    nonfinite_signal_rows: list[dict[str, Any]] | None = None,
    bandpower_nonfinite_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    subjects = sorted({row["participant_id"] for row in rows})
    sessions = sorted({f"{row['participant_id']}/{row['session_id']}" for row in rows})
    return {
        "status": "phase1_final_feature_matrix_rows_extracted",
        "source": source,
        "rows": rows,
        "feature_names": feature_names,
        "row_identity_columns": matrix_config.get("row_identity_columns", []),
        "subjects": subjects,
        "sessions": sessions,
        "skipped_sessions": skipped_sessions,
        "read_fallbacks": read_fallbacks,
        "channel_aliases": channel_aliases or [],
        "invalid_window_rows": invalid_window_rows or [],
        "missing_source_channels": missing_source_channels or [],
        "missing_feature_counts": missing_feature_counts or {},
        "nonfinite_signal_rows": nonfinite_signal_rows or [],
        "bandpower_nonfinite_counts": bandpower_nonfinite_counts or {},
        "blockers": [],
        "scientific_limit": "Extracted rows are feature values and labels only; no model outputs or metrics are included.",
    }


def _load_binary_load_events(events_path: Path, feature_manifest: dict[str, Any]) -> list[dict[str, str]]:
    rows = _read_tsv(events_path)
    allowed_artifact = {str(value) for value in feature_manifest.get("trial_filter", {}).get("artifact_values_allowed", [])}
    allowed_sizes = {int(value) for value in feature_manifest.get("trial_filter", {}).get("set_size_values_allowed", [])}
    selected = []
    for row in rows:
        artifact = str(row.get("Artifact", ""))
        if artifact not in allowed_artifact:
            continue
        set_size = _safe_float(row.get("SetSize"))
        if math.isfinite(set_size) and int(set_size) in allowed_sizes:
            selected.append(row)
    return selected


def _nonfinite_sample_count(np: Any, signal: Any) -> int:
    values = np.asarray(signal, dtype=float)
    return int(values.size - int(np.isfinite(values).sum()))


def _validate_matrix(
    *,
    extracted: dict[str, Any],
    feature: dict[str, Any],
    matrix_config: dict[str, Any],
    input_blockers: list[str],
) -> dict[str, Any]:
    manifest = feature["manifest"]
    rows = extracted.get("rows", [])
    feature_names = extracted.get("feature_names", [])
    blockers = list(input_blockers) + list(extracted.get("blockers", []))
    rules = matrix_config.get("validation_rules", {})
    expected_rows = int(manifest.get("n_event_rows_planned", 0))
    expected_features = list(manifest.get("feature_names", []))
    nonfinite_examples = _nonfinite_feature_examples(rows, feature_names, max_examples=25)
    nonfinite = sum(row.get("nonfinite_feature_count", 0) for row in rows)
    missing_source_channels = extracted.get("missing_source_channels", [])
    nonfinite_signal_rows = extracted.get("nonfinite_signal_rows", [])
    bandpower_nonfinite_counts = extracted.get("bandpower_nonfinite_counts", {})
    labels = {row.get("label") for row in rows}
    if rules.get("row_count_must_match_final_feature_manifest_planned_event_rows") and len(rows) != expected_rows:
        blockers.append("row_count_does_not_match_final_feature_manifest")
    if rules.get("subjects_must_match_final_feature_manifest_subjects") and set(extracted.get("subjects", [])) != set(manifest.get("subjects", [])):
        blockers.append("subjects_do_not_match_final_feature_manifest")
    if rules.get("feature_names_must_match_final_feature_manifest") and feature_names != expected_features:
        blockers.append("feature_names_do_not_match_final_feature_manifest")
    if rules.get("all_rows_must_have_binary_labels") and not labels <= {0, 1}:
        blockers.append("non_binary_labels_present")
    if rules.get("all_feature_values_must_be_finite") and nonfinite:
        blockers.append("nonfinite_feature_values_present")
    if missing_source_channels:
        blockers.append("source_channels_missing_for_feature_manifest")
    if nonfinite_signal_rows:
        blockers.append("nonfinite_signal_samples_present")
    if bandpower_nonfinite_counts:
        blockers.append("bandpower_feature_extraction_returned_nonfinite")
    if rules.get("all_eeg_payloads_must_be_readable") and extracted.get("skipped_sessions"):
        blockers.append("one_or_more_sessions_skipped")
    if not rows:
        blockers.append("no_feature_rows_materialized")
    return {
        "status": "phase1_final_feature_matrix_validation_passed" if not blockers else "phase1_final_feature_matrix_validation_blocked",
        "feature_matrix_ready": not blockers,
        "n_rows": len(rows),
        "n_expected_rows": expected_rows,
        "n_features": len(feature_names),
        "n_expected_features": int(manifest.get("feature_count", 0)),
        "subjects": extracted.get("subjects", []),
        "expected_subjects": manifest.get("subjects", []),
        "feature_names_match_manifest": feature_names == expected_features,
        "labels": sorted(labels),
        "nonfinite_feature_values": nonfinite,
        "nonfinite_feature_examples": nonfinite_examples,
        "missing_source_channels_count": len(missing_source_channels),
        "missing_source_channels": missing_source_channels[:50],
        "missing_feature_counts": extracted.get("missing_feature_counts", {}),
        "nonfinite_signal_rows_count": len(nonfinite_signal_rows),
        "nonfinite_signal_rows": nonfinite_signal_rows[:100],
        "bandpower_nonfinite_counts": bandpower_nonfinite_counts,
        "invalid_window_rows": extracted.get("invalid_window_rows", []),
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "contains_model_outputs": False,
        "contains_logits": False,
        "contains_metrics": False,
        "blockers": _unique(blockers),
        "scientific_limit": "Validation covers feature matrix materialization only; it is not model evidence.",
    }


def _build_schema(
    matrix_config: dict[str, Any],
    feature: dict[str, Any],
    extracted: dict[str, Any],
    matrix_ready: bool,
) -> dict[str, Any]:
    return {
        "status": "phase1_final_feature_matrix_schema_recorded",
        "feature_matrix_ready": matrix_ready,
        "matrix_id": matrix_config.get("matrix_id"),
        "feature_set_id": feature["manifest"].get("feature_set_id"),
        "row_identity_columns": matrix_config.get("row_identity_columns", []),
        "feature_names": extracted.get("feature_names", []),
        "feature_count": len(extracted.get("feature_names", [])),
        "matrix_boundary": matrix_config.get("matrix_boundary", {}),
        "contains_model_outputs": False,
        "contains_logits": False,
        "contains_metrics": False,
        "scientific_limit": "Schema records feature-matrix columns only; it is not model evidence.",
    }


def _build_row_index(extracted: dict[str, Any], matrix_ready: bool) -> dict[str, Any]:
    return {
        "status": "phase1_final_feature_row_index_recorded" if matrix_ready else "phase1_final_feature_row_index_blocked",
        "feature_matrix_ready": matrix_ready,
        "n_rows": len(extracted.get("rows", [])) if matrix_ready else 0,
        "rows": [
            {key: row[key] for key in [
                "row_id",
                "participant_id",
                "session_id",
                "trial_id",
                "label",
                "set_size",
                "event_onset_sample",
                "event_onset_sec",
                "source_eeg_file",
                "source_events_file",
            ]}
            for row in extracted.get("rows", [])
        ]
        if matrix_ready
        else [],
        "scientific_limit": "Row index links feature rows to source events only; it is not model evidence.",
    }


def _write_matrix_csv(path: Path, rows: list[dict[str, Any]], feature_names: list[str], matrix_config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    identity_columns = matrix_config.get("row_identity_columns", [])
    fieldnames = list(identity_columns) + list(feature_names)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output = {key: row[key] for key in identity_columns}
            output.update({name: row["features"][index] for index, name in enumerate(feature_names)})
            writer.writerow(output)


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    final_feature_run: Path,
    final_leakage_run: Path,
    runner_readiness_run: Path,
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    split_path = final_split_run / "final_split_manifest.json"
    feature_path = final_feature_run / "final_feature_manifest.json"
    leakage_path = final_leakage_run / "final_leakage_audit.json"
    runner_path = runner_readiness_run / "phase1_final_comparator_runner_readiness_summary.json"
    return {
        "status": "phase1_final_feature_matrix_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_manifest": str(split_path),
        "final_split_manifest_sha256": _sha256(split_path),
        "final_feature_manifest": str(feature_path),
        "final_feature_manifest_sha256": _sha256(feature_path),
        "final_leakage_audit": str(leakage_path),
        "final_leakage_audit_sha256": _sha256(leakage_path),
        "runner_readiness_summary": str(runner_path),
        "runner_readiness_summary_sha256": _sha256(runner_path),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links document provenance for feature matrix materialization only.",
    }


def _build_claim_state(
    matrix_config: dict[str, Any],
    matrix_ready: bool,
    matrix_blockers: list[str],
) -> dict[str, Any]:
    blockers = list(matrix_blockers)
    if matrix_ready:
        blockers.extend(matrix_config.get("claim_blockers_after_success", []))
    else:
        blockers.append("final_feature_matrix_missing_or_blocked")
        blockers.append("claim_blocked_until_final_feature_matrix_materializes")
    return {
        "status": "phase1_final_feature_matrix_claim_state_blocked",
        "feature_matrix_ready": matrix_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "contains_model_outputs": False,
        "contains_logits": False,
        "contains_metrics": False,
        "standalone_claim_ready": matrix_config.get("matrix_boundary", {}).get("standalone_claim_ready", False),
        "smoke_feature_rows_allowed_as_final": False,
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": (
            "A final scalp feature matrix exists for final comparator runner inputs, with no model outputs or metrics."
            if matrix_ready
            else "Final feature matrix materialization is blocked; downstream final comparator runners must not use it."
        ),
    }


def _build_blocked_record(extracted: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "phase1_final_feature_matrix_not_written",
        "reason": "Final feature matrix prerequisites or extraction validation failed.",
        "extraction_status": extracted.get("status"),
        "candidate_rows": len(extracted.get("rows", [])),
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "invalid_window_rows": extracted.get("invalid_window_rows", []),
        "missing_source_channels": extracted.get("missing_source_channels", [])[:100],
        "missing_feature_counts": extracted.get("missing_feature_counts", {}),
        "nonfinite_signal_rows": extracted.get("nonfinite_signal_rows", [])[:100],
        "bandpower_nonfinite_counts": extracted.get("bandpower_nonfinite_counts", {}),
        "blockers": validation["blockers"],
        "scientific_limit": "Blocked record is not a feature matrix and must not be used by final comparator runners.",
    }


def _render_report(summary: dict[str, Any], validation: dict[str, Any], claim_state: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 Final Feature Matrix Materialization",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Feature matrix ready: `{summary['feature_matrix_ready']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Rows: `{summary['n_rows']}`",
        f"- Candidate rows: `{summary['n_candidate_rows']}`",
        f"- Expected rows: `{summary['n_expected_rows']}`",
        f"- Features: `{summary['n_features']}`",
        f"- Expected features: `{summary['n_expected_features']}`",
        f"- Skipped sessions: `{summary['skipped_sessions_count']}`",
        f"- Read fallbacks: `{summary['read_fallbacks_count']}`",
        f"- Invalid window rows: `{summary['invalid_window_rows_count']}`",
        f"- Non-finite feature values: `{summary['nonfinite_feature_values']}`",
        f"- Missing source channel records: `{summary.get('missing_source_channels_count', 0)}`",
        f"- Rows with non-finite signal samples: `{summary.get('nonfinite_signal_rows_count', 0)}`",
        f"- Bandpower non-finite feature groups: `{summary.get('bandpower_nonfinite_feature_count', 0)}`",
        "",
        "## Validation",
        "",
        f"- Validation status: `{validation['status']}`",
        f"- Feature names match manifest: `{validation['feature_names_match_manifest']}`",
        f"- Contains model outputs: `{validation['contains_model_outputs']}`",
        f"- Contains logits: `{validation['contains_logits']}`",
        f"- Contains metrics: `{validation['contains_metrics']}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Scientific Integrity", ""])
    lines.append("- This run materializes feature values and labels only.")
    lines.append("- It does not train models, compute metrics, create logits or audit runtime comparator logs.")
    lines.append("- It is not decoder evidence and cannot open headline claims.")
    lines.extend(["", "## Not OK To Claim", ""])
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _split_session_label(label: str) -> tuple[str, str]:
    parts = label.split("/")
    if len(parts) != 2:
        raise Phase1FinalFeatureMatrixError(f"Unexpected session label in final feature manifest: {label}")
    return parts[0], parts[1]


def _expected_channels_from_feature_names(feature_names: list[str]) -> list[str]:
    channels = []
    for name in feature_names:
        if ":" not in name:
            raise Phase1FinalFeatureMatrixError(f"Feature name does not follow channel:band format: {name}")
        channel = name.split(":", 1)[0]
        if channel not in channels:
            channels.append(channel)
    return channels


def _feature_aliases_for_raw_channels(expected_channels: list[str], raw_channels: list[str]) -> dict[str, str | None]:
    normalized_raw: dict[str, list[str]] = {}
    for channel in raw_channels:
        normalized_raw.setdefault(_normalize_channel_name(channel), []).append(channel)
    aliases: dict[str, str | None] = {}
    for expected in expected_channels:
        candidates = normalized_raw.get(_normalize_channel_name(expected), [])
        aliases[expected] = candidates[0] if len(candidates) == 1 else None
    return aliases


def _normalize_channel_name(name: str) -> str:
    value = str(name).strip().lower()
    for prefix in ("eeg ", "eeg_", "eeg-"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    for suffix in ("-ref", "_ref", " ref", "-avg", "_avg", " avg"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return "".join(char for char in value if char.isalnum())


def _nonfinite_feature_examples(
    rows: list[dict[str, Any]],
    feature_names: list[str],
    *,
    max_examples: int,
) -> list[dict[str, Any]]:
    examples = []
    for row in rows:
        for feature_name, value in zip(feature_names, row.get("features", [])):
            if not math.isfinite(float(value)):
                examples.append(
                    {
                        "row_id": row.get("row_id"),
                        "participant_id": row.get("participant_id"),
                        "session_id": row.get("session_id"),
                        "trial_id": row.get("trial_id"),
                        "feature_name": feature_name,
                        "event_onset_sample": row.get("event_onset_sample"),
                        "source_eeg_file": row.get("source_eeg_file"),
                    }
                )
                if len(examples) >= max_examples:
                    return examples
    return examples


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
