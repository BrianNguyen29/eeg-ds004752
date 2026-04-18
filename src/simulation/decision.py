"""Gate 1 decision simulation and governance artefact writer.

This module intentionally does not inspect signal payloads or model outputs.
Gate 1 locks the decision layer from Gate 0 cohort metadata before any
substantive real-data model phase is allowed.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


class Gate1Error(RuntimeError):
    """Raised when Gate 1 cannot be run with the provided frozen inputs."""


@dataclass(frozen=True)
class Gate1Result:
    output_dir: Path
    inputs_path: Path
    integrity_path: Path
    n_eff_path: Path
    simulation_registry_path: Path
    sesoi_registry_path: Path
    influence_rule_path: Path
    decision_memo_path: Path
    summary_path: Path
    summary: dict[str, Any]


def run_gate1_decision(
    gate0_run: str | Path,
    config: dict[str, Any],
    output_root: str | Path,
    repo_root: str | Path | None = None,
) -> Gate1Result:
    gate0_run = Path(gate0_run)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    if not gate0_run.exists():
        raise FileNotFoundError(f"Gate 0 run not found: {gate0_run}")

    manifest_path = gate0_run / "manifest.json"
    cohort_lock_path = gate0_run / "cohort_lock.json"
    materialization_path = gate0_run / "materialization_report.json"
    audit_report_path = gate0_run / "audit_report.md"
    manifest = _read_json(manifest_path)
    cohort_lock = _read_json(cohort_lock_path)

    validation = validate_gate1_inputs(manifest, cohort_lock)
    if validation["errors"]:
        raise Gate1Error("; ".join(validation["errors"]))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    n_eff = build_n_eff_statement(manifest, cohort_lock)
    inputs = build_gate1_inputs(gate0_run, manifest_path, cohort_lock_path, manifest, cohort_lock, n_eff)
    integrity = build_input_integrity(
        output_dir,
        repo_root,
        gate0_run,
        manifest_path,
        cohort_lock_path,
        materialization_path,
        audit_report_path,
    )
    simulation_registry = run_decision_simulation(n_eff, config)
    sesoi_registry = build_sesoi_registry(config)
    influence_rule = build_influence_rule(config)
    summary = build_gate1_summary(
        timestamp,
        output_dir,
        inputs,
        integrity,
        n_eff,
        simulation_registry,
        sesoi_registry,
        influence_rule,
    )

    inputs_path = output_dir / "gate1_inputs.json"
    integrity_path = output_dir / "gate1_input_integrity.json"
    n_eff_path = output_dir / "n_eff_statement.json"
    simulation_registry_path = output_dir / "simulation_registry.json"
    sesoi_registry_path = output_dir / "sesoi_registry.json"
    influence_rule_path = output_dir / "influence_rule.json"
    decision_memo_path = output_dir / "decision_memo.md"
    summary_path = output_dir / "gate1_summary.json"

    _write_json(inputs_path, inputs)
    _write_json(integrity_path, integrity)
    _write_json(n_eff_path, n_eff)
    _write_json(simulation_registry_path, simulation_registry)
    _write_json(sesoi_registry_path, sesoi_registry)
    _write_json(influence_rule_path, influence_rule)
    decision_memo_path.write_text(
        render_decision_memo(inputs, n_eff, simulation_registry, sesoi_registry, influence_rule),
        encoding="utf-8",
    )
    _write_json(summary_path, summary)
    _write_latest_pointer(output_root, output_dir)

    return Gate1Result(
        output_dir=output_dir,
        inputs_path=inputs_path,
        integrity_path=integrity_path,
        n_eff_path=n_eff_path,
        simulation_registry_path=simulation_registry_path,
        sesoi_registry_path=sesoi_registry_path,
        influence_rule_path=influence_rule_path,
        decision_memo_path=decision_memo_path,
        summary_path=summary_path,
        summary=summary,
    )


def validate_gate1_inputs(manifest: dict[str, Any], cohort_lock: dict[str, Any]) -> dict[str, Any]:
    signal = manifest.get("signal_audit", {})
    payload = manifest.get("payload_state", {})
    subjects = manifest.get("subjects", {})
    expected_sessions = subjects.get("n_sessions")
    expected_mat = payload.get("mat", {}).get("count")
    errors = []

    if manifest.get("manifest_status") != "signal_audit_ready":
        errors.append(f"manifest_status is not signal_audit_ready: {manifest.get('manifest_status')}")
    if signal.get("status") != "ok":
        errors.append(f"signal_audit.status is not ok: {signal.get('status')}")
    if signal.get("subject_filter"):
        errors.append("signal_audit has a subject_filter; Gate 1 requires an unfiltered full audit")
    if signal.get("session_filter"):
        errors.append("signal_audit has a session_filter; Gate 1 requires an unfiltered full audit")
    if expected_sessions is None or signal.get("candidate_sessions") != expected_sessions:
        errors.append(
            f"candidate_sessions mismatch: expected {expected_sessions}, got {signal.get('candidate_sessions')}"
        )
    if expected_sessions is None or signal.get("sessions_checked") != expected_sessions:
        errors.append(f"sessions_checked mismatch: expected {expected_sessions}, got {signal.get('sessions_checked')}")
    if expected_mat is None or signal.get("candidate_mat_files") != expected_mat:
        errors.append(f"candidate_mat_files mismatch: expected {expected_mat}, got {signal.get('candidate_mat_files')}")
    if expected_mat is None or signal.get("mat_files_checked") != expected_mat:
        errors.append(f"mat_files_checked mismatch: expected {expected_mat}, got {signal.get('mat_files_checked')}")
    if manifest.get("gate0_blockers") != []:
        errors.append(f"Gate 0 blockers are not empty: {manifest.get('gate0_blockers')}")
    if payload.get("edf", {}).get("pointer_like_count") != 0:
        errors.append("EDF payloads are not fully materialized")
    if payload.get("mat", {}).get("pointer_like_count") != 0:
        errors.append("MAT derivatives are not fully materialized")
    if cohort_lock.get("cohort_lock_status") != "signal_audit_ready":
        errors.append(f"cohort_lock_status is not signal_audit_ready: {cohort_lock.get('cohort_lock_status')}")
    if cohort_lock.get("n_primary_eligible") is None:
        errors.append("n_primary_eligible is missing")

    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }


def build_n_eff_statement(manifest: dict[str, Any], cohort_lock: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "locked_from_gate0_cohort_lock",
        "n_raw": manifest["participants"]["n_raw_public"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "primary_denominator": "subject",
        "outer_fold_unit": "participant_id",
        "n_outer_folds_planned": cohort_lock["n_primary_eligible"],
        "sessions_total": manifest["subjects"]["n_sessions"],
        "sessions_are_primary_independent_units": False,
        "primary_endpoint": "nested_loso_subject_level_binary_load_4_vs_8",
        "participant_ids": [item["participant_id"] for item in cohort_lock.get("participants", [])],
        "fallback_reader_registry": cohort_lock.get("fallback_reader_registry", []),
        "interpretation_limits": [
            "N_primary_eligible is Gate 0 technical eligibility, not model efficacy.",
            "Sessions are repeated measurements and not independent primary denominator units.",
            "Gate 1 does not authorize real-data substantive model phases.",
        ],
    }


def build_gate1_inputs(
    gate0_run: Path,
    manifest_path: Path,
    cohort_lock_path: Path,
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    n_eff: dict[str, Any],
) -> dict[str, Any]:
    signal = manifest["signal_audit"]
    payload = manifest["payload_state"]
    return {
        "status": "gate1_input_freeze_ready",
        "gate0_source_of_truth": str(gate0_run),
        "manifest_path": str(manifest_path),
        "cohort_lock_path": str(cohort_lock_path),
        "n_eff": n_eff,
        "gate0_checks": {
            "manifest_status": manifest["manifest_status"],
            "signal_status": signal["status"],
            "candidate_sessions": signal["candidate_sessions"],
            "sessions_checked": signal["sessions_checked"],
            "candidate_mat_files": signal["candidate_mat_files"],
            "mat_files_checked": signal["mat_files_checked"],
            "gate0_blockers": manifest["gate0_blockers"],
            "edf_materialized": payload["edf"]["materialized_count"],
            "edf_missing": payload["edf"]["pointer_like_count"],
            "mat_materialized": payload["mat"]["materialized_count"],
            "mat_missing": payload["mat"]["pointer_like_count"],
            "cohort_lock_status": cohort_lock["cohort_lock_status"],
        },
        "scientific_integrity_limits": n_eff["interpretation_limits"]
        + [
            "Gate 1 must read cohort from cohort_lock.json, not participants.tsv.",
            "Gate 1 must not tune SESOI or thresholds using real model outcomes.",
        ],
    }


def build_input_integrity(
    gate1_run: Path,
    repo_root: Path,
    gate0_run: Path,
    manifest_path: Path,
    cohort_lock_path: Path,
    materialization_path: Path,
    audit_report_path: Path,
) -> dict[str, Any]:
    return {
        "status": "gate1_input_integrity_recorded",
        "gate1_run": str(gate1_run),
        "repo": _git_identity(repo_root),
        "gate0_source_of_truth": str(gate0_run),
        "artifact_hashes_sha256": {
            "manifest_json": _hash_entry(manifest_path),
            "cohort_lock_json": _hash_entry(cohort_lock_path),
            "materialization_report_json": _hash_entry(materialization_path),
            "audit_report_md": _hash_entry(audit_report_path),
        },
        "interpretation": (
            "This file records exact Gate 0 artifacts and code state used to start Gate 1. "
            "It does not authorize real-data substantive phases."
        ),
    }


def run_decision_simulation(n_eff: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    seed = int(config["random_seed"])
    n_repeats = int(config["n_repeats"])
    ci_method = str(config.get("ci_method", "binomial_order_statistic_median_ci"))
    ci_alpha = float(config.get("ci_alpha", 0.05))
    sesoi = float(config["subject_level_sesoi_delta_ba"])
    influence_ceiling = float(config["influence_ceiling"])
    n_subjects = int(n_eff["n_primary_eligible"])
    rng = random.Random(seed)
    scenarios = []

    for delta in config["effect_grid_delta_ba"]:
        for survival in config["teacher_survival_fraction_grid"]:
            for heterogeneity_name, heterogeneity_sd in config["heterogeneity_levels"].items():
                scenarios.append(
                    _simulate_scenario(
                        rng,
                        n_subjects=n_subjects,
                        n_repeats=n_repeats,
                        ci_alpha=ci_alpha,
                        ci_method=ci_method,
                        assumed_delta_ba=float(delta),
                        teacher_survival_fraction=float(survival),
                        heterogeneity_name=str(heterogeneity_name),
                        heterogeneity_sd=float(heterogeneity_sd),
                        sesoi=sesoi,
                        influence_ceiling=influence_ceiling,
                    )
                )

    return {
        "status": "complete",
        "simulation_type": "gate1_subject_level_decision_proxy",
        "not_a_model_result": True,
        "random_seed": seed,
        "n_repeats": n_repeats,
        "ci_method": ci_method,
        "n_subjects": n_subjects,
        "effect_grid_delta_ba": config["effect_grid_delta_ba"],
        "teacher_survival_fraction_grid": config["teacher_survival_fraction_grid"],
        "heterogeneity_levels": config["heterogeneity_levels"],
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "interpretation": (
            "This registry explores decision-rule behavior under preregistered assumptions. "
            "It is not empirical model performance and must not be used as evidence of efficacy."
        ),
    }


def build_sesoi_registry(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "registry_status": "locked_by_gate1_for_gate2_planning",
        "primary_subject_level_sesoi": {
            "metric": config["primary_metric"],
            "comparison": f"{config['privileged_model']}_vs_{config['primary_comparator']}",
            "median_delta_ba_min": config["subject_level_sesoi_delta_ba"],
        },
        "calibration_tolerance": {
            "metric": "expected_calibration_error",
            "max_allowed_delta_ece": config["max_allowed_delta_ece"],
        },
        "strong_claim_requires": [
            "median_subject_delta_ba >= subject_level_sesoi_delta_ba",
            "subject_level_ci_lower > 0",
            "paired_permutation_p < 0.05 in real analysis",
            "influence_concentration <= influence_ceiling",
            "no required negative-control failure",
            "privileged model exceeds A3 and scalp-only comparators including A2d",
        ],
        "pivot_if": [
            "teacher survival is too sparse for the locked N_eff",
            "heterogeneity is too high for stable subject-level interpretation",
            "privileged model does not robustly exceed A2d",
            "influence governance blocks a strong claim",
        ],
    }


def build_influence_rule(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_id": "gate1_subject_level_influence_v1",
        "unit": "outer_test_subject",
        "influence_ceiling": config["influence_ceiling"],
        "metrics": [
            "max_single_subject_absolute_contribution_share",
            "leave_one_subject_out_claim_state_change",
        ],
        "strong_claim_blocked_if": [
            "max_single_subject_absolute_contribution_share > influence_ceiling",
            "leave_one_subject_out_changes_claim_state",
        ],
        "scope": "claim_governance_not_replacement_for_permutation_or_ci",
    }


def build_gate1_summary(
    timestamp: str,
    output_dir: Path,
    inputs: dict[str, Any],
    integrity: dict[str, Any],
    n_eff: dict[str, Any],
    simulation_registry: dict[str, Any],
    sesoi_registry: dict[str, Any],
    influence_rule: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "gate1_decision_layer_ready",
        "created_utc": timestamp,
        "run_dir": str(output_dir),
        "gate0_source_of_truth": inputs["gate0_source_of_truth"],
        "git_commit": integrity["repo"]["commit"],
        "working_tree_clean": integrity["repo"]["working_tree_clean"],
        "n_eff": {
            "n_primary_eligible": n_eff["n_primary_eligible"],
            "n_outer_folds_planned": n_eff["n_outer_folds_planned"],
            "primary_denominator": n_eff["primary_denominator"],
        },
        "simulation": {
            "status": simulation_registry["status"],
            "scenario_count": simulation_registry["scenario_count"],
            "n_repeats": simulation_registry["n_repeats"],
            "not_a_model_result": simulation_registry["not_a_model_result"],
        },
        "sesoi": {
            "subject_level_sesoi_delta_ba": sesoi_registry["primary_subject_level_sesoi"]["median_delta_ba_min"],
            "max_allowed_delta_ece": sesoi_registry["calibration_tolerance"]["max_allowed_delta_ece"],
        },
        "influence": {
            "influence_ceiling": influence_rule["influence_ceiling"],
            "unit": influence_rule["unit"],
        },
        "real_data_phase_authorized": False,
        "next_gate": "gate2_synthetic_validation",
    }


def render_decision_memo(
    inputs: dict[str, Any],
    n_eff: dict[str, Any],
    simulation_registry: dict[str, Any],
    sesoi_registry: dict[str, Any],
    influence_rule: dict[str, Any],
) -> str:
    lines = [
        "# Gate 1 Decision Memo",
        "",
        "## Status",
        "",
        "Gate 1 decision layer is ready for Gate 2 synthetic validation.",
        "No real-data substantive phase is authorized by this memo.",
        "",
        "## Gate 0 Source Of Truth",
        "",
        f"- Gate 0 run: `{inputs['gate0_source_of_truth']}`",
        f"- Manifest status: `{inputs['gate0_checks']['manifest_status']}`",
        f"- Cohort lock status: `{inputs['gate0_checks']['cohort_lock_status']}`",
        "",
        "## N_eff Statement",
        "",
        f"- N raw: {n_eff['n_raw']}",
        f"- N primary eligible: {n_eff['n_primary_eligible']}",
        f"- Primary denominator: {n_eff['primary_denominator']}",
        f"- Planned outer folds: {n_eff['n_outer_folds_planned']}",
        f"- Sessions total: {n_eff['sessions_total']}",
        "- Sessions are not independent primary denominator units.",
        "",
        "## Simulation Grid",
        "",
        f"- Scenario count: {simulation_registry['scenario_count']}",
        f"- Repeats per scenario: {simulation_registry['n_repeats']}",
        f"- Delta BA grid: {simulation_registry['effect_grid_delta_ba']}",
        f"- Teacher survival grid: {simulation_registry['teacher_survival_fraction_grid']}",
        f"- Heterogeneity levels: {simulation_registry['heterogeneity_levels']}",
        "",
        "## SESOI",
        "",
        f"- Median subject-level Delta BA minimum: {sesoi_registry['primary_subject_level_sesoi']['median_delta_ba_min']}",
        f"- Maximum allowed Delta ECE: {sesoi_registry['calibration_tolerance']['max_allowed_delta_ece']}",
        "",
        "## Influence Governance",
        "",
        f"- Unit: {influence_rule['unit']}",
        f"- Influence ceiling: {influence_rule['influence_ceiling']}",
        "- Strong claim is blocked if one outer-test subject dominates the gain.",
        "",
        "## Scientific Integrity Limits",
        "",
        "- This memo does not contain empirical model performance.",
        "- This memo does not prove privileged transfer efficacy.",
        "- Phase 0.5/1/2/3 real-data substantive runs remain blocked until Gate 2 and Gate 2.5 pass.",
        "- Thresholds and interpretation rules must not be tuned after viewing real substantive model outcomes.",
        "",
    ]
    return "\n".join(lines)


def _simulate_scenario(
    rng: random.Random,
    *,
    n_subjects: int,
    n_repeats: int,
    ci_alpha: float,
    ci_method: str,
    assumed_delta_ba: float,
    teacher_survival_fraction: float,
    heterogeneity_name: str,
    heterogeneity_sd: float,
    sesoi: float,
    influence_ceiling: float,
) -> dict[str, Any]:
    sesoi_hits = 0
    ci_excludes_zero = 0
    influence_blocks = 0
    strong_claim_proxy_hits = 0
    medians = []

    for _ in range(n_repeats):
        effects = []
        for _subject in range(n_subjects):
            survives = rng.random() < teacher_survival_fraction
            effect = rng.gauss(assumed_delta_ba, heterogeneity_sd) if survives else 0.0
            effects.append(effect)
        med = median(effects)
        ci_low, _ci_high = _median_ci(effects, ci_alpha, ci_method)
        influence = _influence_metrics(effects, sesoi)
        sesoi_hit = med >= sesoi
        ci_ok = ci_low > 0
        influence_block = influence["max_single_subject_absolute_contribution_share"] > influence_ceiling or influence[
            "leave_one_subject_out_changes_claim_state"
        ]

        medians.append(med)
        sesoi_hits += int(sesoi_hit)
        ci_excludes_zero += int(ci_ok)
        influence_blocks += int(influence_block)
        strong_claim_proxy_hits += int(sesoi_hit and ci_ok and not influence_block)

    return {
        "assumed_delta_ba": assumed_delta_ba,
        "teacher_survival_fraction": teacher_survival_fraction,
        "heterogeneity_level": heterogeneity_name,
        "heterogeneity_sd": heterogeneity_sd,
        "median_of_repeat_medians": round(median(medians), 6),
        "sesoi_hit_rate": round(sesoi_hits / n_repeats, 6),
        "ci_excludes_zero_rate": round(ci_excludes_zero / n_repeats, 6),
        "influence_block_rate": round(influence_blocks / n_repeats, 6),
        "strong_claim_proxy_rate": round(strong_claim_proxy_hits / n_repeats, 6),
        "expected_claim_state": _expected_claim_state(strong_claim_proxy_hits / n_repeats),
    }


def _median_ci(
    values: list[float],
    alpha: float,
    method: str,
) -> tuple[float, float]:
    if method != "binomial_order_statistic_median_ci":
        raise Gate1Error(f"Unsupported Gate 1 CI method: {method}")
    ordered = sorted(values)
    n = len(ordered)
    lower_index = _median_order_stat_lower_index(n, alpha)
    upper_index = n - lower_index - 1
    return ordered[lower_index], ordered[upper_index]


def _median_order_stat_lower_index(n: int, alpha: float) -> int:
    lower_index = 0
    for candidate in range((n // 2) + 1):
        tail = sum(math.comb(n, item) for item in range(candidate)) * (0.5 ** n)
        coverage = 1 - (2 * tail)
        if coverage >= 1 - alpha:
            lower_index = candidate
            continue
        break
    return lower_index


def _influence_metrics(effects: list[float], sesoi: float) -> dict[str, Any]:
    absolute_total = sum(abs(item) for item in effects)
    max_share = max((abs(item) / absolute_total for item in effects), default=0.0) if absolute_total else 0.0
    full_claim = median(effects) >= sesoi
    loo_changes = False
    if len(effects) > 1:
        for index in range(len(effects)):
            without_one = effects[:index] + effects[index + 1 :]
            if (median(without_one) >= sesoi) != full_claim:
                loo_changes = True
                break
    return {
        "max_single_subject_absolute_contribution_share": max_share,
        "leave_one_subject_out_changes_claim_state": loo_changes,
    }


def _expected_claim_state(strong_claim_proxy_rate: float) -> str:
    if strong_claim_proxy_rate >= 0.8:
        return "strong_claim_plausible_under_assumption"
    if strong_claim_proxy_rate >= 0.5:
        return "claim_sensitive_to_sampling_and_influence"
    return "default_to_mechanism_or_atlas_centered_interpretation"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Gate1Error(f"JSON root must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.joinpath("latest.txt").write_text(str(output_dir), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required artifact not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_entry(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
    }


def _git_identity(repo_root: Path) -> dict[str, Any]:
    commit = _git_output(repo_root, ["git", "rev-parse", "HEAD"])
    branch = _git_output(repo_root, ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    status = _git_output(repo_root, ["git", "status", "--short"])
    return {
        "path": str(repo_root),
        "branch": branch,
        "commit": commit,
        "working_tree_clean": status == "",
        "git_status_short": status,
    }


def _git_output(repo_root: Path, command: list[str]) -> str:
    try:
        return subprocess.check_output(command, cwd=repo_root, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"
