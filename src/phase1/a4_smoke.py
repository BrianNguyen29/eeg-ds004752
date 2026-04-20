"""Phase 1 A4 privileged train-time-only implementation smoke.

This runner validates A4 split discipline with a bounded internal NumPy proxy.
The proxy simulates a train-time privileged/teacher-side path for engineering
checks only. It does not load real iEEG privileged features, it never uses the
privileged path at inference time, and it cannot support decoder efficacy or
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
from .a3_smoke import _fit_logistic_np, _fit_transform_standardizer, _sample_weights_np, _sigmoid_np, _numpy
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


class Phase1A4SmokeError(RuntimeError):
    """Raised when Phase 1 A4 smoke cannot proceed."""


@dataclass(frozen=True)
class Phase1A4SmokeResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_A4_SMOKE_CONFIG = {
    "workflow": "a4_privileged_train_time_only_smoke",
    "backend": "internal_numpy_privileged_train_time_proxy",
    "signal_windows_sec": {"task_maintenance": [2.25, 4.75]},
    "frequency_bands_hz": {
        "theta": [4.0, 8.0],
        "alpha": [8.0, 13.0],
        "beta": [13.0, 30.0],
    },
    "default_max_outer_folds": 2,
    "default_max_trials_per_session": 24,
    "privileged_proxy": {
        "source": "training_subjects_internal_teacher_side_proxy_not_real_ieeg",
        "real_ieeg_privileged_used": False,
        "privileged_used_at_inference": False,
        "temperature": 2.0,
        "soft_label_clip": 0.02,
        "learning_rate": 0.05,
        "n_steps": 180,
        "l2": 0.001,
        "subject_balanced": True,
    },
    "observability_gate_proxy": {
        "fit_scope": "training_subjects_only",
        "feature_weight_floor": 0.35,
        "feature_weight_ceiling": 1.0,
        "uses_outer_test_subject": False,
    },
    "student_probe": {
        "distillation_alpha_hard_label": 0.45,
        "learning_rate": 0.05,
        "n_steps": 180,
        "l2": 0.001,
        "subject_balanced": True,
    },
}


def run_phase1_a4_smoke(
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
) -> Phase1A4SmokeResult:
    """Run a non-claim A4 train-time-only privileged implementation smoke."""

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
        raise Phase1A4SmokeError(str(exc)) from exc

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
    logits_dir = output_dir / "a4_logits_smoke"
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
        raise Phase1A4SmokeError("At least two subjects with load 4/8 feature rows are required for A4 smoke")

    fold_logs = []
    fold_metrics = []
    all_logits = []
    privileged_audit = {
        "status": "a4_privileged_train_time_audit_smoke",
        "backend": config["backend"],
        "privileged_proxy_source": config["privileged_proxy"]["source"],
        "real_ieeg_privileged_used": False,
        "privileged_used_at_inference": False,
        "folds": [],
        "outer_test_subject_used_for_any_fit": False,
        "scientific_limit": "A4 smoke audit validates train-time-only privileged path discipline only; it is not final A4 evidence.",
    }

    for fold_index, outer_subject in enumerate(selected_subjects, start=1):
        fold = _run_a4_fold(
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
        privileged_audit["folds"].append(fold["privileged_audit"])
        if not fold["privileged_audit"]["no_outer_test_subject_in_any_fit"]:
            privileged_audit["outer_test_subject_used_for_any_fit"] = True
        _write_json(fold_dir / f"{fold['fold_id']}.json", fold)

    metrics_summary = _summarize_a4_metrics(fold_metrics)
    feature_manifest = _build_feature_manifest(extracted, rows, feature_names, config)
    privileged_manifest = _build_privileged_manifest(fold_logs, config)
    gate_manifest = _build_gate_manifest(fold_logs, config)
    calibration_report = _build_calibration_report(all_logits)
    negative_controls_report = {
        "status": "negative_controls_not_executed_a4_smoke",
        "reason": "A4 implementation smoke does not run shuffled/time-shifted teacher or nuisance controls.",
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
        privileged_manifest=privileged_manifest,
        gate_manifest=gate_manifest,
        fold_logs=fold_logs,
        metrics_summary=metrics_summary,
        privileged_audit=privileged_audit,
        calibration_report=calibration_report,
        negative_controls_report=negative_controls_report,
        influence_report=influence_report,
    )

    inputs_path = output_dir / "phase1_a4_smoke_inputs.json"
    summary_path = output_dir / "phase1_a4_smoke_summary.json"
    report_path = output_dir / "phase1_a4_smoke_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "a4_metrics_smoke.json", {"folds": fold_metrics, "summary": metrics_summary})
    _write_json(output_dir / "a4_privileged_train_time_audit.json", privileged_audit)
    _write_json(output_dir / "a4_privileged_manifest.json", privileged_manifest)
    _write_json(output_dir / "a4_gate_manifest.json", gate_manifest)
    _write_json(output_dir / "a4_feature_manifest.json", feature_manifest)
    _write_json(output_dir / "calibration_a4_smoke_report.json", calibration_report)
    _write_json(output_dir / "negative_controls_a4_smoke_report.json", negative_controls_report)
    _write_json(output_dir / "influence_a4_smoke_report.json", influence_report)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, metrics_summary), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1A4SmokeResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _merge_config(config: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_A4_SMOKE_CONFIG))
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
            raise Phase1A4SmokeError(f"Unsupported A4 label: {label}")
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


def _run_a4_fold(
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
        raise Phase1A4SmokeError(f"Fold {outer_subject} has empty train/test rows")
    _validate_binary_classes(train_rows, f"training fold excluding {outer_subject}")
    _validate_binary_classes(test_rows, f"outer-test fold {outer_subject}")

    x_train_raw = np.asarray([[float(value) for value in row["features"]] for row in train_rows], dtype=float)
    x_test_raw = np.asarray([[float(value) for value in row["features"]] for row in test_rows], dtype=float)
    x_train, x_test, standardizer = _fit_transform_standardizer(x_train_raw, x_test_raw)
    y_train = np.asarray([float(row["label"]) for row in train_rows], dtype=float)
    y_test = [float(row["label"]) for row in test_rows]

    gate_weights = _fit_gate_weights(x_train, y_train, config)
    x_train_student = x_train * gate_weights
    x_test_student = x_test * gate_weights
    x_train_privileged = _build_train_time_privileged_view(x_train, y_train, gate_weights)

    privileged_weights = _sample_weights_np(train_rows, bool(config["privileged_proxy"].get("subject_balanced", True)))
    privileged_model = _fit_logistic_np(x_train_privileged, y_train, privileged_weights, config["privileged_proxy"])
    privileged_train_prob = _sigmoid_np(
        (x_train_privileged @ privileged_model["coef"] + privileged_model["intercept"])
        / float(config["privileged_proxy"]["temperature"])
    )
    privileged_train_prob = np.clip(
        privileged_train_prob,
        float(config["privileged_proxy"]["soft_label_clip"]),
        1.0 - float(config["privileged_proxy"]["soft_label_clip"]),
    )

    alpha = float(config["student_probe"]["distillation_alpha_hard_label"])
    alpha = max(0.0, min(1.0, alpha))
    train_time_targets = alpha * y_train + (1.0 - alpha) * privileged_train_prob
    student_weights = _sample_weights_np(train_rows, bool(config["student_probe"].get("subject_balanced", True)))
    student_model = _fit_logistic_np(x_train_student, train_time_targets, student_weights, config["student_probe"])
    prob_arr = _sigmoid_np(x_test_student @ student_model["coef"] + student_model["intercept"])
    prob = [float(value) for value in prob_arr.tolist()]
    pred = [1 if value >= 0.5 else 0 for value in prob]
    metrics = _classification_metrics(y_test, prob, pred)

    fold_id = f"fold_{fold_index:02d}_{outer_subject}"
    train_subjects = sorted({row["subject"] for row in train_rows})
    metrics.update(
        {
            "comparator_id": "A4_privileged",
            "outer_test_subject": outer_subject,
            "n_train_trials": int(len(train_rows)),
            "n_test_trials": int(len(test_rows)),
            "training_policy": "training_subjects_only_privileged_proxy_student_scalp_only_inference",
            "distillation_alpha_hard_label": _round_or_none(alpha),
            "privileged_temperature_smoke": _round_or_none(float(config["privileged_proxy"]["temperature"])),
            "scientific_limit": "A4 smoke metric; not final privileged-transfer evidence.",
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
    _write_json(logits_dir / f"{fold_id}_A4_privileged_logits.json", {"rows": logits})

    no_outer = outer_subject not in set(train_subjects)
    audit = {
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "fit_subjects": train_subjects,
        "transform_subjects": [outer_subject],
        "normalization_fit_subjects": train_subjects,
        "gate_weight_fit_subjects": train_subjects,
        "privileged_proxy_fit_subjects": train_subjects,
        "privileged_outputs_for_student_fit_subjects": train_subjects,
        "student_fit_subjects": train_subjects,
        "calibration_fit_subjects": [],
        "inference_subjects": [outer_subject],
        "privileged_used_at_inference": False,
        "teacher_used_at_inference": False,
        "real_ieeg_privileged_used": False,
        "privileged_proxy_source": config["privileged_proxy"]["source"],
        "no_outer_test_subject_in_train": no_outer,
        "no_outer_test_subject_in_normalization_fit": no_outer,
        "no_outer_test_subject_in_gate_weight_fit": no_outer,
        "no_outer_test_subject_in_privileged_proxy_fit": no_outer,
        "no_outer_test_subject_in_privileged_outputs_for_student_fit": no_outer,
        "no_outer_test_subject_in_student_fit": no_outer,
        "no_outer_test_subject_in_calibration_fit": True,
        "no_outer_test_subject_in_any_fit": no_outer,
        "student_inference_uses_scalp_only": True,
        "n_standardized_features": int(x_train.shape[1]),
        "n_privileged_proxy_features_train_only": int(x_train_privileged.shape[1]),
        "gate_weight_fit_scope": config["observability_gate_proxy"]["fit_scope"],
        "gate_weight_min": _round_or_none(float(np.min(gate_weights))),
        "gate_weight_max": _round_or_none(float(np.max(gate_weights))),
        "standardizer_fit_scope": "training_rows_only",
        "standardizer_n_imputed_features": int(standardizer["n_imputed_features"]),
        "scientific_limit": "Fold audit checks train-time-only privileged mechanics and leakage only.",
    }
    return {
        "status": "phase1_a4_privileged_smoke_fold_complete",
        "fold_id": fold_id,
        "outer_test_subject": outer_subject,
        "train_subjects": train_subjects,
        "test_subjects": [outer_subject],
        "no_outer_test_subject_in_train": no_outer,
        "feature_count": len(feature_names),
        "metrics": metrics,
        "logits": logits,
        "privileged_audit": audit,
    }


def _validate_binary_classes(rows: list[dict[str, Any]], scope: str) -> None:
    labels = {int(row["label"]) for row in rows}
    if labels != {0, 1}:
        raise Phase1A4SmokeError(f"A4 smoke requires load 4 and load 8 labels in {scope}; observed {sorted(labels)}")


def _fit_gate_weights(x_train, y_train, config: dict[str, Any]):
    np = _numpy()
    floor = float(config["observability_gate_proxy"]["feature_weight_floor"])
    ceiling = float(config["observability_gate_proxy"]["feature_weight_ceiling"])
    if floor <= 0.0 or ceiling < floor:
        raise Phase1A4SmokeError("Invalid A4 gate weight floor/ceiling")
    class0 = x_train[y_train < 0.5]
    class1 = x_train[y_train >= 0.5]
    if class0.size == 0 or class1.size == 0:
        raise Phase1A4SmokeError("A4 gate proxy requires both classes in training rows")
    contrast = np.abs(np.mean(class1, axis=0) - np.mean(class0, axis=0))
    denom = float(np.max(contrast))
    if denom <= 1e-12:
        scaled = np.ones_like(contrast)
    else:
        scaled = contrast / denom
    return floor + (ceiling - floor) * scaled


def _build_train_time_privileged_view(x_train, y_train, gate_weights):
    np = _numpy()
    gated = x_train * gate_weights
    label_centered = (y_train.reshape(-1, 1) - float(np.mean(y_train))) * 0.1
    return np.concatenate([gated, label_centered], axis=1)


def _summarize_a4_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "comparator_id": "A4_privileged",
        "n_folds": len(rows),
        "median_balanced_accuracy": _median([row["balanced_accuracy"] for row in rows]),
        "mean_ece_10_bins": _mean([row["ece_10_bins"] for row in rows]),
        "mean_brier": _mean([row["brier"] for row in rows]),
        "claim_ready": False,
        "scientific_limit": "A4 smoke summary only; not final Phase 1 privileged-transfer comparator estimate.",
    }


def _build_feature_manifest(
    extracted: dict[str, Any],
    rows: list[dict[str, Any]],
    feature_names: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "a4_feature_manifest_smoke",
        "backend": config["backend"],
        "n_rows": len(rows),
        "n_features": len(feature_names),
        "feature_names": feature_names,
        "subjects": sorted({row["subject"] for row in rows}),
        "sessions": sorted({f"{row['subject']}/{row['session']}" for row in rows}),
        "skipped_sessions": extracted.get("skipped_sessions", []),
        "read_fallbacks": extracted.get("read_fallbacks", []),
        "scientific_limit": "Smoke feature manifest; not final A4 feature freeze.",
    }


def _build_privileged_manifest(fold_logs: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "a4_privileged_manifest_smoke",
        "privileged_proxy_source": config["privileged_proxy"]["source"],
        "backend": config["backend"],
        "real_ieeg_privileged_used": False,
        "privileged_used_at_inference": False,
        "teacher_used_at_inference": False,
        "privileged_fit_policy": "training_subjects_only_per_outer_fold",
        "student_inference_policy": "scalp_features_only",
        "folds": [
            {
                "fold_id": fold["fold_id"],
                "outer_test_subject": fold["outer_test_subject"],
                "privileged_proxy_fit_subjects": fold["privileged_audit"]["privileged_proxy_fit_subjects"],
                "gate_weight_fit_subjects": fold["privileged_audit"]["gate_weight_fit_subjects"],
                "no_outer_test_subject_in_privileged_proxy_fit": fold["privileged_audit"][
                    "no_outer_test_subject_in_privileged_proxy_fit"
                ],
                "no_outer_test_subject_in_gate_weight_fit": fold["privileged_audit"][
                    "no_outer_test_subject_in_gate_weight_fit"
                ],
            }
            for fold in fold_logs
        ],
        "scientific_limit": (
            "This smoke manifest records an internal train-time privileged proxy only. "
            "It is not evidence from a final iEEG privileged-transfer pathway."
        ),
    }


def _build_gate_manifest(fold_logs: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "a4_gate_manifest_smoke",
        "fit_scope": config["observability_gate_proxy"]["fit_scope"],
        "uses_outer_test_subject": False,
        "folds": [
            {
                "fold_id": fold["fold_id"],
                "outer_test_subject": fold["outer_test_subject"],
                "gate_weight_fit_subjects": fold["privileged_audit"]["gate_weight_fit_subjects"],
                "no_outer_test_subject_in_gate_weight_fit": fold["privileged_audit"][
                    "no_outer_test_subject_in_gate_weight_fit"
                ],
                "gate_weight_min": fold["privileged_audit"]["gate_weight_min"],
                "gate_weight_max": fold["privileged_audit"]["gate_weight_max"],
            }
            for fold in fold_logs
        ],
        "scientific_limit": "Gate manifest is a smoke leak-guard diagnostic only, not final observability weighting evidence.",
    }


def _build_calibration_report(logits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "calibration_a4_smoke_computed_from_student_probe_logits",
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
        "status": "phase1_a4_smoke_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "readiness_run": str(readiness_run),
        "readiness_path": str(readiness_path),
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "comparator": "A4_privileged",
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
    privileged_manifest: dict[str, Any],
    gate_manifest: dict[str, Any],
    fold_logs: list[dict[str, Any]],
    metrics_summary: dict[str, Any],
    privileged_audit: dict[str, Any],
    calibration_report: dict[str, Any],
    negative_controls_report: dict[str, Any],
    influence_report: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if not fold_logs:
        blockers.append("no_folds_completed")
    if any(not fold["no_outer_test_subject_in_train"] for fold in fold_logs):
        blockers.append("outer_test_subject_leakage_detected")
    if privileged_audit["outer_test_subject_used_for_any_fit"]:
        blockers.append("outer_test_subject_used_for_a4_fit")
    return {
        "status": "phase1_a4_privileged_smoke_complete" if not blockers else "phase1_a4_privileged_smoke_with_blockers",
        "output_dir": str(output_dir),
        "comparator": inputs["comparator"],
        "n_outer_folds": len(fold_logs),
        "outer_test_subjects": inputs["outer_test_subjects"],
        "n_feature_rows": len(rows),
        "n_features": feature_manifest["n_features"],
        "feature_manifest_status": feature_manifest["status"],
        "privileged_manifest_status": privileged_manifest["status"],
        "gate_manifest_status": gate_manifest["status"],
        "privileged_audit_status": privileged_audit["status"],
        "metrics_summary": metrics_summary,
        "calibration_status": calibration_report["status"],
        "negative_controls_status": negative_controls_report["status"],
        "influence_status": influence_report["status"],
        "blockers": blockers,
        "decoder_trained": True,
        "model_metrics_computed": True,
        "final_a4_comparator": False,
        "claim_ready": False,
        "does_not_estimate_privileged_transfer_efficacy": True,
        "scientific_limit": (
            "A4 smoke trains a small internal train-time privileged proxy and scalp-only student probe to validate "
            "implementation mechanics. It is not a full Phase 1 A4 privileged-transfer comparator estimate and cannot "
            "support efficacy claims."
        ),
        "next_step": "review_a4_smoke_artifacts_then_continue_full_control_calibration_influence_package_under_revision_policy",
    }


def _render_report(summary: dict[str, Any], metrics_summary: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 A4 Privileged Train-Time-Only Smoke Report",
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
        f"- A4 median BA: `{metrics_summary['median_balanced_accuracy']}`",
        f"- A4 mean ECE: `{metrics_summary['mean_ece_10_bins']}`",
        f"- A4 mean Brier: `{metrics_summary['mean_brier']}`",
        "",
        "## Scientific Integrity",
        "",
        "- This smoke validates A4 train-time-only privileged mechanics only.",
        "- The privileged path is an internal training proxy and not final iEEG privileged evidence.",
        "- Held-out outer-test subjects are excluded from normalization, gate/weight fitting, privileged proxy fitting, privileged outputs for student fitting, student fitting and calibration fitting.",
        "- Inference uses the student probe on scalp features only; privileged outputs are not used at inference.",
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
