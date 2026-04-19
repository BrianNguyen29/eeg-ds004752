"""Phase 1 A2/A2b model implementation smoke runner.

This module performs a deliberately small real-model smoke test for the first
scalp-only comparators. It is not the final EEGNet Phase 1 implementation and
must not be interpreted as privileged-transfer evidence.
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
from ..phase05.estimators import (
    Phase05EstimatorError,
    _optional_signal_imports,
    _read_edf,
    _read_tsv,
    _safe_float,
    _window_bandpower_features,
)
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


class Phase1ModelSmokeError(RuntimeError):
    """Raised when Phase 1 A2/A2b model smoke cannot proceed."""


@dataclass(frozen=True)
class Phase1ModelSmokeResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_MODEL_SMOKE_CONFIG = {
    "signal_windows_sec": {"task_maintenance": [2.25, 4.75]},
    "frequency_bands_hz": {
        "theta": [4.0, 8.0],
        "alpha": [8.0, 13.0],
        "beta": [13.0, 30.0],
    },
    "default_comparators": ["A2", "A2b"],
    "default_max_trials_per_session": 24,
    "logistic_probe": {
        "learning_rate": 0.05,
        "n_steps": 160,
        "l2": 0.001,
        "random_seed": 752061,
    },
}


def run_phase1_model_smoke(
    *,
    prereg_bundle: str | Path,
    readiness_run: str | Path,
    dataset_root: str | Path,
    output_root: str | Path,
    config: dict[str, Any] | None = None,
    repo_root: str | Path | None = None,
    comparators: list[str] | None = None,
    max_outer_folds: int = 2,
    outer_test_subjects: list[str] | None = None,
    max_trials_per_session: int | None = None,
    precomputed_rows: dict[str, Any] | None = None,
) -> Phase1ModelSmokeResult:
    """Run a non-claim A2/A2b model implementation smoke."""

    prereg_bundle = Path(prereg_bundle)
    readiness_run = Path(readiness_run)
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config = _merge_config(config or {})

    requested_comparators = comparators or list(config["default_comparators"])
    unsupported = sorted(set(requested_comparators) - {"A2", "A2b"})
    if unsupported:
        raise Phase1ModelSmokeError(f"Model smoke currently supports only A2/A2b; unsupported: {unsupported}")

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    readiness_path = _readiness_path(readiness_run)
    readiness = _read_json(readiness_path)
    try:
        _validate_readiness(readiness, bundle)
    except Phase1SmokeError as exc:
        raise Phase1ModelSmokeError(str(exc)) from exc

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
    logits_dir = output_dir / "a2_a2b_logits_smoke"
    fold_dir.mkdir(parents=True, exist_ok=True)
    logits_dir.mkdir(parents=True, exist_ok=True)

    max_trials = (
        int(max_trials_per_session)
        if max_trials_per_session is not None
        else int(config["default_max_trials_per_session"])
    )
    extracted = precomputed_rows or _extract_scalp_rows(
        dataset_root=dataset_root,
        sessions=selected_sessions,
        config=config,
        max_trials_per_session=max_trials,
    )
    rows = extracted["rows"]
    if len({row["subject"] for row in rows}) < 2:
        raise Phase1ModelSmokeError("At least two subjects with load 4/8 rows are required for model smoke")

    fold_logs = []
    comparator_metrics: dict[str, list[dict[str, Any]]] = {name: [] for name in requested_comparators}
    all_logits: dict[str, list[dict[str, Any]]] = {name: [] for name in requested_comparators}
    for fold_index, outer_subject in enumerate(selected_subjects, start=1):
        fold = _run_single_fold(
            rows=rows,
            feature_names=extracted["feature_names"],
            outer_subject=outer_subject,
            comparators=requested_comparators,
            config=config,
            fold_index=fold_index,
            logits_dir=logits_dir,
        )
        fold_logs.append(fold)
        _write_json(fold_dir / f"{fold['fold_id']}.json", fold)
        for comparator_id, metrics in fold["metrics_by_comparator"].items():
            comparator_metrics[comparator_id].append(metrics)
        for comparator_id, logits in fold["logits_by_comparator"].items():
            all_logits[comparator_id].extend(logits)

    metrics_summary = _summarize_metrics(comparator_metrics)
    calibration_report = _build_calibration_report(all_logits)
    negative_controls_report = {
        "status": "negative_controls_not_executed_model_smoke",
        "reason": "A2/A2b implementation smoke does not run shuffled/time-shifted teacher controls.",
        "required_for_full_phase1": True,
    }
    influence_report = _build_influence_report(comparator_metrics)
    inputs = _build_inputs(
        timestamp=timestamp,
        prereg_bundle=prereg_bundle,
        readiness_run=readiness_run,
        readiness_path=readiness_path,
        dataset_root=dataset_root,
        output_dir=output_dir,
        selected_subjects=selected_subjects,
        selected_sessions=selected_sessions,
        comparators=requested_comparators,
        config=config,
        repo_root=repo_root,
    )
    summary = _build_summary(
        output_dir=output_dir,
        inputs=inputs,
        extracted=extracted,
        fold_logs=fold_logs,
        metrics_summary=metrics_summary,
        calibration_report=calibration_report,
        negative_controls_report=negative_controls_report,
        influence_report=influence_report,
    )

    inputs_path = output_dir / "phase1_model_smoke_inputs.json"
    summary_path = output_dir / "phase1_model_smoke_summary.json"
    report_path = output_dir / "phase1_model_smoke_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "a2_metrics_smoke.json", {"folds": comparator_metrics.get("A2", []), "summary": metrics_summary.get("A2")})
    _write_json(output_dir / "a2b_metrics_smoke.json", {"folds": comparator_metrics.get("A2b", []), "summary": metrics_summary.get("A2b")})
    _write_json(output_dir / "calibration_model_smoke_report.json", calibration_report)
    _write_json(output_dir / "negative_controls_model_smoke_report.json", negative_controls_report)
    _write_json(output_dir / "influence_model_smoke_report.json", influence_report)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, metrics_summary), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1ModelSmokeResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _merge_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_MODEL_SMOKE_CONFIG))
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _extract_scalp_rows(
    *,
    dataset_root: Path,
    sessions: list[dict[str, str]],
    config: dict[str, Any],
    max_trials_per_session: int,
) -> dict[str, Any]:
    np, mne = _optional_signal_imports()
    bands = {name: tuple(values) for name, values in config["frequency_bands_hz"].items()}
    task_window = tuple(config["signal_windows_sec"]["task_maintenance"])
    rows: list[dict[str, Any]] = []
    feature_name_set: set[str] = set()
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
        sfreq = float(raw.info["sfreq"])
        channel_names = [str(name) for name in raw.ch_names]
        for event in events:
            trial_start = max(int(float(event["begSample"])) - 1, 0)
            features, feature_names = _window_bandpower_features(
                np=np,
                data=data,
                channel_names=channel_names,
                sfreq=sfreq,
                trial_start=trial_start,
                window_sec=task_window,
                bands=bands,
                prefix="scalp_task",
            )
            feature_name_set.update(feature_names)
            rows.append(
                {
                    "subject": subject,
                    "session": session,
                    "trial_id": str(event.get("nTrial", len(rows) + 1)),
                    "set_size": int(float(event["SetSize"])),
                    "label": 1 if int(float(event["SetSize"])) == 8 else 0,
                    "feature_map": dict(zip(feature_names, [float(x) for x in features.tolist()])),
                }
            )

    if not rows:
        raise Phase1ModelSmokeError("No load 4/8 scalp feature rows were extracted")
    feature_names = sorted(feature_name_set)
    for row in rows:
        feature_map = row.pop("feature_map")
        row["features"] = [feature_map.get(name, float("nan")) for name in feature_names]
    return {
        "status": "phase1_scalp_feature_rows_extracted",
        "rows": rows,
        "feature_names": feature_names,
        "skipped_sessions": skipped_sessions,
        "read_fallbacks": read_fallbacks,
    }


def _load_binary_load_events(events_path: Path) -> list[dict[str, str]]:
    events = _read_tsv(events_path)
    selected = []
    for row in events:
        if row.get("Artifact") not in ("0", 0, "0.0", "", None):
            continue
        set_size = _safe_float(row.get("SetSize"))
        if math.isfinite(set_size) and int(set_size) in (4, 8):
            selected.append(row)
    return selected


def _run_single_fold(
    *,
    rows: list[dict[str, Any]],
    feature_names: list[str],
    outer_subject: str,
    comparators: list[str],
    config: dict[str, Any],
    fold_index: int,
    logits_dir: Path,
) -> dict[str, Any]:
    train_rows = [row for row in rows if row["subject"] != outer_subject]
    test_rows = [row for row in rows if row["subject"] == outer_subject]
    if not train_rows or not test_rows:
        raise Phase1ModelSmokeError(f"Fold {outer_subject} has empty train/test rows")
    x_train = [[float(value) for value in row["features"]] for row in train_rows]
    y_train = [float(row["label"]) for row in train_rows]
    x_test = [[float(value) for value in row["features"]] for row in test_rows]
    y_test = [float(row["label"]) for row in test_rows]
    x_train, x_test = _impute_and_standardize(x_train, x_test)

    fold_id = f"fold_{fold_index:02d}_{outer_subject}"
    metrics_by_comparator = {}
    logits_by_comparator = {}
    for comparator_id in comparators:
        weights = _sample_weights(train_rows, comparator_id)
        model = _fit_logistic_probe(x_train, y_train, weights, config["logistic_probe"])
        prob = [_sigmoid(_dot(row, model["coef"]) + model["intercept"]) for row in x_test]
        pred = [1 if value >= 0.5 else 0 for value in prob]
        metrics = _classification_metrics(y_test, prob, pred)
        metrics.update(
            {
                "comparator_id": comparator_id,
                "outer_test_subject": outer_subject,
                "n_train_trials": int(len(train_rows)),
                "n_test_trials": int(len(test_rows)),
                "training_policy": (
                    "subject_balanced_pooled_scalp_only_probe"
                    if comparator_id == "A2b"
                    else "pooled_scalp_only_probe"
                ),
                "scientific_limit": "Implementation smoke metric; not final EEGNet comparator evidence.",
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
        _write_json(logits_dir / f"{fold_id}_{comparator_id}_logits.json", {"rows": logits})
        metrics_by_comparator[comparator_id] = metrics
        logits_by_comparator[comparator_id] = logits

    return {
        "status": "phase1_a2_a2b_model_smoke_fold_complete",
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "feature_count": len(feature_names),
        "train_subjects": sorted({row["subject"] for row in train_rows}),
        "test_subjects": [outer_subject],
        "no_outer_test_subject_in_train": outer_subject not in {row["subject"] for row in train_rows},
        "metrics_by_comparator": metrics_by_comparator,
        "logits_by_comparator": logits_by_comparator,
    }


def _sample_weights(train_rows: list[dict[str, Any]], comparator_id: str) -> list[float]:
    if comparator_id != "A2b":
        return [1.0] * len(train_rows)
    subject_counts: dict[str, int] = {}
    for row in train_rows:
        subject_counts[row["subject"]] = subject_counts.get(row["subject"], 0) + 1
    weights = [1.0 / subject_counts[row["subject"]] for row in train_rows]
    mean_weight = sum(weights) / len(weights)
    return [weight / mean_weight for weight in weights]


def _impute_and_standardize(
    x_train: list[list[float]],
    x_test: list[list[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    if not x_train:
        raise Phase1ModelSmokeError("Cannot standardize an empty training matrix")
    n_features = len(x_train[0])
    means = []
    stds = []
    for column in range(n_features):
        values = [row[column] for row in x_train if math.isfinite(row[column])]
        mean = sum(values) / len(values) if values else 0.0
        variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0.0
        std = math.sqrt(variance)
        means.append(mean)
        stds.append(std if std > 1e-8 else 1.0)

    def transform(matrix: list[list[float]]) -> list[list[float]]:
        transformed = []
        for row in matrix:
            transformed.append(
                [
                    ((value if math.isfinite(value) else means[index]) - means[index]) / stds[index]
                    for index, value in enumerate(row)
                ]
            )
        return transformed

    return transform(x_train), transform(x_test)


def _fit_logistic_probe(
    x: list[list[float]],
    y: list[float],
    sample_weights: list[float],
    config: dict[str, Any],
) -> dict[str, Any]:
    coef = [0.0] * len(x[0])
    intercept = 0.0
    lr = float(config["learning_rate"])
    l2 = float(config["l2"])
    n_steps = int(config["n_steps"])
    weight_sum = sum(sample_weights)
    weights = [weight / weight_sum for weight in sample_weights]
    for _ in range(n_steps):
        grad = [0.0] * len(coef)
        bias_grad = 0.0
        for features, label, weight in zip(x, y, weights):
            prob = _sigmoid(_dot(features, coef) + intercept)
            error = (prob - label) * weight
            for index, value in enumerate(features):
                grad[index] += value * error
            bias_grad += error
        for index, value in enumerate(coef):
            grad[index] += l2 * value
        coef = [value - lr * grad[index] for index, value in enumerate(coef)]
        intercept -= lr * bias_grad
    return {"coef": coef, "intercept": intercept}


def _dot(left: list[float], right: list[float]) -> float:
    return sum(x * y for x, y in zip(left, right))


def _sigmoid(z: float) -> float:
    z = max(-40.0, min(40.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def _classification_metrics(y_true: list[float], prob: list[float], pred: list[int]) -> dict[str, Any]:
    labels = [int(value) for value in y_true]
    positives = [index for index, value in enumerate(labels) if value == 1]
    negatives = [index for index, value in enumerate(labels) if value == 0]
    tpr = _indexed_accuracy(pred, positives, expected=1)
    tnr = _indexed_accuracy(pred, negatives, expected=0)
    ba = _safe_mean([tpr, tnr])
    return {
        "balanced_accuracy": _round_or_none(ba),
        "accuracy": _round_or_none(sum(1 for label, guess in zip(labels, pred) if label == guess) / len(labels)),
        "brier": _round_or_none(sum((p - label) ** 2 for p, label in zip(prob, labels)) / len(labels)),
        "ece_10_bins": _round_or_none(_ece(labels, prob, n_bins=10)),
        "n_pos": len(positives),
        "n_neg": len(negatives),
    }


def _indexed_accuracy(pred: list[int], indices: list[int], expected: int) -> float:
    if not indices:
        return float("nan")
    return sum(1 for index in indices if pred[index] == expected) / len(indices)


def _ece(y_true: list[int], prob: list[float], n_bins: int) -> float:
    total = len(y_true)
    ece = 0.0
    for bin_index in range(n_bins):
        lo = bin_index / n_bins
        hi = (bin_index + 1) / n_bins
        indices = [
            index
            for index, value in enumerate(prob)
            if value >= lo and (value < hi if hi < 1.0 else value <= hi)
        ]
        if not indices:
            continue
        conf = sum(prob[index] for index in indices) / len(indices)
        acc = sum(y_true[index] for index in indices) / len(indices)
        ece += len(indices) / total * abs(conf - acc)
    return ece


def _safe_mean(values: list[float]) -> float:
    finite = [value for value in values if math.isfinite(value)]
    return float(sum(finite) / len(finite)) if finite else float("nan")


def _summarize_metrics(comparator_metrics: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    summary = {}
    for comparator_id, rows in comparator_metrics.items():
        summary[comparator_id] = {
            "n_folds": len(rows),
            "median_balanced_accuracy": _median([row["balanced_accuracy"] for row in rows]),
            "mean_ece_10_bins": _mean([row["ece_10_bins"] for row in rows]),
            "mean_brier": _mean([row["brier"] for row in rows]),
            "claim_ready": False,
            "scientific_limit": "Smoke summary only; not final Phase 1 comparator estimate.",
        }
    return summary


def _build_calibration_report(all_logits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "status": "calibration_smoke_computed_from_probe_logits",
        "comparators": sorted(all_logits),
        "logit_rows_by_comparator": {key: len(value) for key, value in all_logits.items()},
        "required_for_full_phase1": "pooled and subject-wise calibration package remains required for claim evaluation",
    }


def _build_influence_report(comparator_metrics: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "status": "influence_smoke_not_claim_evaluable",
        "fold_count_by_comparator": {key: len(value) for key, value in comparator_metrics.items()},
        "reason": "Only 1-2 smoke folds are expected; influence concentration is a full-run governance calculation.",
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
    comparators: list[str],
    config: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase1_a2_a2b_model_smoke_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "readiness_run": str(readiness_run),
        "readiness_path": str(readiness_path),
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "comparators": comparators,
        "outer_test_subjects": selected_subjects,
        "selected_sessions": selected_sessions,
        "config": config,
        "git": _git_record(repo_root),
    }


def _build_summary(
    *,
    output_dir: Path,
    inputs: dict[str, Any],
    extracted: dict[str, Any],
    fold_logs: list[dict[str, Any]],
    metrics_summary: dict[str, Any],
    calibration_report: dict[str, Any],
    negative_controls_report: dict[str, Any],
    influence_report: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if not fold_logs:
        blockers.append("no_folds_completed")
    if any(not fold["no_outer_test_subject_in_train"] for fold in fold_logs):
        blockers.append("outer_test_subject_leakage_detected")
    return {
        "status": "phase1_a2_a2b_model_smoke_complete" if not blockers else "phase1_a2_a2b_model_smoke_with_blockers",
        "output_dir": str(output_dir),
        "comparators": inputs["comparators"],
        "n_outer_folds": len(fold_logs),
        "outer_test_subjects": inputs["outer_test_subjects"],
        "n_feature_rows": len(extracted["rows"]),
        "n_features": len(extracted["feature_names"]),
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "metrics_summary": metrics_summary,
        "calibration_status": calibration_report["status"],
        "negative_controls_status": negative_controls_report["status"],
        "influence_status": influence_report["status"],
        "blockers": blockers,
        "decoder_trained": True,
        "model_metrics_computed": True,
        "final_eegnet_comparator": False,
        "claim_ready": False,
        "does_not_estimate_privileged_transfer_efficacy": True,
        "scientific_limit": (
            "A2/A2b model smoke trains a small scalp-only probe to validate implementation mechanics. "
            "It is not a full Phase 1 neural comparator run and cannot support efficacy claims."
        ),
        "next_step": "review_smoke_artifacts_then_implement_full_a2_a2b_eegnet_or_continue_a2c_a2d_planning",
    }


def _render_report(summary: dict[str, Any], metrics_summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 A2/A2b Model Implementation Smoke Report",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Comparators: `{summary['comparators']}`",
        f"- Outer folds: `{summary['n_outer_folds']}`",
        f"- Feature rows: `{summary['n_feature_rows']}`",
        f"- Features: `{summary['n_features']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        "",
        "## Metrics Summary",
        "",
    ]
    for comparator_id, item in metrics_summary.items():
        lines.append(f"- {comparator_id}: median BA `{item['median_balanced_accuracy']}`, mean ECE `{item['mean_ece_10_bins']}`")
    lines.extend(
        [
            "",
            "## Scientific Integrity",
            "",
            "- This smoke trains a small scalp-only probe for implementation validation only.",
            "- It is not the final EEGNet comparator estimate.",
            "- It does not use iEEG or teacher targets for A2/A2b.",
            "- It does not prove privileged-transfer efficacy.",
        ]
    )
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


def _median(values: list[float | None]) -> float | None:
    finite = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not finite:
        return None
    mid = len(finite) // 2
    if len(finite) % 2:
        return round(finite[mid], 6)
    return round((finite[mid - 1] + finite[mid]) / 2.0, 6)


def _mean(values: list[float | None]) -> float | None:
    finite = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return round(sum(finite) / len(finite), 6) if finite else None


def _round_or_none(value: float) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 6)
