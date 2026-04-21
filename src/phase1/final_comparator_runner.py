"""Final Phase 1 comparator runner over the materialized feature matrix.

The runner consumes ``final_feature_matrix.csv`` and writes deterministic
feature-matrix comparator outputs, runtime leakage logs and output manifests.
It does not promote smoke artifacts and it does not open scientific claims.
Comparators that cannot be computed from this input are recorded as blocked
instead of being approximated.
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
from .model_smoke import _classification_metrics, _dot, _fit_logistic_probe, _mean, _median, _sigmoid
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalComparatorRunnerError(RuntimeError):
    """Raised when final comparator runner execution cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalComparatorRunnerResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "runner": "configs/phase1/final_comparator_runner.json",
}


def run_phase1_final_comparator_runner(
    *,
    prereg_bundle: str | Path,
    feature_matrix_run: str | Path,
    runner_readiness_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
    comparators: list[str] | None = None,
    max_outer_folds: int | None = None,
) -> Phase1FinalComparatorRunnerResult:
    """Run final feature-matrix comparators while keeping claims closed."""

    prereg_bundle = Path(prereg_bundle)
    feature_matrix_run = _resolve_run_dir(Path(feature_matrix_run))
    runner_readiness_run = _resolve_run_dir(Path(runner_readiness_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    matrix = _read_feature_matrix_run(feature_matrix_run)
    readiness = _read_runner_readiness_run(runner_readiness_run)
    runner_config = load_config(repo_root / config_paths["runner"])

    _validate_feature_matrix_boundary(matrix)
    _validate_runner_readiness_boundary(readiness)
    split_manifest = _read_split_manifest_from_matrix_sources(matrix)
    _validate_split_manifest(split_manifest)

    requested = comparators or list(runner_config.get("required_final_comparators", []))
    unknown = sorted(set(requested) - set(runner_config.get("required_final_comparators", [])))
    if unknown:
        raise Phase1FinalComparatorRunnerError(f"Unsupported final comparators requested: {unknown}")

    rows, feature_names = _load_matrix_rows(matrix["matrix_path"], matrix["schema"])
    input_validation = _validate_inputs(
        matrix=matrix,
        readiness=readiness,
        split_manifest=split_manifest,
        runner_config=runner_config,
        rows=rows,
        feature_names=feature_names,
        requested_comparators=requested,
        max_outer_folds=max_outer_folds,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    for dirname in [
        "fold_logs",
        "final_logits",
        "final_subject_level_metrics",
        "runtime_leakage_logs",
        "comparator_output_manifests",
        "blocked_comparators",
    ]:
        (output_dir / dirname).mkdir(parents=True, exist_ok=True)

    fold_specs = _selected_folds(split_manifest, max_outer_folds)
    completed: dict[str, dict[str, Any]] = {}
    blocked: dict[str, dict[str, Any]] = {}
    for comparator_id in requested:
        if comparator_id not in runner_config.get("feature_matrix_supported_comparators", []):
            blocked[comparator_id] = _write_blocked_comparator(
                output_dir=output_dir,
                comparator_id=comparator_id,
                reason=runner_config.get("blocked_comparator_reasons", {}).get(
                    comparator_id,
                    "Comparator cannot be executed from final_feature_matrix.csv alone.",
                ),
            )
            continue
        completed[comparator_id] = _run_supported_comparator(
            output_dir=output_dir,
            comparator_id=comparator_id,
            rows=rows,
            feature_names=feature_names,
            folds=fold_specs,
            runner_config=runner_config,
        )

    completeness_table = _build_completeness_table(
        required=runner_config.get("required_final_comparators", []),
        completed=completed,
        blocked=blocked,
    )
    aggregate_leakage = _build_aggregate_leakage(completed=completed, blocked=blocked, required=requested)
    claim_state = _build_claim_state(
        input_validation=input_validation,
        completed=completed,
        blocked=blocked,
        runner_config=runner_config,
    )
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        feature_matrix_run=feature_matrix_run,
        runner_readiness_run=runner_readiness_run,
        matrix=matrix,
        config_paths=config_paths,
        repo_root=repo_root,
    )
    summary = _build_summary(
        output_dir=output_dir,
        matrix=matrix,
        readiness=readiness,
        rows=rows,
        feature_names=feature_names,
        fold_specs=fold_specs,
        requested=requested,
        completed=completed,
        blocked=blocked,
        input_validation=input_validation,
        claim_state=claim_state,
    )
    inputs = {
        "status": "phase1_final_comparator_runner_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "feature_matrix_run": str(feature_matrix_run),
        "runner_readiness_run": str(runner_readiness_run),
        "config_paths": config_paths,
        "requested_comparators": requested,
        "max_outer_folds": max_outer_folds,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_comparator_runner_inputs.json"
    summary_path = output_dir / "phase1_final_comparator_runner_summary.json"
    report_path = output_dir / "phase1_final_comparator_runner_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_comparator_runner_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_comparator_runner_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_comparator_runtime_leakage_audit.json", aggregate_leakage)
    _write_json(output_dir / "phase1_final_comparator_completeness_table.json", completeness_table)
    _write_json(output_dir / "phase1_final_comparator_runner_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, completeness_table, aggregate_leakage, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalComparatorRunnerResult(
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


def _read_feature_matrix_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_feature_matrix_summary.json",
        "validation": "phase1_final_feature_matrix_validation.json",
        "schema": "phase1_final_feature_matrix_schema.json",
        "row_index": "final_feature_row_index.json",
        "source_links": "phase1_final_feature_matrix_source_links.json",
        "claim_state": "phase1_final_feature_matrix_claim_state.json",
    }
    payload = _read_required_files(run_dir, required, "Final feature matrix")
    matrix_path = Path(payload["summary"].get("matrix_path") or run_dir / "final_feature_matrix.csv")
    if not matrix_path.exists():
        raise Phase1FinalComparatorRunnerError(f"Final feature matrix CSV not found: {matrix_path}")
    payload["run_dir"] = run_dir
    payload["matrix_path"] = matrix_path
    return payload


def _read_runner_readiness_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_comparator_runner_readiness_summary.json",
        "input_validation": "phase1_final_comparator_runner_input_validation.json",
        "manifest_status": "phase1_final_comparator_runner_manifest_status.json",
        "claim_state": "phase1_final_comparator_runner_claim_state.json",
    }
    payload = _read_required_files(run_dir, required, "Final comparator runner readiness")
    payload["run_dir"] = run_dir
    return payload


def _read_required_files(run_dir: Path, required: dict[str, str], label: str) -> dict[str, Any]:
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalComparatorRunnerError(f"{label} file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_feature_matrix_boundary(matrix: dict[str, Any]) -> None:
    summary = matrix["summary"]
    validation = matrix["validation"]
    schema = matrix["schema"]
    if summary.get("status") != "phase1_final_feature_matrix_materialized":
        raise Phase1FinalComparatorRunnerError("Final comparator runner requires materialized final feature matrix")
    if summary.get("feature_matrix_ready") is not True:
        raise Phase1FinalComparatorRunnerError("Final feature matrix must be ready")
    if validation.get("status") != "phase1_final_feature_matrix_validation_passed":
        raise Phase1FinalComparatorRunnerError("Final feature matrix validation must pass")
    for key in ["contains_model_outputs", "contains_logits", "contains_metrics"]:
        if summary.get(key) is not False or schema.get(key) is not False:
            raise Phase1FinalComparatorRunnerError(f"Final feature matrix must not contain {key}")
    if summary.get("claim_ready") is not False or matrix["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalComparatorRunnerError("Final feature matrix must keep claim_ready=false")
    if int(summary.get("nonfinite_feature_values", -1)) != 0:
        raise Phase1FinalComparatorRunnerError("Final feature matrix contains non-finite feature values")


def _validate_runner_readiness_boundary(readiness: dict[str, Any]) -> None:
    summary = readiness["summary"]
    if summary.get("status") != "phase1_final_comparator_runner_readiness_recorded":
        raise Phase1FinalComparatorRunnerError("Runner requires recorded final comparator runner readiness")
    if summary.get("upstream_manifests_ready") is not True:
        raise Phase1FinalComparatorRunnerError("Runner readiness upstream_manifests_ready must be true")
    if summary.get("final_comparator_outputs_present") is not False:
        raise Phase1FinalComparatorRunnerError("Runner readiness must precede final comparator outputs")
    if summary.get("runtime_comparator_logs_audited") is not False:
        raise Phase1FinalComparatorRunnerError("Runtime comparator logs must be missing before this runner")
    if summary.get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalComparatorRunnerError("Runner readiness must not promote smoke artifacts")
    if summary.get("claim_ready") is not False or readiness["claim_state"].get("claim_ready") is not False:
        raise Phase1FinalComparatorRunnerError("Runner readiness must keep claim_ready=false")


def _read_split_manifest_from_matrix_sources(matrix: dict[str, Any]) -> dict[str, Any]:
    path = Path(matrix["source_links"].get("final_split_manifest", ""))
    if not path.exists():
        raise Phase1FinalComparatorRunnerError(f"Final split manifest source not found: {path}")
    return _read_json(path)


def _validate_split_manifest(split_manifest: dict[str, Any]) -> None:
    if split_manifest.get("status") != "phase1_final_split_manifest_recorded":
        raise Phase1FinalComparatorRunnerError("Final split manifest must be recorded")
    if split_manifest.get("claim_ready") is not False:
        raise Phase1FinalComparatorRunnerError("Final split manifest must keep claim_ready=false")
    for fold in split_manifest.get("folds", []):
        train = set(fold.get("train_subjects", []))
        test = set(fold.get("test_subjects", []))
        if train & test:
            raise Phase1FinalComparatorRunnerError(f"Train/test subject overlap in fold {fold.get('fold_id')}")


def _load_matrix_rows(matrix_path: Path, schema: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    feature_names = list(schema.get("feature_names", []))
    identity = set(schema.get("row_identity_columns", []))
    if not feature_names:
        with matrix_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            feature_names = [name for name in (reader.fieldnames or []) if name not in identity]
    rows = []
    with matrix_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            features = [float(raw[name]) for name in feature_names]
            if any(not math.isfinite(value) for value in features):
                raise Phase1FinalComparatorRunnerError("Final feature matrix contains non-finite values")
            label = int(float(raw["label"]))
            if label not in (0, 1):
                raise Phase1FinalComparatorRunnerError(f"Non-binary label in row {raw.get('row_id')}: {label}")
            rows.append(
                {
                    "row_id": raw.get("row_id"),
                    "participant_id": raw.get("participant_id"),
                    "session_id": raw.get("session_id"),
                    "trial_id": raw.get("trial_id"),
                    "label": label,
                    "set_size": int(float(raw.get("set_size", 8 if label else 4))),
                    "event_onset_sample": raw.get("event_onset_sample"),
                    "source_eeg_file": raw.get("source_eeg_file"),
                    "features": features,
                }
            )
    if not rows:
        raise Phase1FinalComparatorRunnerError("Final feature matrix has no rows")
    return rows, feature_names


def _validate_inputs(
    *,
    matrix: dict[str, Any],
    readiness: dict[str, Any],
    split_manifest: dict[str, Any],
    runner_config: dict[str, Any],
    rows: list[dict[str, Any]],
    feature_names: list[str],
    requested_comparators: list[str],
    max_outer_folds: int | None,
) -> dict[str, Any]:
    subjects_in_rows = sorted({str(row["participant_id"]) for row in rows})
    subjects_in_split = sorted(split_manifest.get("eligible_subjects", []))
    observed = {
        "final_feature_matrix_ready": matrix["summary"].get("feature_matrix_ready"),
        "feature_matrix_contains_model_outputs": matrix["summary"].get("contains_model_outputs"),
        "feature_matrix_contains_logits": matrix["summary"].get("contains_logits"),
        "feature_matrix_contains_metrics": matrix["summary"].get("contains_metrics"),
        "runner_readiness_upstream_manifests_ready": readiness["summary"].get("upstream_manifests_ready"),
        "runner_readiness_final_comparator_outputs_present": readiness["summary"].get(
            "final_comparator_outputs_present"
        ),
        "runner_readiness_runtime_comparator_logs_audited": readiness["summary"].get(
            "runtime_comparator_logs_audited"
        ),
        "runner_readiness_smoke_artifacts_promoted": readiness["summary"].get("smoke_artifacts_promoted"),
    }
    blockers = [
        f"{key}_mismatch"
        for key, expected in runner_config.get("required_inputs", {}).items()
        if observed.get(key) is not expected
    ]
    if subjects_in_split and subjects_in_rows != subjects_in_split:
        blockers.append("feature_matrix_subjects_do_not_match_split_manifest")
    if len(feature_names) != int(matrix["summary"].get("n_features", len(feature_names))):
        blockers.append("feature_count_does_not_match_feature_matrix_summary")
    if max_outer_folds is not None and max_outer_folds < len(split_manifest.get("folds", [])):
        blockers.append("bounded_fold_subset_not_full_final_run")
    return {
        "status": "phase1_final_comparator_runner_inputs_ready" if not blockers else "phase1_final_comparator_runner_inputs_blocked",
        "observed": observed,
        "required": runner_config.get("required_inputs", {}),
        "requested_comparators": requested_comparators,
        "n_rows": len(rows),
        "n_features": len(feature_names),
        "subjects_in_rows": subjects_in_rows,
        "subjects_in_split": subjects_in_split,
        "max_outer_folds": max_outer_folds,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks runner prerequisites only; it is not model evidence.",
    }


def _selected_folds(split_manifest: dict[str, Any], max_outer_folds: int | None) -> list[dict[str, Any]]:
    folds = list(split_manifest.get("folds", []))
    if max_outer_folds is not None:
        folds = folds[:max_outer_folds]
    if not folds:
        raise Phase1FinalComparatorRunnerError("No LOSO folds available in final split manifest")
    return folds


def _run_supported_comparator(
    *,
    output_dir: Path,
    comparator_id: str,
    rows: list[dict[str, Any]],
    feature_names: list[str],
    folds: list[dict[str, Any]],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    fold_logs = []
    all_logits = []
    metrics = []
    for fold_index, fold in enumerate(folds, start=1):
        fold_result = _run_fold(
            comparator_id=comparator_id,
            fold=fold,
            rows=rows,
            runner_config=runner_config,
        )
        fold_logs.append(fold_result["fold_log"])
        all_logits.extend(fold_result["logits"])
        metrics.append(fold_result["metrics"])
        fold_dir = output_dir / "fold_logs" / comparator_id
        _write_json(fold_dir / f"{fold_result['fold_log']['fold_id']}.json", fold_result["fold_log"])

    metric_summary = {
        "status": "phase1_final_comparator_subject_metrics_recorded",
        "comparator_id": comparator_id,
        "n_folds": len(metrics),
        "median_balanced_accuracy": _median([row["balanced_accuracy"] for row in metrics]),
        "mean_ece_10_bins": _mean([row["ece_10_bins"] for row in metrics]),
        "mean_brier": _mean([row["brier"] for row in metrics]),
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": (
            "Feature-matrix final comparator diagnostic only. Claim evaluation still requires the complete "
            "comparator/control/calibration/influence/reporting package."
        ),
        "folds": metrics,
    }
    leakage = _runtime_leakage_audit(comparator_id, fold_logs)
    logits_payload = {
        "status": "phase1_final_comparator_logits_recorded",
        "comparator_id": comparator_id,
        "n_rows": len(all_logits),
        "contains_feature_values": False,
        "claim_ready": False,
        "claim_evaluable": False,
        "rows": all_logits,
        "scientific_limit": "Logits are implementation outputs only until the full claim package passes.",
    }
    manifest = {
        "status": "phase1_final_comparator_output_manifest_recorded",
        "comparator_id": comparator_id,
        "claim_ready": False,
        "claim_evaluable": False,
        "smoke_artifacts_promoted": False,
        "n_folds": len(fold_logs),
        "n_logit_rows": len(all_logits),
        "feature_count": len(feature_names),
        "files": {
            "logits": f"final_logits/{comparator_id}_final_logits.json",
            "subject_level_metrics": f"final_subject_level_metrics/{comparator_id}_subject_level_metrics.json",
            "runtime_leakage_audit": f"runtime_leakage_logs/{comparator_id}_runtime_leakage_audit.json",
            "fold_logs_dir": f"fold_logs/{comparator_id}",
        },
        "runtime_leakage_passed": leakage["outer_test_subject_used_for_any_fit"] is False,
        "scientific_limit": "Output manifest records files only; it is not by itself claim evidence.",
    }

    _write_json(output_dir / "final_logits" / f"{comparator_id}_final_logits.json", logits_payload)
    _write_json(
        output_dir / "final_subject_level_metrics" / f"{comparator_id}_subject_level_metrics.json",
        metric_summary,
    )
    _write_json(output_dir / "runtime_leakage_logs" / f"{comparator_id}_runtime_leakage_audit.json", leakage)
    _write_json(output_dir / "comparator_output_manifests" / f"{comparator_id}_output_manifest.json", manifest)
    return {"manifest": manifest, "metrics": metric_summary, "leakage": leakage, "fold_logs": fold_logs}


def _run_fold(
    *,
    comparator_id: str,
    fold: dict[str, Any],
    rows: list[dict[str, Any]],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    outer_subject = str(fold.get("outer_test_subject") or fold.get("test_subjects", [""])[0])
    train_subjects = set(str(value) for value in fold.get("train_subjects", []))
    test_subjects = set(str(value) for value in fold.get("test_subjects", [outer_subject]))
    train_rows = [row for row in rows if str(row["participant_id"]) in train_subjects]
    test_rows = [row for row in rows if str(row["participant_id"]) in test_subjects]
    if not train_rows or not test_rows:
        raise Phase1FinalComparatorRunnerError(f"Fold {fold.get('fold_id')} has empty train/test rows")
    if any(str(row["participant_id"]) in test_subjects for row in train_rows):
        raise Phase1FinalComparatorRunnerError(f"Fold {fold.get('fold_id')} leaks test subject into training rows")

    x_train_raw = [list(row["features"]) for row in train_rows]
    x_test_raw = [list(row["features"]) for row in test_rows]
    y_train = [float(row["label"]) for row in train_rows]
    y_test = [float(row["label"]) for row in test_rows]
    x_train, x_test, standardizer = _fit_transform_standardizer(x_train_raw, x_test_raw)
    weights = _subject_balanced_weights(train_rows) if comparator_id in {"A2b", "A2c_CORAL"} else [1.0] * len(train_rows)
    policy = "pooled_scalp_only_logistic_probe"
    teacher_used_at_inference = False
    privileged_used_at_inference = False
    alignment_fit_subjects = []
    teacher_fit_subjects = []
    privileged_fit_subjects = []
    gate_fit_subjects = []

    if comparator_id == "A2c_CORAL":
        beta = float(runner_config.get("a2c_feature_alignment", {}).get("beta", 0.1))
        x_train = _training_domain_center(x_train, train_rows, beta)
        policy = "training_subject_domain_centered_scalp_only_probe"
        alignment_fit_subjects = sorted(train_subjects)
    elif comparator_id == "A3_distillation":
        teacher_cfg = runner_config.get("a3_distillation", {})
        teacher = _fit_logistic_probe(x_train, y_train, weights, runner_config["logistic_probe"])
        teacher_probs = [_sigmoid(_dot(row, teacher["coef"]) + teacher["intercept"]) for row in x_train]
        y_train = _soft_targets(y_train, teacher_probs, teacher_cfg)
        policy = "training_only_scalp_proxy_distillation_student"
        teacher_fit_subjects = sorted(train_subjects)
    elif comparator_id == "A4_privileged":
        gate_weights = _fit_training_feature_gate(x_train, y_train, runner_config.get("a4_privileged", {}))
        x_train = _apply_feature_gate(x_train, gate_weights)
        x_test = _apply_feature_gate(x_test, gate_weights)
        proxy = _fit_logistic_probe(x_train, y_train, weights, runner_config["logistic_probe"])
        proxy_probs = [_sigmoid(_dot(row, proxy["coef"]) + proxy["intercept"]) for row in x_train]
        y_train = _soft_targets(y_train, proxy_probs, runner_config.get("a4_privileged", {}))
        policy = "training_only_internal_privileged_proxy_scalp_only_student"
        privileged_fit_subjects = sorted(train_subjects)
        gate_fit_subjects = sorted(train_subjects)
    elif comparator_id == "A2b":
        policy = "subject_balanced_pooled_scalp_only_logistic_probe"

    model = _fit_logistic_probe(x_train, y_train, weights, runner_config["logistic_probe"])
    prob = [_sigmoid(_dot(row, model["coef"]) + model["intercept"]) for row in x_test]
    pred = [1 if value >= 0.5 else 0 for value in prob]
    metrics = _classification_metrics([float(row["label"]) for row in test_rows], prob, pred)
    metrics.update(
        {
            "comparator_id": comparator_id,
            "fold_id": fold.get("fold_id"),
            "outer_test_subject": outer_subject,
            "n_train_rows": len(train_rows),
            "n_test_rows": len(test_rows),
            "claim_ready": False,
            "claim_evaluable": False,
            "scientific_limit": "Fold diagnostic only; not standalone Phase 1 evidence.",
        }
    )
    logits = [
        {
            "row_id": row["row_id"],
            "participant_id": row["participant_id"],
            "session_id": row["session_id"],
            "trial_id": row["trial_id"],
            "outer_test_subject": outer_subject,
            "y_true": int(row["label"]),
            "prob_load8": round(float(value), 8),
            "y_pred": int(guess),
        }
        for row, value, guess in zip(test_rows, prob, pred)
    ]
    fold_log = {
        "status": "phase1_final_comparator_fold_complete",
        "fold_id": fold.get("fold_id"),
        "comparator_id": comparator_id,
        "outer_test_subject": outer_subject,
        "train_subjects": sorted(train_subjects),
        "test_subjects": sorted(test_subjects),
        "no_outer_test_subject_in_any_fit": outer_subject not in train_subjects,
        "normalization_fit_subjects": sorted(train_subjects),
        "normalization_fit_training_subjects_only": True,
        "alignment_fit_subjects": alignment_fit_subjects,
        "teacher_fit_subjects": teacher_fit_subjects,
        "privileged_fit_subjects": privileged_fit_subjects,
        "gate_weight_fit_subjects": gate_fit_subjects,
        "outer_test_subject_used_for_alignment_fit": outer_subject in alignment_fit_subjects,
        "outer_test_subject_used_for_teacher_fit": outer_subject in teacher_fit_subjects,
        "outer_test_subject_used_for_privileged_fit": outer_subject in privileged_fit_subjects,
        "outer_test_subject_used_for_gate_or_weight_fit": outer_subject in gate_fit_subjects,
        "teacher_used_at_inference": teacher_used_at_inference,
        "privileged_used_at_inference": privileged_used_at_inference,
        "student_inference_uses_scalp_only": True,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "training_policy": policy,
        "standardizer": standardizer,
        "metrics": metrics,
        "logit_rows": len(logits),
        "claim_ready": False,
        "claim_evaluable": False,
    }
    return {"fold_log": fold_log, "metrics": metrics, "logits": logits}


def _fit_transform_standardizer(
    x_train: list[list[float]], x_test: list[list[float]]
) -> tuple[list[list[float]], list[list[float]], dict[str, Any]]:
    n_features = len(x_train[0])
    means = []
    stds = []
    for column in range(n_features):
        values = [row[column] for row in x_train]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        std = math.sqrt(variance)
        means.append(mean)
        stds.append(std if std > 1e-8 else 1.0)

    def transform(matrix: list[list[float]]) -> list[list[float]]:
        return [[(value - means[index]) / stds[index] for index, value in enumerate(row)] for row in matrix]

    return (
        transform(x_train),
        transform(x_test),
        {
            "fit_scope": "training_subjects_only",
            "n_features": n_features,
            "zero_variance_features": sum(1 for value in stds if value == 1.0),
        },
    )


def _subject_balanced_weights(train_rows: list[dict[str, Any]]) -> list[float]:
    counts: dict[str, int] = {}
    for row in train_rows:
        subject = str(row["participant_id"])
        counts[subject] = counts.get(subject, 0) + 1
    weights = [1.0 / counts[str(row["participant_id"])] for row in train_rows]
    mean_weight = sum(weights) / len(weights)
    return [weight / mean_weight for weight in weights]


def _training_domain_center(x_train: list[list[float]], train_rows: list[dict[str, Any]], beta: float) -> list[list[float]]:
    n_features = len(x_train[0])
    global_mean = [sum(row[index] for row in x_train) / len(x_train) for index in range(n_features)]
    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for row, source in zip(x_train, train_rows):
        subject = str(source["participant_id"])
        sums.setdefault(subject, [0.0] * n_features)
        counts[subject] = counts.get(subject, 0) + 1
        for index, value in enumerate(row):
            sums[subject][index] += value
    means = {subject: [value / counts[subject] for value in values] for subject, values in sums.items()}
    return [
        [value - beta * (means[str(source["participant_id"])][index] - global_mean[index]) for index, value in enumerate(row)]
        for row, source in zip(x_train, train_rows)
    ]


def _soft_targets(y_true: list[float], teacher_probs: list[float], config: dict[str, Any]) -> list[float]:
    alpha = float(config.get("distillation_alpha_hard_label", 0.5))
    clip = float(config.get("soft_label_clip", 0.02))
    temperature = max(float(config.get("temperature", 1.0)), 1e-6)
    softened = []
    for prob in teacher_probs:
        bounded = min(1.0 - clip, max(clip, float(prob)))
        logit = math.log(bounded / (1.0 - bounded))
        softened.append(_sigmoid(logit / temperature))
    return [min(1.0 - clip, max(clip, alpha * label + (1.0 - alpha) * prob)) for label, prob in zip(y_true, softened)]


def _fit_training_feature_gate(x_train: list[list[float]], y_train: list[float], config: dict[str, Any]) -> list[float]:
    floor = float(config.get("feature_weight_floor", 0.35))
    ceiling = float(config.get("feature_weight_ceiling", 1.0))
    n_features = len(x_train[0])
    scores = []
    for index in range(n_features):
        pos = [row[index] for row, label in zip(x_train, y_train) if label >= 0.5]
        neg = [row[index] for row, label in zip(x_train, y_train) if label < 0.5]
        pos_mean = sum(pos) / len(pos) if pos else 0.0
        neg_mean = sum(neg) / len(neg) if neg else 0.0
        scores.append(abs(pos_mean - neg_mean))
    max_score = max(scores) if scores else 0.0
    if max_score <= 1e-12:
        return [1.0] * n_features
    return [floor + (ceiling - floor) * (score / max_score) for score in scores]


def _apply_feature_gate(x: list[list[float]], weights: list[float]) -> list[list[float]]:
    return [[value * weights[index] for index, value in enumerate(row)] for row in x]


def _runtime_leakage_audit(comparator_id: str, fold_logs: list[dict[str, Any]]) -> dict[str, Any]:
    outer_used = any(
        not fold.get("no_outer_test_subject_in_any_fit")
        or fold.get("outer_test_subject_used_for_alignment_fit")
        or fold.get("outer_test_subject_used_for_teacher_fit")
        or fold.get("outer_test_subject_used_for_privileged_fit")
        or fold.get("outer_test_subject_used_for_gate_or_weight_fit")
        for fold in fold_logs
    )
    return {
        "status": "phase1_final_comparator_runtime_leakage_audit_passed" if not outer_used else "phase1_final_comparator_runtime_leakage_audit_blocked",
        "comparator_id": comparator_id,
        "claim_ready": False,
        "claim_evaluable": False,
        "n_folds": len(fold_logs),
        "outer_test_subject_used_for_any_fit": outer_used,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "normalization_fit_training_subjects_only": all(fold.get("normalization_fit_training_subjects_only") for fold in fold_logs),
        "folds": [
            {
                "fold_id": fold["fold_id"],
                "outer_test_subject": fold["outer_test_subject"],
                "no_outer_test_subject_in_any_fit": fold["no_outer_test_subject_in_any_fit"],
                "teacher_used_at_inference": fold["teacher_used_at_inference"],
                "privileged_used_at_inference": fold["privileged_used_at_inference"],
                "student_inference_uses_scalp_only": fold["student_inference_uses_scalp_only"],
            }
            for fold in fold_logs
        ],
        "scientific_limit": "Runtime leakage audit covers this runner's logs only; it is not efficacy evidence.",
    }


def _write_blocked_comparator(output_dir: Path, comparator_id: str, reason: str) -> dict[str, Any]:
    record = {
        "status": "phase1_final_comparator_blocked",
        "comparator_id": comparator_id,
        "claim_ready": False,
        "claim_evaluable": False,
        "smoke_artifacts_promoted": False,
        "logits_written": False,
        "metrics_written": False,
        "runtime_leakage_log_written": False,
        "blockers": [f"{comparator_id}_not_executable_from_final_feature_matrix"],
        "reason": reason,
        "scientific_limit": "Blocked comparators are not approximated and produce no model evidence.",
    }
    _write_json(output_dir / "blocked_comparators" / f"{comparator_id}_blocked.json", record)
    _write_json(output_dir / "comparator_output_manifests" / f"{comparator_id}_output_manifest.json", record)
    return record


def _build_completeness_table(
    *, required: list[str], completed: dict[str, dict[str, Any]], blocked: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    rows = []
    for comparator_id in required:
        rows.append(
            {
                "comparator_id": comparator_id,
                "output_manifest_present": comparator_id in completed or comparator_id in blocked,
                "logits_present": comparator_id in completed,
                "subject_metrics_present": comparator_id in completed,
                "runtime_leakage_log_present": comparator_id in completed,
                "claim_evaluable": False,
                "status": "completed_claim_closed" if comparator_id in completed else "blocked",
                "blockers": blocked.get(comparator_id, {}).get("blockers", []),
            }
        )
    all_outputs = all(row["logits_present"] and row["runtime_leakage_log_present"] for row in rows)
    return {
        "status": "phase1_final_comparator_completeness_partial" if not all_outputs else "phase1_final_comparator_completeness_recorded",
        "all_final_comparator_outputs_present": all_outputs,
        "claim_ready": False,
        "claim_evaluable": False,
        "rows": rows,
        "scientific_limit": "Completeness table records artifact presence only; it is not model evidence.",
    }


def _build_aggregate_leakage(
    *, completed: dict[str, dict[str, Any]], blocked: dict[str, dict[str, Any]], required: list[str]
) -> dict[str, Any]:
    completed_logs = {key: value["leakage"] for key, value in completed.items()}
    outer_used = any(log["outer_test_subject_used_for_any_fit"] for log in completed_logs.values())
    return {
        "status": "phase1_final_comparator_runtime_leakage_audit_partial_with_blockers" if blocked else "phase1_final_comparator_runtime_leakage_audit_recorded",
        "required_comparators": required,
        "completed_comparators": sorted(completed),
        "blocked_comparators": sorted(blocked),
        "runtime_logs_audited_for_completed_comparators": True,
        "runtime_logs_audited_for_all_required_comparators": not blocked,
        "outer_test_subject_used_for_any_fit": outer_used,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "claim_ready": False,
        "claim_evaluable": False,
        "comparator_logs": completed_logs,
        "blocked": blocked,
        "scientific_limit": "Aggregate audit is not full claim governance while required comparators remain blocked.",
    }


def _build_claim_state(
    *,
    input_validation: dict[str, Any],
    completed: dict[str, dict[str, Any]],
    blocked: dict[str, dict[str, Any]],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", []))
    blockers.extend(record["blockers"][0] for record in blocked.values())
    blockers.extend(runner_config.get("claim_blockers_after_run", []))
    if blocked:
        blockers.append("final_comparator_outputs_incomplete")
    return {
        "status": "phase1_final_comparator_runner_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "completed_comparators": sorted(completed),
        "blocked_comparators": sorted(blocked),
        "smoke_artifacts_promoted": False,
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "scientific_limit": "Claim state remains blocked until every final comparator and governance package passes.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    feature_matrix_run: Path,
    runner_readiness_run: Path,
    matrix: dict[str, Any],
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    matrix_path = matrix["matrix_path"]
    readiness_summary = runner_readiness_run / "phase1_final_comparator_runner_readiness_summary.json"
    return {
        "status": "phase1_final_comparator_runner_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "feature_matrix_run": str(feature_matrix_run),
        "final_feature_matrix": str(matrix_path),
        "final_feature_matrix_sha256": _sha256(matrix_path),
        "feature_matrix_summary": str(feature_matrix_run / "phase1_final_feature_matrix_summary.json"),
        "feature_matrix_summary_sha256": _sha256(feature_matrix_run / "phase1_final_feature_matrix_summary.json"),
        "runner_readiness_run": str(runner_readiness_run),
        "runner_readiness_summary": str(readiness_summary),
        "runner_readiness_summary_sha256": _sha256(readiness_summary),
        "upstream_source_links": matrix["source_links"],
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not model evidence.",
    }


def _build_summary(
    *,
    output_dir: Path,
    matrix: dict[str, Any],
    readiness: dict[str, Any],
    rows: list[dict[str, Any]],
    feature_names: list[str],
    fold_specs: list[dict[str, Any]],
    requested: list[str],
    completed: dict[str, dict[str, Any]],
    blocked: dict[str, dict[str, Any]],
    input_validation: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    any_blocker = bool(blocked or input_validation.get("blockers"))
    return {
        "status": "phase1_final_comparator_runner_partial_with_blockers" if any_blocker else "phase1_final_comparator_runner_complete_claim_closed",
        "output_dir": str(output_dir),
        "feature_matrix_run": str(matrix["run_dir"]),
        "runner_readiness_run": str(readiness["run_dir"]),
        "feature_matrix_path": str(matrix["matrix_path"]),
        "n_rows": len(rows),
        "n_features": len(feature_names),
        "n_folds": len(fold_specs),
        "requested_comparators": requested,
        "completed_comparators": sorted(completed),
        "blocked_comparators": sorted(blocked),
        "final_comparator_outputs_present": not blocked and not input_validation.get("blockers"),
        "all_comparator_output_manifests_present": True,
        "runtime_comparator_logs_audited_for_completed_comparators": True,
        "runtime_comparator_logs_audited_for_all_required_comparators": not blocked,
        "smoke_artifacts_promoted": False,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "This runner writes final feature-matrix comparator implementation outputs. It does not by itself "
            "prove decoder efficacy, privileged-transfer efficacy, or full Phase 1 performance."
        ),
    }


def _render_report(
    summary: dict[str, Any],
    completeness: dict[str, Any],
    leakage: dict[str, Any],
    claim_state: dict[str, Any],
) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Comparator Runner",
            "",
            f"Status: `{summary['status']}`",
            f"Feature matrix: `{summary['feature_matrix_path']}`",
            f"Rows/features: {summary['n_rows']} / {summary['n_features']}",
            f"Completed comparators: {', '.join(summary['completed_comparators']) or 'none'}",
            f"Blocked comparators: {', '.join(summary['blocked_comparators']) or 'none'}",
            "",
            "## Integrity Boundary",
            "",
            "- Claims remain closed.",
            "- Smoke artifacts are not promoted.",
            "- Logits do not contain feature values.",
            "- Comparators unsupported by `final_feature_matrix.csv` are blocked rather than approximated.",
            "",
            "## Runtime Leakage",
            "",
            f"Outer-test subject used for any completed-comparator fit: `{leakage['outer_test_subject_used_for_any_fit']}`",
            f"Runtime logs audited for all required comparators: `{leakage['runtime_logs_audited_for_all_required_comparators']}`",
            "",
            "## Completeness",
            "",
            f"All final comparator outputs present: `{completeness['all_final_comparator_outputs_present']}`",
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
