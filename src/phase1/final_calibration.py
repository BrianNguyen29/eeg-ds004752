"""Final Phase 1 calibration package.

This runner consumes reconciled final comparator logits and writes a
claim-closed calibration manifest. It computes calibration diagnostics from
existing final logits only; it does not recalibrate predictions, retrain
comparators, fabricate diagrams, or open claims.
"""

from __future__ import annotations

import hashlib
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed
from .calibration import REQUIRED_FINAL_CALIBRATION_ARTIFACTS
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalCalibrationError(RuntimeError):
    """Raised when final calibration cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalCalibrationResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "calibration": "configs/phase1/final_calibration.json",
    "metrics": "configs/eval/metrics.yaml",
    "inference": "configs/eval/inference_defaults.yaml",
    "gate1": "configs/gate1/decision_simulation.json",
}


def run_phase1_final_calibration(
    *,
    prereg_bundle: str | Path,
    comparator_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalCalibrationResult:
    """Write final calibration artifacts while keeping claims closed."""

    prereg_bundle = Path(prereg_bundle)
    comparator_reconciliation_run = _resolve_run_dir(Path(comparator_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    calibration_config = load_config(repo_root / config_paths["calibration"])
    metrics_config = load_config(repo_root / config_paths["metrics"])
    inference_config = load_config(repo_root / config_paths["inference"])
    gate1_config = load_config(repo_root / config_paths["gate1"])
    comparator = _read_comparator_reconciliation_run(comparator_reconciliation_run)
    input_validation = _validate_inputs(
        comparator=comparator,
        calibration_config=calibration_config,
        metrics_config=metrics_config,
        inference_config=inference_config,
    )
    logits = _load_reconciled_logits(comparator["completeness"])
    calibration_outputs = _compute_calibration_outputs(
        logits=logits,
        calibration_config=calibration_config,
        gate1_config=gate1_config,
    )
    manifest = _build_manifest(
        calibration_outputs=calibration_outputs,
        input_validation=input_validation,
        calibration_config=calibration_config,
    )
    claim_state = _build_claim_state(manifest=manifest, input_validation=input_validation)
    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        comparator=comparator,
        repo_root=repo_root,
        config_paths=config_paths,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)
    inputs = {
        "status": "phase1_final_calibration_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "comparator_reconciliation_run": str(comparator_reconciliation_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        comparator=comparator,
        manifest=manifest,
        input_validation=input_validation,
        claim_state=claim_state,
        calibration_outputs=calibration_outputs,
    )

    inputs_path = output_dir / "phase1_final_calibration_inputs.json"
    summary_path = output_dir / "phase1_final_calibration_summary.json"
    report_path = output_dir / "phase1_final_calibration_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_calibration_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_calibration_input_validation.json", input_validation)
    _write_json(output_dir / "final_comparator_logits_index.json", calibration_outputs["logits_index"])
    _write_json(output_dir / "pooled_ece_10_bins.json", calibration_outputs["pooled_ece_10_bins"])
    _write_json(output_dir / "subject_level_ece.json", calibration_outputs["subject_level_ece"])
    _write_json(output_dir / "brier_score.json", calibration_outputs["brier_score"])
    _write_json(output_dir / "negative_log_likelihood.json", calibration_outputs["negative_log_likelihood"])
    _write_json(output_dir / "reliability_table.json", calibration_outputs["reliability_table"])
    _write_json(output_dir / "reliability_diagram.json", calibration_outputs["reliability_diagram"])
    _write_json(output_dir / "risk_coverage_curve.json", calibration_outputs["risk_coverage_curve"])
    _write_json(output_dir / "calibration_delta_vs_baseline.json", calibration_outputs["calibration_delta_vs_baseline"])
    _write_json(output_dir / "final_calibration_manifest.json", manifest)
    _write_json(output_dir / "phase1_final_calibration_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, manifest, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalCalibrationResult(
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
        "source_links": "phase1_final_comparator_reconciliation_source_links.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalCalibrationError(f"Comparator reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    comparator: dict[str, Any],
    calibration_config: dict[str, Any],
    metrics_config: dict[str, Any],
    inference_config: dict[str, Any],
) -> dict[str, Any]:
    summary = comparator["summary"]
    completeness = comparator["completeness"]
    runtime_leakage = comparator["runtime_leakage"]
    blockers = []
    if summary.get("status") != "phase1_final_comparator_reconciliation_complete_claim_closed":
        blockers.append("comparator_reconciliation_not_complete_claim_closed")
    if summary.get("all_final_comparator_outputs_present") is not True:
        blockers.append("final_comparator_outputs_not_complete")
    if runtime_leakage.get("runtime_logs_audited_for_all_required_comparators") is not True:
        blockers.append("runtime_logs_not_audited_for_all_required_comparators")
    if summary.get("claim_ready") is not False or comparator["claim_state"].get("claim_ready") is not False:
        blockers.append("comparator_reconciliation_claim_not_closed")
    if summary.get("smoke_artifacts_promoted") is not False:
        blockers.append("comparator_reconciliation_promoted_smoke_artifacts")
    required_comparators = list(calibration_config.get("required_comparators", []))
    observed_comparators = [str(row.get("comparator_id")) for row in completeness.get("rows", [])]
    missing_comparators = [item for item in required_comparators if item not in observed_comparators]
    if missing_comparators:
        blockers.append("calibration_required_comparator_logits_missing")
    if str(metrics_config.get("metrics_status") or "") != "executable":
        blockers.append("metrics_config_not_executable")
    if str(inference_config.get("inference_status") or "") != "executable":
        blockers.append("inference_config_not_executable")
    return {
        "status": "phase1_final_calibration_inputs_ready" if not blockers else "phase1_final_calibration_inputs_blocked",
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "required_comparators": required_comparators,
        "observed_comparators": observed_comparators,
        "missing_comparators": missing_comparators,
        "metrics_config_status": metrics_config.get("metrics_status"),
        "inference_config_status": inference_config.get("inference_status"),
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks final calibration prerequisites only; it is not calibration evidence.",
    }


def _load_reconciled_logits(completeness: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    logits: dict[str, list[dict[str, Any]]] = {}
    for row in completeness.get("rows", []):
        comparator_id = str(row.get("comparator_id"))
        path_value = row.get("files", {}).get("logits")
        if not path_value:
            continue
        path = Path(path_value)
        if not path.exists():
            raise Phase1FinalCalibrationError(f"Final logits file not found for {comparator_id}: {path}")
        payload = _read_json(path)
        if payload.get("claim_ready") is not False:
            raise Phase1FinalCalibrationError(f"Final logits for {comparator_id} must keep claim_ready=false")
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not rows:
            raise Phase1FinalCalibrationError(f"Final logits for {comparator_id} have no rows")
        logits[comparator_id] = rows
    return logits


def _compute_calibration_outputs(
    *,
    logits: dict[str, list[dict[str, Any]]],
    calibration_config: dict[str, Any],
    gate1_config: dict[str, Any],
) -> dict[str, Any]:
    n_bins = int(calibration_config.get("ece_bins", 10))
    baseline = str(calibration_config.get("baseline_comparator", "A2"))
    coverage_thresholds = [float(value) for value in calibration_config.get("risk_coverage_thresholds", [])]
    threshold = gate1_config.get("max_allowed_delta_ece")
    max_allowed_delta_ece = float(threshold) if threshold is not None else None
    comparator_summary = {}
    reliability_rows = []
    subject_rows = []
    risk_rows = []
    for comparator_id, rows in sorted(logits.items()):
        normalized = [_normalize_logit_row(row) for row in rows]
        labels = [row["y_true"] for row in normalized]
        probs = [row["prob_load8"] for row in normalized]
        comparator_summary[comparator_id] = {
            "comparator_id": comparator_id,
            "n_rows": len(normalized),
            "pooled_ece_10_bins": _round(_ece(labels, probs, n_bins)),
            "brier_score": _round(_brier(labels, probs)),
            "negative_log_likelihood": _round(_nll(labels, probs)),
            "claim_ready": False,
            "claim_evaluable": False,
        }
        reliability_rows.extend(_reliability_rows(comparator_id, labels, probs, n_bins))
        subject_rows.extend(_subject_level_rows(comparator_id, normalized, n_bins))
        risk_rows.extend(_risk_coverage_rows(comparator_id, normalized, coverage_thresholds))
    baseline_ece = comparator_summary.get(baseline, {}).get("pooled_ece_10_bins")
    delta_rows = []
    max_abs_delta = 0.0
    for comparator_id, summary in sorted(comparator_summary.items()):
        delta = None if baseline_ece is None else float(summary["pooled_ece_10_bins"]) - float(baseline_ece)
        if delta is not None:
            max_abs_delta = max(max_abs_delta, abs(delta))
        delta_rows.append(
            {
                "comparator_id": comparator_id,
                "baseline_comparator": baseline,
                "pooled_ece_10_bins": summary["pooled_ece_10_bins"],
                "baseline_pooled_ece_10_bins": baseline_ece,
                "delta_ece_vs_baseline": _round(delta),
            }
        )
    passed = bool(comparator_summary) and max_allowed_delta_ece is not None and max_abs_delta <= max_allowed_delta_ece
    common = {
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": "Calibration diagnostics from final logits only; not efficacy evidence.",
    }
    return {
        "logits_index": {
            "status": "phase1_final_calibration_logits_index_recorded",
            "comparators": sorted(logits),
            "n_rows_by_comparator": {key: len(value) for key, value in sorted(logits.items())},
            **common,
        },
        "pooled_ece_10_bins": {
            "status": "phase1_final_pooled_ece_recorded",
            "n_bins": n_bins,
            "comparators": comparator_summary,
            **common,
        },
        "subject_level_ece": {
            "status": "phase1_final_subject_level_ece_recorded",
            "n_bins": n_bins,
            "rows": subject_rows,
            **common,
        },
        "brier_score": {
            "status": "phase1_final_brier_score_recorded",
            "comparators": {
                key: {"brier_score": value["brier_score"], "n_rows": value["n_rows"]}
                for key, value in comparator_summary.items()
            },
            **common,
        },
        "negative_log_likelihood": {
            "status": "phase1_final_negative_log_likelihood_recorded",
            "comparators": {
                key: {"negative_log_likelihood": value["negative_log_likelihood"], "n_rows": value["n_rows"]}
                for key, value in comparator_summary.items()
            },
            **common,
        },
        "reliability_table": {
            "status": "phase1_final_reliability_table_recorded",
            "n_bins": n_bins,
            "rows": reliability_rows,
            **common,
        },
        "reliability_diagram": {
            "status": "phase1_final_reliability_diagram_data_recorded",
            "format": "json_points_for_downstream_rendering",
            "source": "reliability_table.json",
            "rows": reliability_rows,
            **common,
        },
        "risk_coverage_curve": {
            "status": "phase1_final_risk_coverage_curve_recorded",
            "thresholds": coverage_thresholds,
            "rows": risk_rows,
            **common,
        },
        "calibration_delta_vs_baseline": {
            "status": "phase1_final_calibration_delta_vs_baseline_recorded",
            "baseline_comparator": baseline,
            "max_allowed_delta_ece": max_allowed_delta_ece,
            "max_abs_delta_ece_vs_baseline": _round(max_abs_delta),
            "calibration_delta_passed": passed,
            "rows": delta_rows,
            **common,
        },
    }


def _build_manifest(
    *,
    calibration_outputs: dict[str, Any],
    input_validation: dict[str, Any],
    calibration_config: dict[str, Any],
) -> dict[str, Any]:
    required = list(calibration_config.get("required_final_calibration_artifacts", REQUIRED_FINAL_CALIBRATION_ARTIFACTS))
    artifact_key_map = {
        "final_comparator_logits": "logits_index",
        "pooled_ece_10_bins": "pooled_ece_10_bins",
        "subject_level_ece": "subject_level_ece",
        "brier_score": "brier_score",
        "negative_log_likelihood": "negative_log_likelihood",
        "reliability_table": "reliability_table",
        "reliability_diagram": "reliability_diagram",
        "risk_coverage_curve": "risk_coverage_curve",
        "calibration_delta_vs_baseline": "calibration_delta_vs_baseline",
    }
    provided = [item for item in required if artifact_key_map.get(item) in calibration_outputs]
    missing = [item for item in required if item not in provided]
    blockers = list(input_validation.get("blockers", []))
    if missing:
        blockers.append("required_final_calibration_artifacts_missing")
    delta = calibration_outputs["calibration_delta_vs_baseline"]
    if delta.get("calibration_delta_passed") is not True:
        blockers.append("calibration_delta_threshold_not_passed")
    calibration_package_passed = not blockers
    return {
        "status": "phase1_final_calibration_manifest_recorded"
        if calibration_package_passed
        else "phase1_final_calibration_blocked_manifest_recorded",
        "artifacts": provided,
        "required_artifacts": required,
        "missing_artifacts": missing,
        "artifact_files": {
            "final_comparator_logits": "final_comparator_logits_index.json",
            "pooled_ece_10_bins": "pooled_ece_10_bins.json",
            "subject_level_ece": "subject_level_ece.json",
            "brier_score": "brier_score.json",
            "negative_log_likelihood": "negative_log_likelihood.json",
            "reliability_table": "reliability_table.json",
            "reliability_diagram": "reliability_diagram.json",
            "risk_coverage_curve": "risk_coverage_curve.json",
            "calibration_delta_vs_baseline": "calibration_delta_vs_baseline.json",
        },
        "calibration_package_passed": calibration_package_passed,
        "claim_ready": False,
        "claim_evaluable": calibration_package_passed,
        "smoke_artifacts_promoted": False,
        "blockers": _unique(blockers),
        "scientific_limit": (
            "Final calibration manifest records diagnostics computed from final logits. "
            "It does not open claims."
        ),
    }


def _build_claim_state(*, manifest: dict[str, Any], input_validation: dict[str, Any]) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", [])) + list(manifest.get("blockers", []))
    if manifest.get("calibration_package_passed") is not True:
        blockers.append("final_calibration_package_not_passed")
    return {
        "status": "phase1_final_calibration_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "calibration_package_passed": manifest.get("calibration_package_passed"),
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


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    comparator: dict[str, Any],
    repo_root: Path,
    config_paths: dict[str, str | Path],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_calibration_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "comparator_reconciliation_summary": str(comparator["run_dir"] / "phase1_final_comparator_reconciliation_summary.json"),
        "comparator_reconciliation_summary_sha256": _sha256(
            comparator["run_dir"] / "phase1_final_comparator_reconciliation_summary.json"
        ),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links record provenance only; they are not calibration evidence.",
    }


def _build_summary(
    *,
    output_dir: Path,
    comparator: dict[str, Any],
    manifest: dict[str, Any],
    input_validation: dict[str, Any],
    claim_state: dict[str, Any],
    calibration_outputs: dict[str, Any],
) -> dict[str, Any]:
    passed = manifest.get("calibration_package_passed") is True and not input_validation.get("blockers")
    delta = calibration_outputs["calibration_delta_vs_baseline"]
    return {
        "status": "phase1_final_calibration_complete_claim_closed" if passed else "phase1_final_calibration_blocked",
        "output_dir": str(output_dir),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "comparators": calibration_outputs["logits_index"].get("comparators", []),
        "calibration_package_passed": passed,
        "max_allowed_delta_ece": delta.get("max_allowed_delta_ece"),
        "max_abs_delta_ece_vs_baseline": delta.get("max_abs_delta_ece_vs_baseline"),
        "calibration_delta_passed": delta.get("calibration_delta_passed"),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final calibration package records calibration diagnostics computed from final logits. "
            "It does not prove Phase 1 efficacy."
        ),
    }


def _render_report(summary: dict[str, Any], manifest: dict[str, Any], claim_state: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Calibration",
            "",
            f"Status: `{summary['status']}`",
            f"Calibration package passed: `{summary['calibration_package_passed']}`",
            f"Comparators: `{', '.join(summary['comparators'])}`",
            f"Max allowed delta ECE: `{summary['max_allowed_delta_ece']}`",
            f"Max absolute delta ECE vs baseline: `{summary['max_abs_delta_ece_vs_baseline']}`",
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


def _normalize_logit_row(row: dict[str, Any]) -> dict[str, Any]:
    prob = float(row["prob_load8"])
    if not math.isfinite(prob) or prob < 0.0 or prob > 1.0:
        raise Phase1FinalCalibrationError(f"Invalid probability in final logits row {row.get('row_id')}: {prob}")
    label = int(row["y_true"])
    if label not in (0, 1):
        raise Phase1FinalCalibrationError(f"Invalid label in final logits row {row.get('row_id')}: {label}")
    return {
        "row_id": str(row.get("row_id")),
        "participant_id": str(row.get("participant_id")),
        "session_id": str(row.get("session_id")),
        "trial_id": str(row.get("trial_id")),
        "outer_test_subject": str(row.get("outer_test_subject")),
        "y_true": label,
        "prob_load8": prob,
        "y_pred": int(row.get("y_pred", 1 if prob >= 0.5 else 0)),
    }


def _reliability_rows(comparator_id: str, labels: list[int], probs: list[float], n_bins: int) -> list[dict[str, Any]]:
    rows = []
    total = len(labels)
    for bin_index in range(n_bins):
        lo = bin_index / n_bins
        hi = (bin_index + 1) / n_bins
        indices = [
            index
            for index, value in enumerate(probs)
            if value >= lo and (value < hi if hi < 1.0 else value <= hi)
        ]
        if indices:
            mean_prob = sum(probs[index] for index in indices) / len(indices)
            event_rate = sum(labels[index] for index in indices) / len(indices)
        else:
            mean_prob = None
            event_rate = None
        rows.append(
            {
                "comparator_id": comparator_id,
                "bin_index": bin_index,
                "probability_lower": _round(lo),
                "probability_upper": _round(hi),
                "n_rows": len(indices),
                "fraction_rows": _round(len(indices) / total if total else 0.0),
                "mean_predicted_probability": _round(mean_prob),
                "observed_event_rate": _round(event_rate),
                "absolute_calibration_gap": _round(
                    abs(float(mean_prob) - float(event_rate)) if mean_prob is not None and event_rate is not None else None
                ),
            }
        )
    return rows


def _subject_level_rows(comparator_id: str, rows: list[dict[str, Any]], n_bins: int) -> list[dict[str, Any]]:
    by_subject: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_subject.setdefault(row["participant_id"], []).append(row)
    result = []
    for subject, subject_rows in sorted(by_subject.items()):
        labels = [row["y_true"] for row in subject_rows]
        probs = [row["prob_load8"] for row in subject_rows]
        result.append(
            {
                "comparator_id": comparator_id,
                "participant_id": subject,
                "n_rows": len(subject_rows),
                "ece_10_bins": _round(_ece(labels, probs, n_bins)),
                "brier_score": _round(_brier(labels, probs)),
                "negative_log_likelihood": _round(_nll(labels, probs)),
                "claim_ready": False,
            }
        )
    return result


def _risk_coverage_rows(
    comparator_id: str, rows: list[dict[str, Any]], thresholds: list[float]
) -> list[dict[str, Any]]:
    result = []
    for threshold in thresholds:
        selected = [row for row in rows if max(row["prob_load8"], 1.0 - row["prob_load8"]) >= threshold]
        if selected:
            errors = [
                1
                for row in selected
                if int(row.get("y_pred", 1 if row["prob_load8"] >= 0.5 else 0)) != int(row["y_true"])
            ]
            risk = sum(errors) / len(selected)
        else:
            risk = None
        result.append(
            {
                "comparator_id": comparator_id,
                "confidence_threshold": _round(threshold),
                "coverage": _round(len(selected) / len(rows) if rows else 0.0),
                "risk": _round(risk),
                "n_rows": len(selected),
            }
        )
    return result


def _ece(labels: list[int], probs: list[float], n_bins: int) -> float:
    total = len(labels)
    if total == 0:
        return float("nan")
    ece = 0.0
    for bin_index in range(n_bins):
        lo = bin_index / n_bins
        hi = (bin_index + 1) / n_bins
        indices = [
            index
            for index, value in enumerate(probs)
            if value >= lo and (value < hi if hi < 1.0 else value <= hi)
        ]
        if not indices:
            continue
        conf = sum(probs[index] for index in indices) / len(indices)
        acc = sum(labels[index] for index in indices) / len(indices)
        ece += len(indices) / total * abs(conf - acc)
    return ece


def _brier(labels: list[int], probs: list[float]) -> float:
    return sum((prob - label) ** 2 for prob, label in zip(probs, labels)) / len(labels)


def _nll(labels: list[int], probs: list[float]) -> float:
    eps = 1e-12
    clipped = [min(max(prob, eps), 1.0 - eps) for prob in probs]
    return -sum(label * math.log(prob) + (1 - label) * math.log(1.0 - prob) for label, prob in zip(labels, clipped)) / len(labels)


def _round(value: float | None) -> float | None:
    if value is None or not math.isfinite(float(value)):
        return None
    return round(float(value), 6)


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
