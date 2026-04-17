"""Gate 0 metadata audit for the ds004752 BIDS snapshot."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .materialization import build_materialization_report, payload_state_from_report
from .signal import run_signal_audit

CORE_EVENT_FIELDS = (
    "nTrial",
    "duration",
    "SetSize",
    "ProbeLetter",
    "Match",
    "Correct",
    "ResponseTime",
    "Artifact",
)


@dataclass(frozen=True)
class AuditResult:
    output_dir: Path
    manifest_path: Path
    cohort_lock_path: Path
    audit_report_path: Path
    override_log_path: Path
    bridge_availability_path: Path
    materialization_report_path: Path
    manifest: dict[str, Any]


def run_gate0_audit(
    dataset_root: str | Path,
    output_root: str | Path,
    include_signal: bool = False,
    signal_max_sessions: int = 4,
    signal_subjects: list[str] | None = None,
    signal_sessions: list[str] | None = None,
) -> AuditResult:
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    dataset_description = _read_json(dataset_root / "dataset_description.json")
    participants = _read_tsv(dataset_root / "participants.tsv")
    file_inventory = _file_inventory(dataset_root)
    subject_inventory = _subject_inventory(dataset_root)
    events_audit = _events_audit(dataset_root)
    sidecar_audit = _sidecar_audit(dataset_root)
    materialization_report = build_materialization_report(dataset_root)
    payload_state = payload_state_from_report(materialization_report)
    bridge_availability = _bridge_availability(dataset_root, materialization_report)
    signal_audit = run_signal_audit(
        dataset_root,
        signal_max_sessions,
        subjects=signal_subjects,
        sessions=signal_sessions,
    ) if include_signal else {
        "status": "not_requested"
    }

    manifest: dict[str, Any] = {
        "manifest_status": _manifest_status(include_signal, signal_audit),
        "created_utc": timestamp,
        "dataset_root": str(dataset_root),
        "dataset_identity": {
            "name": dataset_description.get("Name"),
            "bids_version": dataset_description.get("BIDSVersion"),
            "dataset_type": dataset_description.get("DatasetType"),
            "license": dataset_description.get("License"),
            "dataset_doi": dataset_description.get("DatasetDOI"),
        },
        "participants": {
            "n_raw_public": len(participants),
            "n_primary_eligible": None,
            "primary_eligibility_status": "not_locked_pending_signal_level_gate0",
        },
        "file_inventory": file_inventory,
        "payload_state": payload_state,
        "materialization": {
            "status": materialization_report["status"],
            "datalad_get_suggestions": materialization_report["datalad_get_suggestions"],
        },
        "subjects": subject_inventory,
        "events_audit": events_audit,
        "sidecar_audit": sidecar_audit,
        "signal_audit": signal_audit,
        "derivatives": {
            "bridge_availability_status": "pointer_level_only"
            if payload_state["mat"]["pointer_like_count"]
            else "materialized_or_unknown",
            "beamforming_subjects_with_files": bridge_availability["subjects_with_beamforming_pointer"],
        },
        "gate0_blockers": _gate0_blockers(payload_state, events_audit, signal_audit),
    }

    cohort_lock = _cohort_lock(manifest, participants)

    manifest_path = output_dir / "manifest.json"
    cohort_lock_path = output_dir / "cohort_lock.json"
    audit_report_path = output_dir / "audit_report.md"
    override_log_path = output_dir / "override_log.md"
    bridge_availability_path = output_dir / "bridge_availability.json"
    materialization_report_path = output_dir / "materialization_report.json"

    _write_json(manifest_path, manifest)
    _write_json(cohort_lock_path, cohort_lock)
    _write_json(bridge_availability_path, bridge_availability)
    _write_json(materialization_report_path, materialization_report)
    audit_report_path.write_text(_render_audit_report(manifest), encoding="utf-8")
    override_log_path.write_text(_render_override_log(timestamp), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return AuditResult(
        output_dir=output_dir,
        manifest_path=manifest_path,
        cohort_lock_path=cohort_lock_path,
        audit_report_path=audit_report_path,
        override_log_path=override_log_path,
        bridge_availability_path=bridge_availability_path,
        materialization_report_path=materialization_report_path,
        manifest=manifest,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _file_inventory(dataset_root: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for path in dataset_root.rglob("*"):
        if path.is_file():
            suffix = path.suffix.lower() or "<no_extension>"
            counts[suffix] = counts.get(suffix, 0) + 1
    return {
        "by_extension": dict(sorted(counts.items())),
        "total_files": sum(counts.values()),
    }


def _subject_inventory(dataset_root: Path) -> dict[str, Any]:
    subjects: dict[str, Any] = {}
    for sub_dir in sorted(dataset_root.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        sessions: dict[str, Any] = {}
        for ses_dir in sorted(sub_dir.glob("ses-*")):
            if not ses_dir.is_dir():
                continue
            sessions[ses_dir.name] = {
                "eeg_runs": len(list((ses_dir / "eeg").glob("*_eeg.edf"))),
                "ieeg_runs": len(list((ses_dir / "ieeg").glob("*_ieeg.edf"))),
                "eeg_events": len(list((ses_dir / "eeg").glob("*_events.tsv"))),
                "ieeg_events": len(list((ses_dir / "ieeg").glob("*_events.tsv"))),
                "ieeg_electrodes": len(list((ses_dir / "ieeg").glob("*_electrodes.tsv"))),
            }
        subjects[sub_dir.name] = {
            "n_sessions": len(sessions),
            "sessions": sessions,
        }
    return {
        "n_subjects": len(subjects),
        "n_sessions": sum(item["n_sessions"] for item in subjects.values()),
        "by_subject": subjects,
    }


def _events_audit(dataset_root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    mismatch_count = 0
    trial_count_mismatches: list[dict[str, Any]] = []
    content_mismatches: list[dict[str, Any]] = []
    eeg_trials_total = 0
    ieeg_trials_total = 0
    artifact_trials_total = 0
    correct_trials_total = 0

    for ses_dir in sorted(dataset_root.glob("sub-*/ses-*")):
        sub_id = ses_dir.parent.name
        ses_id = ses_dir.name
        eeg_events_path = _first((ses_dir / "eeg").glob("*_events.tsv"))
        ieeg_events_path = _first((ses_dir / "ieeg").glob("*_events.tsv"))
        eeg_events = _read_tsv(eeg_events_path) if eeg_events_path else []
        ieeg_events = _read_tsv(ieeg_events_path) if ieeg_events_path else []
        eeg_count = len(eeg_events)
        ieeg_count = len(ieeg_events)
        eeg_trials_total += eeg_count
        ieeg_trials_total += ieeg_count
        artifact_trials_total += sum(1 for event in eeg_events if event.get("Artifact") == "1")
        correct_trials_total += sum(1 for event in eeg_events if event.get("Correct") == "1")
        if eeg_count != ieeg_count:
            trial_count_mismatches.append(
                {"subject": sub_id, "session": ses_id, "eeg_trials": eeg_count, "ieeg_trials": ieeg_count}
            )
        for idx, (eeg_event, ieeg_event) in enumerate(zip(eeg_events, ieeg_events), start=1):
            for field in CORE_EVENT_FIELDS:
                if eeg_event.get(field) != ieeg_event.get(field):
                    mismatch_count += 1
                    if len(content_mismatches) < 20:
                        content_mismatches.append(
                            {
                                "subject": sub_id,
                                "session": ses_id,
                                "row": idx,
                                "field": field,
                                "eeg": eeg_event.get(field),
                                "ieeg": ieeg_event.get(field),
                            }
                        )
        rows.append(
            {
                "subject": sub_id,
                "session": ses_id,
                "eeg_trials": eeg_count,
                "ieeg_trials": ieeg_count,
                "artifact_trials": sum(1 for event in eeg_events if event.get("Artifact") == "1"),
                "correct_trials": sum(1 for event in eeg_events if event.get("Correct") == "1"),
            }
        )

    return {
        "sessions_checked": len(rows),
        "eeg_trials_total": eeg_trials_total,
        "ieeg_trials_total": ieeg_trials_total,
        "artifact_trials_total_from_eeg_events": artifact_trials_total,
        "correct_trials_total_from_eeg_events": correct_trials_total,
        "sessions_with_mismatched_trial_counts": len(trial_count_mismatches),
        "trial_count_mismatches": trial_count_mismatches,
        "core_field_mismatch_count": mismatch_count,
        "core_field_mismatch_examples": content_mismatches,
        "core_fields_compared": list(CORE_EVENT_FIELDS),
        "session_rows": rows,
    }


def _sidecar_audit(dataset_root: Path) -> dict[str, Any]:
    channel_sampling: dict[str, int] = {}
    channel_types: dict[str, int] = {}
    no_label_found = 0
    electrode_rows = 0

    for channels_path in dataset_root.glob("sub-*/ses-*/*/*_channels.tsv"):
        for row in _read_tsv(channels_path):
            sfreq = row.get("sampling_frequency", "")
            channel_sampling[sfreq] = channel_sampling.get(sfreq, 0) + 1
            channel_type = row.get("type", "")
            channel_types[channel_type] = channel_types.get(channel_type, 0) + 1

    for electrodes_path in dataset_root.glob("sub-*/ses-*/ieeg/*_electrodes.tsv"):
        for row in _read_tsv(electrodes_path):
            electrode_rows += 1
            if row.get("AnatomicalLocation") == "no_label_found":
                no_label_found += 1

    return {
        "channel_sampling_frequency_counts": dict(sorted(channel_sampling.items())),
        "channel_type_counts": dict(sorted(channel_types.items())),
        "electrode_rows": electrode_rows,
        "electrodes_with_no_label_found": no_label_found,
    }


def _bridge_availability(dataset_root: Path, materialization_report: dict[str, Any]) -> dict[str, Any]:
    rows = []
    mat_payloads_by_path = {
        record["relative_path"]: record
        for record in (
            materialization_report.get("payloads", {})
            .get("mat", {})
            .get("missing_examples", [])
            + materialization_report.get("payloads", {})
            .get("mat", {})
            .get("materialized_examples", [])
        )
    }
    for sub_dir in sorted(dataset_root.glob("sub-*")):
        if not sub_dir.is_dir():
            continue
        mat_files = sorted((dataset_root / "derivatives" / sub_dir.name / "beamforming").glob("*.mat"))
        mat_payloads = [mat_payloads_by_path.get(path.relative_to(dataset_root).as_posix()) for path in mat_files]
        rows.append(
            {
                "subject": sub_dir.name,
                "beamforming_files": [path.relative_to(dataset_root).as_posix() for path in mat_files],
                "n_beamforming_files": len(mat_files),
                "all_files_pointer_like": all(
                    payload is not None and not payload["materialized"] for payload in mat_payloads
                ) if mat_files else False,
            }
        )
    return {
        "status": "pointer_level_inventory",
        "subjects_with_beamforming_pointer": sum(1 for row in rows if row["n_beamforming_files"] > 0),
        "subjects": rows,
    }


def _manifest_status(include_signal: bool, signal_audit: dict[str, Any]) -> str:
    if not include_signal:
        return "draft_metadata_only"
    if signal_audit.get("status") == "ok":
        return "draft_metadata_plus_signal_sample"
    return "draft_metadata_signal_attempted"


def _gate0_blockers(
    payload_state: dict[str, Any],
    events_audit: dict[str, Any],
    signal_audit: dict[str, Any],
) -> list[str]:
    blockers = []
    if payload_state["edf"]["pointer_like_count"]:
        blockers.append("edf_payloads_not_materialized")
    if payload_state["mat"]["pointer_like_count"]:
        blockers.append("mat_derivatives_not_materialized")
    if events_audit["core_field_mismatch_count"]:
        blockers.append("eeg_ieeg_event_core_field_mismatches")
    if signal_audit.get("status") in {"dependency_missing", "failed"}:
        blockers.append("signal_level_audit_not_passed")
    blockers.append("cohort_lock_is_draft_until_signal_level_audit")
    return blockers


def _cohort_lock(manifest: dict[str, Any], participants: list[dict[str, str]]) -> dict[str, Any]:
    by_subject = manifest["subjects"]["by_subject"]
    return {
        "cohort_lock_status": "draft_not_primary_locked",
        "reason": "Signal-level payloads are not materialized; primary eligibility cannot be locked.",
        "participants": [
            {
                "participant_id": row.get("participant_id"),
                "age": row.get("age"),
                "sex": row.get("sex"),
                "pathology": row.get("pathology"),
                "n_sessions": by_subject.get(row.get("participant_id"), {}).get("n_sessions", 0),
                "metadata_present": row.get("participant_id") in by_subject,
                "primary_eligible": None,
            }
            for row in participants
        ],
    }


def _render_audit_report(manifest: dict[str, Any]) -> str:
    identity = manifest["dataset_identity"]
    events = manifest["events_audit"]
    payload = manifest["payload_state"]
    subjects = manifest["subjects"]
    sidecar = manifest["sidecar_audit"]
    signal = manifest["signal_audit"]
    materialization = manifest["materialization"]
    blockers = "\n".join(f"- {item}" for item in manifest["gate0_blockers"])
    return f"""# Gate 0 audit report

Created UTC: {manifest["created_utc"]}

## Dataset identity

- Name: {identity.get("name")}
- DOI: {identity.get("dataset_doi")}
- BIDS version: {identity.get("bids_version")}
- Dataset type: {identity.get("dataset_type")}
- License: {identity.get("license")}

## Inventory summary

- Subjects: {subjects["n_subjects"]}
- Sessions: {subjects["n_sessions"]}
- EEG event trials: {events["eeg_trials_total"]}
- iEEG event trials: {events["ieeg_trials_total"]}
- Sessions with trial-count mismatch: {events["sessions_with_mismatched_trial_counts"]}
- Core EEG/iEEG event field mismatches: {events["core_field_mismatch_count"]}
- Artifact trials from EEG events: {events["artifact_trials_total_from_eeg_events"]}
- Correct trials from EEG events: {events["correct_trials_total_from_eeg_events"]}

## Payload state

- EDF files: {payload["edf"]["count"]}, pointer-like: {payload["edf"]["pointer_like_count"]}
- MAT files: {payload["mat"]["count"]}, pointer-like: {payload["mat"]["pointer_like_count"]}
- Materialization status: {materialization["status"]}

## Sidecar summary

- Channel sampling frequencies: {sidecar["channel_sampling_frequency_counts"]}
- Channel types: {sidecar["channel_type_counts"]}
- Electrode rows: {sidecar["electrode_rows"]}
- Electrodes with no_label_found: {sidecar["electrodes_with_no_label_found"]}

## Gate 0 blockers

{blockers}

## Signal audit

- Status: {signal.get("status")}
- Sessions checked: {signal.get("sessions_checked", 0)}
- MAT files checked: {signal.get("mat_files_checked", 0)}

## Conclusion

Metadata-level Gate 0 audit is complete. Primary cohort lock and
signal-level freeze remain blocked until EDF/MAT payloads are materialized.
"""


def _render_override_log(timestamp: str) -> str:
    return f"""# Override log

Created UTC: {timestamp}

No overrides recorded.
"""


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(_json_safe(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    latest = output_root / "latest.txt"
    latest.write_text(str(output_dir.resolve()) + "\n", encoding="utf-8")


def _first(paths: Any) -> Path | None:
    for path in paths:
        return path
    return None
