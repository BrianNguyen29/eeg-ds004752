"""Phase 0.5 task-contrast observability estimators.

The workflow in this module is deliberately narrower than Phase 1 model
training. It validates the locked preregistration bundle, reads the Gate 0
signal-audit cohort, extracts simple band-power teacher/student summaries,
and computes task-vs-control observability estimates with grouped teacher
permutation checks.

It does not train a decoder, tune a classifier, or authorize a privileged
transfer efficacy claim.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..guards import assert_real_phase_allowed


class Phase05EstimatorError(RuntimeError):
    """Raised when Phase 0.5 estimator workflow cannot proceed."""


@dataclass(frozen=True)
class Phase05EstimatorResult:
    output_dir: Path
    inputs_path: Path
    feature_report_path: Path
    observability_path: Path
    controls_report_path: Path
    teacher_survival_path: Path
    coverage_registry_path: Path
    exclusion_note_path: Path
    report_path: Path
    summary_path: Path
    summary: dict[str, Any]


def run_phase05_estimators(
    *,
    prereg_bundle: str | Path,
    phase05_run: str | Path,
    dataset_root: str | Path,
    config: dict[str, Any],
    output_root: str | Path,
    repo_root: str | Path | None = None,
    subjects: list[str] | None = None,
    max_subjects: int | None = None,
    max_sessions: int | None = None,
    max_trials_per_session: int | None = None,
    n_permutations: int | None = None,
) -> Phase05EstimatorResult:
    prereg_bundle = Path(prereg_bundle)
    phase05_run = Path(phase05_run)
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()

    bundle = assert_real_phase_allowed("phase05_real", prereg_bundle)
    phase05_summary = _read_json(phase05_run / "phase05_summary.json")
    phase05_inputs = _read_json(phase05_run / "phase05_inputs.json")
    _validate_phase05_source(bundle, phase05_summary, phase05_inputs, prereg_bundle)

    gate0_run = Path(bundle["source_runs"]["gate0"])
    manifest = _read_json(gate0_run / "manifest.json")
    cohort_lock = _read_json(gate0_run / "cohort_lock.json")
    threshold_registry = _read_json(Path(bundle["source_runs"]["gate2"]) / "gate_threshold_registry.json")

    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    selected_sessions = _select_sessions(
        manifest=manifest,
        cohort_lock=cohort_lock,
        subjects=subjects,
        max_subjects=max_subjects if max_subjects is not None else int(config["default_max_subjects"]),
        max_sessions=max_sessions if max_sessions is not None else int(config["default_max_sessions"]),
    )
    if not selected_sessions:
        raise Phase05EstimatorError("No sessions selected for Phase 0.5 estimator run")

    n_perm = n_permutations if n_permutations is not None else int(config["default_n_permutations"])
    max_trials = (
        max_trials_per_session
        if max_trials_per_session is not None
        else int(config["default_max_trials_per_session"])
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    inputs = _build_inputs(
        timestamp=timestamp,
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        phase05_run=phase05_run,
        dataset_root=dataset_root,
        config=config,
        selected_sessions=selected_sessions,
        n_permutations=n_perm,
        max_trials_per_session=max_trials,
        repo_root=repo_root,
    )
    extracted = _extract_feature_table(dataset_root, selected_sessions, config, max_trials)
    feature_report = _build_feature_report(extracted, selected_sessions, config)
    observability = _run_observability_estimates(
        extracted=extracted,
        config=config,
        threshold_registry=threshold_registry,
        n_permutations=n_perm,
    )
    controls_report = _build_controls_report(observability, config, threshold_registry, n_perm)
    teacher_survival = _build_teacher_survival_table(observability, threshold_registry, config, n_perm)
    coverage_registry = _build_coverage_registry(extracted, selected_sessions)
    exclusion_note = _build_exclusion_note(extracted, selected_sessions, bundle, phase05_run)
    summary = _build_summary(
        output_dir=output_dir,
        inputs=inputs,
        feature_report=feature_report,
        observability=observability,
        controls_report=controls_report,
        teacher_survival=teacher_survival,
        coverage_registry=coverage_registry,
        exclusion_note=exclusion_note,
        config=config,
        n_permutations=n_perm,
    )

    inputs_path = output_dir / "phase05_estimator_inputs.json"
    feature_report_path = output_dir / "feature_extraction_report.json"
    observability_path = output_dir / "task_contrast_observability_results.json"
    controls_report_path = output_dir / "controls_report.json"
    teacher_survival_path = output_dir / "teacher_survival_table.json"
    coverage_registry_path = output_dir / "coverage_registry.json"
    exclusion_note_path = output_dir / "phase05_estimator_exclusion_note.json"
    report_path = output_dir / "phase05_estimators_report.md"
    summary_path = output_dir / "phase05_estimators_summary.json"

    _write_json(inputs_path, inputs)
    _write_json(feature_report_path, feature_report)
    _write_json(observability_path, observability)
    _write_json(controls_report_path, controls_report)
    _write_json(teacher_survival_path, teacher_survival)
    _write_json(coverage_registry_path, coverage_registry)
    _write_json(exclusion_note_path, exclusion_note)
    report_path.write_text(_render_report(summary, controls_report, teacher_survival), encoding="utf-8")
    _write_json(summary_path, summary)
    _write_latest_pointer(output_root, output_dir)

    return Phase05EstimatorResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        feature_report_path=feature_report_path,
        observability_path=observability_path,
        controls_report_path=controls_report_path,
        teacher_survival_path=teacher_survival_path,
        coverage_registry_path=coverage_registry_path,
        exclusion_note_path=exclusion_note_path,
        report_path=report_path,
        summary_path=summary_path,
        summary=summary,
    )


def _validate_phase05_source(
    bundle: dict[str, Any],
    phase05_summary: dict[str, Any],
    phase05_inputs: dict[str, Any],
    prereg_bundle: Path,
) -> None:
    if phase05_summary.get("status") != "phase05_observability_preflight_ready":
        raise Phase05EstimatorError(f"Phase 0.5 preflight is not ready: {phase05_summary.get('status')}")
    expected_hash = bundle["prereg_bundle_hash_sha256"]
    if phase05_summary.get("prereg_bundle_hash_sha256") != expected_hash:
        raise Phase05EstimatorError("Phase 0.5 summary prereg hash does not match bundle hash")
    if phase05_inputs.get("prereg_bundle_hash_sha256") != expected_hash:
        raise Phase05EstimatorError("Phase 0.5 inputs prereg hash does not match bundle hash")
    if Path(phase05_summary.get("prereg_bundle_path", "")) != prereg_bundle:
        raise Phase05EstimatorError("Phase 0.5 summary points to a different prereg bundle path")
    _validate_bundle_hashes(bundle)


def _select_sessions(
    *,
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    subjects: list[str] | None,
    max_subjects: int,
    max_sessions: int,
) -> list[dict[str, str]]:
    eligible = {
        item["participant_id"]
        for item in cohort_lock.get("participants", [])
        if item.get("primary_eligible") is True
    }
    requested = set(subjects or [])
    session_results = manifest.get("signal_audit", {}).get("session_results", [])
    candidates = []
    for item in session_results:
        subject = item.get("subject")
        session = item.get("session")
        if item.get("status") != "ok" or subject not in eligible:
            continue
        if requested and subject not in requested:
            continue
        candidates.append({"subject": subject, "session": session})
    selected_subjects: list[str] = []
    selected = []
    for item in sorted(candidates, key=lambda x: (x["subject"], x["session"])):
        if item["subject"] not in selected_subjects:
            if len(selected_subjects) >= max_subjects:
                continue
            selected_subjects.append(item["subject"])
        if len(selected) >= max_sessions:
            break
        selected.append(item)
    return selected


def _extract_feature_table(
    dataset_root: Path,
    selected_sessions: list[dict[str, str]],
    config: dict[str, Any],
    max_trials_per_session: int,
) -> dict[str, Any]:
    np, mne = _optional_signal_imports()
    bands = {name: tuple(values) for name, values in config["frequency_bands_hz"].items()}
    task_window = tuple(config["signal_windows_sec"]["task_maintenance"])
    control_window = tuple(config["signal_windows_sec"]["matched_temporal_control"])

    rows: list[dict[str, Any]] = []
    teacher_name_set: set[str] = set()
    feature_name_set: set[str] = set()
    skipped_sessions = []
    read_fallbacks = []

    for item in selected_sessions:
        subject = item["subject"]
        session = item["session"]
        eeg_dir = dataset_root / subject / session / "eeg"
        ieeg_dir = dataset_root / subject / session / "ieeg"
        stem = f"{subject}_{session}_task-verbalWM_run-01"
        eeg_path = eeg_dir / f"{stem}_eeg.edf"
        ieeg_path = ieeg_dir / f"{stem}_ieeg.edf"
        events_path = eeg_dir / f"{stem}_events.tsv"
        electrodes_path = ieeg_dir / f"{stem}_electrodes.tsv"
        if not all(path.exists() for path in [eeg_path, ieeg_path, events_path, electrodes_path]):
            skipped_sessions.append({"subject": subject, "session": session, "reason": "missing_required_file"})
            continue

        events = _read_tsv(events_path)
        events = [row for row in events if row.get("Artifact") in ("0", 0, "0.0")]
        if max_trials_per_session > 0:
            events = events[:max_trials_per_session]
        if not events:
            skipped_sessions.append({"subject": subject, "session": session, "reason": "no_clean_events_selected"})
            continue

        try:
            eeg_raw = _read_edf(mne, eeg_path)
            ieeg_raw = _read_edf(mne, ieeg_path)
        except Phase05EstimatorError as exc:
            skipped_sessions.append({"subject": subject, "session": session, "reason": str(exc)})
            continue
        for modality, raw in [("eeg", eeg_raw), ("ieeg", ieeg_raw)]:
            fallback = getattr(raw, "_phase05_read_fallback", None)
            if fallback:
                read_fallbacks.append({"subject": subject, "session": session, "modality": modality, **fallback})
        eeg_data = eeg_raw.get_data()
        ieeg_data = ieeg_raw.get_data()
        eeg_sfreq = float(eeg_raw.info["sfreq"])
        ieeg_sfreq = float(ieeg_raw.info["sfreq"])
        eeg_names = [str(name) for name in eeg_raw.ch_names]
        ieeg_names = [str(name) for name in ieeg_raw.ch_names]
        roi_by_channel = _read_ieeg_roi_families(electrodes_path, ieeg_names)

        for event in events:
            trial_start_eeg = max(int(float(event["begSample"])) - 1, 0)
            trial_start_ieeg = int(round(trial_start_eeg * ieeg_sfreq / eeg_sfreq))
            x_task, x_names = _window_bandpower_features(
                np=np,
                data=eeg_data,
                channel_names=eeg_names,
                sfreq=eeg_sfreq,
                trial_start=trial_start_eeg,
                window_sec=task_window,
                bands=bands,
                prefix="scalp_task",
            )
            x_base, base_names = _window_bandpower_features(
                np=np,
                data=eeg_data,
                channel_names=eeg_names,
                sfreq=eeg_sfreq,
                trial_start=trial_start_eeg,
                window_sec=control_window,
                bands=bands,
                prefix="scalp_control",
            )
            z, z_names = _teacher_roi_band_targets(
                np=np,
                data=ieeg_data,
                channel_names=ieeg_names,
                roi_by_channel=roi_by_channel,
                sfreq=ieeg_sfreq,
                trial_start=trial_start_ieeg,
                window_sec=task_window,
                bands=bands,
            )
            nuisance, nuisance_names = _nuisance_features(event)
            feature_name_set.update(x_names)
            feature_name_set.update(base_names)
            teacher_name_set.update(z_names)
            rows.append(
                {
                    "subject": subject,
                    "session": session,
                    "trial_id": str(event["nTrial"]),
                    "eeg_path": str(eeg_path),
                    "trial_start_eeg": trial_start_eeg,
                    "eeg_sfreq": eeg_sfreq,
                    "set_size": _safe_float(event.get("SetSize")),
                    "x_task_map": dict(zip(x_names, x_task.tolist())),
                    "x_base_map": dict(zip(base_names, x_base.tolist())),
                    "x_nuisance": nuisance,
                    "z_teacher_map": dict(zip(z_names, z.tolist())),
                    "nuisance_names": nuisance_names,
                }
            )

    if not rows:
        raise Phase05EstimatorError("No feature rows were extracted")
    feature_names = sorted(feature_name_set)
    teacher_names = sorted(teacher_name_set)
    for row in rows:
        task_map = row.pop("x_task_map")
        base_map = row.pop("x_base_map")
        teacher_map = row.pop("z_teacher_map")
        row["x_task"] = [task_map.get(name, float("nan")) for name in feature_names]
        row["x_base"] = [base_map.get(name, float("nan")) for name in feature_names]
        row["z_teacher"] = [teacher_map.get(name, float("nan")) for name in teacher_names]
    return {
        "rows": rows,
        "feature_names": feature_names,
        "teacher_names": teacher_names,
        "skipped_sessions": skipped_sessions,
        "read_fallbacks": read_fallbacks,
    }


def _read_edf(mne: Any, path: Path) -> Any:
    try:
        return mne.io.read_raw_edf(path, preload=True, verbose="ERROR")
    except Exception as exc:  # pragma: no cover - depends on real EDF edge cases
        message = str(exc)
        if "second must be in 0..59" not in message:
            raise Phase05EstimatorError(f"Could not read EDF payload {path}: {message}") from exc
        try:
            raw = _read_edf_with_patched_starttime(mne, path)
        except Exception as fallback_exc:
            raise Phase05EstimatorError(
                f"Could not read EDF payload {path}: {message}; patched-starttime fallback failed: {fallback_exc}"
            ) from fallback_exc
        setattr(
            raw,
            "_phase05_read_fallback",
            {
                "path": str(path),
                "reason": message,
                "fallback": "patched_edf_header_starttime_seconds_to_59",
            },
        )
        return raw


def _read_edf_with_patched_starttime(mne: Any, path: Path) -> Any:
    patched = _patch_edf_header_starttime(path.read_bytes())
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".edf", delete=False) as handle:
            handle.write(patched)
            temp_path = Path(handle.name)
        return mne.io.read_raw_edf(temp_path, preload=True, verbose="ERROR")
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _patch_edf_header_starttime(payload: bytes) -> bytes:
    if len(payload) < 184:
        raise Phase05EstimatorError("EDF payload too small to patch starttime header")
    patched = bytearray(payload)
    raw_time = bytes(patched[176:184]).decode("ascii", errors="ignore")
    parts = raw_time.split(".")
    if len(parts) != 3:
        raise Phase05EstimatorError(f"Unexpected EDF starttime format: {raw_time!r}")
    hour, minute, second = (_clamp_time_component(part, limit) for part, limit in zip(parts, [23, 59, 59]))
    patched[176:184] = f"{hour:02d}.{minute:02d}.{second:02d}".encode("ascii")
    return bytes(patched)


def _clamp_time_component(value: str, limit: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise Phase05EstimatorError(f"Invalid EDF starttime component: {value!r}") from exc
    return max(0, min(limit, parsed))


def _window_bandpower_features(
    *,
    np: Any,
    data: Any,
    channel_names: list[str],
    sfreq: float,
    trial_start: int,
    window_sec: tuple[float, float],
    bands: dict[str, tuple[float, float]],
    prefix: str,
) -> tuple[Any, list[str]]:
    start = trial_start + int(round(window_sec[0] * sfreq))
    stop = trial_start + int(round(window_sec[1] * sfreq))
    stop = min(stop, data.shape[1])
    if stop <= start:
        raise Phase05EstimatorError("Invalid feature extraction window")
    segment = data[:, start:stop]
    values = []
    names = []
    for channel_index, channel_name in enumerate(channel_names):
        signal = segment[channel_index]
        for band_name, band in bands.items():
            values.append(_band_log_power(np, signal, sfreq, band))
            names.append(f"{channel_name}:{band_name}")
    return np.asarray(values, dtype=float), names


def _teacher_roi_band_targets(
    *,
    np: Any,
    data: Any,
    channel_names: list[str],
    roi_by_channel: dict[str, str],
    sfreq: float,
    trial_start: int,
    window_sec: tuple[float, float],
    bands: dict[str, tuple[float, float]],
) -> tuple[Any, list[str]]:
    start = trial_start + int(round(window_sec[0] * sfreq))
    stop = trial_start + int(round(window_sec[1] * sfreq))
    stop = min(stop, data.shape[1])
    if stop <= start:
        raise Phase05EstimatorError("Invalid teacher extraction window")
    segment = data[:, start:stop]
    roi_to_indices: dict[str, list[int]] = {}
    for index, name in enumerate(channel_names):
        roi = roi_by_channel.get(name, "unknown")
        roi_to_indices.setdefault(roi, []).append(index)
    values = []
    names = []
    for roi in sorted(roi_to_indices):
        indices = roi_to_indices[roi]
        for band_name, band in bands.items():
            powers = [_band_log_power(np, segment[index], sfreq, band) for index in indices]
            values.append(float(np.mean(powers)))
            names.append(f"group_a_roi_band:{roi}:{band_name}")
    return np.asarray(values, dtype=float), names


def _band_log_power(np: Any, signal: Any, sfreq: float, band: tuple[float, float]) -> float:
    signal = np.asarray(signal, dtype=float)
    signal = signal - float(np.mean(signal))
    if signal.size < 4:
        return float("nan")
    freqs = np.fft.rfftfreq(signal.size, d=1.0 / sfreq)
    spectrum = np.abs(np.fft.rfft(signal)) ** 2
    mask = (freqs >= band[0]) & (freqs < band[1])
    if not bool(np.any(mask)):
        return float("nan")
    return float(np.log(float(np.mean(spectrum[mask])) + 1e-12))


def _nuisance_features(event: dict[str, Any]) -> tuple[list[float], list[str]]:
    names = ["set_size", "response_time", "correct", "artifact"]
    values = [
        _safe_float(event.get("SetSize")),
        _safe_float(event.get("ResponseTime")),
        _safe_float(event.get("Correct")),
        _safe_float(event.get("Artifact")),
    ]
    return values, names


def _run_observability_estimates(
    *,
    extracted: dict[str, Any],
    config: dict[str, Any],
    threshold_registry: dict[str, Any],
    n_permutations: int,
) -> dict[str, Any]:
    np, _mne = _optional_signal_imports()
    rows = extracted["rows"]
    subjects = sorted({row["subject"] for row in rows})
    if len(subjects) < 2:
        raise Phase05EstimatorError("At least two subjects are required for LOSO observability estimates")

    x_task = np.asarray([row["x_task"] for row in rows], dtype=float)
    x_base = np.asarray([row["x_base"] for row in rows], dtype=float)
    x_nuisance = np.asarray([row["x_nuisance"] for row in rows], dtype=float)
    z = np.asarray([row["z_teacher"] for row in rows], dtype=float)
    x_spatial = _rowwise_spatial_permutation(
        np,
        x_task,
        extracted["feature_names"],
        seed=int(config["random_seed"]) + 1701,
    )
    ica_by_subject = _build_ica_features_by_outer_subject(
        np=np,
        mne=_mne,
        rows=rows,
        subjects=subjects,
        feature_names=extracted["feature_names"],
        config=config,
    )
    row_subjects = [row["subject"] for row in rows]
    row_sessions = [row["session"] for row in rows]
    teacher_names = list(extracted["teacher_names"])
    alpha = float(config["ridge_alpha"])
    thresholds = threshold_registry["thresholds"]
    delta_obs_min = float(thresholds["delta_obs_min"])
    nuisance_relative = float(thresholds["nuisance_relative_ceiling"])
    nuisance_absolute = float(thresholds["nuisance_absolute_ceiling"])
    spatial_relative = float(thresholds.get("spatial_relative_ceiling", 0.67))
    spatial_min_delta = float(config.get("spatial_min_delta_q2", 0.02))
    ica_min_ratio = float(config.get("ica_robustness_min_ratio", 0.7))
    ica_epsilon = 1e-6

    fold_results = []
    teacher_summaries = []
    rng = random.Random(int(config["random_seed"]))
    for teacher_index, teacher_name in enumerate(teacher_names):
        per_fold = []
        for outer_subject in subjects:
            train_idx = [i for i, sub in enumerate(row_subjects) if sub != outer_subject]
            test_idx = [i for i, sub in enumerate(row_subjects) if sub == outer_subject]
            y_train = z[train_idx, teacher_index]
            y_test = z[test_idx, teacher_index]
            task_q2 = _ridge_q2(np, x_task[train_idx], y_train, x_task[test_idx], y_test, alpha)
            base_q2 = _ridge_q2(np, x_base[train_idx], y_train, x_base[test_idx], y_test, alpha)
            nuisance_q2 = _ridge_q2(np, x_nuisance[train_idx], y_train, x_nuisance[test_idx], y_test, alpha)
            spatial_q2 = _ridge_q2(np, x_spatial[train_idx], y_train, x_spatial[test_idx], y_test, alpha)
            ica_fold = ica_by_subject.get(outer_subject, {"status": "failed", "reason": "missing_ica_fold"})
            x_ica = ica_fold.get("x_ica")
            q2_ica = (
                _ridge_q2(np, x_ica[train_idx], y_train, x_ica[test_idx], y_test, alpha)
                if ica_fold.get("status") == "ok" and x_ica is not None
                else float("nan")
            )
            null_q2 = []
            train_groups = [f"{row_subjects[i]}:{row_sessions[i]}" for i in train_idx]
            for _ in range(n_permutations):
                y_perm = _permute_within_groups(rng, list(y_train), train_groups)
                null_q2.append(_ridge_q2(np, x_task[train_idx], np.asarray(y_perm), x_task[test_idx], y_test, alpha))
            p_perm = _right_tail_p(task_q2, null_q2)
            delta_q2 = task_q2 - base_q2
            nuisance_veto = (
                nuisance_q2 >= nuisance_relative * task_q2
                if task_q2 > 0
                else nuisance_q2 >= nuisance_absolute
            ) or nuisance_q2 >= nuisance_absolute
            spatial_veto = (
                spatial_q2 >= spatial_relative * task_q2
                if task_q2 > 0
                else False
            ) or ((task_q2 - spatial_q2) < spatial_min_delta if not math.isnan(spatial_q2) and not math.isnan(task_q2) else True)
            pass_task_contrast = task_q2 > 0 and p_perm < 0.05 and delta_q2 >= delta_obs_min
            ica_ratio = q2_ica / (task_q2 + ica_epsilon) if task_q2 > 0 and not math.isnan(q2_ica) else float("nan")
            ica_veto = bool(pass_task_contrast and (math.isnan(ica_ratio) or ica_ratio < ica_min_ratio))
            per_fold.append(
                {
                    "outer_test_subject": outer_subject,
                    "q2_task": _round_or_none(task_q2),
                    "q2_base": _round_or_none(base_q2),
                    "delta_q2_obs": _round_or_none(delta_q2),
                    "q2_nuisance": _round_or_none(nuisance_q2),
                    "q2_spatial": _round_or_none(spatial_q2),
                    "q2_ica": _round_or_none(q2_ica),
                    "ica_ratio": _round_or_none(ica_ratio),
                    "p_perm": _round_or_none(p_perm),
                    "pass_task_contrast": bool(pass_task_contrast),
                    "nuisance_veto": bool(nuisance_veto),
                    "spatial_veto": bool(spatial_veto),
                    "ica_veto": bool(ica_veto),
                    "ica_fold_status": ica_fold.get("status"),
                    "ica_fold_reason": ica_fold.get("reason"),
                    "n_train_trials": len(train_idx),
                    "n_test_trials": len(test_idx),
                }
            )
        deltas = [item["delta_q2_obs"] for item in per_fold if item["delta_q2_obs"] is not None]
        task_q2s = [item["q2_task"] for item in per_fold if item["q2_task"] is not None]
        passed_folds = [
            item
            for item in per_fold
            if item["pass_task_contrast"] and not item["nuisance_veto"] and not item["spatial_veto"] and not item["ica_veto"]
        ]
        ica_failed_folds = [item for item in per_fold if item["ica_fold_status"] != "ok"]
        teacher_summary = {
            "teacher_id": teacher_name,
            "folds_total": len(per_fold),
            "folds_task_contrast_passed_full_computed_controls": len(passed_folds),
            "folds_with_ica_computed": len(per_fold) - len(ica_failed_folds),
            "median_q2_task": _median(deltas=[] if not task_q2s else task_q2s),
            "median_delta_q2_obs": _median(deltas),
            "status": "survived_computed_controls_screen" if passed_folds else "not_survived_computed_controls_screen",
            "computed_controls": [
                "task_vs_matched_temporal_control",
                "grouped_teacher_permutation",
                "nuisance_only_control",
                "rowwise_spatial_permutation_control",
                "ica_robustness_control",
            ],
            "controls_not_yet_computed": [],
        }
        teacher_summaries.append(teacher_summary)
        fold_results.append({"teacher_id": teacher_name, "fold_results": per_fold})

    return {
        "status": "task_contrast_observability_estimated_with_limitations",
        "n_rows": len(rows),
        "n_subjects": len(subjects),
        "n_teachers": len(teacher_names),
        "n_permutations": n_permutations,
        "permutation_inference_status": "final_min_met" if n_permutations >= int(config["final_min_n_permutations"]) else "smoke_not_final",
        "thresholds_used": {
            "delta_obs_min": delta_obs_min,
            "nuisance_relative_ceiling": nuisance_relative,
            "nuisance_absolute_ceiling": nuisance_absolute,
            "spatial_relative_ceiling": spatial_relative,
            "spatial_min_delta_q2": spatial_min_delta,
            "ica_robustness_min_ratio": ica_min_ratio,
            "p_perm_threshold": 0.05,
        },
        "ica_diagnostics": {
            outer_subject: {key: value for key, value in fold.items() if key != "x_ica"}
            for outer_subject, fold in ica_by_subject.items()
        },
        "ica_control_status": "computed" if all(fold.get("status") == "ok" for fold in ica_by_subject.values()) else "incomplete",
        "teacher_summaries": teacher_summaries,
        "fold_results": fold_results,
        "scientific_limit": (
            "These are task-contrast observability estimates for teacher targets, not decoder results. "
            "ICA robustness is computed only when the ICA stress-test branch fits and labels components successfully."
        ),
    }


def _rowwise_spatial_permutation(np: Any, x: Any, feature_names: list[str], seed: int) -> Any:
    """Destroy scalp channel-location mapping while preserving row/band marginals.

    Feature names are expected to be ``channel:band``. For each trial row and
    each frequency band, values are shuffled across channels. This is stricter
    than a column relabeling control because a fixed column permutation would be
    algebraically invisible to ridge regression.
    """

    x = np.asarray(x, dtype=float).copy()
    rng = np.random.default_rng(seed)
    band_to_indices: dict[str, list[int]] = {}
    for index, name in enumerate(feature_names):
        parts = str(name).split(":")
        if len(parts) < 2:
            continue
        band_to_indices.setdefault(parts[-1], []).append(index)
    for indices in band_to_indices.values():
        if len(indices) < 2:
            continue
        for row_index in range(x.shape[0]):
            values = x[row_index, indices].copy()
            rng.shuffle(values)
            x[row_index, indices] = values
    return x


def _build_ica_features_by_outer_subject(
    *,
    np: Any,
    mne: Any,
    rows: list[dict[str, Any]],
    subjects: list[str],
    feature_names: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for outer_subject in subjects:
        try:
            results[outer_subject] = _build_single_fold_ica_features(
                np=np,
                mne=mne,
                rows=rows,
                outer_subject=outer_subject,
                feature_names=feature_names,
                config=config,
            )
        except Exception as exc:  # pragma: no cover - real EDF/ICA edge cases are environment-specific
            results[outer_subject] = {
                "status": "failed",
                "reason": f"ica_fit_or_transform_failed: {exc}",
                "x_ica": None,
            }
    return results


def _build_single_fold_ica_features(
    *,
    np: Any,
    mne: Any,
    rows: list[dict[str, Any]],
    outer_subject: str,
    feature_names: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    target_sfreq = float(config.get("ica_target_sfreq", 200.0))
    artifact_probability = float(config.get("ica_iclabel_artifact_probability", 0.9))
    max_components = int(config.get("ica_max_components", 15))
    random_state = int(config.get("ica_random_state", 752051))
    bands = {name: tuple(values) for name, values in config["frequency_bands_hz"].items()}
    task_window = tuple(config["signal_windows_sec"]["task_maintenance"])

    raw_by_path = _read_raws_for_rows(mne, rows)
    common_channels = _common_channels(raw_by_path)
    if len(common_channels) < 2:
        return {"status": "failed", "reason": "fewer_than_two_common_scalp_channels", "x_ica": None}

    train_rows = [row for row in rows if row["subject"] != outer_subject]
    train_segments = []
    for row in train_rows:
        segment = _extract_resampled_segment(
            np=np,
            raw=raw_by_path[row["eeg_path"]],
            channel_names=common_channels,
            trial_start=int(row["trial_start_eeg"]),
            window_sec=task_window,
            target_sfreq=target_sfreq,
        )
        train_segments.append(segment)
    if not train_segments:
        return {"status": "failed", "reason": "no_training_segments_for_ica", "x_ica": None}

    train_data = np.concatenate(train_segments, axis=1)
    if train_data.shape[1] < max(20, 4 * len(common_channels)):
        return {"status": "failed", "reason": "insufficient_training_samples_for_ica", "x_ica": None}

    info = mne.create_info(ch_names=common_channels, sfreq=target_sfreq, ch_types="eeg")
    raw_train = mne.io.RawArray(train_data, info, verbose="ERROR")
    try:
        raw_train.set_montage("standard_1020", on_missing="ignore", verbose="ERROR")
    except Exception:
        pass
    h_freq = min(100.0, target_sfreq / 2.0 - 1.0)
    if h_freq > 2.0:
        raw_train.filter(l_freq=1.0, h_freq=h_freq, verbose="ERROR")

    n_components = max(1, min(max_components, len(common_channels) - 1))
    ica = mne.preprocessing.ICA(
        n_components=n_components,
        method="fastica",
        random_state=random_state,
        max_iter="auto",
        verbose="ERROR",
    )
    ica.fit(raw_train, verbose="ERROR")
    labels, probabilities = _label_ica_components(raw_train, ica)
    if not labels:
        return {
            "status": "failed",
            "reason": "iclabel_unavailable_or_failed",
            "x_ica": None,
            "n_common_channels": len(common_channels),
            "n_components": n_components,
        }

    excluded = [
        index
        for index, (label, probability) in enumerate(zip(labels, probabilities))
        if label != "brain" and float(probability) >= artifact_probability
    ]
    x_ica = np.full((len(rows), len(feature_names)), np.nan, dtype=float)
    feature_index = {name: index for index, name in enumerate(feature_names)}
    for row_index, row in enumerate(rows):
        segment = _extract_resampled_segment(
            np=np,
            raw=raw_by_path[row["eeg_path"]],
            channel_names=common_channels,
            trial_start=int(row["trial_start_eeg"]),
            window_sec=task_window,
            target_sfreq=target_sfreq,
        )
        raw_segment = mne.io.RawArray(segment, info.copy(), verbose="ERROR")
        try:
            raw_segment.set_montage("standard_1020", on_missing="ignore", verbose="ERROR")
        except Exception:
            pass
        cleaned = ica.apply(raw_segment, exclude=excluded, verbose="ERROR").get_data()
        values, names = _window_bandpower_features(
            np=np,
            data=cleaned,
            channel_names=common_channels,
            sfreq=target_sfreq,
            trial_start=0,
            window_sec=(0.0, cleaned.shape[1] / target_sfreq),
            bands=bands,
            prefix="scalp_ica",
        )
        for name, value in zip(names, values.tolist()):
            if name in feature_index:
                x_ica[row_index, feature_index[name]] = value

    return {
        "status": "ok",
        "reason": "ica_stress_branch_computed",
        "x_ica": x_ica,
        "n_common_channels": len(common_channels),
        "common_channels": common_channels,
        "target_sfreq": target_sfreq,
        "n_components": n_components,
        "component_labels": labels,
        "component_probabilities": [round(float(value), 6) for value in probabilities],
        "excluded_components": excluded,
        "artifact_probability_threshold": artifact_probability,
    }


def _read_raws_for_rows(mne: Any, rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw_by_path = {}
    for path_text in sorted({row["eeg_path"] for row in rows}):
        raw_by_path[path_text] = _read_edf(mne, Path(path_text))
    return raw_by_path


def _common_channels(raw_by_path: dict[str, Any]) -> list[str]:
    common: set[str] | None = None
    for raw in raw_by_path.values():
        channels = {str(name) for name in raw.ch_names}
        common = channels if common is None else common & channels
    return sorted(common or set())


def _extract_resampled_segment(
    *,
    np: Any,
    raw: Any,
    channel_names: list[str],
    trial_start: int,
    window_sec: tuple[float, float],
    target_sfreq: float,
) -> Any:
    sfreq = float(raw.info["sfreq"])
    picks = [raw.ch_names.index(name) for name in channel_names]
    data = raw.get_data(picks=picks)
    start = trial_start + int(round(window_sec[0] * sfreq))
    stop = min(trial_start + int(round(window_sec[1] * sfreq)), data.shape[1])
    if stop <= start:
        raise Phase05EstimatorError("Invalid ICA segment extraction window")
    segment = data[:, start:stop]
    duration = (stop - start) / sfreq
    n_target = max(4, int(round(duration * target_sfreq)))
    old_t = np.linspace(0.0, duration, segment.shape[1], endpoint=False)
    new_t = np.linspace(0.0, duration, n_target, endpoint=False)
    return np.vstack([np.interp(new_t, old_t, channel) for channel in segment])


def _label_ica_components(raw_train: Any, ica: Any) -> tuple[list[str], list[float]]:
    try:
        from mne_icalabel import label_components  # type: ignore
    except Exception:
        return [], []
    try:
        labels = label_components(raw_train, ica, method="iclabel")
    except Exception:
        return [], []
    component_labels = [str(label) for label in labels.get("labels", [])]
    probabilities = labels.get("y_pred_proba", [])
    return component_labels, [float(value) for value in probabilities]


def _ridge_q2(np: Any, x_train: Any, y_train: Any, x_test: Any, y_test: Any, alpha: float) -> float:
    valid_train = ~(np.isnan(y_train) | np.isinf(y_train))
    valid_test = ~(np.isnan(y_test) | np.isinf(y_test))
    if int(np.sum(valid_train)) < 3 or int(np.sum(valid_test)) < 1:
        return float("nan")
    x_train = np.asarray(x_train, dtype=float)[valid_train]
    y_train = np.asarray(y_train, dtype=float)[valid_train]
    x_test = np.asarray(x_test, dtype=float)[valid_test]
    y_test = np.asarray(y_test, dtype=float)[valid_test]
    x_train = _standardize(np, x_train)
    train_mean = x_train["mean"]
    train_std = x_train["std"]
    xtr = x_train["x"]
    xte = (np.asarray(x_test, dtype=float) - train_mean) / train_std
    y_train = np.asarray(y_train, dtype=float)
    y_test = np.asarray(y_test, dtype=float)
    y_mean = float(np.mean(y_train))
    y_centered = y_train - y_mean
    xtx = xtr.T @ xtr
    reg = alpha * np.eye(xtx.shape[0])
    try:
        beta = np.linalg.solve(xtx + reg, xtr.T @ y_centered)
    except np.linalg.LinAlgError:
        beta = np.linalg.pinv(xtx + reg) @ xtr.T @ y_centered
    pred = xte @ beta + y_mean
    sse = float(np.sum((y_test - pred) ** 2))
    baseline = float(np.sum((y_test - y_mean) ** 2))
    if baseline <= 1e-12:
        return float("nan")
    return 1.0 - sse / baseline


def _standardize(np: Any, x: Any) -> dict[str, Any]:
    x = np.asarray(x, dtype=float)
    with np.errstate(all="ignore"):
        mean = np.nanmean(x, axis=0)
        std = np.nanstd(x, axis=0)
    mean = np.nan_to_num(mean, nan=0.0, posinf=0.0, neginf=0.0)
    std = np.nan_to_num(std, nan=1.0, posinf=1.0, neginf=1.0)
    std = np.where(std <= 1e-12, 1.0, std)
    x = np.nan_to_num((x - mean) / std, nan=0.0, posinf=0.0, neginf=0.0)
    return {"x": x, "mean": mean, "std": std}


def _permute_within_groups(rng: random.Random, values: list[float], groups: list[str]) -> list[float]:
    grouped_indices: dict[str, list[int]] = {}
    for index, group in enumerate(groups):
        grouped_indices.setdefault(group, []).append(index)
    out = list(values)
    for indices in grouped_indices.values():
        shuffled = [out[index] for index in indices]
        rng.shuffle(shuffled)
        for index, value in zip(indices, shuffled):
            out[index] = value
    return out


def _right_tail_p(observed: float, null_values: list[float]) -> float:
    if not null_values or observed is None or math.isnan(observed):
        return float("nan")
    count = sum(1 for value in null_values if value >= observed)
    return (count + 1) / (len(null_values) + 1)


def _build_inputs(
    *,
    timestamp: str,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    phase05_run: Path,
    dataset_root: Path,
    config: dict[str, Any],
    selected_sessions: list[dict[str, str]],
    n_permutations: int,
    max_trials_per_session: int,
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase05_estimator_inputs_locked",
        "created_utc": timestamp,
        "phase_id": "phase05_real",
        "workflow": config["workflow"],
        "prereg_bundle_path": str(prereg_bundle),
        "prereg_bundle_hash_sha256": bundle["prereg_bundle_hash_sha256"],
        "phase05_source_of_truth": str(phase05_run),
        "dataset_root": str(dataset_root),
        "selected_sessions": selected_sessions,
        "n_permutations": n_permutations,
        "max_trials_per_session": max_trials_per_session,
        "repo": _git_identity(repo_root),
        "scientific_scope": config["scientific_scope"],
    }


def _build_feature_report(extracted: dict[str, Any], selected_sessions: list[dict[str, str]], config: dict[str, Any]) -> dict[str, Any]:
    rows = extracted["rows"]
    return {
        "status": "feature_extraction_complete",
        "feature_family": config["student_feature_family"],
        "teacher_target_family": config["teacher_target_family"],
        "selected_sessions": selected_sessions,
        "skipped_sessions": extracted["skipped_sessions"],
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "n_rows": len(rows),
        "n_subjects": len({row["subject"] for row in rows}),
        "n_sessions": len({f"{row['subject']}:{row['session']}" for row in rows}),
        "n_scalp_features": len(extracted["feature_names"]),
        "n_teacher_targets": len(extracted["teacher_names"]),
        "signal_windows_sec": config["signal_windows_sec"],
        "frequency_bands_hz": config["frequency_bands_hz"],
        "scientific_limit": "Feature extraction is for Phase 0.5 observability only and is not decoder training.",
    }


def _build_controls_report(
    observability: dict[str, Any],
    config: dict[str, Any],
    threshold_registry: dict[str, Any],
    n_permutations: int,
) -> dict[str, Any]:
    blockers = []
    if observability.get("ica_control_status") != "computed":
        blockers.append("ica_robustness_control_not_computed")
    if n_permutations < int(config["final_min_n_permutations"]):
        blockers.append("permutation_count_below_final_minimum")
    return {
        "status": "controls_report_complete" if not blockers else "controls_report_with_explicit_blockers",
        "implemented_controls": config["implemented_controls"],
        "pending_controls": config["pending_controls"],
        "threshold_registry_hash_sha256": threshold_registry["threshold_registry_hash_sha256"],
        "n_permutations": n_permutations,
        "permutation_inference_status": observability["permutation_inference_status"],
        "ica_control_status": observability.get("ica_control_status"),
        "ica_diagnostics": observability.get("ica_diagnostics"),
        "final_min_n_permutations": config["final_min_n_permutations"],
        "phase05_teacher_survival_table_ready": not blockers,
        "final_teacher_survival_claim_allowed": not blockers,
        "blockers": blockers,
        "scientific_limit": (
            "Task/base/nuisance/spatial/ICA estimates support Phase 0.5 observability tables only. "
            "They do not prove decoder performance or privileged-transfer efficacy."
        ),
    }


def _build_teacher_survival_table(
    observability: dict[str, Any],
    threshold_registry: dict[str, Any],
    config: dict[str, Any],
    n_permutations: int,
) -> dict[str, Any]:
    rows = []
    for item in observability["teacher_summaries"]:
        rows.append(
            {
                "teacher_id": item["teacher_id"],
                "task_contrast_screen_status": item["status"],
                "folds_total": item["folds_total"],
                "folds_task_contrast_passed_full_computed_controls": item[
                    "folds_task_contrast_passed_full_computed_controls"
                ],
                "median_q2_task": item["median_q2_task"],
                "median_delta_q2_obs": item["median_delta_q2_obs"],
                "final_survival_status": "claim_ready_for_phase05_observability_table"
                if observability.get("ica_control_status") == "computed"
                and n_permutations >= int(config["final_min_n_permutations"])
                else "not_claim_ready_pending_controls_or_final_permutation_count",
            }
        )
    return {
        "status": "teacher_survival_table_ready_for_phase05_observability"
        if observability.get("ica_control_status") == "computed"
        and n_permutations >= int(config["final_min_n_permutations"])
        else "teacher_survival_table_draft_not_claim_ready",
        "threshold_registry_hash_sha256": threshold_registry["threshold_registry_hash_sha256"],
        "n_permutations": n_permutations,
        "final_min_n_permutations": config["final_min_n_permutations"],
        "rows": rows,
    }


def _build_coverage_registry(extracted: dict[str, Any], selected_sessions: list[dict[str, str]]) -> dict[str, Any]:
    teacher_names = extracted["teacher_names"]
    roi_families = sorted({name.split(":")[1] for name in teacher_names if ":" in name})
    bands = sorted({name.split(":")[2] for name in teacher_names if name.count(":") >= 2})
    return {
        "status": "coverage_registry_from_selected_estimator_run",
        "selected_sessions": selected_sessions,
        "roi_families": roi_families,
        "frequency_bands": bands,
        "n_teacher_targets": len(teacher_names),
        "scientific_limit": "Coverage is limited to selected sessions in this estimator run.",
    }


def _build_exclusion_note(
    extracted: dict[str, Any],
    selected_sessions: list[dict[str, str]],
    bundle: dict[str, Any],
    phase05_run: Path,
) -> dict[str, Any]:
    skipped = extracted.get("skipped_sessions", [])
    read_fallbacks = extracted.get("read_fallbacks", [])
    selected_keys = {f"{item['subject']}:{item['session']}" for item in selected_sessions}
    included_keys = {f"{row['subject']}:{row['session']}" for row in extracted["rows"]}
    return {
        "status": "no_phase05_estimator_exclusions" if not skipped else "phase05_estimator_exclusions_recorded",
        "phase05_source_of_truth": str(phase05_run),
        "prereg_bundle_hash_sha256": bundle["prereg_bundle_hash_sha256"],
        "selected_sessions": len(selected_keys),
        "included_sessions": len(included_keys),
        "excluded_sessions": len(skipped),
        "skipped_sessions": skipped,
        "read_fallbacks": read_fallbacks,
        "fallback_policy": (
            "EDF payloads with invalid starttime seconds are read through a temporary header-patched copy "
            "that clamps the EDF header starttime seconds field to 59. Signal samples are otherwise unchanged. "
            "If this fallback fails, the session remains excluded and is listed here."
        ),
        "scientific_limit": (
            "Exclusions or EDF read fallbacks affect Phase 0.5 observability coverage only. "
            "They do not provide decoder efficacy evidence."
        ),
    }


def _build_summary(
    *,
    output_dir: Path,
    inputs: dict[str, Any],
    feature_report: dict[str, Any],
    observability: dict[str, Any],
    controls_report: dict[str, Any],
    teacher_survival: dict[str, Any],
    coverage_registry: dict[str, Any],
    exclusion_note: dict[str, Any],
    config: dict[str, Any],
    n_permutations: int,
) -> dict[str, Any]:
    smoke = n_permutations < int(config["final_min_n_permutations"])
    controls_complete = not controls_report["blockers"]
    return {
        "status": "phase05_estimators_smoke_complete"
        if smoke
        else ("phase05_estimators_controls_complete" if controls_complete else "phase05_estimators_control_limited_complete"),
        "run_dir": str(output_dir),
        "phase_id": inputs["phase_id"],
        "workflow": inputs["workflow"],
        "phase05_source_of_truth": inputs["phase05_source_of_truth"],
        "prereg_bundle_hash_sha256": inputs["prereg_bundle_hash_sha256"],
        "n_subjects": feature_report["n_subjects"],
        "n_sessions": feature_report["n_sessions"],
        "n_trials": feature_report["n_rows"],
        "n_teacher_targets": feature_report["n_teacher_targets"],
        "n_permutations": n_permutations,
        "permutation_inference_status": observability["permutation_inference_status"],
        "controls_blockers": controls_report["blockers"],
        "teacher_survival_status": teacher_survival["status"],
        "coverage_status": coverage_registry["status"],
        "selected_sessions": exclusion_note["selected_sessions"],
        "included_sessions": exclusion_note["included_sessions"],
        "excluded_sessions": exclusion_note["excluded_sessions"],
        "exclusion_note_status": exclusion_note["status"],
        "does_not_train_decoder": True,
        "does_not_estimate_privileged_transfer_efficacy": True,
        "claim_ready": False,
        "phase05_observability_table_ready": controls_complete,
        "next_step": "review_phase05_observability_tables_before_phase1"
        if controls_complete
        else "complete_remaining_controls_or_rerun_with_final_permutation_count",
        "scientific_integrity_limits": [
            "This is a Phase 0.5 observability estimator run, not Phase 1 decoding.",
            "Teacher survival table is not evidence of decoder performance or privileged-transfer efficacy.",
            "No privileged-transfer efficacy claim is allowed from this output.",
        ],
    }


def _render_report(
    summary: dict[str, Any],
    controls_report: dict[str, Any],
    teacher_survival: dict[str, Any],
) -> str:
    lines = [
        "# Phase 0.5 Observability Estimators Report",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Phase 0.5 source: `{summary['phase05_source_of_truth']}`",
        f"- Subjects: {summary['n_subjects']}",
        f"- Sessions: {summary['n_sessions']}",
        f"- Trials: {summary['n_trials']}",
        f"- Teacher targets: {summary['n_teacher_targets']}",
        f"- Permutations: {summary['n_permutations']}",
        f"- Claim ready: `{summary['claim_ready']}`",
        "",
        "## Controls",
        "",
        f"- Implemented controls: {controls_report['implemented_controls']}",
        f"- Pending controls: {controls_report['pending_controls']}",
        f"- Blockers: {controls_report['blockers']}",
        "",
        "## Teacher Survival",
        "",
        f"- Status: `{teacher_survival['status']}`",
        f"- Rows: {len(teacher_survival['rows'])}",
        "",
        "## Scientific Integrity",
        "",
        "- This report does not train a decoder.",
        "- This report does not show privileged-transfer efficacy.",
        "- Draft teacher survival must not be reported as final until all locked controls pass.",
        "",
    ]
    return "\n".join(lines)


def _read_ieeg_roi_families(path: Path, channel_names: list[str]) -> dict[str, str]:
    rows = _read_tsv(path)
    labels = {}
    for row in rows:
        name = str(row.get("name", ""))
        label = str(row.get("AnatomicalLocation", "unknown"))
        labels[name] = _coarse_roi_family(label)
    return {name: labels.get(name, "unknown") for name in channel_names}


def _coarse_roi_family(label: str) -> str:
    normalized = label.strip().lower()
    if not normalized or normalized == "no_label_found":
        return "unknown"
    first = normalized.split(",")[0].strip()
    first = first.replace(" ", "_").replace("/", "_")
    return "".join(ch for ch in first if ch.isalnum() or ch == "_") or "unknown"


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _median(deltas: list[float]) -> float | None:
    values = sorted(value for value in deltas if value is not None and not math.isnan(value))
    if not values:
        return None
    mid = len(values) // 2
    if len(values) % 2:
        return _round_or_none(values[mid])
    return _round_or_none((values[mid - 1] + values[mid]) / 2)


def _round_or_none(value: float | None) -> float | None:
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return round(float(value), 6)


def _optional_signal_imports() -> tuple[Any, Any]:
    try:
        import numpy as np  # type: ignore
        import mne  # type: ignore
    except Exception as exc:  # pragma: no cover - environment specific
        raise Phase05EstimatorError(
            "Phase 0.5 estimators require signal extras. Run INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh"
        ) from exc
    return np, mne


def _validate_bundle_hashes(bundle: dict[str, Any]) -> None:
    for group_name, group in bundle.get("artifact_hashes", {}).items():
        if group_name == "threshold_registry":
            _validate_hash_entry(group)
            continue
        if not isinstance(group, dict):
            raise Phase05EstimatorError(f"Invalid artifact hash group: {group_name}")
        for item in group.values():
            _validate_hash_entry(item)


def _validate_hash_entry(item: dict[str, Any]) -> None:
    path = Path(item["path"])
    expected = item["sha256"]
    actual = _sha256_file(path)
    if actual != expected:
        raise Phase05EstimatorError(f"Hash mismatch for {path}: expected {expected}, got {actual}")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Phase05EstimatorError(f"JSON root must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.joinpath("latest.txt").write_text(str(output_dir), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found for hashing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_identity(repo_root: Path) -> dict[str, Any]:
    commit = _safe_command(["git", "rev-parse", "HEAD"], repo_root)
    branch = _safe_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    status = _safe_command(["git", "status", "--short"], repo_root)
    return {
        "path": str(repo_root),
        "branch": branch,
        "commit": commit,
        "working_tree_clean": status == "",
        "git_status_short": status,
    }


def _safe_command(command: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(command, cwd=cwd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"
