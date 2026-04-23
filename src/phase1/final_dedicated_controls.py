"""Dedicated final Phase 1 negative controls.

This runner executes the final controls that cannot be inferred from existing
final logits alone. It consumes reviewed final feature-matrix rows and the
locked LOSO split contract, fits only on training subjects, and writes a
claim-closed dedicated-control manifest. Failed controls remain failed; this
module never changes thresholds or opens claims.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .final_comparator_runner import (
    Phase1FinalComparatorRunnerError,
    _classification_metrics,
    _dot,
    _fit_logistic_probe,
    _fit_transform_standardizer,
    _load_matrix_rows,
    _read_feature_matrix_run,
    _read_split_manifest_from_matrix_sources,
    _selected_folds,
    _sigmoid,
    _soft_targets,
    _validate_feature_matrix_boundary,
    _validate_split_manifest,
)
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalDedicatedControlsError(RuntimeError):
    """Raised when dedicated final controls cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalDedicatedControlsResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "dedicated_controls": "configs/phase1/final_dedicated_controls.json",
    "comparator_runner": "configs/phase1/final_comparator_runner.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}

RAW_BA_RATIO_CONTRACT = {
    "formula_id": "raw_ba_ratio",
    "definition": "control_balanced_accuracy / baseline_balanced_accuracy",
    "applies_to": [
        "nuisance_shared_control.relative_to_baseline",
        "spatial_control.relative_to_baseline",
    ],
    "default_baseline_comparator": "A2",
    "status": "prospective_contract_clarification",
    "current_artifacts_reclassified": False,
    "thresholds_changed": False,
    "claims_opened": False,
}


def run_phase1_final_dedicated_controls(
    *,
    prereg_bundle: str | Path,
    feature_matrix_run: str | Path,
    comparator_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
    max_outer_folds: int | None = None,
) -> Phase1FinalDedicatedControlsResult:
    """Run dedicated final controls while keeping all claims closed."""

    prereg_bundle = Path(prereg_bundle)
    feature_matrix_run = _resolve_run_dir(Path(feature_matrix_run))
    comparator_reconciliation_run = _resolve_run_dir(Path(comparator_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    dedicated_config = load_config(repo_root / config_paths["dedicated_controls"])
    runner_config = load_config(repo_root / config_paths["comparator_runner"])
    gate2_config = load_config(repo_root / config_paths["gate2"])
    matrix = _read_feature_matrix_run(feature_matrix_run)
    comparator = _read_comparator_reconciliation_run(comparator_reconciliation_run)

    try:
        _validate_feature_matrix_boundary(matrix)
        split_manifest = _read_split_manifest_from_matrix_sources(matrix)
        _validate_split_manifest(split_manifest)
    except Phase1FinalComparatorRunnerError as exc:
        raise Phase1FinalDedicatedControlsError(str(exc)) from exc

    rows, feature_names = _load_matrix_rows(matrix["matrix_path"], matrix["schema"])
    folds = _selected_folds(split_manifest, max_outer_folds)
    input_validation = _validate_inputs(
        matrix=matrix,
        comparator=comparator,
        dedicated_config=dedicated_config,
        rows=rows,
        feature_names=feature_names,
        folds=folds,
    )
    baseline_metrics = _baseline_metrics(comparator["completeness"])
    controls = _run_controls(
        rows=rows,
        feature_names=feature_names,
        folds=folds,
        runner_config=runner_config,
        dedicated_config=dedicated_config,
        gate2_config=gate2_config,
        baseline_metrics=baseline_metrics,
    )
    leakage = _build_runtime_leakage(controls)
    manifest = _build_manifest(
        controls=controls,
        leakage=leakage,
        input_validation=input_validation,
        dedicated_config=dedicated_config,
    )
    claim_state = _build_claim_state(manifest=manifest, input_validation=input_validation)
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        feature_matrix_run=feature_matrix_run,
        comparator_reconciliation_run=comparator_reconciliation_run,
        matrix=matrix,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_dedicated_controls_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "feature_matrix_run": str(feature_matrix_run),
        "comparator_reconciliation_run": str(comparator_reconciliation_run),
        "config_paths": config_paths,
        "max_outer_folds": max_outer_folds,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        manifest=manifest,
        input_validation=input_validation,
        controls=controls,
    )

    inputs_path = output_dir / "phase1_final_dedicated_controls_inputs.json"
    summary_path = output_dir / "phase1_final_dedicated_controls_summary.json"
    report_path = output_dir / "phase1_final_dedicated_controls_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_dedicated_controls_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_dedicated_controls_input_validation.json", input_validation)
    _write_json(output_dir / "nuisance_shared_control.json", controls["nuisance_shared_control"])
    _write_json(output_dir / "spatial_control.json", controls["spatial_control"])
    _write_json(output_dir / "shuffled_teacher_control.json", controls["shuffled_teacher"])
    _write_json(output_dir / "time_shifted_teacher_control.json", controls["time_shifted_teacher"])
    _write_json(output_dir / "phase1_final_dedicated_controls_runtime_leakage_audit.json", leakage)
    _write_json(output_dir / "final_dedicated_control_manifest.json", manifest)
    _write_json(output_dir / "phase1_final_dedicated_controls_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, manifest, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalDedicatedControlsResult(
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


def _read_comparator_reconciliation_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_comparator_reconciliation_summary.json",
        "completeness": "phase1_final_comparator_reconciled_completeness_table.json",
        "runtime_leakage": "phase1_final_comparator_reconciled_runtime_leakage_audit.json",
        "claim_state": "phase1_final_comparator_reconciled_claim_state.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalDedicatedControlsError(f"Comparator reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    matrix: dict[str, Any],
    comparator: dict[str, Any],
    dedicated_config: dict[str, Any],
    rows: list[dict[str, Any]],
    feature_names: list[str],
    folds: list[dict[str, Any]],
) -> dict[str, Any]:
    summary = comparator["summary"]
    runtime = comparator["runtime_leakage"]
    blockers = []
    if summary.get("status") != "phase1_final_comparator_reconciliation_complete_claim_closed":
        blockers.append("comparator_reconciliation_not_complete_claim_closed")
    if summary.get("all_final_comparator_outputs_present") is not True:
        blockers.append("final_comparator_outputs_not_complete")
    if runtime.get("runtime_logs_audited_for_all_required_comparators") is not True:
        blockers.append("runtime_logs_not_audited_for_all_required_comparators")
    if comparator["claim_state"].get("claim_ready") is not False:
        blockers.append("comparator_reconciliation_claim_state_not_closed")
    required = list(dedicated_config.get("required_dedicated_controls", []))
    if set(required) != {"nuisance_shared_control", "spatial_control", "shuffled_teacher", "time_shifted_teacher"}:
        blockers.append("dedicated_control_contract_mismatch")
    relative_contract = _relative_metric_contract(dedicated_config)
    if relative_contract.get("formula_id") != RAW_BA_RATIO_CONTRACT["formula_id"]:
        blockers.append("relative_metric_formula_contract_mismatch")
    if relative_contract.get("definition") != RAW_BA_RATIO_CONTRACT["definition"]:
        blockers.append("relative_metric_formula_definition_mismatch")
    if relative_contract.get("thresholds_changed") is not False:
        blockers.append("relative_metric_contract_thresholds_changed")
    if relative_contract.get("current_artifacts_reclassified") is not False:
        blockers.append("relative_metric_contract_reclassifies_current_artifacts")
    if relative_contract.get("claims_opened") is not False:
        blockers.append("relative_metric_contract_opens_claims")
    if not rows:
        blockers.append("final_feature_matrix_has_no_rows")
    if not feature_names:
        blockers.append("final_feature_matrix_has_no_features")
    if not folds:
        blockers.append("final_split_has_no_folds")
    return {
        "status": "phase1_final_dedicated_controls_inputs_ready" if not blockers else "phase1_final_dedicated_controls_inputs_blocked",
        "feature_matrix_run": str(matrix["run_dir"]),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "required_dedicated_controls": required,
        "relative_metric_contract": relative_contract,
        "n_rows": len(rows),
        "n_features": len(feature_names),
        "n_folds": len(folds),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks dedicated-control prerequisites only; it is not control evidence.",
    }


def _baseline_metrics(completeness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    baselines: dict[str, dict[str, Any]] = {}
    for row in completeness.get("rows", []):
        comparator_id = str(row.get("comparator_id"))
        path_value = row.get("files", {}).get("logits")
        if not path_value or not Path(path_value).exists():
            continue
        payload = _read_json(Path(path_value))
        logits = payload.get("rows", [])
        if logits:
            baselines[comparator_id] = _metrics_from_logits(logits)
    return baselines


def _run_controls(
    *,
    rows: list[dict[str, Any]],
    feature_names: list[str],
    folds: list[dict[str, Any]],
    runner_config: dict[str, Any],
    dedicated_config: dict[str, Any],
    gate2_config: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    thresholds = {
        "nuisance_relative_ceiling": gate2_config.get("frozen_threshold_defaults", {}).get("nuisance_relative_ceiling"),
        "nuisance_absolute_ceiling": gate2_config.get("frozen_threshold_defaults", {}).get("nuisance_absolute_ceiling"),
        "spatial_relative_ceiling": gate2_config.get("frozen_threshold_defaults", {}).get("spatial_relative_ceiling"),
        "shuffled_teacher_max_gain_over_a3": _threshold_from_gate2(
            gate2_config,
            "shuffled_teacher_max_gain_over_a3",
        ),
        "time_shifted_teacher_max_gain_over_a3": _threshold_from_gate2(
            gate2_config,
            "time_shifted_teacher_max_gain_over_a3",
        ),
    }
    relative_contract = _relative_metric_contract(dedicated_config)
    if relative_contract.get("formula_id") != RAW_BA_RATIO_CONTRACT["formula_id"]:
        raise Phase1FinalDedicatedControlsError(
            "Dedicated controls support only raw_ba_ratio until a reviewed formula-contract patch lands."
        )
    return {
        "nuisance_shared_control": _nuisance_control(
            rows=rows,
            folds=folds,
            config=dedicated_config.get("nuisance_control", {}),
            runner_config=runner_config,
            thresholds=thresholds,
            relative_contract=relative_contract,
            baseline_metrics=baseline_metrics,
        ),
        "spatial_control": _spatial_control(
            rows=rows,
            feature_names=feature_names,
            folds=folds,
            config=dedicated_config.get("spatial_control", {}),
            runner_config=runner_config,
            thresholds=thresholds,
            relative_contract=relative_contract,
            baseline_metrics=baseline_metrics,
        ),
        "shuffled_teacher": _teacher_control(
            control_id="shuffled_teacher",
            rows=rows,
            folds=folds,
            runner_config=runner_config,
            threshold=thresholds["shuffled_teacher_max_gain_over_a3"],
            baseline_metrics=baseline_metrics,
            policy="reverse",
        ),
        "time_shifted_teacher": _teacher_control(
            control_id="time_shifted_teacher",
            rows=rows,
            folds=folds,
            runner_config=runner_config,
            threshold=thresholds["time_shifted_teacher_max_gain_over_a3"],
            baseline_metrics=baseline_metrics,
            policy="rotate",
        ),
    }


def _nuisance_control(
    *,
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    config: dict[str, Any],
    runner_config: dict[str, Any],
    thresholds: dict[str, Any],
    relative_contract: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    metadata_columns = [str(value) for value in config.get("metadata_columns", ["session_id", "trial_id"])]
    fold_logs = []
    all_logits = []
    for fold in folds:
        result = _run_metadata_fold(
            control_id="nuisance_shared_control",
            fold=fold,
            rows=rows,
            metadata_columns=metadata_columns,
            runner_config=runner_config,
        )
        fold_logs.append(result["fold_log"])
        all_logits.extend(result["logits"])
    metrics = _metrics_from_logits(all_logits)
    baseline_ba = _baseline_ba(baseline_metrics, "A2")
    relative = _relative(metrics.get("balanced_accuracy"), baseline_ba)
    absolute_gain = abs(_delta(metrics.get("balanced_accuracy"), 0.5))
    rel_ceiling = _float_or_none(thresholds["nuisance_relative_ceiling"])
    abs_ceiling = _float_or_none(thresholds["nuisance_absolute_ceiling"])
    passed = (
        rel_ceiling is not None
        and abs_ceiling is not None
        and relative <= rel_ceiling
        and absolute_gain <= abs_ceiling
        and _leakage_passed(fold_logs)
    )
    return _control_payload(
        control_id="nuisance_shared_control",
        status="phase1_final_nuisance_shared_control_recorded",
        passed=passed,
        metrics=metrics,
        fold_logs=fold_logs,
        logits=all_logits,
        threshold={
            "nuisance_relative_ceiling": rel_ceiling,
            "nuisance_absolute_ceiling": abs_ceiling,
            "baseline_comparator": "A2",
            "relative_metric_formula_id": relative_contract["formula_id"],
            "relative_metric_formula_definition": relative_contract["definition"],
            "relative_metric_formula_source": "configs/phase1/final_dedicated_controls.json:relative_metric_contract",
            "relative_to_baseline": _round(relative),
            "absolute_gain_over_chance": _round(absolute_gain),
        },
        scientific_limit="Nuisance control uses available metadata covariates only and is not decoder evidence.",
    )


def _spatial_control(
    *,
    rows: list[dict[str, Any]],
    feature_names: list[str],
    folds: list[dict[str, Any]],
    config: dict[str, Any],
    runner_config: dict[str, Any],
    thresholds: dict[str, Any],
    relative_contract: dict[str, Any],
    baseline_metrics: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    permuted_rows = _spatially_permuted_rows(rows, feature_names)
    fold_logs = []
    all_logits = []
    for fold in folds:
        result = _run_feature_fold(
            control_id="spatial_control",
            fold=fold,
            rows=permuted_rows,
            runner_config=runner_config,
            training_policy=str(config.get("permutation", "reverse_channel_order_within_band")),
        )
        fold_logs.append(result["fold_log"])
        all_logits.extend(result["logits"])
    metrics = _metrics_from_logits(all_logits)
    baseline_ba = _baseline_ba(baseline_metrics, "A2")
    relative = _relative(metrics.get("balanced_accuracy"), baseline_ba)
    ceiling = _float_or_none(thresholds["spatial_relative_ceiling"])
    passed = ceiling is not None and relative <= ceiling and _leakage_passed(fold_logs)
    return _control_payload(
        control_id="spatial_control",
        status="phase1_final_spatial_control_recorded",
        passed=passed,
        metrics=metrics,
        fold_logs=fold_logs,
        logits=all_logits,
        threshold={
            "spatial_relative_ceiling": ceiling,
            "baseline_comparator": "A2",
            "relative_metric_formula_id": relative_contract["formula_id"],
            "relative_metric_formula_definition": relative_contract["definition"],
            "relative_metric_formula_source": "configs/phase1/final_dedicated_controls.json:relative_metric_contract",
            "relative_to_baseline": _round(relative),
        },
        scientific_limit="Spatial control uses deterministic within-band channel permutation; it is not decoder evidence.",
    )


def _teacher_control(
    *,
    control_id: str,
    rows: list[dict[str, Any]],
    folds: list[dict[str, Any]],
    runner_config: dict[str, Any],
    threshold: Any,
    baseline_metrics: dict[str, dict[str, Any]],
    policy: str,
) -> dict[str, Any]:
    fold_logs = []
    all_logits = []
    for fold in folds:
        result = _run_teacher_control_fold(
            control_id=control_id,
            fold=fold,
            rows=rows,
            runner_config=runner_config,
            policy=policy,
        )
        fold_logs.append(result["fold_log"])
        all_logits.extend(result["logits"])
    metrics = _metrics_from_logits(all_logits)
    baseline_ba = _baseline_ba(baseline_metrics, "A3_distillation")
    gain = max(0.0, _delta(metrics.get("balanced_accuracy"), baseline_ba))
    ceiling = _float_or_none(threshold)
    passed = ceiling is not None and gain <= ceiling and _leakage_passed(fold_logs)
    return _control_payload(
        control_id=control_id,
        status=f"phase1_final_{control_id}_control_recorded",
        passed=passed,
        metrics=metrics,
        fold_logs=fold_logs,
        logits=all_logits,
        threshold={
            "max_gain_over_a3": ceiling,
            "baseline_comparator": "A3_distillation",
            "gain_over_a3": _round(gain),
            "teacher_policy": policy,
        },
        scientific_limit="Teacher control corrupts training-only scalp-proxy teacher outputs; no teacher output is used at test time.",
    )


def _run_feature_fold(
    *,
    control_id: str,
    fold: dict[str, Any],
    rows: list[dict[str, Any]],
    runner_config: dict[str, Any],
    training_policy: str,
) -> dict[str, Any]:
    train_rows, test_rows, subjects = _fold_rows(fold, rows)
    x_train, x_test, standardizer = _fit_transform_standardizer(
        [list(row["features"]) for row in train_rows],
        [list(row["features"]) for row in test_rows],
    )
    y_train = [float(row["label"]) for row in train_rows]
    weights = [1.0] * len(train_rows)
    model = _fit_logistic_probe(x_train, y_train, weights, runner_config["logistic_probe"])
    prob = [_sigmoid(_dot(row, model["coef"]) + model["intercept"]) for row in x_test]
    return _fold_result(
        control_id=control_id,
        fold=fold,
        train_rows=train_rows,
        test_rows=test_rows,
        prob=prob,
        training_policy=training_policy,
        standardizer=standardizer,
        teacher_fit_subjects=[],
        privileged_fit_subjects=[],
        gate_fit_subjects=[],
        train_subjects=subjects["train_subjects"],
        test_subjects=subjects["test_subjects"],
    )


def _run_metadata_fold(
    *,
    control_id: str,
    fold: dict[str, Any],
    rows: list[dict[str, Any]],
    metadata_columns: list[str],
    runner_config: dict[str, Any],
) -> dict[str, Any]:
    train_rows, test_rows, subjects = _fold_rows(fold, rows)
    categories = {
        column: sorted({str(row.get(column, "")) for row in train_rows})
        for column in metadata_columns
    }
    def encode(row: dict[str, Any]) -> list[float]:
        values = []
        for column in metadata_columns:
            current = str(row.get(column, ""))
            values.extend([1.0 if current == item else 0.0 for item in categories[column]])
        return values or [0.0]

    x_train = [encode(row) for row in train_rows]
    x_test = [encode(row) for row in test_rows]
    y_train = [float(row["label"]) for row in train_rows]
    model = _fit_logistic_probe(x_train, y_train, [1.0] * len(train_rows), runner_config["logistic_probe"])
    prob = [_sigmoid(_dot(row, model["coef"]) + model["intercept"]) for row in x_test]
    return _fold_result(
        control_id=control_id,
        fold=fold,
        train_rows=train_rows,
        test_rows=test_rows,
        prob=prob,
        training_policy="training_subjects_only_metadata_nuisance_probe",
        standardizer={"fit_scope": "training_subjects_only", "metadata_columns": metadata_columns},
        teacher_fit_subjects=[],
        privileged_fit_subjects=[],
        gate_fit_subjects=[],
        train_subjects=subjects["train_subjects"],
        test_subjects=subjects["test_subjects"],
    )


def _run_teacher_control_fold(
    *,
    control_id: str,
    fold: dict[str, Any],
    rows: list[dict[str, Any]],
    runner_config: dict[str, Any],
    policy: str,
) -> dict[str, Any]:
    train_rows, test_rows, subjects = _fold_rows(fold, rows)
    x_train, x_test, standardizer = _fit_transform_standardizer(
        [list(row["features"]) for row in train_rows],
        [list(row["features"]) for row in test_rows],
    )
    y_train_hard = [float(row["label"]) for row in train_rows]
    teacher = _fit_logistic_probe(x_train, y_train_hard, [1.0] * len(train_rows), runner_config["logistic_probe"])
    teacher_probs = [_sigmoid(_dot(row, teacher["coef"]) + teacher["intercept"]) for row in x_train]
    corrupted = list(reversed(teacher_probs)) if policy == "reverse" else teacher_probs[1:] + teacher_probs[:1]
    y_train = _soft_targets(y_train_hard, corrupted, runner_config.get("a3_distillation", {}))
    student = _fit_logistic_probe(x_train, y_train, [1.0] * len(train_rows), runner_config["logistic_probe"])
    prob = [_sigmoid(_dot(row, student["coef"]) + student["intercept"]) for row in x_test]
    return _fold_result(
        control_id=control_id,
        fold=fold,
        train_rows=train_rows,
        test_rows=test_rows,
        prob=prob,
        training_policy=f"training_only_corrupted_teacher_{policy}_scalp_only_student",
        standardizer=standardizer,
        teacher_fit_subjects=subjects["train_subjects"],
        privileged_fit_subjects=[],
        gate_fit_subjects=[],
        train_subjects=subjects["train_subjects"],
        test_subjects=subjects["test_subjects"],
    )


def _fold_rows(fold: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    outer_subject = str(fold.get("outer_test_subject") or fold.get("test_subjects", [""])[0])
    train_subjects = set(str(value) for value in fold.get("train_subjects", []))
    test_subjects = set(str(value) for value in fold.get("test_subjects", [outer_subject]))
    train_rows = [row for row in rows if str(row["participant_id"]) in train_subjects]
    test_rows = [row for row in rows if str(row["participant_id"]) in test_subjects]
    if not train_rows or not test_rows:
        raise Phase1FinalDedicatedControlsError(f"Fold {fold.get('fold_id')} has empty train/test rows")
    if any(str(row["participant_id"]) in test_subjects for row in train_rows):
        raise Phase1FinalDedicatedControlsError(f"Fold {fold.get('fold_id')} leaks test subject into training rows")
    return train_rows, test_rows, {
        "outer_subject": outer_subject,
        "train_subjects": sorted(train_subjects),
        "test_subjects": sorted(test_subjects),
    }


def _fold_result(
    *,
    control_id: str,
    fold: dict[str, Any],
    train_rows: list[dict[str, Any]],
    test_rows: list[dict[str, Any]],
    prob: list[float],
    training_policy: str,
    standardizer: dict[str, Any],
    teacher_fit_subjects: list[str],
    privileged_fit_subjects: list[str],
    gate_fit_subjects: list[str],
    train_subjects: list[str],
    test_subjects: list[str],
) -> dict[str, Any]:
    outer_subject = str(fold.get("outer_test_subject") or test_subjects[0])
    pred = [1 if value >= 0.5 else 0 for value in prob]
    metrics = _classification_metrics([float(row["label"]) for row in test_rows], prob, pred)
    metrics.update({
        "control_id": control_id,
        "fold_id": fold.get("fold_id"),
        "outer_test_subject": outer_subject,
        "n_train_rows": len(train_rows),
        "n_test_rows": len(test_rows),
        "claim_ready": False,
        "claim_evaluable": False,
    })
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
        "status": "phase1_final_dedicated_control_fold_complete",
        "fold_id": fold.get("fold_id"),
        "control_id": control_id,
        "outer_test_subject": outer_subject,
        "train_subjects": train_subjects,
        "test_subjects": test_subjects,
        "no_outer_test_subject_in_any_fit": outer_subject not in train_subjects,
        "normalization_fit_subjects": train_subjects,
        "normalization_fit_training_subjects_only": True,
        "teacher_fit_subjects": teacher_fit_subjects,
        "privileged_fit_subjects": privileged_fit_subjects,
        "gate_weight_fit_subjects": gate_fit_subjects,
        "outer_test_subject_used_for_teacher_fit": outer_subject in teacher_fit_subjects,
        "outer_test_subject_used_for_privileged_fit": outer_subject in privileged_fit_subjects,
        "outer_test_subject_used_for_gate_or_weight_fit": outer_subject in gate_fit_subjects,
        "teacher_used_at_inference": False,
        "privileged_used_at_inference": False,
        "student_inference_uses_scalp_only": True,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "training_policy": training_policy,
        "standardizer": standardizer,
        "metrics": metrics,
        "claim_ready": False,
        "claim_evaluable": False,
    }
    return {"fold_log": fold_log, "metrics": metrics, "logits": logits}


def _spatially_permuted_rows(rows: list[dict[str, Any]], feature_names: list[str]) -> list[dict[str, Any]]:
    channels = sorted({name.split(":", 1)[0] for name in feature_names if ":" in name})
    reverse = {channel: replacement for channel, replacement in zip(channels, reversed(channels))}
    index_by_name = {name: index for index, name in enumerate(feature_names)}
    result = []
    for row in rows:
        new_row = dict(row)
        features = list(row["features"])
        permuted = []
        for name in feature_names:
            if ":" not in name:
                permuted.append(features[index_by_name[name]])
                continue
            channel, band = name.split(":", 1)
            source = f"{reverse.get(channel, channel)}:{band}"
            permuted.append(features[index_by_name.get(source, index_by_name[name])])
        new_row["features"] = permuted
        result.append(new_row)
    return result


def _control_payload(
    *,
    control_id: str,
    status: str,
    passed: bool,
    metrics: dict[str, Any],
    fold_logs: list[dict[str, Any]],
    logits: list[dict[str, Any]],
    threshold: dict[str, Any],
    scientific_limit: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "control_id": control_id,
        "passed": passed,
        "claim_ready": False,
        "claim_evaluable": False,
        "metrics": metrics,
        "threshold": threshold,
        "n_folds": len(fold_logs),
        "n_logit_rows": len(logits),
        "fold_logs": fold_logs,
        "logits": logits,
        "runtime_leakage_passed": _leakage_passed(fold_logs),
        "scientific_limit": scientific_limit,
    }


def _build_runtime_leakage(controls: dict[str, Any]) -> dict[str, Any]:
    fold_logs = [fold for control in controls.values() for fold in control.get("fold_logs", [])]
    outer_used = any(
        not fold.get("no_outer_test_subject_in_any_fit")
        or fold.get("outer_test_subject_used_for_teacher_fit")
        or fold.get("outer_test_subject_used_for_privileged_fit")
        or fold.get("outer_test_subject_used_for_gate_or_weight_fit")
        for fold in fold_logs
    )
    return {
        "status": "phase1_final_dedicated_controls_runtime_leakage_audit_passed" if not outer_used else "phase1_final_dedicated_controls_runtime_leakage_audit_blocked",
        "claim_ready": False,
        "claim_evaluable": False,
        "outer_test_subject_used_for_any_fit": outer_used,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "n_fold_logs": len(fold_logs),
        "scientific_limit": "Runtime leakage audit covers dedicated-control folds only; it is not efficacy evidence.",
    }


def _build_manifest(
    *,
    controls: dict[str, Any],
    leakage: dict[str, Any],
    input_validation: dict[str, Any],
    dedicated_config: dict[str, Any],
) -> dict[str, Any]:
    required = list(dedicated_config.get("required_dedicated_controls", []))
    results = [key for key in required if key in controls]
    missing = [key for key in required if key not in results]
    failed = [key for key, payload in controls.items() if payload.get("passed") is not True]
    blockers = list(input_validation.get("blockers", []))
    if missing:
        blockers.append("dedicated_final_control_results_missing")
    if failed:
        blockers.append("dedicated_final_control_thresholds_not_passed")
    if leakage.get("outer_test_subject_used_for_any_fit") is True:
        blockers.append("dedicated_final_control_runtime_leakage_detected")
    control_suite_passed = not blockers
    return {
        "status": "phase1_final_dedicated_controls_manifest_recorded"
        if control_suite_passed
        else "phase1_final_dedicated_controls_blocked_manifest_recorded",
        "results": results,
        "required_results": required,
        "missing_results": missing,
        "failed_results": failed,
        "relative_metric_contract": _relative_metric_contract(dedicated_config),
        "dedicated_control_suite_passed": control_suite_passed,
        "claim_ready": False,
        "claim_evaluable": control_suite_passed,
        "smoke_artifacts_promoted": False,
        "real_ieeg_teacher_used": False,
        "teacher_used_at_inference": False,
        "test_time_privileged_or_teacher_outputs_allowed": False,
        "blockers": _unique(blockers),
        "scientific_limit": "Dedicated controls may pass or fail; either result leaves claims closed pending full governance.",
    }


def _relative_metric_contract(dedicated_config: dict[str, Any]) -> dict[str, Any]:
    contract = dict(dedicated_config.get("relative_metric_contract") or {})
    if not contract:
        return {}
    return {
        "formula_id": contract.get("formula_id"),
        "definition": contract.get("definition"),
        "applies_to": list(contract.get("applies_to", [])),
        "default_baseline_comparator": contract.get("default_baseline_comparator"),
        "status": contract.get("status"),
        "current_artifacts_reclassified": contract.get("current_artifacts_reclassified"),
        "thresholds_changed": contract.get("thresholds_changed"),
        "claims_opened": contract.get("claims_opened"),
    }


def _build_claim_state(*, manifest: dict[str, Any], input_validation: dict[str, Any]) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", [])) + list(manifest.get("blockers", []))
    if manifest.get("dedicated_control_suite_passed") is not True:
        blockers.append("final_dedicated_control_suite_not_passed")
    return {
        "status": "phase1_final_dedicated_controls_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "dedicated_control_suite_passed": manifest.get("dedicated_control_suite_passed"),
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A2d efficacy",
            "A3/A4 efficacy",
            "A4 superiority",
            "privileged-transfer efficacy",
            "full Phase 1 neural comparator performance",
        ],
    }


def _build_summary(
    *,
    output_dir: Path,
    manifest: dict[str, Any],
    input_validation: dict[str, Any],
    controls: dict[str, Any],
) -> dict[str, Any]:
    passed = manifest.get("dedicated_control_suite_passed") is True and not input_validation.get("blockers")
    return {
        "status": "phase1_final_dedicated_controls_complete_claim_closed" if passed else "phase1_final_dedicated_controls_blocked",
        "output_dir": str(output_dir),
        "computed_dedicated_control_results": list(controls.keys()),
        "failed_dedicated_control_results": manifest.get("failed_results", []),
        "dedicated_control_suite_passed": passed,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": manifest.get("blockers", []),
        "scientific_limit": "Dedicated controls are negative-control diagnostics only and do not prove Phase 1 efficacy.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    feature_matrix_run: Path,
    comparator_reconciliation_run: Path,
    matrix: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_dedicated_controls_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "feature_matrix_run": str(feature_matrix_run),
        "final_feature_matrix": str(matrix["matrix_path"]),
        "final_feature_matrix_sha256": _sha256(matrix["matrix_path"]),
        "comparator_reconciliation_run": str(comparator_reconciliation_run),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not control evidence.",
    }


def _render_report(summary: dict[str, Any], manifest: dict[str, Any], claim_state: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Dedicated Controls",
            "",
            f"Status: `{summary['status']}`",
            f"Dedicated control suite passed: `{summary['dedicated_control_suite_passed']}`",
            f"Computed dedicated controls: `{', '.join(summary['computed_dedicated_control_results']) or 'none'}`",
            f"Failed dedicated controls: `{', '.join(summary['failed_dedicated_control_results']) or 'none'}`",
            "",
            "## Claim State",
            "",
            f"Claim ready: `{claim_state['claim_ready']}`",
            "Blockers:",
            *[f"- `{blocker}`" for blocker in claim_state["blockers"]],
            "",
            "NOT OK TO CLAIM: decoder efficacy, A2d efficacy, A3/A4 efficacy, A4 superiority, privileged-transfer efficacy, or full Phase 1 neural comparator performance.",
            "",
        ]
    )


def _metrics_from_logits(rows: list[dict[str, Any]]) -> dict[str, Any]:
    y_true = [float(row["y_true"]) for row in rows]
    prob = [float(row["prob_load8"]) for row in rows]
    pred = [int(row.get("y_pred", 1 if float(row["prob_load8"]) >= 0.5 else 0)) for row in rows]
    return _classification_metrics(y_true, prob, pred)


def _baseline_ba(baselines: dict[str, dict[str, Any]], comparator_id: str) -> float | None:
    value = baselines.get(comparator_id, {}).get("balanced_accuracy")
    return float(value) if value is not None else None


def _relative(value: Any, baseline: Any) -> float:
    if value is None or baseline is None or abs(float(baseline)) < 1e-12:
        return float("inf")
    return float(value) / float(baseline)


def _delta(value: Any, baseline: Any) -> float:
    if value is None or baseline is None:
        return 0.0
    return float(value) - float(baseline)


def _float_or_none(value: Any) -> float | None:
    return float(value) if value is not None else None


def _threshold_from_gate2(gate2_config: dict[str, Any], key: str) -> Any:
    negative_controls = gate2_config.get("negative_controls", {})
    if key in negative_controls:
        return negative_controls.get(key)
    return gate2_config.get("control_suite", {}).get(key)


def _round(value: float) -> float:
    return round(float(value), 6)


def _leakage_passed(fold_logs: list[dict[str, Any]]) -> bool:
    return all(
        fold.get("no_outer_test_subject_in_any_fit")
        and not fold.get("teacher_used_at_inference")
        and not fold.get("privileged_used_at_inference")
        and not fold.get("test_time_privileged_or_teacher_outputs_allowed")
        for fold in fold_logs
    )


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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
