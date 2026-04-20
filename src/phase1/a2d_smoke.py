"""Phase 1 A2d Riemannian comparator implementation smoke.

This runner is deliberately narrow. It validates the A2d data path, LOSO
discipline, training-only covariance reference fitting, tangent projection,
small logistic probe, and artifact writing. It is not the final A2d comparator
estimate and cannot support decoder efficacy or privileged-transfer claims.
"""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..guards import assert_real_phase_allowed
from ..phase05.estimators import Phase05EstimatorError, _optional_signal_imports, _read_edf
from .model_smoke import _classification_metrics, _load_binary_load_events, _mean, _median, _round_or_none
from .smoke import (
    Phase1SmokeError,
    _eligible_subjects,
    _read_json,
    _readiness_path,
    _select_outer_subjects,
    _session_inventory,
    _validate_readiness,
    _write_json,
    _write_latest_pointer,
)


class Phase1A2dSmokeError(RuntimeError):
    """Raised when Phase 1 A2d smoke cannot proceed."""


@dataclass(frozen=True)
class Phase1A2dSmokeResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_A2D_SMOKE_CONFIG = {
    "workflow": "a2d_riemannian_comparator_smoke",
    "backend": "internal_numpy_logeuclidean_tangent_smoke",
    "signal_windows_sec": {"task_maintenance": [2.25, 4.75]},
    "default_max_outer_folds": 2,
    "default_max_trials_per_session": 24,
    "max_channels": 32,
    "covariance": {
        "diagonal_loading": 1e-6,
        "trace_normalize": True,
        "min_window_samples": 8,
    },
    "logistic_probe": {
        "learning_rate": 0.05,
        "n_steps": 160,
        "l2": 0.001,
        "subject_balanced": True,
    },
}


def run_phase1_a2d_smoke(
    *,
    prereg_bundle: str | Path,
    readiness_run: str | Path,
    dataset_root: str | Path,
    output_root: str | Path,
    config: dict[str, Any] | None = None,
    repo_root: str | Path | None = None,
    max_outer_folds: int = 2,
    outer_test_subjects: list[str] | None = None,
    max_trials_per_session: int | None = None,
    precomputed_rows: dict[str, Any] | None = None,
) -> Phase1A2dSmokeResult:
    """Run a non-claim A2d Riemannian comparator smoke."""

    prereg_bundle = Path(prereg_bundle)
    readiness_run = Path(readiness_run)
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config = _merge_config(config or {})

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    readiness_path = _readiness_path(readiness_run)
    readiness = _read_json(readiness_path)
    try:
        _validate_readiness(readiness, bundle)
    except Phase1SmokeError as exc:
        raise Phase1A2dSmokeError(str(exc)) from exc

    gate0_run = Path(readiness.get("source_of_truth", {}).get("gate0") or bundle["source_runs"]["gate0"])
    manifest = _read_json(gate0_run / "manifest.json")
    cohort_lock = _read_json(gate0_run / "cohort_lock.json")
    eligible_subjects = _eligible_subjects(cohort_lock)
    selected_subjects = _select_outer_subjects(
        eligible_subjects=eligible_subjects,
        requested=outer_test_subjects or [],
        max_outer_folds=max_outer_folds,
    )
    sessions = _session_inventory(manifest, eligible_subjects)
    selected_sessions = [row for row in sessions if row["subject"] in set(eligible_subjects)]

    if precomputed_rows is None and not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    fold_dir = output_dir / "fold_logs"
    logits_dir = output_dir / "a2d_logits_smoke"
    fold_dir.mkdir(parents=True, exist_ok=True)
    logits_dir.mkdir(parents=True, exist_ok=True)

    max_trials = (
        int(max_trials_per_session)
        if max_trials_per_session is not None
        else int(config["default_max_trials_per_session"])
    )
    extracted = precomputed_rows or _extract_covariance_rows(
        dataset_root=dataset_root,
        sessions=selected_sessions,
        config=config,
        max_trials_per_session=max_trials,
    )
    rows = _coerce_covariance_rows(extracted["rows"])
    if len({row["subject"] for row in rows}) < 2:
        raise Phase1A2dSmokeError("At least two subjects with load 4/8 covariance rows are required for A2d smoke")

    fold_logs = []
    fold_metrics = []
    all_logits = []
    alignment_audit = {
        "status": "a2d_alignment_audit_smoke",
        "backend": config["backend"],
        "folds": [],
        "outer_test_subject_used_for_fit": False,
    }
    for fold_index, outer_subject in enumerate(selected_subjects, start=1):
        fold = _run_a2d_fold(
            rows=rows,
            outer_subject=outer_subject,
            config=config,
            fold_index=fold_index,
            logits_dir=logits_dir,
        )
        fold_logs.append(fold)
        fold_metrics.append(fold["metrics"])
        all_logits.extend(fold["logits"])
        alignment_audit["folds"].append(fold["alignment_audit"])
        if not fold["alignment_audit"]["no_outer_test_subject_in_any_fit"]:
            alignment_audit["outer_test_subject_used_for_fit"] = True
        _write_json(fold_dir / f"{fold['fold_id']}.json", fold)

    metrics_summary = _summarize_a2d_metrics(fold_metrics)
    covariance_manifest = _build_covariance_manifest(extracted, rows, config)
    calibration_report = _build_calibration_report(all_logits)
    negative_controls_report = {
        "status": "negative_controls_not_executed_a2d_smoke",
        "reason": "A2d implementation smoke does not run shuffled/time-shifted teacher controls.",
        "required_for_full_phase1": True,
    }
    influence_report = {
        "status": "influence_smoke_not_claim_evaluable",
        "fold_count": len(fold_logs),
        "reason": "Only bounded smoke folds are expected; influence concentration is a full-run governance calculation.",
    }
    inputs = _build_inputs(
        timestamp=timestamp,
        prereg_bundle=prereg_bundle,
        readiness_run=readiness_run,
        readiness_path=readiness_path,
        dataset_root=dataset_root,
        output_dir=output_dir,
        selected_subjects=selected_subjects,
        selected_sessions=selected_sessions,
        config=config,
        repo_root=repo_root,
    )
    summary = _build_summary(
        output_dir=output_dir,
        inputs=inputs,
        rows=rows,
        fold_logs=fold_logs,
        metrics_summary=metrics_summary,
        covariance_manifest=covariance_manifest,
        alignment_audit=alignment_audit,
        calibration_report=calibration_report,
        negative_controls_report=negative_controls_report,
        influence_report=influence_report,
    )

    inputs_path = output_dir / "phase1_a2d_smoke_inputs.json"
    summary_path = output_dir / "phase1_a2d_smoke_summary.json"
    report_path = output_dir / "phase1_a2d_smoke_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "a2d_metrics_smoke.json", {"folds": fold_metrics, "summary": metrics_summary})
    _write_json(output_dir / "a2d_alignment_audit.json", alignment_audit)
    _write_json(output_dir / "a2d_covariance_manifest.json", covariance_manifest)
    _write_json(output_dir / "calibration_a2d_smoke_report.json", calibration_report)
    _write_json(output_dir / "negative_controls_a2d_smoke_report.json", negative_controls_report)
    _write_json(output_dir / "influence_a2d_smoke_report.json", influence_report)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, metrics_summary), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1A2dSmokeResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _merge_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_A2D_SMOKE_CONFIG))
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _extract_covariance_rows(
    *,
    dataset_root: Path,
    sessions: list[dict[str, str]],
    config: dict[str, Any],
    max_trials_per_session: int,
) -> dict[str, Any]:
    np, mne = _optional_signal_imports()
    task_window = tuple(config["signal_windows_sec"]["task_maintenance"])
    max_channels = int(config.get("max_channels") or 0)
    min_window_samples = int(config["covariance"].get("min_window_samples", 8))
    rows: list[dict[str, Any]] = []
    skipped_sessions = []
    read_fallbacks = []

    for item in sessions:
        subject = item["subject"]
        session = item["session"]
        eeg_dir = dataset_root / subject / session / "eeg"
        stem = f"{subject}_{session}_task-verbalWM_run-01"
        eeg_path = eeg_dir / f"{stem}_eeg.edf"
        events_path = eeg_dir / f"{stem}_events.tsv"
        if not eeg_path.exists() or not events_path.exists():
            skipped_sessions.append({"subject": subject, "session": session, "reason": "missing_eeg_or_events"})
            continue

        events = _load_binary_load_events(events_path)
        if max_trials_per_session > 0:
            events = events[:max_trials_per_session]
        if not events:
            skipped_sessions.append({"subject": subject, "session": session, "reason": "no_load_4_or_8_clean_events"})
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
        channel_names = [str(name) for name in raw.ch_names]
        if max_channels > 0 and len(channel_names) > max_channels:
            data = data[:max_channels, :]
            channel_names = channel_names[:max_channels]
        sfreq = float(raw.info["sfreq"])

        for event in events:
            trial_start = max(int(float(event["begSample"])) - 1, 0)
            start = trial_start + max(int(round(task_window[0] * sfreq)), 0)
            stop = trial_start + max(int(round(task_window[1] * sfreq)), 0)
            stop = min(stop, data.shape[1])
            if stop - start < min_window_samples:
                continue
            segment = data[:, start:stop]
            cov = np.cov(segment)
            rows.append(
                {
                    "subject": subject,
                    "session": session,
                    "trial_id": str(event.get("nTrial", len(rows) + 1)),
                    "set_size": int(float(event["SetSize"])),
                    "label": 1 if int(float(event["SetSize"])) == 8 else 0,
                    "covariance": cov.tolist(),
                    "channel_names": channel_names,
                }
            )

    if not rows:
        raise Phase1A2dSmokeError("No load 4/8 scalp covariance rows were extracted")
    return {
        "status": "phase1_a2d_covariance_rows_extracted",
        "rows": rows,
        "skipped_sessions": skipped_sessions,
        "read_fallbacks": read_fallbacks,
    }


def _coerce_covariance_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    np = _numpy()
    prepared = []
    for row in rows:
        cov = row.get("covariance")
        if cov is None:
            raise Phase1A2dSmokeError("A2d rows require covariance matrices")
        matrix = np.asarray(cov, dtype=float)
        if len(matrix.shape) != 2 or matrix.shape[0] != matrix.shape[1]:
            raise Phase1A2dSmokeError("Covariance matrices must be square")
        channel_names = list(row.get("channel_names", []))
        if channel_names and len(channel_names) != matrix.shape[0]:
            raise Phase1A2dSmokeError(
                f"Channel name count {len(channel_names)} does not match covariance shape {matrix.shape}"
            )
        label = int(row.get("label", 1 if int(row.get("set_size", 0)) == 8 else 0))
        prepared.append(
            {
                "subject": str(row["subject"]),
                "session": str(row.get("session", "")),
                "trial_id": str(row.get("trial_id", "")),
                "set_size": int(row.get("set_size", 8 if label else 4)),
                "label": label,
                "covariance": matrix,
                "channel_names": channel_names,
            }
        )

    if prepared and all(row["channel_names"] for row in prepared):
        common = set(prepared[0]["channel_names"])
        for row in prepared[1:]:
            common &= set(row["channel_names"])
        common_ordered = [name for name in prepared[0]["channel_names"] if name in common]
        if len(common_ordered) < 2:
            raise Phase1A2dSmokeError(
                f"A2d channel alignment requires at least two common channels; got {common_ordered}"
            )
        for row in prepared:
            index_by_name = {name: index for index, name in enumerate(row["channel_names"])}
            indices = [index_by_name[name] for name in common_ordered]
            row["covariance"] = row["covariance"][np.ix_(indices, indices)]
            row["channel_names"] = list(common_ordered)

    coerced = []
    for row in prepared:
        row["covariance"] = row["covariance"].tolist()
        coerced.append(row)
    return coerced


def _run_a2d_fold(
    *,
    rows: list[dict[str, Any]],
    outer_subject: str,
    config: dict[str, Any],
    fold_index: int,
    logits_dir: Path,
) -> dict[str, Any]:
    np = _numpy()
    train_rows = [row for row in rows if row["subject"] != outer_subject]
    test_rows = [row for row in rows if row["subject"] == outer_subject]
    if not train_rows or not test_rows:
        raise Phase1A2dSmokeError(f"Fold {outer_subject} has empty train/test rows")
    _validate_binary_classes(train_rows, f"training fold excluding {outer_subject}")
    _validate_binary_classes(test_rows, f"outer-test fold {outer_subject}")

    train_cov = _stack_covariances(train_rows)
    test_cov = _stack_covariances(test_rows)
    reference = _logeuclidean_reference(train_cov, config)
    x_train = _tangent_project(train_cov, reference, config)
    x_test = _tangent_project(test_cov, reference, config)
    x_train, x_test = _standardize_np(x_train, x_test)
    y_train = np.asarray([float(row["label"]) for row in train_rows], dtype=float)
    y_test = [float(row["label"]) for row in test_rows]
    weights = _sample_weights_np(train_rows, bool(config["logistic_probe"].get("subject_balanced", True)))
    model = _fit_logistic_np(x_train, y_train, weights, config["logistic_probe"])
    prob_arr = _sigmoid_np(x_test @ model["coef"] + model["intercept"])
    prob = [float(value) for value in prob_arr.tolist()]
    pred = [1 if value >= 0.5 else 0 for value in prob]
    metrics = _classification_metrics(y_test, prob, pred)
    fold_id = f"fold_{fold_index:02d}_{outer_subject}"
    train_subjects = sorted({row["subject"] for row in train_rows})
    test_subjects = [outer_subject]
    metrics.update(
        {
            "comparator_id": "A2d_riemannian",
            "outer_test_subject": outer_subject,
            "n_train_trials": int(len(train_rows)),
            "n_test_trials": int(len(test_rows)),
            "training_policy": "training_subjects_only_logeuclidean_tangent_l2_logistic_probe",
            "scientific_limit": "A2d smoke metric; not final Riemannian comparator evidence.",
        }
    )
    logits = [
        {
            "subject": row["subject"],
            "session": row["session"],
            "trial_id": row["trial_id"],
            "y_true": int(y),
            "prob_load8": round(float(p), 8),
            "y_pred": int(pp),
        }
        for row, y, p, pp in zip(test_rows, y_test, prob, pred)
    ]
    _write_json(logits_dir / f"{fold_id}_A2d_riemannian_logits.json", {"rows": logits})
    alignment_audit = {
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "fit_subjects": train_subjects,
        "transform_subjects": test_subjects,
        "reference_fit_subjects": train_subjects,
        "alignment_fit_subjects": train_subjects,
        "classifier_fit_subjects": train_subjects,
        "calibration_fit_subjects": [],
        "no_outer_test_subject_in_train": outer_subject not in set(train_subjects),
        "no_outer_test_subject_in_reference_fit": outer_subject not in set(train_subjects),
        "no_outer_test_subject_in_alignment_fit": outer_subject not in set(train_subjects),
        "no_outer_test_subject_in_classifier_fit": outer_subject not in set(train_subjects),
        "no_outer_test_subject_in_calibration_fit": True,
        "no_outer_test_subject_in_any_fit": outer_subject not in set(train_subjects),
        "reference_matrix_trace": _round_or_none(float(np.trace(reference))),
    }
    return {
        "status": "phase1_a2d_riemannian_smoke_fold_complete",
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "train_subjects": train_subjects,
        "test_subjects": test_subjects,
        "no_outer_test_subject_in_train": outer_subject not in set(train_subjects),
        "n_tangent_features": int(x_train.shape[1]),
        "metrics": metrics,
        "logits": logits,
        "alignment_audit": alignment_audit,
    }


def _validate_binary_classes(rows: list[dict[str, Any]], label: str) -> None:
    labels = {int(row["label"]) for row in rows}
    if labels != {0, 1}:
        raise Phase1A2dSmokeError(f"A2d smoke requires both load classes in {label}; got labels {sorted(labels)}")


def _stack_covariances(rows: list[dict[str, Any]]):
    np = _numpy()
    matrices = [np.asarray(row["covariance"], dtype=float) for row in rows]
    shapes = {matrix.shape for matrix in matrices}
    if len(shapes) != 1:
        raise Phase1A2dSmokeError(f"Covariance matrix shapes are inconsistent: {sorted(shapes)}")
    if len(next(iter(shapes))) != 2 or next(iter(shapes))[0] != next(iter(shapes))[1]:
        raise Phase1A2dSmokeError("Covariance matrices must be square")
    return np.stack(matrices, axis=0)


def _logeuclidean_reference(covariances, config: dict[str, Any]):
    np = _numpy()
    logs = np.stack([_logm_spd(_regularize_cov(cov, config)) for cov in covariances], axis=0)
    return _expm_sym(np.mean(logs, axis=0))


def _tangent_project(covariances, reference, config: dict[str, Any]):
    np = _numpy()
    invsqrt = _invsqrtm_spd(reference)
    rows = []
    for cov in covariances:
        centered = invsqrt @ _regularize_cov(cov, config) @ invsqrt
        tangent = _logm_spd(centered)
        rows.append(_upper_triangular_features(tangent))
    return np.stack(rows, axis=0)


def _regularize_cov(covariance, config: dict[str, Any]):
    np = _numpy()
    cov = np.asarray(covariance, dtype=float)
    cov = (cov + cov.T) / 2.0
    if bool(config["covariance"].get("trace_normalize", True)):
        trace = float(np.trace(cov))
        if math.isfinite(trace) and trace > 0:
            cov = cov / trace * cov.shape[0]
    loading = float(config["covariance"].get("diagonal_loading", 1e-6))
    return cov + np.eye(cov.shape[0]) * loading


def _logm_spd(matrix):
    np = _numpy()
    values, vectors = np.linalg.eigh((matrix + matrix.T) / 2.0)
    values = np.clip(values, 1e-12, None)
    return (vectors * np.log(values)) @ vectors.T


def _expm_sym(matrix):
    np = _numpy()
    values, vectors = np.linalg.eigh((matrix + matrix.T) / 2.0)
    return (vectors * np.exp(values)) @ vectors.T


def _invsqrtm_spd(matrix):
    np = _numpy()
    values, vectors = np.linalg.eigh((matrix + matrix.T) / 2.0)
    values = np.clip(values, 1e-12, None)
    return (vectors * (1.0 / np.sqrt(values))) @ vectors.T


def _upper_triangular_features(matrix):
    np = _numpy()
    n = matrix.shape[0]
    values = []
    for i in range(n):
        for j in range(i, n):
            value = float(matrix[i, j])
            if i != j:
                value *= math.sqrt(2.0)
            values.append(value)
    return np.asarray(values, dtype=float)


def _standardize_np(x_train, x_test):
    np = _numpy()
    means = np.nanmean(x_train, axis=0)
    means = np.where(np.isfinite(means), means, 0.0)
    stds = np.nanstd(x_train, axis=0)
    stds = np.where(stds > 1e-12, stds, 1.0)
    train = np.where(np.isfinite(x_train), x_train, means)
    test = np.where(np.isfinite(x_test), x_test, means)
    return (train - means) / stds, (test - means) / stds


def _sample_weights_np(train_rows: list[dict[str, Any]], subject_balanced: bool):
    np = _numpy()
    if not subject_balanced:
        return np.ones(len(train_rows), dtype=float)
    counts: dict[str, int] = {}
    for row in train_rows:
        counts[row["subject"]] = counts.get(row["subject"], 0) + 1
    weights = np.asarray([1.0 / counts[row["subject"]] for row in train_rows], dtype=float)
    return weights / float(np.mean(weights))


def _fit_logistic_np(x, y, sample_weights, config: dict[str, Any]) -> dict[str, Any]:
    np = _numpy()
    coef = np.zeros(x.shape[1], dtype=float)
    intercept = 0.0
    lr = float(config["learning_rate"])
    l2 = float(config["l2"])
    n_steps = int(config["n_steps"])
    weights = sample_weights / float(np.sum(sample_weights))
    for _ in range(n_steps):
        prob = _sigmoid_np(x @ coef + intercept)
        error = (prob - y) * weights
        grad = x.T @ error + l2 * coef
        bias_grad = float(np.sum(error))
        coef = coef - lr * grad
        intercept -= lr * bias_grad
    return {"coef": coef, "intercept": float(intercept)}


def _sigmoid_np(values):
    np = _numpy()
    values = np.clip(values, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-values))


def _summarize_a2d_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "comparator_id": "A2d_riemannian",
        "n_folds": len(rows),
        "median_balanced_accuracy": _median([row["balanced_accuracy"] for row in rows]),
        "mean_ece_10_bins": _mean([row["ece_10_bins"] for row in rows]),
        "mean_brier": _mean([row["brier"] for row in rows]),
        "claim_ready": False,
        "scientific_limit": "A2d smoke summary only; not final Phase 1 comparator estimate.",
    }


def _build_covariance_manifest(extracted: dict[str, Any], rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    matrix_shapes = sorted({f"{len(row['covariance'])}x{len(row['covariance'][0])}" for row in rows})
    return {
        "status": "a2d_covariance_manifest_smoke",
        "backend": config["backend"],
        "n_rows": len(rows),
        "subjects": sorted({row["subject"] for row in rows}),
        "sessions": sorted({f"{row['subject']}/{row['session']}" for row in rows}),
        "matrix_shapes": matrix_shapes,
        "max_channels_smoke": config.get("max_channels"),
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "scientific_limit": "Smoke covariance manifest; not final A2d feature freeze.",
    }


def _build_calibration_report(logits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "calibration_a2d_smoke_computed_from_probe_logits",
        "logit_rows": len(logits),
        "required_for_full_phase1": "pooled and subject-wise calibration package remains required for claim evaluation",
    }


def _build_inputs(
    *,
    timestamp: str,
    prereg_bundle: Path,
    readiness_run: Path,
    readiness_path: Path,
    dataset_root: Path,
    output_dir: Path,
    selected_subjects: list[str],
    selected_sessions: list[dict[str, str]],
    config: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase1_a2d_smoke_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "readiness_run": str(readiness_run),
        "readiness_path": str(readiness_path),
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "comparator": "A2d_riemannian",
        "outer_test_subjects": selected_subjects,
        "selected_sessions": selected_sessions,
        "config": config,
        "git": _git_record(repo_root),
    }


def _build_summary(
    *,
    output_dir: Path,
    inputs: dict[str, Any],
    rows: list[dict[str, Any]],
    fold_logs: list[dict[str, Any]],
    metrics_summary: dict[str, Any],
    covariance_manifest: dict[str, Any],
    alignment_audit: dict[str, Any],
    calibration_report: dict[str, Any],
    negative_controls_report: dict[str, Any],
    influence_report: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if not fold_logs:
        blockers.append("no_folds_completed")
    if any(not fold["no_outer_test_subject_in_train"] for fold in fold_logs):
        blockers.append("outer_test_subject_leakage_detected")
    if alignment_audit["outer_test_subject_used_for_fit"]:
        blockers.append("outer_test_subject_used_for_a2d_fit")
    return {
        "status": "phase1_a2d_riemannian_smoke_complete" if not blockers else "phase1_a2d_riemannian_smoke_with_blockers",
        "output_dir": str(output_dir),
        "comparator": inputs["comparator"],
        "n_outer_folds": len(fold_logs),
        "outer_test_subjects": inputs["outer_test_subjects"],
        "n_covariance_rows": len(rows),
        "covariance_status": covariance_manifest["status"],
        "alignment_audit_status": alignment_audit["status"],
        "metrics_summary": metrics_summary,
        "calibration_status": calibration_report["status"],
        "negative_controls_status": negative_controls_report["status"],
        "influence_status": influence_report["status"],
        "blockers": blockers,
        "decoder_trained": True,
        "model_metrics_computed": True,
        "final_a2d_comparator": False,
        "claim_ready": False,
        "does_not_estimate_privileged_transfer_efficacy": True,
        "scientific_limit": (
            "A2d smoke trains a small scalp-only covariance/tangent probe to validate implementation mechanics. "
            "It is not a full Phase 1 A2d comparator estimate and cannot support efficacy claims."
        ),
        "next_step": "review_a2d_smoke_artifacts_then_extend_required_comparator_suite_under_revision_policy",
    }


def _render_report(summary: dict[str, Any], metrics_summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 A2d Riemannian Smoke Report",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Comparator: `{summary['comparator']}`",
        f"- Outer folds: `{summary['n_outer_folds']}`",
        f"- Covariance rows: `{summary['n_covariance_rows']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        "",
        "## Metrics Summary",
        "",
        f"- A2d median BA: `{metrics_summary['median_balanced_accuracy']}`",
        f"- A2d mean ECE: `{metrics_summary['mean_ece_10_bins']}`",
        f"- A2d mean Brier: `{metrics_summary['mean_brier']}`",
        "",
        "## Scientific Integrity",
        "",
        "- This smoke validates A2d implementation mechanics only.",
        "- It uses scalp EEG covariance inputs only.",
        "- Held-out outer-test subjects are excluded from reference/alignment/classifier fitting.",
        "- It is not the final A2d comparator estimate.",
        "- It does not prove decoder efficacy or privileged-transfer efficacy.",
    ]
    return "\n".join(lines) + "\n"


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


def _numpy():
    try:
        import numpy as np  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - numpy is present in target runtimes
        raise Phase1A2dSmokeError("A2d smoke requires numpy. Install signal/runtime extras before running.") from exc
    return np
