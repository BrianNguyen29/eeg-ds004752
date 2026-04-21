"""Final feature schema and provenance manifest for Phase 1.

This module records a final scalp feature manifest after the final LOSO split
manifest exists. It does not write feature matrices, train models, compute
metrics, or replace the final leakage audit.
"""

from __future__ import annotations

import csv
import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalFeatureManifestError(RuntimeError):
    """Raised when final feature manifest generation cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalFeatureManifestResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "manifest": "configs/phase1/final_feature_manifest.json",
    "readiness": "configs/phase1/final_split_feature_leakage.json",
}


def run_phase1_final_feature_manifest(
    *,
    prereg_bundle: str | Path,
    final_split_run: str | Path,
    dataset_root: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalFeatureManifestResult:
    """Write a final feature manifest or a fail-closed blocked record."""

    prereg_bundle = Path(prereg_bundle)
    final_split_run = _resolve_run_dir(Path(final_split_run))
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    split = _read_final_split_run(final_split_run)
    _validate_final_split_boundary(split)
    manifest_config = load_config(repo_root / config_paths["manifest"])
    readiness_config = load_config(repo_root / config_paths["readiness"])

    gate0_run = Path(split["manifest"]["source_gate0_run"])
    gate0 = _read_gate0_run(gate0_run)
    materialization = _read_materialization(gate0_run)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    inventory = _build_feature_inventory(dataset_root, split["manifest"], manifest_config)
    readiness = _validate_feature_manifest_inputs(
        split=split,
        gate0=gate0,
        materialization=materialization,
        dataset_root=dataset_root,
        inventory=inventory,
        manifest_config=manifest_config,
    )
    feature_ready = not readiness["blockers"]
    final_feature_manifest = None
    if feature_ready:
        final_feature_manifest = _build_final_feature_manifest(
            timestamp=timestamp,
            manifest_config=manifest_config,
            readiness_config=readiness_config,
            inventory=inventory,
            prereg_bundle=prereg_bundle,
            bundle=bundle,
            final_split_run=final_split_run,
            split=split,
            gate0_run=gate0_run,
            gate0=gate0,
            materialization=materialization,
            dataset_root=dataset_root,
        )
        validation = _validate_final_feature_manifest(final_feature_manifest)
    else:
        validation = _blocked_validation(readiness, inventory, manifest_config)

    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        final_split_run=final_split_run,
        split=split,
        gate0_run=gate0_run,
        gate0=gate0,
        dataset_root=dataset_root,
        config_paths=config_paths,
        repo_root=repo_root,
    )
    claim_state = _build_claim_state(manifest_config, feature_ready, readiness["blockers"])
    blocked_record = None if feature_ready else _build_blocked_record(readiness, inventory, manifest_config)

    status = "phase1_final_feature_manifest_recorded" if feature_ready else "phase1_final_feature_manifest_blocked"
    summary = {
        "status": status,
        "output_dir": str(output_dir),
        "feature_manifest_ready": feature_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "feature_set_id": manifest_config.get("feature_set_id"),
        "feature_family": manifest_config.get("feature_family"),
        "dataset_root": str(dataset_root),
        "final_split_run": str(final_split_run),
        "gate0_manifest_status": gate0["manifest"].get("manifest_status"),
        "cohort_lock_status": gate0["cohort_lock"].get("cohort_lock_status"),
        "materialization_status": materialization.get("status"),
        "n_subjects": len(inventory["subjects"]),
        "n_sessions": len(inventory["sessions"]),
        "n_event_rows_planned": inventory["n_event_rows_planned"],
        "n_channels": len(inventory["channels"]),
        "n_all_discovered_channels": len(inventory["all_discovered_channels"]),
        "n_excluded_non_common_channels": len(inventory["excluded_non_common_channels"]),
        "n_features": len(inventory["feature_names"]),
        "feature_manifest_path": str(output_dir / "final_feature_manifest.json") if final_feature_manifest else None,
        "feature_manifest_blockers": readiness["blockers"],
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final feature schema/provenance manifest only. This run does not write feature matrices, train models, "
            "compute metrics, run leakage audits, or support Phase 1 claims."
        ),
    }
    inputs = {
        "status": "phase1_final_feature_manifest_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "dataset_root": str(dataset_root),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_feature_manifest_inputs.json"
    summary_path = output_dir / "phase1_final_feature_manifest_summary.json"
    report_path = output_dir / "phase1_final_feature_manifest_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_feature_manifest_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_feature_inventory.json", inventory)
    _write_json(output_dir / "phase1_final_feature_manifest_validation.json", validation)
    _write_json(output_dir / "phase1_final_feature_manifest_claim_state.json", claim_state)
    if final_feature_manifest is not None:
        _write_json(output_dir / "final_feature_manifest.json", final_feature_manifest)
    if blocked_record is not None:
        _write_json(output_dir / "phase1_final_feature_manifest_blocked.json", blocked_record)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, validation, source_links, claim_state, final_feature_manifest, blocked_record),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalFeatureManifestResult(
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
        "source_links": "phase1_final_split_manifest_source_links.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalFeatureManifestError(f"Final split manifest file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_final_split_boundary(split: dict[str, Any]) -> None:
    summary = split["summary"]
    validation = split["validation"]
    claim_state = split["claim_state"]
    manifest = split["manifest"]
    if summary.get("status") != "phase1_final_split_manifest_recorded":
        raise Phase1FinalFeatureManifestError("Final feature manifest requires a recorded final split manifest")
    if summary.get("split_manifest_ready") is not True:
        raise Phase1FinalFeatureManifestError("Final split manifest must be ready")
    if validation.get("status") != "phase1_final_split_manifest_validation_passed":
        raise Phase1FinalFeatureManifestError("Final split manifest validation must pass")
    if validation.get("no_subject_overlap_between_train_and_test") is not True:
        raise Phase1FinalFeatureManifestError("Final split manifest must have no train/test subject overlap")
    if manifest.get("claim_ready") is not False or claim_state.get("claim_ready") is not False:
        raise Phase1FinalFeatureManifestError("Final split manifest must keep claim_ready=false")
    if manifest.get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalFeatureManifestError("Final split manifest must not promote smoke artifacts")


def _read_gate0_run(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    cohort_lock_path = run_dir / "cohort_lock.json"
    if not manifest_path.exists():
        raise Phase1FinalFeatureManifestError(f"Gate 0 manifest not found: {manifest_path}")
    if not cohort_lock_path.exists():
        raise Phase1FinalFeatureManifestError(f"Gate 0 cohort lock not found: {cohort_lock_path}")
    return {
        "manifest": _read_json(manifest_path),
        "cohort_lock": _read_json(cohort_lock_path),
        "manifest_path": manifest_path,
        "cohort_lock_path": cohort_lock_path,
    }


def _read_materialization(gate0_run: Path) -> dict[str, Any]:
    path = gate0_run / "materialization_report.json"
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    report = _read_json(path)
    report["path"] = str(path)
    return report


def _build_feature_inventory(
    dataset_root: Path,
    split_manifest: dict[str, Any],
    manifest_config: dict[str, Any],
) -> dict[str, Any]:
    eligible_subjects = list(split_manifest.get("eligible_subjects", []))
    bands = manifest_config.get("frequency_bands_hz", {})
    channel_union: set[str] = set()
    channel_sets_by_session: dict[str, list[str]] = {}
    sessions: set[str] = set()
    channel_files = []
    events_files = []
    missing_channel_files = []
    missing_event_files = []
    event_rows_planned = 0
    event_rows_by_subject: dict[str, int] = {subject: 0 for subject in eligible_subjects}

    for subject in eligible_subjects:
        subject_dir = dataset_root / subject
        for session_dir in sorted(subject_dir.glob("ses-*")):
            if not session_dir.is_dir():
                continue
            session_id = f"{subject}/{session_dir.name}"
            sessions.add(session_id)
            channel_path = _first((session_dir / "eeg").glob("*_channels.tsv"))
            events_path = _first((session_dir / "eeg").glob("*_events.tsv"))
            if channel_path is None:
                missing_channel_files.append(session_id)
            else:
                channel_files.append(channel_path.relative_to(dataset_root).as_posix())
                session_channels = []
                for row in _read_tsv(channel_path):
                    name = str(row.get("name", "")).strip()
                    if name:
                        session_channels.append(name)
                        channel_union.add(name)
                channel_sets_by_session[session_id] = sorted(set(session_channels))
            if events_path is None:
                missing_event_files.append(session_id)
            else:
                events_files.append(events_path.relative_to(dataset_root).as_posix())
                selected = _load_binary_load_events(events_path, manifest_config)
                event_rows_planned += len(selected)
                event_rows_by_subject[subject] += len(selected)

    if channel_sets_by_session:
        common_channels = set(next(iter(channel_sets_by_session.values())))
        for session_channels in channel_sets_by_session.values():
            common_channels &= set(session_channels)
    else:
        common_channels = set()
    channel_list = sorted(common_channels)
    band_names = sorted(bands)
    feature_names = [manifest_config.get("feature_name_template", "{channel}:{band}").format(channel=channel, band=band) for channel in channel_list for band in band_names]
    excluded_channels = sorted(channel_union - common_channels)
    channel_availability = {
        channel: sorted(session for session, session_channels in channel_sets_by_session.items() if channel in session_channels)
        for channel in sorted(channel_union)
    }
    return {
        "status": "phase1_final_feature_inventory_recorded",
        "dataset_root": str(dataset_root),
        "subjects": eligible_subjects,
        "sessions": sorted(sessions),
        "channels": channel_list,
        "channel_selection_policy": "intersection_across_final_sessions",
        "all_discovered_channels": sorted(channel_union),
        "excluded_non_common_channels": excluded_channels,
        "channel_availability_by_session": channel_sets_by_session,
        "channel_availability": channel_availability,
        "frequency_bands_hz": bands,
        "feature_names": feature_names,
        "n_event_rows_planned": event_rows_planned,
        "event_rows_by_subject": event_rows_by_subject,
        "channel_files": sorted(channel_files),
        "events_files": sorted(events_files),
        "missing_channel_files": missing_channel_files,
        "missing_event_files": missing_event_files,
        "contains_feature_matrix": False,
        "scientific_limit": "Inventory records feature schema/provenance only; it does not contain feature values.",
    }


def _load_binary_load_events(events_path: Path, manifest_config: dict[str, Any]) -> list[dict[str, str]]:
    rows = _read_tsv(events_path)
    allowed_artifact = {str(value) for value in manifest_config.get("trial_filter", {}).get("artifact_values_allowed", [])}
    allowed_set_sizes = {int(value) for value in manifest_config.get("trial_filter", {}).get("set_size_values_allowed", [])}
    selected = []
    for row in rows:
        artifact = str(row.get("Artifact", ""))
        if artifact not in allowed_artifact:
            continue
        try:
            set_size = int(float(str(row.get("SetSize"))))
        except (TypeError, ValueError):
            continue
        if set_size not in allowed_set_sizes:
            continue
        selected.append(row)
    return selected


def _validate_feature_manifest_inputs(
    *,
    split: dict[str, Any],
    gate0: dict[str, Any],
    materialization: dict[str, Any],
    dataset_root: Path,
    inventory: dict[str, Any],
    manifest_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    required = manifest_config.get("required_inputs", {})
    if split["summary"].get("split_manifest_ready") is not required.get("final_split_manifest_ready"):
        blockers.append("final_split_manifest_not_ready")
    if gate0["manifest"].get("manifest_status") != required.get("gate0_manifest_status"):
        blockers.append("gate0_manifest_not_signal_audit_ready")
    if gate0["cohort_lock"].get("cohort_lock_status") != required.get("cohort_lock_status"):
        blockers.append("cohort_lock_not_signal_audit_ready")
    if materialization.get("status") != required.get("materialization_status"):
        blockers.append("materialization_not_complete")
    if required.get("dataset_root_exists") and not dataset_root.exists():
        blockers.append("dataset_root_missing")
    if not inventory["subjects"]:
        blockers.append("no_split_subjects_available")
    if not inventory["all_discovered_channels"]:
        blockers.append("no_eeg_channels_discovered")
    if not inventory["channels"]:
        blockers.append("no_common_eeg_channels_across_final_sessions")
    if not inventory["feature_names"]:
        blockers.append("no_feature_names_discovered")
    if inventory["missing_channel_files"]:
        blockers.append("missing_eeg_channel_sidecars")
    if inventory["missing_event_files"]:
        blockers.append("missing_eeg_event_files")
    if inventory["n_event_rows_planned"] <= 0:
        blockers.append("no_binary_load_event_rows_planned")
    if any(count <= 0 for count in inventory["event_rows_by_subject"].values()):
        blockers.append("one_or_more_subjects_have_no_binary_load_event_rows")

    return {
        "status": "phase1_final_feature_manifest_input_validation_passed" if not blockers else "phase1_final_feature_manifest_input_validation_blocked",
        "feature_manifest_ready": not blockers,
        "split_manifest_ready": split["summary"].get("split_manifest_ready"),
        "gate0_manifest_status": gate0["manifest"].get("manifest_status"),
        "cohort_lock_status": gate0["cohort_lock"].get("cohort_lock_status"),
        "materialization_status": materialization.get("status"),
        "dataset_root_exists": dataset_root.exists(),
        "n_subjects": len(inventory["subjects"]),
        "n_sessions": len(inventory["sessions"]),
        "n_channels": len(inventory["channels"]),
        "n_all_discovered_channels": len(inventory["all_discovered_channels"]),
        "n_excluded_non_common_channels": len(inventory["excluded_non_common_channels"]),
        "n_features": len(inventory["feature_names"]),
        "n_event_rows_planned": inventory["n_event_rows_planned"],
        "blockers": _unique(blockers),
    }


def _build_final_feature_manifest(
    *,
    timestamp: str,
    manifest_config: dict[str, Any],
    readiness_config: dict[str, Any],
    inventory: dict[str, Any],
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    split: dict[str, Any],
    gate0_run: Path,
    gate0: dict[str, Any],
    materialization: dict[str, Any],
    dataset_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase1_final_feature_manifest_recorded",
        "created_utc": timestamp,
        "feature_manifest_id": manifest_config.get("manifest_id"),
        "feature_set_id": manifest_config.get("feature_set_id"),
        "feature_family": manifest_config.get("feature_family"),
        "feature_name_template": manifest_config.get("feature_name_template"),
        "feature_count": len(inventory["feature_names"]),
        "feature_names": inventory["feature_names"],
        "channel_count": len(inventory["channels"]),
        "channels": inventory["channels"],
        "channel_selection_policy": inventory["channel_selection_policy"],
        "all_discovered_channels": inventory["all_discovered_channels"],
        "excluded_non_common_channels": inventory["excluded_non_common_channels"],
        "channel_availability": inventory["channel_availability"],
        "frequency_bands_hz": manifest_config.get("frequency_bands_hz", {}),
        "signal_windows_sec": manifest_config.get("signal_windows_sec", {}),
        "trial_filter": manifest_config.get("trial_filter", {}),
        "feature_extraction_policy": manifest_config.get("feature_extraction_policy", {}),
        "manifest_boundary": manifest_config.get("manifest_boundary", {}),
        "source_prereg_bundle": str(prereg_bundle),
        "source_prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "source_final_split_run": str(final_split_run),
        "source_final_split_manifest_status": split["manifest"].get("status"),
        "source_gate0_run": str(gate0_run),
        "source_gate0_manifest": str(gate0["manifest_path"]),
        "source_cohort_lock": str(gate0["cohort_lock_path"]),
        "source_dataset_root": str(dataset_root),
        "source_materialization_report": materialization.get("path"),
        "source_gate0_manifest_status": gate0["manifest"].get("manifest_status"),
        "source_cohort_lock_status": gate0["cohort_lock"].get("cohort_lock_status"),
        "source_materialization_status": materialization.get("status"),
        "subjects": inventory["subjects"],
        "sessions": inventory["sessions"],
        "n_event_rows_planned": inventory["n_event_rows_planned"],
        "event_rows_by_subject": inventory["event_rows_by_subject"],
        "channel_files": inventory["channel_files"],
        "events_files": inventory["events_files"],
        "readiness_required_schema": readiness_config.get("feature_manifest_schema", {}),
        "contains_feature_matrix": False,
        "contains_model_outputs": False,
        "contains_metrics": False,
        "claim_ready": False,
        "standalone_claim_ready": False,
        "smoke_feature_rows_allowed_as_final": False,
        "scientific_limit": (
            "This final feature manifest records schema/provenance only. It does not contain feature values, "
            "model outputs, metrics, leakage audits, controls, calibration, influence or reports."
        ),
    }


def _validate_final_feature_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    if manifest.get("contains_feature_matrix") is not False:
        blockers.append("feature_manifest_contains_feature_matrix")
    if manifest.get("contains_model_outputs") is not False:
        blockers.append("feature_manifest_contains_model_outputs")
    if manifest.get("contains_metrics") is not False:
        blockers.append("feature_manifest_contains_metrics")
    if manifest.get("claim_ready") is not False:
        blockers.append("feature_manifest_claim_ready_not_false")
    if manifest.get("smoke_feature_rows_allowed_as_final") is not False:
        blockers.append("smoke_feature_rows_allowed_as_final")
    if int(manifest.get("feature_count", 0)) != len(manifest.get("feature_names", [])):
        blockers.append("feature_count_does_not_match_feature_names")
    if int(manifest.get("feature_count", 0)) <= 0:
        blockers.append("feature_count_not_positive")
    return {
        "status": "phase1_final_feature_manifest_validation_passed" if not blockers else "phase1_final_feature_manifest_validation_failed",
        "feature_manifest_ready": not blockers,
        "feature_set_id": manifest.get("feature_set_id"),
        "feature_count": manifest.get("feature_count"),
        "channel_count": manifest.get("channel_count"),
        "n_subjects": len(manifest.get("subjects", [])),
        "n_sessions": len(manifest.get("sessions", [])),
        "contains_feature_matrix": manifest.get("contains_feature_matrix"),
        "contains_model_outputs": manifest.get("contains_model_outputs"),
        "contains_metrics": manifest.get("contains_metrics"),
        "smoke_feature_rows_allowed_as_final": manifest.get("smoke_feature_rows_allowed_as_final"),
        "blockers": blockers,
        "scientific_limit": "Validation covers feature schema/provenance only; it is not model evidence.",
    }


def _blocked_validation(
    readiness: dict[str, Any],
    inventory: dict[str, Any],
    manifest_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_feature_manifest_validation_blocked",
        "feature_manifest_ready": False,
        "feature_set_id": manifest_config.get("feature_set_id"),
        "feature_count": len(inventory["feature_names"]),
        "channel_count": len(inventory["channels"]),
        "n_subjects": len(inventory["subjects"]),
        "n_sessions": len(inventory["sessions"]),
        "contains_feature_matrix": False,
        "contains_model_outputs": False,
        "contains_metrics": False,
        "smoke_feature_rows_allowed_as_final": False,
        "blockers": readiness["blockers"],
        "scientific_limit": "No final feature manifest was written because prerequisites are not met.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    final_split_run: Path,
    split: dict[str, Any],
    gate0_run: Path,
    gate0: dict[str, Any],
    dataset_root: Path,
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    split_manifest_path = final_split_run / "final_split_manifest.json"
    return {
        "status": "phase1_final_feature_manifest_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "final_split_run": str(final_split_run),
        "final_split_manifest": str(split_manifest_path),
        "final_split_manifest_sha256": _sha256(split_manifest_path),
        "final_split_validation_status": split["validation"].get("status"),
        "gate0_run": str(gate0_run),
        "gate0_manifest": str(gate0["manifest_path"]),
        "gate0_manifest_sha256": _sha256(gate0["manifest_path"]),
        "cohort_lock": str(gate0["cohort_lock_path"]),
        "cohort_lock_sha256": _sha256(gate0["cohort_lock_path"]),
        "dataset_root": str(dataset_root),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links document provenance for the final feature manifest only.",
    }


def _build_claim_state(
    manifest_config: dict[str, Any],
    feature_ready: bool,
    feature_blockers: list[str],
) -> dict[str, Any]:
    blockers = list(feature_blockers)
    if feature_ready:
        blockers.extend(
            [
                "final_leakage_audit_missing",
                "final_comparator_outputs_not_claim_evaluable",
                "headline_claim_blocked_until_full_package_passes",
            ]
        )
    else:
        blockers.append("final_feature_manifest_missing")
        blockers.append("claim_blocked_until_final_feature_manifest_exists")
    return {
        "status": "phase1_final_feature_manifest_claim_state_blocked",
        "feature_manifest_ready": feature_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "standalone_claim_ready": manifest_config.get("manifest_boundary", {}).get("standalone_claim_ready", False),
        "smoke_artifacts_promoted": False,
        "remaining_required_manifests_after_feature": manifest_config.get("remaining_required_manifests_after_feature", []),
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": (
            "A final feature schema/provenance manifest exists and may be used as an input contract for final feature extraction/comparator runners."
            if feature_ready
            else "Final feature manifest generation is blocked until required provenance inputs are complete."
        ),
    }


def _build_blocked_record(
    readiness: dict[str, Any],
    inventory: dict[str, Any],
    manifest_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_feature_manifest_not_written",
        "reason": "Final feature manifest prerequisites are not met.",
        "feature_set_id": manifest_config.get("feature_set_id"),
        "inventory_status": inventory.get("status"),
        "n_candidate_features": len(inventory["feature_names"]),
        "n_candidate_event_rows": inventory["n_event_rows_planned"],
        "blockers": readiness["blockers"],
        "scientific_limit": "Blocked record is not a final feature manifest and must not be used by final comparator runners.",
    }


def _render_report(
    summary: dict[str, Any],
    validation: dict[str, Any],
    source_links: dict[str, Any],
    claim_state: dict[str, Any],
    final_feature_manifest: dict[str, Any] | None,
    blocked_record: dict[str, Any] | None,
) -> str:
    lines = [
        "# Phase 1 Final Feature Manifest",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Feature manifest ready: `{summary['feature_manifest_ready']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Gate 0 manifest status: `{summary['gate0_manifest_status']}`",
        f"- Cohort lock status: `{summary['cohort_lock_status']}`",
        f"- Materialization status: `{summary['materialization_status']}`",
        f"- Subjects: `{summary['n_subjects']}`",
        f"- Sessions: `{summary['n_sessions']}`",
        f"- Common channels used: `{summary['n_channels']}`",
        f"- All discovered channels: `{summary.get('n_all_discovered_channels', 0)}`",
        f"- Excluded non-common channels: `{summary.get('n_excluded_non_common_channels', 0)}`",
        f"- Features: `{summary['n_features']}`",
        f"- Planned binary load event rows: `{summary['n_event_rows_planned']}`",
        "",
        "## Source Links",
        "",
        f"- Prereg hash: `{source_links.get('locked_prereg_bundle_hash')}`",
        f"- Final split validation status: `{source_links.get('final_split_validation_status')}`",
        f"- Final split manifest SHA256: `{source_links.get('final_split_manifest_sha256')}`",
        f"- Gate 0 manifest SHA256: `{source_links.get('gate0_manifest_sha256')}`",
        f"- Cohort lock SHA256: `{source_links.get('cohort_lock_sha256')}`",
        "",
        "## Validation",
        "",
        f"- Validation status: `{validation['status']}`",
        f"- Contains feature matrix: `{validation['contains_feature_matrix']}`",
        f"- Contains model outputs: `{validation['contains_model_outputs']}`",
        f"- Contains metrics: `{validation['contains_metrics']}`",
        f"- Smoke feature rows allowed as final: `{validation['smoke_feature_rows_allowed_as_final']}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Output Boundary", ""])
    if final_feature_manifest is not None:
        lines.append("- `final_feature_manifest.json` was written as a schema/provenance artifact.")
    if blocked_record is not None:
        lines.append("- `final_feature_manifest.json` was not written because prerequisites are blocked.")
    lines.append("- This run does not write feature matrices, run leakage audits, train models, compute metrics or open claims.")
    lines.append("- Smoke feature rows remain non-claim diagnostics and cannot satisfy final evidence requirements.")
    lines.extend(["", "## Not OK To Claim", ""])
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _first(paths: Any) -> Path | None:
    for path in paths:
        return path
    return None


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
