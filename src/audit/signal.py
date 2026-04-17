"""Optional signal-level audit for materialized EDF/MAT payloads."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from typing import Any


def run_signal_audit(
    dataset_root: str | Path,
    max_sessions: int = 4,
    subjects: list[str] | None = None,
    sessions: list[str] | None = None,
) -> dict[str, Any]:
    dataset_root = Path(dataset_root)
    missing = _missing_dependencies()
    if missing:
        return {
            "status": "dependency_missing",
            "missing_dependencies": missing,
            "message": "Install signal extras before EDF/MAT audit.",
        }

    import mne  # type: ignore
    import scipy.io  # type: ignore

    selected_sessions = _select_session_dirs(dataset_root, subjects, sessions)

    session_results = []
    for ses_dir in selected_sessions:
        if len(session_results) >= max_sessions:
            break
        session_results.append(_audit_session(dataset_root, ses_dir, mne))

    mat_results = []
    for mat_path in _select_mat_paths(dataset_root, subjects)[:max_sessions]:
        mat_results.append(_audit_mat(dataset_root, mat_path, scipy.io))

    blockers = []
    for session in session_results:
        if session["status"] != "ok":
            blockers.append(f"signal_audit_failed:{session['subject']}:{session['session']}")
    for mat in mat_results:
        if mat["status"] != "ok":
            blockers.append(f"mat_audit_failed:{mat['relative_path']}")

    return {
        "status": "ok" if not blockers else "failed",
        "max_sessions": max_sessions,
        "subject_filter": subjects or [],
        "session_filter": sessions or [],
        "candidate_sessions": len(selected_sessions),
        "sessions_checked": len(session_results),
        "session_results": session_results,
        "mat_files_checked": len(mat_results),
        "mat_results": mat_results,
        "blockers": blockers,
    }


def _select_session_dirs(
    dataset_root: Path,
    subjects: list[str] | None,
    sessions: list[str] | None,
) -> list[Path]:
    subject_filter = set(subjects or [])
    session_filter = set(sessions or [])
    session_dirs = []
    for ses_dir in sorted(dataset_root.glob("sub-*/ses-*")):
        if subject_filter and ses_dir.parent.name not in subject_filter:
            continue
        if session_filter and ses_dir.name not in session_filter:
            continue
        session_dirs.append(ses_dir)
    return session_dirs


def _select_mat_paths(dataset_root: Path, subjects: list[str] | None) -> list[Path]:
    subject_filter = set(subjects or [])
    mat_paths = []
    for mat_path in sorted(dataset_root.glob("derivatives/sub-*/beamforming/*.mat")):
        subject = mat_path.parents[1].name
        if subject_filter and subject not in subject_filter:
            continue
        mat_paths.append(mat_path)
    return mat_paths


def _missing_dependencies() -> list[str]:
    missing = []
    if importlib.util.find_spec("mne") is None:
        missing.append("mne")
    if importlib.util.find_spec("scipy") is None:
        missing.append("scipy")
    return missing


def _audit_session(dataset_root: Path, ses_dir: Path, mne: Any) -> dict[str, Any]:
    sub_id = ses_dir.parent.name
    ses_id = ses_dir.name
    eeg_path = _first((ses_dir / "eeg").glob("*_eeg.edf"))
    ieeg_path = _first((ses_dir / "ieeg").glob("*_ieeg.edf"))
    eeg_events_path = _first((ses_dir / "eeg").glob("*_events.tsv"))
    ieeg_events_path = _first((ses_dir / "ieeg").glob("*_events.tsv"))

    if not eeg_path or not ieeg_path or not eeg_events_path or not ieeg_events_path:
        return {
            "status": "missing_file",
            "subject": sub_id,
            "session": ses_id,
        }

    try:
        eeg_raw = mne.io.read_raw_edf(eeg_path, preload=False, verbose="ERROR")
        ieeg_raw = mne.io.read_raw_edf(ieeg_path, preload=False, verbose="ERROR")
    except Exception as exc:
        return {
            "status": "read_error",
            "subject": sub_id,
            "session": ses_id,
            "error": str(exc),
        }

    eeg_events = _read_tsv(eeg_events_path)
    ieeg_events = _read_tsv(ieeg_events_path)
    eeg_alignment = _check_event_sample_ranges(eeg_events, eeg_raw.n_times)
    ieeg_alignment = _check_event_sample_ranges(ieeg_events, ieeg_raw.n_times)
    status = "ok" if eeg_alignment["status"] == "ok" and ieeg_alignment["status"] == "ok" else "failed"

    return {
        "status": status,
        "subject": sub_id,
        "session": ses_id,
        "eeg": {
            "relative_path": str(eeg_path.relative_to(dataset_root)),
            "sfreq": eeg_raw.info["sfreq"],
            "n_channels": len(eeg_raw.ch_names),
            "n_times": eeg_raw.n_times,
            "duration_sec": eeg_raw.n_times / eeg_raw.info["sfreq"],
            "event_alignment": eeg_alignment,
        },
        "ieeg": {
            "relative_path": str(ieeg_path.relative_to(dataset_root)),
            "sfreq": ieeg_raw.info["sfreq"],
            "n_channels": len(ieeg_raw.ch_names),
            "n_times": ieeg_raw.n_times,
            "duration_sec": ieeg_raw.n_times / ieeg_raw.info["sfreq"],
            "event_alignment": ieeg_alignment,
        },
    }


def _audit_mat(dataset_root: Path, mat_path: Path, scipy_io: Any) -> dict[str, Any]:
    try:
        data = scipy_io.loadmat(mat_path, simplify_cells=True)
    except Exception as exc:
        return {
            "status": "read_error",
            "relative_path": str(mat_path.relative_to(dataset_root)),
            "size_bytes": mat_path.resolve().stat().st_size,
            "error": str(exc),
        }

    public_keys = sorted(key for key in data.keys() if not key.startswith("__"))
    return {
        "status": "ok",
        "relative_path": str(mat_path.relative_to(dataset_root)),
        "size_bytes": mat_path.resolve().stat().st_size,
        "top_level_keys": public_keys,
    }


def _check_event_sample_ranges(events: list[dict[str, str]], n_times: int) -> dict[str, Any]:
    invalid = []
    for index, event in enumerate(events, start=1):
        try:
            beg = int(float(event["begSample"]))
            end = int(float(event["endSample"]))
        except (KeyError, ValueError):
            invalid.append({"row": index, "reason": "invalid_sample_fields"})
            continue
        if beg < 1 or end < beg or end > n_times:
            invalid.append({"row": index, "begSample": beg, "endSample": end, "n_times": n_times})
    return {
        "status": "ok" if not invalid else "failed",
        "n_events": len(events),
        "invalid_count": len(invalid),
        "invalid_examples": invalid[:20],
    }


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _first(paths: Any) -> Path | None:
    for path in paths:
        return path
    return None
