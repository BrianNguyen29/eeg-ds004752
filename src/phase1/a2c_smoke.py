"""Phase 1 A2c CORAL comparator implementation smoke.

This runner is intentionally bounded. It validates the A2c data path, LOSO
split discipline, training-only domain covariance fitting, a small scalp-only
CORAL alignment proxy, logistic probe training, and artifact writing. It is not
the final neural CORAL comparator and cannot support decoder efficacy or
privileged-transfer claims.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..guards import assert_real_phase_allowed
from .model_smoke import _classification_metrics, _extract_scalp_rows, _mean, _median, _round_or_none
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


class Phase1A2cSmokeError(RuntimeError):
    """Raised when Phase 1 A2c smoke cannot proceed."""


@dataclass(frozen=True)
class Phase1A2cSmokeResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_A2C_SMOKE_CONFIG = {
    "workflow": "a2c_coral_comparator_smoke",
    "backend": "internal_numpy_coral_alignment_smoke_proxy",
    "signal_windows_sec": {"task_maintenance": [2.25, 4.75]},
    "frequency_bands_hz": {
        "theta": [4.0, 8.0],
        "alpha": [8.0, 13.0],
        "beta": [13.0, 30.0],
    },
    "default_max_outer_folds": 2,
    "default_max_trials_per_session": 24,
    "domain_key": "subject",
    "coral": {
        "beta": 0.1,
        "beta_selection_policy": "fixed_predeclared_smoke_value_no_outer_test_selection",
        "pairing_rule": "all_training_domain_pairs",
        "diagonal_loading": 1e-6,
        "min_rows_per_domain": 2,
        "alignment_interpolation": True,
    },
    "logistic_probe": {
        "learning_rate": 0.05,
        "n_steps": 160,
        "l2": 0.001,
        "subject_balanced": True,
    },
}


def run_phase1_a2c_smoke(
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
) -> Phase1A2cSmokeResult:
    """Run a non-claim A2c CORAL implementation smoke."""

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
        raise Phase1A2cSmokeError(str(exc)) from exc

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
    logits_dir = output_dir / "a2c_logits_smoke"
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
    rows = _coerce_feature_rows(extracted["rows"])
    feature_names = list(extracted.get("feature_names") or _default_feature_names(rows))
    if len({row["subject"] for row in rows}) < 2:
        raise Phase1A2cSmokeError("At least two subjects with load 4/8 feature rows are required for A2c smoke")

    fold_logs = []
    fold_metrics = []
    all_logits = []
    domain_audit = {
        "status": "a2c_domain_audit_smoke",
        "backend": config["backend"],
        "domain_key": config["domain_key"],
        "folds": [],
        "outer_test_subject_used_for_fit": False,
        "beta_selection_scope": config["coral"]["beta_selection_policy"],
    }
    coral_penalty_audit = {
        "status": "a2c_coral_penalty_audit_smoke",
        "backend": config["backend"],
        "formula": "mean_pairwise_frobenius_squared_domain_covariance_distance_div_4d2",
        "folds": [],
        "scientific_limit": "Penalty values are implementation diagnostics only, not final CORAL training evidence.",
    }

    for fold_index, outer_subject in enumerate(selected_subjects, start=1):
        fold = _run_a2c_fold(
            rows=rows,
            feature_names=feature_names,
            outer_subject=outer_subject,
            config=config,
            fold_index=fold_index,
            logits_dir=logits_dir,
        )
        fold_logs.append(fold)
        fold_metrics.append(fold["metrics"])
        all_logits.extend(fold["logits"])
        domain_audit["folds"].append(fold["domain_audit"])
        coral_penalty_audit["folds"].append(fold["coral_penalty_audit"])
        if not fold["domain_audit"]["no_outer_test_subject_in_any_fit"]:
            domain_audit["outer_test_subject_used_for_fit"] = True
        _write_json(fold_dir / f"{fold['fold_id']}.json", fold)

    metrics_summary = _summarize_a2c_metrics(fold_metrics)
    feature_manifest = _build_feature_manifest(extracted, rows, feature_names, config)
    calibration_report = _build_calibration_report(all_logits)
    negative_controls_report = {
        "status": "negative_controls_not_executed_a2c_smoke",
        "reason": "A2c implementation smoke does not run shuffled/time-shifted teacher controls.",
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
        feature_manifest=feature_manifest,
        fold_logs=fold_logs,
        metrics_summary=metrics_summary,
        domain_audit=domain_audit,
        calibration_report=calibration_report,
        negative_controls_report=negative_controls_report,
        influence_report=influence_report,
    )

    inputs_path = output_dir / "phase1_a2c_smoke_inputs.json"
    summary_path = output_dir / "phase1_a2c_smoke_summary.json"
    report_path = output_dir / "phase1_a2c_smoke_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "a2c_metrics_smoke.json", {"folds": fold_metrics, "summary": metrics_summary})
    _write_json(output_dir / "a2c_domain_audit.json", domain_audit)
    _write_json(output_dir / "a2c_coral_penalty_audit.json", coral_penalty_audit)
    _write_json(output_dir / "a2c_feature_manifest.json", feature_manifest)
    _write_json(output_dir / "calibration_a2c_smoke_report.json", calibration_report)
    _write_json(output_dir / "negative_controls_a2c_smoke_report.json", negative_controls_report)
    _write_json(output_dir / "influence_a2c_smoke_report.json", influence_report)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, metrics_summary), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1A2cSmokeResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _merge_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_A2C_SMOKE_CONFIG))
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def _coerce_feature_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    coerced = []
    for row in rows:
        features = [float(value) for value in row["features"]]
        label = int(row["label"])
        if label not in {0, 1}:
            raise Phase1A2cSmokeError(f"Unsupported A2c label: {label}")
        coerced.append(
            {
                "subject": str(row["subject"]),
                "session": str(row.get("session", "ses-unknown")),
                "trial_id": str(row.get("trial_id", len(coerced) + 1)),
                "set_size": int(row.get("set_size", 8 if label else 4)),
                "label": label,
                "features": features,
            }
        )
    return coerced


def _default_feature_names(rows: list[dict[str, Any]]) -> list[str]:
    n_features = len(rows[0]["features"]) if rows else 0
    return [f"feature_{index:03d}" for index in range(n_features)]


def _run_a2c_fold(
    *,
    rows: list[dict[str, Any]],
    feature_names: list[str],
    outer_subject: str,
    config: dict[str, Any],
    fold_index: int,
    logits_dir: Path,
) -> dict[str, Any]:
    np = _numpy()
    train_rows = [row for row in rows if row["subject"] != outer_subject]
    test_rows = [row for row in rows if row["subject"] == outer_subject]
    if not train_rows or not test_rows:
        raise Phase1A2cSmokeError(f"Fold {outer_subject} has empty train/test rows")
    _validate_binary_classes(train_rows, f"training fold excluding {outer_subject}")
    _validate_binary_classes(test_rows, f"outer-test fold {outer_subject}")

    x_train_raw = np.asarray([[float(value) for value in row["features"]] for row in train_rows], dtype=float)
    x_test_raw = np.asarray([[float(value) for value in row["features"]] for row in test_rows], dtype=float)
    x_train, x_test, standardizer = _fit_transform_standardizer(x_train_raw, x_test_raw)
    y_train = np.asarray([float(row["label"]) for row in train_rows], dtype=float)
    y_test = [float(row["label"]) for row in test_rows]

    domain_stats = _fit_training_domain_stats(x_train, train_rows, config)
    before_penalty = _coral_pairwise_penalty([item["covariance"] for item in domain_stats.values()])
    x_train_coral, after_penalty = _align_training_domains(x_train, train_rows, domain_stats, config)
    weights = _sample_weights_np(train_rows, bool(config["logistic_probe"].get("subject_balanced", True)))
    model = _fit_logistic_np(x_train_coral, y_train, weights, config["logistic_probe"])
    prob_arr = _sigmoid_np(x_test @ model["coef"] + model["intercept"])
    prob = [float(value) for value in prob_arr.tolist()]
    pred = [1 if value >= 0.5 else 0 for value in prob]
    metrics = _classification_metrics(y_test, prob, pred)

    fold_id = f"fold_{fold_index:02d}_{outer_subject}"
    train_subjects = sorted({row["subject"] for row in train_rows})
    train_domains = sorted(domain_stats)
    beta = float(config["coral"]["beta"])
    metrics.update(
        {
            "comparator_id": "A2c_CORAL",
            "outer_test_subject": outer_subject,
            "n_train_trials": int(len(train_rows)),
            "n_test_trials": int(len(test_rows)),
            "training_policy": "training_subjects_only_coral_alignment_proxy_l2_logistic_probe",
            "coral_beta_smoke": _round_or_none(beta),
            "scientific_limit": "A2c smoke metric; not final neural CORAL comparator evidence.",
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
    _write_json(logits_dir / f"{fold_id}_A2c_CORAL_logits.json", {"rows": logits})

    no_outer = outer_subject not in set(train_subjects)
    domain_audit = {
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "fit_subjects": train_subjects,
        "transform_subjects": [outer_subject],
        "domain_key": config["domain_key"],
        "train_domains": train_domains,
        "test_domains": sorted({_domain_id(row, config) for row in test_rows}),
        "normalization_fit_subjects": train_subjects,
        "coral_statistics_fit_subjects": train_subjects,
        "beta_selection_subjects": [],
        "beta_selection_scope": config["coral"]["beta_selection_policy"],
        "classifier_fit_subjects": train_subjects,
        "calibration_fit_subjects": [],
        "no_outer_test_subject_in_train": no_outer,
        "no_outer_test_subject_in_normalization_fit": no_outer,
        "no_outer_test_subject_in_coral_statistics_fit": no_outer,
        "no_outer_test_subject_in_beta_selection": True,
        "no_outer_test_subject_in_classifier_fit": no_outer,
        "no_outer_test_subject_in_calibration_fit": True,
        "no_outer_test_subject_in_any_fit": no_outer,
        "n_standardized_features": int(x_train.shape[1]),
        "standardizer_fit_scope": "training_rows_only",
        "standardizer_n_imputed_features": int(standardizer["n_imputed_features"]),
    }
    coral_penalty_audit = {
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "beta": _round_or_none(beta),
        "n_train_domains": len(train_domains),
        "training_domain_pairing_rule": config["coral"]["pairing_rule"],
        "before_alignment_mean_pairwise_penalty": _round_or_none(before_penalty),
        "after_alignment_mean_pairwise_penalty": _round_or_none(after_penalty),
        "outer_test_subject_used_for_coral_statistics": False,
        "scientific_limit": "Penalty audit is a smoke diagnostic only.",
    }
    return {
        "status": "phase1_a2c_coral_smoke_fold_complete",
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "train_subjects": train_subjects,
        "test_subjects": [outer_subject],
        "no_outer_test_subject_in_train": no_outer,
        "feature_count": len(feature_names),
        "metrics": metrics,
        "logits": logits,
        "domain_audit": domain_audit,
        "coral_penalty_audit": coral_penalty_audit,
    }


def _validate_binary_classes(rows: list[dict[str, Any]], scope: str) -> None:
    labels = {int(row["label"]) for row in rows}
    if labels != {0, 1}:
        raise Phase1A2cSmokeError(f"A2c smoke requires load 4 and load 8 labels in {scope}; observed {sorted(labels)}")


def _fit_transform_standardizer(x_train, x_test):
    np = _numpy()
    means = np.nanmean(x_train, axis=0)
    means = np.where(np.isfinite(means), means, 0.0)
    stds = np.nanstd(x_train, axis=0)
    stds = np.where(stds > 1e-12, stds, 1.0)
    train = np.where(np.isfinite(x_train), x_train, means)
    test = np.where(np.isfinite(x_test), x_test, means)
    return (train - means) / stds, (test - means) / stds, {
        "n_imputed_features": int(np.sum(~np.isfinite(np.nanmean(x_train, axis=0)))),
    }


def _fit_training_domain_stats(x_train, train_rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    np = _numpy()
    min_rows = int(config["coral"]["min_rows_per_domain"])
    diagonal_loading = float(config["coral"]["diagonal_loading"])
    domains = sorted({_domain_id(row, config) for row in train_rows})
    if len(domains) < 2:
        raise Phase1A2cSmokeError("A2c CORAL smoke requires at least two training domains")
    stats: dict[str, dict[str, Any]] = {}
    for domain in domains:
        indices = [index for index, row in enumerate(train_rows) if _domain_id(row, config) == domain]
        if len(indices) < min_rows:
            raise Phase1A2cSmokeError(
                f"A2c CORAL smoke domain {domain} has {len(indices)} rows; min_rows_per_domain={min_rows}"
            )
        values = x_train[indices, :]
        mean = np.mean(values, axis=0)
        centered = values - mean
        covariance = (centered.T @ centered) / max(len(indices) - 1, 1)
        covariance = covariance + diagonal_loading * np.eye(covariance.shape[0])
        stats[domain] = {"indices": indices, "mean": mean, "covariance": covariance}
    return stats


def _align_training_domains(x_train, train_rows: list[dict[str, Any]], domain_stats: dict[str, dict[str, Any]], config: dict[str, Any]):
    np = _numpy()
    beta = float(config["coral"]["beta"])
    beta = max(0.0, min(1.0, beta))
    reference = sum(item["covariance"] for item in domain_stats.values()) / float(len(domain_stats))
    reference_sqrt = _sqrtm_spd(reference)
    aligned = np.array(x_train, copy=True)
    for domain, item in domain_stats.items():
        invsqrt = _invsqrtm_spd(item["covariance"])
        indices = item["indices"]
        centered = x_train[indices, :] - item["mean"]
        domain_aligned = centered @ invsqrt @ reference_sqrt
        if bool(config["coral"].get("alignment_interpolation", True)):
            aligned[indices, :] = (1.0 - beta) * x_train[indices, :] + beta * domain_aligned
        else:
            aligned[indices, :] = domain_aligned
    after_covariances = []
    for domain, item in domain_stats.items():
        values = aligned[item["indices"], :]
        centered = values - np.mean(values, axis=0)
        after_covariances.append((centered.T @ centered) / max(len(item["indices"]) - 1, 1))
    return aligned, _coral_pairwise_penalty(after_covariances)


def _sqrtm_spd(matrix):
    np = _numpy()
    values, vectors = np.linalg.eigh(matrix)
    values = np.clip(values, 1e-12, None)
    return (vectors * np.sqrt(values)) @ vectors.T


def _invsqrtm_spd(matrix):
    np = _numpy()
    values, vectors = np.linalg.eigh(matrix)
    values = np.clip(values, 1e-12, None)
    return (vectors * (1.0 / np.sqrt(values))) @ vectors.T


def _coral_pairwise_penalty(covariances: list[Any]) -> float:
    np = _numpy()
    if len(covariances) < 2:
        return float("nan")
    d = float(covariances[0].shape[0])
    values = []
    for left_index, left in enumerate(covariances):
        for right in covariances[left_index + 1 :]:
            diff = left - right
            values.append(float(np.sum(diff * diff) / (4.0 * d * d)))
    return float(sum(values) / len(values)) if values else float("nan")


def _domain_id(row: dict[str, Any], config: dict[str, Any]) -> str:
    key = str(config.get("domain_key", "subject"))
    if key == "subject_session":
        return f"{row['subject']}/{row['session']}"
    if key != "subject":
        raise Phase1A2cSmokeError(f"Unsupported A2c smoke domain_key: {key}")
    return str(row["subject"])


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


def _summarize_a2c_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "comparator_id": "A2c_CORAL",
        "n_folds": len(rows),
        "median_balanced_accuracy": _median([row["balanced_accuracy"] for row in rows]),
        "mean_ece_10_bins": _mean([row["ece_10_bins"] for row in rows]),
        "mean_brier": _mean([row["brier"] for row in rows]),
        "claim_ready": False,
        "scientific_limit": "A2c smoke summary only; not final Phase 1 comparator estimate.",
    }


def _build_feature_manifest(
    extracted: dict[str, Any],
    rows: list[dict[str, Any]],
    feature_names: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "a2c_feature_manifest_smoke",
        "backend": config["backend"],
        "n_rows": len(rows),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "subjects": sorted({row["subject"] for row in rows}),
        "sessions": sorted({f"{row['subject']}/{row['session']}" for row in rows}),
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "scientific_limit": "Smoke feature manifest; not final A2c feature freeze.",
    }


def _build_calibration_report(logits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "calibration_a2c_smoke_computed_from_probe_logits",
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
        "status": "phase1_a2c_smoke_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "readiness_run": str(readiness_run),
        "readiness_path": str(readiness_path),
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "comparator": "A2c_CORAL",
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
    feature_manifest: dict[str, Any],
    fold_logs: list[dict[str, Any]],
    metrics_summary: dict[str, Any],
    domain_audit: dict[str, Any],
    calibration_report: dict[str, Any],
    negative_controls_report: dict[str, Any],
    influence_report: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if not fold_logs:
        blockers.append("no_folds_completed")
    if any(not fold["no_outer_test_subject_in_train"] for fold in fold_logs):
        blockers.append("outer_test_subject_leakage_detected")
    if domain_audit["outer_test_subject_used_for_fit"]:
        blockers.append("outer_test_subject_used_for_a2c_fit")
    return {
        "status": "phase1_a2c_coral_smoke_complete" if not blockers else "phase1_a2c_coral_smoke_with_blockers",
        "output_dir": str(output_dir),
        "comparator": inputs["comparator"],
        "n_outer_folds": len(fold_logs),
        "outer_test_subjects": inputs["outer_test_subjects"],
        "n_feature_rows": len(rows),
        "n_features": feature_manifest["n_features"],
        "feature_manifest_status": feature_manifest["status"],
        "domain_audit_status": domain_audit["status"],
        "metrics_summary": metrics_summary,
        "calibration_status": calibration_report["status"],
        "negative_controls_status": negative_controls_report["status"],
        "influence_status": influence_report["status"],
        "blockers": blockers,
        "decoder_trained": True,
        "model_metrics_computed": True,
        "final_a2c_comparator": False,
        "claim_ready": False,
        "does_not_estimate_privileged_transfer_efficacy": True,
        "scientific_limit": (
            "A2c smoke trains a small scalp-only CORAL alignment proxy to validate implementation mechanics. "
            "It is not a full Phase 1 neural CORAL comparator estimate and cannot support efficacy claims."
        ),
        "next_step": "review_a2c_smoke_artifacts_then_continue_required_comparator_suite_under_revision_policy",
    }


def _render_report(summary: dict[str, Any], metrics_summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 A2c CORAL Smoke Report",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Comparator: `{summary['comparator']}`",
        f"- Outer folds: `{summary['n_outer_folds']}`",
        f"- Feature rows: `{summary['n_feature_rows']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        "",
        "## Metrics Summary",
        "",
        f"- A2c median BA: `{metrics_summary['median_balanced_accuracy']}`",
        f"- A2c mean ECE: `{metrics_summary['mean_ece_10_bins']}`",
        f"- A2c mean Brier: `{metrics_summary['mean_brier']}`",
        "",
        "## Scientific Integrity",
        "",
        "- This smoke validates A2c implementation mechanics only.",
        "- It uses scalp EEG features only.",
        "- Held-out outer-test subjects are excluded from normalization, CORAL statistics, beta selection, classifier and calibration fitting.",
        "- It is not the final neural CORAL comparator estimate.",
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
        raise Phase1A2cSmokeError("A2c smoke requires numpy. Install runtime dependencies before running.") from exc
    return np
