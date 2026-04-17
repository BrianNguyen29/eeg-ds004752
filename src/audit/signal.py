"""Optional signal-level audit for materialized EDF/MAT payloads."""

from __future__ import annotations

import csv
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EdfInfo:
    sfreq: float
    n_channels: int
    n_times: int
    duration_sec: float
    source: str
    warning: str | None = None


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
        eeg_info = _read_edf_info(eeg_path, mne)
        ieeg_info = _read_edf_info(ieeg_path, mne)
    except Exception as exc:
        return {
            "status": "read_error",
            "subject": sub_id,
            "session": ses_id,
            "error": str(exc),
        }

    eeg_events = _read_tsv(eeg_events_path)
    ieeg_events = _read_tsv(ieeg_events_path)
    eeg_alignment = _check_event_sample_ranges(eeg_events, eeg_info.n_times)
    ieeg_alignment = _check_event_sample_ranges(ieeg_events, ieeg_info.n_times)
    status = "ok" if eeg_alignment["status"] == "ok" and ieeg_alignment["status"] == "ok" else "failed"

    return {
        "status": status,
        "subject": sub_id,
        "session": ses_id,
        "eeg": {
            "relative_path": str(eeg_path.relative_to(dataset_root)),
            "sfreq": eeg_info.sfreq,
            "n_channels": eeg_info.n_channels,
            "n_times": eeg_info.n_times,
            "duration_sec": eeg_info.duration_sec,
            "reader": eeg_info.source,
            "reader_warning": eeg_info.warning,
            "event_alignment": eeg_alignment,
        },
        "ieeg": {
            "relative_path": str(ieeg_path.relative_to(dataset_root)),
            "sfreq": ieeg_info.sfreq,
            "n_channels": ieeg_info.n_channels,
            "n_times": ieeg_info.n_times,
            "duration_sec": ieeg_info.duration_sec,
            "reader": ieeg_info.source,
            "reader_warning": ieeg_info.warning,
            "event_alignment": ieeg_alignment,
        },
    }


def _read_edf_info(path: Path, mne: Any) -> EdfInfo:
    try:
        raw = mne.io.read_raw_edf(path, preload=False, verbose="ERROR")
    except ValueError as exc:
        if "second must be in 0..59" not in str(exc):
            raise
        fallback = _read_edf_header_info(path)
        return EdfInfo(
            sfreq=fallback.sfreq,
            n_channels=fallback.n_channels,
            n_times=fallback.n_times,
            duration_sec=fallback.duration_sec,
            source="edf_header_fallback",
            warning=str(exc),
        )

    return EdfInfo(
        sfreq=float(raw.info["sfreq"]),
        n_channels=len(raw.ch_names),
        n_times=int(raw.n_times),
        duration_sec=float(raw.n_times / raw.info["sfreq"]),
        source="mne",
    )


def _read_edf_header_info(path: Path) -> EdfInfo:
    with path.open("rb") as handle:
        fixed_header = handle.read(256)
        if len(fixed_header) < 256:
            raise ValueError(f"EDF header too short: {path}")
        header_bytes = int(_decode_edf_ascii(fixed_header[184:192]))
        n_records = int(float(_decode_edf_ascii(fixed_header[236:244])))
        record_duration = float(_decode_edf_ascii(fixed_header[244:252]))
        n_channels = int(_decode_edf_ascii(fixed_header[252:256]))

        handle.seek(256 + (216 * n_channels))
        samples_per_record = []
        for _ in range(n_channels):
            samples_per_record.append(int(_decode_edf_ascii(handle.read(8))))

    if header_bytes < 256 or n_channels <= 0 or n_records <= 0 or record_duration <= 0:
        raise ValueError(f"Invalid EDF header values: {path}")
    if len(set(samples_per_record)) != 1:
        raise ValueError(f"EDF channels have non-uniform samples per record: {path}")

    samples = samples_per_record[0]
    n_times = n_records * samples
    sfreq = samples / record_duration
    return EdfInfo(
        sfreq=float(sfreq),
        n_channels=n_channels,
        n_times=n_times,
        duration_sec=float(n_records * record_duration),
        source="edf_header",
    )


def _decode_edf_ascii(data: bytes) -> str:
    return data.decode("ascii", errors="ignore").strip()


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
