"""Final Phase 1 control-suite package.

This runner consumes the reconciled final comparator outputs and writes a
claim-closed control manifest. It computes only logit-level controls that are
valid from existing final logits. Controls requiring dedicated reruns remain
explicit blockers until real artifacts are provided.
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
from .controls import REQUIRED_FINAL_CONTROL_RESULTS
from .model_smoke import _classification_metrics
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalControlsError(RuntimeError):
    """Raised when final controls cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalControlsResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "controls": "configs/phase1/final_controls.json",
    "control_suite": "configs/controls/control_suite_spec.yaml",
    "gate2": "configs/gate2/synthetic_validation.json",
}


def run_phase1_final_controls(
    *,
    prereg_bundle: str | Path,
    comparator_reconciliation_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
    dedicated_control_manifest: str | Path | None = None,
) -> Phase1FinalControlsResult:
    """Write final control-suite artifacts while keeping claims closed."""

    prereg_bundle = Path(prereg_bundle)
    comparator_reconciliation_run = _resolve_run_dir(Path(comparator_reconciliation_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    controls_config = load_config(repo_root / config_paths["controls"])
    control_suite_config = load_config(repo_root / config_paths["control_suite"])
    gate2_config = load_config(repo_root / config_paths["gate2"])
    comparator = _read_comparator_reconciliation_run(comparator_reconciliation_run)
    input_validation = _validate_inputs(
        comparator=comparator,
        controls_config=controls_config,
        control_suite_config=control_suite_config,
    )
    logits = _load_reconciled_logits(comparator["completeness"])
    logit_controls = _compute_logit_level_controls(
        logits=logits,
        controls_config=controls_config,
        gate2_config=gate2_config,
    )
    dedicated_controls = _load_dedicated_control_manifest(dedicated_control_manifest)
    rerun_requirements = _build_rerun_requirements(controls_config, dedicated_controls=dedicated_controls)
    manifest = _build_manifest(
        logit_controls=logit_controls,
        dedicated_controls=dedicated_controls,
        rerun_requirements=rerun_requirements,
        input_validation=input_validation,
        controls_config=controls_config,
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
        "status": "phase1_final_controls_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "comparator_reconciliation_run": str(comparator_reconciliation_run),
        "dedicated_control_manifest": str(dedicated_control_manifest) if dedicated_control_manifest else None,
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }
    summary = _build_summary(
        output_dir=output_dir,
        comparator=comparator,
        manifest=manifest,
        input_validation=input_validation,
        claim_state=claim_state,
    )

    inputs_path = output_dir / "phase1_final_controls_inputs.json"
    summary_path = output_dir / "phase1_final_controls_summary.json"
    report_path = output_dir / "phase1_final_controls_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_controls_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_controls_input_validation.json", input_validation)
    _write_json(output_dir / "phase1_final_logit_level_control_results.json", logit_controls)
    _write_json(output_dir / "phase1_final_dedicated_control_requirements.json", rerun_requirements)
    _write_json(output_dir / "phase1_final_dedicated_control_manifest_review.json", dedicated_controls)
    _write_json(output_dir / "final_control_manifest.json", manifest)
    _write_json(output_dir / "phase1_final_controls_claim_state.json", claim_state)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, manifest, claim_state), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalControlsResult(
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
            raise Phase1FinalControlsError(f"Comparator reconciliation file not found: {path}")
        payload[key] = _read_json(path)
    payload["run_dir"] = run_dir
    return payload


def _validate_inputs(
    *,
    comparator: dict[str, Any],
    controls_config: dict[str, Any],
    control_suite_config: dict[str, Any],
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
    if len(completeness.get("rows", [])) != 6:
        blockers.append("comparator_reconciliation_missing_required_comparators")

    required = set(controls_config.get("required_final_control_results", REQUIRED_FINAL_CONTROL_RESULTS))
    configured = set((control_suite_config.get("controls") or {}).keys())
    missing_config = sorted(required - configured)
    if str(control_suite_config.get("control_suite_status") or "") != "executable":
        blockers.append("control_suite_config_not_executable")
    if missing_config:
        blockers.append("required_control_configs_missing")

    return {
        "status": "phase1_final_controls_inputs_ready" if not blockers else "phase1_final_controls_inputs_blocked",
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "completed_comparators": summary.get("completed_comparators", []),
        "blocked_comparators": summary.get("blocked_comparators", []),
        "required_final_control_results": sorted(required),
        "configured_controls": sorted(configured),
        "missing_configured_controls": missing_config,
        "blockers": _unique(blockers),
        "scientific_limit": "Input validation checks control prerequisites only; it is not control evidence.",
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
            raise Phase1FinalControlsError(f"Final logits file not found for {comparator_id}: {path}")
        payload = _read_json(path)
        if payload.get("claim_ready") is not False:
            raise Phase1FinalControlsError(f"Final logits for {comparator_id} must keep claim_ready=false")
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not rows:
            raise Phase1FinalControlsError(f"Final logits for {comparator_id} have no rows")
        logits[comparator_id] = rows
    return logits


def _compute_logit_level_controls(
    *,
    logits: dict[str, list[dict[str, Any]]],
    controls_config: dict[str, Any],
    gate2_config: dict[str, Any],
) -> dict[str, Any]:
    threshold = gate2_config.get("pass_criteria", {}).get("negative_control_max_abs_gain")
    threshold = float(threshold) if threshold is not None else None
    comparator_metrics = {
        comparator_id: _metrics_from_rows(rows)
        for comparator_id, rows in sorted(logits.items())
    }
    controls = []
    if "A2" in comparator_metrics:
        controls.append(
            {
                "control_id": "scalp_only_baseline",
                "status": "computed_from_final_a2_logits",
                "comparator_id": "A2",
                "metrics": comparator_metrics["A2"],
                "claim_ready": False,
                "claim_evaluable": False,
                "scientific_limit": "Baseline diagnostic only; it is not a negative-control pass by itself.",
            }
        )
    controls.append(_grouped_permutation_control(logits, threshold))
    controls.append(_shuffled_labels_control(logits, threshold))
    controls.append(_transfer_consistency_control(logits))
    return {
        "status": "phase1_final_logit_level_controls_recorded",
        "claim_ready": False,
        "claim_evaluable": False,
        "computed_control_ids": [row["control_id"] for row in controls],
        "controls": controls,
        "comparator_metrics_from_logits": comparator_metrics,
        "threshold_sources": controls_config.get("threshold_sources", {}),
        "negative_control_max_abs_gain": threshold,
        "scientific_limit": (
            "These controls are limited to diagnostics valid from final logits. Dedicated nuisance/spatial/"
            "teacher controls still require real rerun artifacts."
        ),
    }


def _metrics_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    y_true = [float(row["y_true"]) for row in rows]
    prob = [float(row["prob_load8"]) for row in rows]
    pred = [int(row.get("y_pred", 1 if float(row["prob_load8"]) >= 0.5 else 0)) for row in rows]
    return _classification_metrics(y_true, prob, pred)


def _grouped_permutation_control(logits: dict[str, list[dict[str, Any]]], threshold: float | None) -> dict[str, Any]:
    rows = []
    max_abs_gain = 0.0
    for comparator_id, comp_rows in sorted(logits.items()):
        permuted = _rotate_labels_by_group(comp_rows, "outer_test_subject")
        metrics = _classification_metrics(
            [float(value) for value in permuted],
            [float(row["prob_load8"]) for row in comp_rows],
            [int(row.get("y_pred", 1 if float(row["prob_load8"]) >= 0.5 else 0)) for row in comp_rows],
        )
        original = _metrics_from_rows(comp_rows)
        gain = _delta(metrics.get("balanced_accuracy"), original.get("balanced_accuracy"))
        max_abs_gain = max(max_abs_gain, abs(gain))
        rows.append(
            {
                "comparator_id": comparator_id,
                "balanced_accuracy_after_grouped_label_rotation": metrics.get("balanced_accuracy"),
                "original_balanced_accuracy": original.get("balanced_accuracy"),
                "delta_balanced_accuracy": _round(gain),
            }
        )
    passed = threshold is not None and max_abs_gain <= threshold
    return {
        "control_id": "grouped_permutation",
        "status": "computed_from_final_logits",
        "threshold": threshold,
        "max_abs_delta_balanced_accuracy": _round(max_abs_gain),
        "passed": passed,
        "claim_ready": False,
        "claim_evaluable": False,
        "rows": rows,
        "scientific_limit": "Grouped label rotation is a logit-level diagnostic, not a substitute for rerun controls.",
    }


def _shuffled_labels_control(logits: dict[str, list[dict[str, Any]]], threshold: float | None) -> dict[str, Any]:
    rows = []
    max_abs_gain = 0.0
    for comparator_id, comp_rows in sorted(logits.items()):
        labels = [float(row["y_true"]) for row in comp_rows]
        shuffled = list(reversed(labels))
        metrics = _classification_metrics(
            shuffled,
            [float(row["prob_load8"]) for row in comp_rows],
            [int(row.get("y_pred", 1 if float(row["prob_load8"]) >= 0.5 else 0)) for row in comp_rows],
        )
        original = _metrics_from_rows(comp_rows)
        gain = _delta(metrics.get("balanced_accuracy"), original.get("balanced_accuracy"))
        max_abs_gain = max(max_abs_gain, abs(gain))
        rows.append(
            {
                "comparator_id": comparator_id,
                "balanced_accuracy_after_label_reversal": metrics.get("balanced_accuracy"),
                "original_balanced_accuracy": original.get("balanced_accuracy"),
                "delta_balanced_accuracy": _round(gain),
            }
        )
    passed = threshold is not None and max_abs_gain <= threshold
    return {
        "control_id": "shuffled_labels",
        "status": "computed_from_final_logits",
        "threshold": threshold,
        "max_abs_delta_balanced_accuracy": _round(max_abs_gain),
        "passed": passed,
        "claim_ready": False,
        "claim_evaluable": False,
        "rows": rows,
        "scientific_limit": "Shuffled-label logit diagnostic does not replace a model retrain under shuffled labels.",
    }


def _transfer_consistency_control(logits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    signatures = {}
    for comparator_id, comp_rows in logits.items():
        signatures[comparator_id] = [
            (
                str(row.get("row_id")),
                str(row.get("participant_id")),
                str(row.get("session_id")),
                str(row.get("trial_id")),
                int(row.get("y_true")),
            )
            for row in comp_rows
        ]
    first = next(iter(signatures.values())) if signatures else []
    mismatched = [key for key, value in signatures.items() if value != first]
    return {
        "control_id": "transfer_consistency",
        "status": "computed_from_final_logits",
        "passed": not mismatched and bool(signatures),
        "mismatched_comparators": mismatched,
        "n_comparators_checked": len(signatures),
        "n_rows_per_comparator": {key: len(value) for key, value in signatures.items()},
        "claim_ready": False,
        "claim_evaluable": False,
        "scientific_limit": "Transfer consistency checks row alignment only; it is not efficacy evidence.",
    }


def _rotate_labels_by_group(rows: list[dict[str, Any]], group_key: str) -> list[int]:
    rotated = [int(row["y_true"]) for row in rows]
    by_group: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        by_group.setdefault(str(row.get(group_key)), []).append(index)
    for indices in by_group.values():
        if len(indices) < 2:
            continue
        values = [rotated[index] for index in indices]
        values = values[1:] + values[:1]
        for index, value in zip(indices, values):
            rotated[index] = value
    return rotated


def _load_dedicated_control_manifest(path: str | Path | None) -> dict[str, Any]:
    manifest_path = Path(path) if path else None
    if manifest_path is None or not manifest_path.exists():
        return {
            "status": "phase1_final_dedicated_controls_not_provided",
            "manifest_path": str(manifest_path) if manifest_path else None,
            "results": [],
            "dedicated_control_suite_passed": None,
            "claim_ready": False,
            "claim_evaluable": False,
            "blockers": ["dedicated_final_control_manifest_missing"],
        }
    data = _read_json(manifest_path)
    data["manifest_path"] = str(manifest_path)
    return data


def _build_rerun_requirements(
    controls_config: dict[str, Any],
    *,
    dedicated_controls: dict[str, Any],
) -> dict[str, Any]:
    required = list(controls_config.get("dedicated_rerun_required_controls", []))
    provided = list(dedicated_controls.get("results", []))
    missing = [control_id for control_id in required if control_id not in provided]
    dedicated_passed = dedicated_controls.get("dedicated_control_suite_passed")
    return {
        "status": "phase1_final_dedicated_control_reruns_required"
        if missing or dedicated_passed is not True
        else "phase1_final_dedicated_control_reruns_satisfied",
        "claim_ready": False,
        "claim_evaluable": dedicated_passed is True and not missing,
        "missing_control_ids": missing,
        "dedicated_control_manifest_path": dedicated_controls.get("manifest_path"),
        "dedicated_control_suite_passed": dedicated_passed,
        "dedicated_control_blockers": list(dedicated_controls.get("blockers", [])),
        "requirements": [
            {
                "control_id": control_id,
                "status": "missing_dedicated_final_control_artifact",
                "required_action": "execute dedicated final control runner under locked prereg/revision policy",
            }
            for control_id in missing
        ],
        "scientific_limit": "Missing dedicated controls are blockers; they must not be inferred from logits.",
    }


def _build_manifest(
    *,
    logit_controls: dict[str, Any],
    dedicated_controls: dict[str, Any],
    rerun_requirements: dict[str, Any],
    input_validation: dict[str, Any],
    controls_config: dict[str, Any],
) -> dict[str, Any]:
    computed = list(logit_controls.get("computed_control_ids", []))
    dedicated_results = list(dedicated_controls.get("results", []))
    computed_all = computed + [item for item in dedicated_results if item not in computed]
    missing = list(rerun_requirements.get("missing_control_ids", []))
    required = list(controls_config.get("required_final_control_results", REQUIRED_FINAL_CONTROL_RESULTS))
    blockers = list(input_validation.get("blockers", []))
    if missing:
        blockers.append("dedicated_final_control_artifacts_missing")
    if dedicated_controls.get("dedicated_control_suite_passed") is not True:
        blockers.append("dedicated_final_control_suite_not_passed")
    blockers.extend(list(dedicated_controls.get("blockers", [])))
    missing_required = [item for item in required if item not in computed_all]
    if missing_required:
        blockers.append("required_final_control_results_missing")
    control_suite_passed = not blockers and not missing_required
    return {
        "status": "phase1_final_controls_manifest_recorded"
        if control_suite_passed
        else "phase1_final_controls_blocked_manifest_recorded",
        "results": computed_all,
        "logit_level_results": computed,
        "dedicated_control_results": dedicated_results,
        "required_results": required,
        "missing_results": missing_required,
        "dedicated_rerun_required_controls": missing,
        "dedicated_control_manifest_path": dedicated_controls.get("manifest_path"),
        "dedicated_control_suite_passed": dedicated_controls.get("dedicated_control_suite_passed"),
        "control_suite_passed": control_suite_passed,
        "claim_ready": False,
        "claim_evaluable": control_suite_passed,
        "smoke_artifacts_promoted": False,
        "blockers": _unique(blockers),
        "scientific_limit": (
            "Final control manifest records executed controls and missing dedicated controls. "
            "It does not open claims."
        ),
    }


def _build_claim_state(*, manifest: dict[str, Any], input_validation: dict[str, Any]) -> dict[str, Any]:
    blockers = list(input_validation.get("blockers", [])) + list(manifest.get("blockers", []))
    if manifest.get("control_suite_passed") is not True:
        blockers.append("final_control_suite_not_passed")
    return {
        "status": "phase1_final_controls_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "control_suite_passed": manifest.get("control_suite_passed"),
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
        "status": "phase1_final_controls_source_links_recorded",
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
        "scientific_limit": "Source links record provenance only; they are not control evidence.",
    }


def _build_summary(
    *,
    output_dir: Path,
    comparator: dict[str, Any],
    manifest: dict[str, Any],
    input_validation: dict[str, Any],
    claim_state: dict[str, Any],
) -> dict[str, Any]:
    control_suite_passed = manifest.get("control_suite_passed") is True and not input_validation.get("blockers")
    return {
        "status": "phase1_final_controls_complete_claim_closed"
        if control_suite_passed
        else "phase1_final_controls_blocked",
        "output_dir": str(output_dir),
        "comparator_reconciliation_run": str(comparator["run_dir"]),
        "computed_control_results": manifest.get("results", []),
        "missing_control_results": manifest.get("missing_results", []),
        "control_suite_passed": control_suite_passed,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final controls package records controls that were actually computed and controls still missing. "
            "It does not prove Phase 1 efficacy."
        ),
    }


def _render_report(summary: dict[str, Any], manifest: dict[str, Any], claim_state: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Phase 1 Final Controls",
            "",
            f"Status: `{summary['status']}`",
            f"Control suite passed: `{summary['control_suite_passed']}`",
            f"Computed control results: `{', '.join(summary['computed_control_results']) or 'none'}`",
            f"Missing control results: `{', '.join(summary['missing_control_results']) or 'none'}`",
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


def _delta(value: Any, baseline: Any) -> float:
    if value is None or baseline is None:
        return 0.0
    return float(value) - float(baseline)


def _round(value: float) -> float:
    return round(float(value), 6)


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
