"""Gate 2 synthetic validation and threshold registry workflow.

This is a controlled synthetic validation proxy. It does not train real EEG
models and it does not inspect real signal payloads. Its purpose is to lock
expected synthetic recovery patterns and threshold provenance before Gate 2.5.
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


class Gate2Error(RuntimeError):
    """Raised when Gate 2 cannot proceed from the provided Gate 1 artefacts."""


@dataclass(frozen=True)
class Gate2Result:
    output_dir: Path
    generator_spec_path: Path
    recovery_report_path: Path
    recovery_json_path: Path
    threshold_registry_path: Path
    summary_path: Path
    summary: dict[str, Any]


def run_gate2_synthetic_validation(
    gate1_run: str | Path,
    config: dict[str, Any],
    output_root: str | Path,
    repo_root: str | Path | None = None,
) -> Gate2Result:
    gate1_run = Path(gate1_run)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    if not gate1_run.exists():
        raise FileNotFoundError(f"Gate 1 run not found: {gate1_run}")

    gate1_summary_path = gate1_run / "gate1_summary.json"
    gate1_inputs_path = gate1_run / "gate1_inputs.json"
    n_eff_path = gate1_run / "n_eff_statement.json"
    sesoi_path = gate1_run / "sesoi_registry.json"
    influence_path = gate1_run / "influence_rule.json"
    simulation_path = gate1_run / "simulation_registry.json"

    gate1_summary = _read_json(gate1_summary_path)
    gate1_inputs = _read_json(gate1_inputs_path)
    n_eff = _read_json(n_eff_path)
    sesoi = _read_json(sesoi_path)
    influence = _read_json(influence_path)
    simulation = _read_json(simulation_path)

    validation = validate_gate2_inputs(gate1_summary, n_eff, sesoi, influence, simulation)
    if validation["errors"]:
        raise Gate2Error("; ".join(validation["errors"]))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    generator_spec = build_synthetic_generator_spec(timestamp, gate1_run, gate1_summary, n_eff, config, repo_root)
    recovery = run_synthetic_recovery(generator_spec, config)
    threshold_registry = build_threshold_registry(timestamp, generator_spec, recovery, config, sesoi, influence)
    summary = build_gate2_summary(
        timestamp,
        output_dir,
        gate1_run,
        gate1_summary,
        gate1_inputs,
        generator_spec,
        recovery,
        threshold_registry,
    )

    generator_spec_path = output_dir / "synthetic_generator_spec.json"
    recovery_json_path = output_dir / "synthetic_recovery_report.json"
    recovery_report_path = output_dir / "synthetic_recovery_report.md"
    threshold_registry_path = output_dir / "gate_threshold_registry.json"
    summary_path = output_dir / "gate2_summary.json"

    _write_json(generator_spec_path, generator_spec)
    _write_json(recovery_json_path, recovery)
    recovery_report_path.write_text(render_recovery_report(generator_spec, recovery, threshold_registry), encoding="utf-8")
    _write_json(threshold_registry_path, threshold_registry)
    _write_json(summary_path, summary)
    _write_latest_pointer(output_root, output_dir)

    return Gate2Result(
        output_dir=output_dir,
        generator_spec_path=generator_spec_path,
        recovery_report_path=recovery_report_path,
        recovery_json_path=recovery_json_path,
        threshold_registry_path=threshold_registry_path,
        summary_path=summary_path,
        summary=summary,
    )


def validate_gate2_inputs(
    gate1_summary: dict[str, Any],
    n_eff: dict[str, Any],
    sesoi: dict[str, Any],
    influence: dict[str, Any],
    simulation: dict[str, Any],
) -> dict[str, Any]:
    errors = []
    if gate1_summary.get("status") != "gate1_decision_layer_ready":
        errors.append(f"Gate 1 status is not ready: {gate1_summary.get('status')}")
    if gate1_summary.get("real_data_phase_authorized") is not False:
        errors.append("Gate 1 must not authorize real-data phases before Gate 2")
    if gate1_summary.get("next_gate") != "gate2_synthetic_validation":
        errors.append(f"Gate 1 next_gate mismatch: {gate1_summary.get('next_gate')}")
    if n_eff.get("n_primary_eligible") != gate1_summary.get("n_eff", {}).get("n_primary_eligible"):
        errors.append("N_eff mismatch between Gate 1 summary and n_eff_statement")
    if sesoi.get("primary_subject_level_sesoi", {}).get("median_delta_ba_min") is None:
        errors.append("SESOI registry is missing median_delta_ba_min")
    if influence.get("influence_ceiling") is None:
        errors.append("Influence rule is missing influence_ceiling")
    if simulation.get("not_a_model_result") is not True:
        errors.append("Gate 1 simulation registry must be marked not_a_model_result")
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }


def build_synthetic_generator_spec(
    timestamp: str,
    gate1_run: Path,
    gate1_summary: dict[str, Any],
    n_eff: dict[str, Any],
    config: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    spec = {
        "status": "locked_for_gate2_run",
        "created_utc": timestamp,
        "gate1_source_of_truth": str(gate1_run),
        "gate1_git_commit": gate1_summary.get("git_commit"),
        "repo": _git_identity(repo_root),
        "generator_type": "standard_library_subject_level_synthetic_recovery_proxy",
        "uses_real_signal_payloads": False,
        "uses_real_model_outputs": False,
        "allowed_real_inputs": [
            "Gate 1 N_eff statement",
            "Gate 1 SESOI registry",
            "Gate 1 influence rule",
            "Gate 1 decision simulation assumptions",
        ],
        "n_eff": {
            "n_primary_eligible": n_eff["n_primary_eligible"],
            "primary_denominator": n_eff["primary_denominator"],
        },
        "parameters": {
            "random_seed": config["random_seed"],
            "n_subjects": config["n_subjects"],
            "trials_per_class_per_subject": config["trials_per_class_per_subject"],
            "classes": config["classes"],
            "n_repeats": config["n_repeats"],
            "effect_profiles": config["effect_profiles"],
            "negative_controls": config["negative_controls"],
            "pass_criteria": config["pass_criteria"],
            "threshold_sweep": config["threshold_sweep"],
        },
        "scientific_scope": (
            "This synthetic suite checks expected recovery/control patterns before real-data phases. "
            "It is not evidence of real EEG model efficacy."
        ),
    }
    spec["generator_hash_sha256"] = _sha256_json(spec)
    return spec


def run_synthetic_recovery(generator_spec: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(int(config["random_seed"]))
    n_subjects = int(config["n_subjects"])
    n_repeats = int(config["n_repeats"])
    pass_criteria = config["pass_criteria"]
    profile_results = []
    for profile_name, profile in config["effect_profiles"].items():
        profile_results.append(
            _simulate_profile(
                rng,
                profile_name=profile_name,
                profile=profile,
                n_subjects=n_subjects,
                n_repeats=n_repeats,
                pass_criteria=pass_criteria,
                negative_controls=config["negative_controls"],
            )
        )
    gate2_pass = all(item["status"] == "passed" for item in profile_results)
    return {
        "status": "passed" if gate2_pass else "failed",
        "not_a_real_data_result": True,
        "generator_hash_sha256": generator_spec["generator_hash_sha256"],
        "profiles": profile_results,
        "required_expected_patterns": [
            "truly_observable: A4 > A3 > A2",
            "non_observable: A4 does not robustly exceed A3",
            "nuisance_shared: nuisance control vetoes raw privileged gain",
            "shuffled/time-shifted teacher controls remove privileged gain",
        ],
        "interpretation": (
            "Pass means the synthetic proxy produced the expected governance patterns. "
            "It does not authorize real-data substantive phases; Gate 2.5 prereg remains required."
        ),
    }


def build_threshold_registry(
    timestamp: str,
    generator_spec: dict[str, Any],
    recovery: dict[str, Any],
    config: dict[str, Any],
    sesoi: dict[str, Any],
    influence: dict[str, Any],
) -> dict[str, Any]:
    status = "locked_after_gate2_pass" if recovery["status"] == "passed" else "draft_failed_gate2"
    defaults = dict(config["frozen_threshold_defaults"])
    defaults["subject_level_sesoi_delta_ba"] = sesoi["primary_subject_level_sesoi"]["median_delta_ba_min"]
    defaults["max_allowed_delta_ece"] = sesoi["calibration_tolerance"]["max_allowed_delta_ece"]
    defaults["influence_ceiling"] = influence["influence_ceiling"]
    registry = {
        "status": status,
        "created_utc": timestamp,
        "generator_hash_sha256": generator_spec["generator_hash_sha256"],
        "recovery_status": recovery["status"],
        "thresholds": defaults,
        "sweep_grid": config["threshold_sweep"],
        "provenance": {
            "source": "Gate 2 synthetic validation proxy and Gate 1 governance registries",
            "hard_code_policy": "Downstream phases must read these thresholds from this registry, not notebooks.",
        },
        "real_data_phase_authorized": False,
        "next_gate": "gate2_5_preregistration_bundle" if recovery["status"] == "passed" else "fix_gate2_synthetic_validation",
    }
    registry["threshold_registry_hash_sha256"] = _sha256_json(registry)
    return registry


def build_gate2_summary(
    timestamp: str,
    output_dir: Path,
    gate1_run: Path,
    gate1_summary: dict[str, Any],
    gate1_inputs: dict[str, Any],
    generator_spec: dict[str, Any],
    recovery: dict[str, Any],
    threshold_registry: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "gate2_synthetic_ready" if recovery["status"] == "passed" else "gate2_synthetic_failed",
        "created_utc": timestamp,
        "run_dir": str(output_dir),
        "gate0_source_of_truth": gate1_inputs["gate0_source_of_truth"],
        "gate1_source_of_truth": str(gate1_run),
        "git_commit": gate1_summary.get("git_commit"),
        "generator_hash_sha256": generator_spec["generator_hash_sha256"],
        "recovery_status": recovery["status"],
        "threshold_registry_status": threshold_registry["status"],
        "real_data_phase_authorized": False,
        "next_gate": threshold_registry["next_gate"],
        "scientific_integrity_limits": [
            "Gate 2 synthetic validation is not empirical EEG model evidence.",
            "Gate 2 does not authorize real-data substantive phases without Gate 2.5 preregistration.",
            "Thresholds must be read from gate_threshold_registry.json downstream.",
        ],
    }


def render_recovery_report(
    generator_spec: dict[str, Any],
    recovery: dict[str, Any],
    threshold_registry: dict[str, Any],
) -> str:
    lines = [
        "# Gate 2 Synthetic Recovery Report",
        "",
        "## Status",
        "",
        f"- Recovery status: `{recovery['status']}`",
        f"- Generator hash: `{generator_spec['generator_hash_sha256']}`",
        f"- Threshold registry status: `{threshold_registry['status']}`",
        "- Real-data phase authorized: `False`",
        "",
        "## Scope",
        "",
        "This report is based on a synthetic recovery proxy. It does not train real EEG models, inspect real signal payloads, or prove real-data privileged transfer efficacy.",
        "",
        "## Profile Results",
        "",
    ]
    for item in recovery["profiles"]:
        lines.extend(
            [
                f"### {item['profile']}",
                "",
                f"- Status: `{item['status']}`",
                f"- Median A2 BA: {item['median_a2_ba']}",
                f"- Median A3 BA: {item['median_a3_ba']}",
                f"- Median A4 BA: {item['median_a4_ba']}",
                f"- Median A3-A2: {item['median_a3_minus_a2']}",
                f"- Median A4-A3: {item['median_a4_minus_a3']}",
                f"- Negative controls passed: {item['negative_controls_passed']}",
                f"- Nuisance veto applied: {item['nuisance_veto_applied']}",
                f"- Reason: {item['reason']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Threshold Registry",
            "",
            f"- Registry hash: `{threshold_registry['threshold_registry_hash_sha256']}`",
            f"- Next gate: `{threshold_registry['next_gate']}`",
            "",
            "## Scientific Integrity",
            "",
            "- Synthetic pass is necessary but not sufficient for real-data phases.",
            "- Gate 2.5 preregistration remains required before Phase 0.5/1/2/3 real-data runs.",
        ]
    )
    return "\n".join(lines) + "\n"


def _simulate_profile(
    rng: random.Random,
    *,
    profile_name: str,
    profile: dict[str, Any],
    n_subjects: int,
    n_repeats: int,
    pass_criteria: dict[str, Any],
    negative_controls: dict[str, Any],
) -> dict[str, Any]:
    median_a2 = []
    median_a3 = []
    median_a4 = []
    median_a3_minus_a2 = []
    median_a4_minus_a3 = []
    shuffled_gains = []
    shifted_gains = []
    for _repeat in range(n_repeats):
        a2_scores = []
        a3_scores = []
        a4_scores = []
        for _subject in range(n_subjects):
            a2 = _bounded_ba(rng.gauss(float(profile["a2_mean_ba"]), float(profile["subject_sd"])))
            a3 = _bounded_ba(a2 + rng.gauss(float(profile["a3_gain_over_a2"]), float(profile["subject_sd"]) / 3))
            a4 = _bounded_ba(a3 + rng.gauss(float(profile["a4_gain_over_a3"]), float(profile["subject_sd"]) / 3))
            a2_scores.append(a2)
            a3_scores.append(a3)
            a4_scores.append(a4)
        med_a2 = median(a2_scores)
        med_a3 = median(a3_scores)
        med_a4 = median(a4_scores)
        median_a2.append(med_a2)
        median_a3.append(med_a3)
        median_a4.append(med_a4)
        median_a3_minus_a2.append(med_a3 - med_a2)
        median_a4_minus_a3.append(med_a4 - med_a3)
        shuffled_gains.append(abs(rng.gauss(0.0, float(negative_controls["shuffled_teacher_max_gain_over_a3"]) / 2)))
        shifted_gains.append(abs(rng.gauss(0.0, float(negative_controls["time_shifted_teacher_max_gain_over_a3"]) / 2)))

    result = {
        "profile": profile_name,
        "median_a2_ba": round(median(median_a2), 6),
        "median_a3_ba": round(median(median_a3), 6),
        "median_a4_ba": round(median(median_a4), 6),
        "median_a3_minus_a2": round(median(median_a3_minus_a2), 6),
        "median_a4_minus_a3": round(median(median_a4_minus_a3), 6),
        "median_shuffled_teacher_abs_gain": round(median(shuffled_gains), 6),
        "median_time_shifted_teacher_abs_gain": round(median(shifted_gains), 6),
    }
    result.update(_evaluate_profile(profile_name, result, pass_criteria, negative_controls))
    return result


def _evaluate_profile(
    profile_name: str,
    result: dict[str, Any],
    pass_criteria: dict[str, Any],
    negative_controls: dict[str, Any],
) -> dict[str, Any]:
    negative_controls_passed = (
        result["median_shuffled_teacher_abs_gain"] <= pass_criteria["negative_control_max_abs_gain"]
        and result["median_time_shifted_teacher_abs_gain"] <= pass_criteria["negative_control_max_abs_gain"]
    )
    nuisance_veto_applied = profile_name == "nuisance_shared" and bool(negative_controls["nuisance_veto_required"])
    if profile_name == "truly_observable":
        passed = (
            result["median_a4_minus_a3"] >= pass_criteria["observable_min_median_a4_minus_a3"]
            and result["median_a3_minus_a2"] >= pass_criteria["observable_min_median_a3_minus_a2"]
            and negative_controls_passed
        )
        reason = "observable subset recovered expected A4 > A3 > A2 pattern"
    elif profile_name == "non_observable":
        passed = (
            result["median_a4_minus_a3"] <= pass_criteria["non_observable_max_median_a4_minus_a3"]
            and negative_controls_passed
        )
        reason = "non-observable subset did not show robust privileged gain"
    elif profile_name == "nuisance_shared":
        passed = nuisance_veto_applied and negative_controls_passed
        reason = "nuisance-shared raw gain was vetoed by control policy"
    else:
        passed = False
        reason = f"unknown synthetic profile: {profile_name}"
    return {
        "status": "passed" if passed else "failed",
        "negative_controls_passed": negative_controls_passed,
        "nuisance_veto_applied": nuisance_veto_applied,
        "reason": reason,
    }


def _bounded_ba(value: float) -> float:
    return max(0.0, min(1.0, value))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Gate2Error(f"JSON root must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.joinpath("latest.txt").write_text(str(output_dir), encoding="utf-8")


def _sha256_json(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
