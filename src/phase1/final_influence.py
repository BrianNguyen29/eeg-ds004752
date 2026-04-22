"""Final Phase 1 influence package.

This runner consumes reconciled final comparator logits and writes a
claim-closed influence manifest. It computes subject-level and
leave-one-subject-out diagnostics from existing final logits only; it does not
retrain comparators, edit logits, fabricate influence checks, or open claims.
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
from .influence import REQUIRED_FINAL_INFLUENCE_ARTIFACTS
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalInfluenceError(RuntimeError):
    """Raised when final influence cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalInfluenceResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "influence": "configs/phase1/final_influence.json",
    "gate1": "configs/gate1/decision_simulation.json",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_influence(
    *,
    prereg_bundle: str | Path,
    comparator_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalInfluenceResult:
    """Write final influence artifacts while keeping claims closed."""

    prereg_bundle = Path(prereg_bundle)
    comparator_reconciliation_run = _resolve_run_dir(Path(comparator_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    influence_config = load_config(repo_root / config_paths["influence"])
    gate1_config = load_config(repo_root / config_paths["gate1"])
    gate2_config = load_config(repo_root / config_paths["gate2"])
    comparator = _read_comparator_reconciliation_run(comparator_reconciliation_run)
    input_validation = _validate_inputs(comparator=comparator, influence_config=influence_config)
    logits = _load_reconciled_logits(comparator["completeness"])
    influence_outputs = _compute_influence_outputs(
        logits=logits,
        influence_config=influence_config,
        gate1_config=gate1_config,
        gate2_config=gate2_config,
    )
    manifest = _build_manifest(
        influence_outputs=influence_outputs,
        input_validation=input_validation,
        influence_config=influence_config,
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
        "status": "phase1_final_influence_inputs_locked",
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
        influence_outputs=influence_outputs,
    )

    inputs_path = output_dir / "phase1_final_influence_inputs.json"
    summary_path = output_dir / "phase1_final_influence_summary.json"
    report_path = output_dir / "phase1_final_influence_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_influence_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_influence_input_validation.json", input_validation)
    _write_json(output_dir / "subject_level_fold_metrics.json", influence_outputs["subject_level_fold_metrics"])
    _write_json(output_dir / "leave_one_subject_out_deltas.json", influence_outputs["leave_one_subject_out_deltas"])
    _write_json(
        output_dir / "max_single_subject_contribution_share.json",
        influence_outputs["max_single_subject_contribution_share"],
    )
    _write_json(
        output_dir / "claim_state_leave_one_subject_out.json",
        influence_outputs["claim_state_leave_one_subject_out"],
    )
    _write_json(output_dir / "influence_veto_decision.json", influence_outputs["influence_veto_decision"])
    _write_json(output_dir / "final_influence_manifest.json", manifest)
    _write_json(output_dir / "phase1_final_influence_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, manifest, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalInfluenceResult(
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
            raise Phase1FinalInfluenceError(f"Comparator reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(*, comparator: dict[str, Any], influence_config: dict[str, Any]) -> dict[str, Any]:
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
    required_comparators = list(influence_config.get("required_comparators", []))
    observed_comparators = [str(row.get("comparator_id")) for row in completeness.get("rows", [])]
    missing_comparators = [item for item in required_comparators if item not in observed_comparators]
    if missing_comparators:
        blockers.append("influence_required_comparator_logits_missing")
    for row in completeness.get("rows", []):
        comparator_id = str(row.get("comparator_id"))
        if row.get("status") != "completed_claim_closed":
            blockers.append(f"{comparator_id}_not_completed_claim_closed")
        if row.get("logits_present") is not True:
            blockers.append(f"{comparator_id}_logits_missing")
        if row.get("runtime_leakage_passed") is not True:
            blockers.append(f"{comparator_id}_runtime_leakage_not_passed")
    return {
        "status": "phase1_final_influence_inputs_ready" if not blockers else "phase1_final_influence_inputs_blocked",
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "required_comparators": required_comparators,
        "observed_comparators": observed_comparators,
        "missing_comparators": missing_comparators,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks final influence prerequisites only; it is not influence evidence.",
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
            raise Phase1FinalInfluenceError(f"Final logits file not found for {comparator_id}: {path}")
        payload = _read_json(path)
        if payload.get("claim_ready") is not False:
            raise Phase1FinalInfluenceError(f"Final logits for {comparator_id} must keep claim_ready=false")
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not rows:
            raise Phase1FinalInfluenceError(f"Final logits for {comparator_id} have no rows")
        logits[comparator_id] = [_normalize_logit_row(item) for item in rows]
    return logits


def _compute_influence_outputs(
    *,
    logits: dict[str, list[dict[str, Any]]],
    influence_config: dict[str, Any],
    gate1_config: dict[str, Any],
    gate2_config: dict[str, Any],
) -> dict[str, Any]:
    comparisons = list(influence_config.get("influence_comparisons", []))
    gate1_ceiling = gate1_config.get("influence_ceiling")
    gate2_ceiling = gate2_config.get("frozen_threshold_defaults", {}).get("influence_ceiling")
    ceilings = [float(value) for value in [gate1_ceiling, gate2_ceiling] if value is not None]
    influence_ceiling = min(ceilings) if ceilings else None
    subjects = sorted({row["participant_id"] for rows in logits.values() for row in rows})

    subject_metric_rows = _subject_level_metrics(logits)
    loso_rows = []
    contribution_rows = []
    blockers = []
    max_share = 0.0
    max_record: dict[str, Any] | None = None

    for comparison in comparisons:
        comparison_id = str(comparison["comparison_id"])
        reference = str(comparison["reference"])
        target = str(comparison["target"])
        if reference not in logits or target not in logits:
            blockers.append(f"{comparison_id}_comparison_logits_missing")
            continue
        overall_ref = _balanced_accuracy(logits[reference])
        overall_target = _balanced_accuracy(logits[target])
        overall_delta = _delta(overall_target, overall_ref)
        if overall_delta is None:
            blockers.append(f"{comparison_id}_overall_metric_not_estimable")
        subject_shifts = []
        for subject in subjects:
            ref_without = [row for row in logits[reference] if row["participant_id"] != subject]
            target_without = [row for row in logits[target] if row["participant_id"] != subject]
            loso_ref = _balanced_accuracy(ref_without)
            loso_target = _balanced_accuracy(target_without)
            loso_delta = _delta(loso_target, loso_ref)
            if loso_delta is None:
                blockers.append(f"{comparison_id}_loso_metric_not_estimable")
            shift = None if overall_delta is None or loso_delta is None else overall_delta - loso_delta
            subject_shifts.append({"participant_id": subject, "shift": shift})
            loso_rows.append(
                {
                    "comparison_id": comparison_id,
                    "reference": reference,
                    "target": target,
                    "left_out_subject": subject,
                    "overall_delta_balanced_accuracy": _round(overall_delta),
                    "loso_delta_balanced_accuracy": _round(loso_delta),
                    "delta_shift_when_left_out": _round(shift),
                    "claim_ready": False,
                }
            )
        denominator = sum(abs(float(item["shift"])) for item in subject_shifts if item["shift"] is not None)
        for item in subject_shifts:
            share = 0.0 if denominator == 0.0 or item["shift"] is None else abs(float(item["shift"])) / denominator
            row = {
                "comparison_id": comparison_id,
                "participant_id": item["participant_id"],
                "abs_delta_shift": _round(abs(float(item["shift"])) if item["shift"] is not None else None),
                "single_subject_contribution_share": _round(share),
                "influence_ceiling": influence_ceiling,
                "exceeds_influence_ceiling": bool(influence_ceiling is not None and share > influence_ceiling),
            }
            contribution_rows.append(row)
            if share > max_share:
                max_share = share
                max_record = row
    if influence_ceiling is None:
        blockers.append("influence_ceiling_missing")
    if any(row["exceeds_influence_ceiling"] for row in contribution_rows):
        blockers.append("single_subject_influence_ceiling_exceeded")
    if not loso_rows:
        blockers.append("leave_one_subject_out_deltas_missing")
    influence_veto = bool(blockers)
    common = {
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": "Influence diagnostics from final logits only; not efficacy evidence.",
    }
    return {
        "subject_level_fold_metrics": {
            "status": "phase1_final_subject_level_fold_metrics_recorded",
            "primary_metric": "balanced_accuracy",
            "rows": subject_metric_rows,
            **common,
        },
        "leave_one_subject_out_deltas": {
            "status": "phase1_final_leave_one_subject_out_deltas_recorded",
            "comparisons": comparisons,
            "n_subjects": len(subjects),
            "rows": loso_rows,
            **common,
        },
        "max_single_subject_contribution_share": {
            "status": "phase1_final_max_single_subject_contribution_share_recorded",
            "influence_ceiling": influence_ceiling,
            "max_single_subject_contribution_share": _round(max_share),
            "max_record": max_record,
            "rows": contribution_rows,
            **common,
        },
        "claim_state_leave_one_subject_out": {
            "status": "phase1_final_loso_claim_state_recorded",
            "leave_one_subject_out_executed": bool(loso_rows),
            "single_subject_influence_ceiling_exceeded": "single_subject_influence_ceiling_exceeded" in blockers,
            "blockers": _unique(blockers),
            **common,
        },
        "influence_veto_decision": {
            "status": "phase1_final_influence_veto_recorded",
            "influence_vetoed": influence_veto,
            "veto_reasons": _unique(blockers),
            **common,
        },
    }


def _subject_level_metrics(logits: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for comparator_id, comparator_rows in sorted(logits.items()):
        by_subject: dict[str, list[dict[str, Any]]] = {}
        for row in comparator_rows:
            by_subject.setdefault(row["participant_id"], []).append(row)
        for subject, subject_rows in sorted(by_subject.items()):
            rows.append(
                {
                    "comparator_id": comparator_id,
                    "participant_id": subject,
                    "n_rows": len(subject_rows),
                    "balanced_accuracy": _round(_balanced_accuracy(subject_rows)),
                    "accuracy": _round(_accuracy(subject_rows)),
                    "n_pos": sum(1 for row in subject_rows if row["y_true"] == 1),
                    "n_neg": sum(1 for row in subject_rows if row["y_true"] == 0),
                    "claim_ready": False,
                }
            )
    return rows


def _build_manifest(
    *,
    influence_outputs: dict[str, Any],
    input_validation: dict[str, Any],
    influence_config: dict[str, Any],
) -> dict[str, Any]:
    required = list(influence_config.get("required_final_influence_artifacts", REQUIRED_FINAL_INFLUENCE_ARTIFACTS))
    artifact_key_map = {
        "subject_level_fold_metrics": "subject_level_fold_metrics",
        "leave_one_subject_out_deltas": "leave_one_subject_out_deltas",
        "max_single_subject_contribution_share": "max_single_subject_contribution_share",
        "claim_state_leave_one_subject_out": "claim_state_leave_one_subject_out",
        "influence_veto_decision": "influence_veto_decision",
    }
    provided = [item for item in required if artifact_key_map.get(item) in influence_outputs]
    missing = [item for item in required if item not in provided]
    loso_state = influence_outputs["claim_state_leave_one_subject_out"]
    veto = influence_outputs["influence_veto_decision"]
    blockers = list(input_validation.get("blockers", [])) + list(loso_state.get("blockers", []))
    if missing:
        blockers.append("required_final_influence_artifacts_missing")
    if loso_state.get("leave_one_subject_out_executed") is not True:
        blockers.append("leave_one_subject_out_claim_state_checks_missing")
    if veto.get("influence_vetoed") is True:
        blockers.append("final_influence_vetoed")
    influence_package_passed = not blockers
    return {
        "status": "phase1_final_influence_manifest_recorded"
        if influence_package_passed
        else "phase1_final_influence_blocked_manifest_recorded",
        "artifacts": provided,
        "required_artifacts": required,
        "missing_artifacts": missing,
        "artifact_files": {
            "subject_level_fold_metrics": "subject_level_fold_metrics.json",
            "leave_one_subject_out_deltas": "leave_one_subject_out_deltas.json",
            "max_single_subject_contribution_share": "max_single_subject_contribution_share.json",
            "claim_state_leave_one_subject_out": "claim_state_leave_one_subject_out.json",
            "influence_veto_decision": "influence_veto_decision.json",
        },
        "leave_one_subject_out_executed": loso_state.get("leave_one_subject_out_executed") is True,
        "influence_package_passed": influence_package_passed,
        "claim_ready": False,
        "claim_evaluable": influence_package_passed,
        "smoke_artifacts_promoted": False,
        "blockers": _unique(blockers),
        "scientific_limit": (
            "Final influence manifest records subject-level and leave-one-subject-out diagnostics "
            "computed from final logits. It does not open claims."
        ),
    }


def _build_claim_state(*, manifest: dict[str, Any], input_validation: dict[str, Any]) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", [])) + list(manifest.get("blockers", []))
    if manifest.get("influence_package_passed") is not True:
        blockers.append("final_influence_package_not_passed")
    return {
        "status": "phase1_final_influence_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "influence_package_passed": manifest.get("influence_package_passed"),
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
        "status": "phase1_final_influence_source_links_recorded",
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
        "scientific_limit": "Source links record provenance only; they are not influence evidence.",
    }


def _build_summary(
    *,
    output_dir: Path,
    comparator: dict[str, Any],
    manifest: dict[str, Any],
    input_validation: dict[str, Any],
    claim_state: dict[str, Any],
    influence_outputs: dict[str, Any],
) -> dict[str, Any]:
    passed = manifest.get("influence_package_passed") is True and not input_validation.get("blockers")
    max_share = influence_outputs["max_single_subject_contribution_share"]
    veto = influence_outputs["influence_veto_decision"]
    return {
        "status": "phase1_final_influence_complete_claim_closed" if passed else "phase1_final_influence_blocked",
        "output_dir": str(output_dir),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "influence_package_passed": passed,
        "leave_one_subject_out_executed": manifest.get("leave_one_subject_out_executed"),
        "influence_ceiling": max_share.get("influence_ceiling"),
        "max_single_subject_contribution_share": max_share.get("max_single_subject_contribution_share"),
        "influence_vetoed": veto.get("influence_vetoed"),
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final influence package records subject-level and leave-one-subject-out diagnostics "
            "computed from final logits. It does not prove Phase 1 efficacy."
        ),
    }


def _render_report(summary: dict[str, Any], manifest: dict[str, Any], claim_state: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Influence",
            "",
            f"Status: `{summary['status']}`",
            f"Influence package passed: `{summary['influence_package_passed']}`",
            f"Leave-one-subject-out executed: `{summary['leave_one_subject_out_executed']}`",
            f"Influence ceiling: `{summary['influence_ceiling']}`",
            f"Max single-subject contribution share: `{summary['max_single_subject_contribution_share']}`",
            f"Influence vetoed: `{summary['influence_vetoed']}`",
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
        raise Phase1FinalInfluenceError(f"Invalid probability in final logits row {row.get('row_id')}: {prob}")
    label = int(row["y_true"])
    if label not in (0, 1):
        raise Phase1FinalInfluenceError(f"Invalid label in final logits row {row.get('row_id')}: {label}")
    return {
        "row_id": str(row.get("row_id")),
        "participant_id": str(row.get("participant_id") or row.get("outer_test_subject")),
        "outer_test_subject": str(row.get("outer_test_subject") or row.get("participant_id")),
        "y_true": label,
        "prob_load8": prob,
        "y_pred": int(row.get("y_pred", 1 if prob >= 0.5 else 0)),
    }


def _balanced_accuracy(rows: list[dict[str, Any]]) -> float | None:
    positives = [row for row in rows if row["y_true"] == 1]
    negatives = [row for row in rows if row["y_true"] == 0]
    if not positives or not negatives:
        return None
    tpr = sum(1 for row in positives if row["y_pred"] == 1) / len(positives)
    tnr = sum(1 for row in negatives if row["y_pred"] == 0) / len(negatives)
    return (tpr + tnr) / 2.0


def _accuracy(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row["y_pred"] == row["y_true"]) / len(rows)


def _delta(target: float | None, reference: float | None) -> float | None:
    if target is None or reference is None:
        return None
    return target - reference


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
