"""Phase 0.5 observability-only workflow.

This workflow starts the first preregistered real-data phase, but remains
pre-decoder: it validates the locked prereg bundle, assembles teacher/control
registries, and creates an atlas draft from Gate 0 signal audit metadata.
It does not train a Phase 1 decoder and does not estimate real Q2 metrics.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import load_config
from ..guards import assert_real_phase_allowed


class Phase05Error(RuntimeError):
    """Raised when Phase 0.5 observability-only workflow cannot proceed."""


@dataclass(frozen=True)
class Phase05Result:
    output_dir: Path
    inputs_path: Path
    teacher_plan_path: Path
    teacher_qc_registry_path: Path
    controls_plan_path: Path
    atlas_path: Path
    report_path: Path
    summary_path: Path
    summary: dict[str, Any]


def run_phase05_observability(
    prereg_bundle: str | Path,
    config: dict[str, Any],
    output_root: str | Path,
    repo_root: str | Path | None = None,
) -> Phase05Result:
    prereg_bundle = Path(prereg_bundle)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    bundle = assert_real_phase_allowed("phase05_real", prereg_bundle)

    source_runs = bundle.get("source_runs", {})
    gate0_run = Path(source_runs.get("gate0", ""))
    gate1_run = Path(source_runs.get("gate1", ""))
    gate2_run = Path(source_runs.get("gate2", ""))
    _validate_source_runs(gate0_run, gate1_run, gate2_run)
    _validate_bundle_hashes(bundle)

    manifest = _read_json(gate0_run / "manifest.json")
    cohort_lock = _read_json(gate0_run / "cohort_lock.json")
    n_eff = _read_json(gate1_run / "n_eff_statement.json")
    threshold_registry = _read_json(gate2_run / "gate_threshold_registry.json")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    inputs = build_phase05_inputs(
        timestamp,
        prereg_bundle,
        bundle,
        gate0_run,
        gate1_run,
        gate2_run,
        manifest,
        cohort_lock,
        n_eff,
        threshold_registry,
        config,
        repo_root,
    )
    teacher_plan = build_teacher_observability_plan(bundle, config, repo_root)
    teacher_qc_registry = build_teacher_qc_registry(cohort_lock, manifest, teacher_plan)
    controls_plan = build_controls_plan(bundle, config, threshold_registry)
    atlas = build_observability_atlas_draft(manifest, cohort_lock, teacher_plan)
    summary = build_phase05_summary(output_dir, inputs, teacher_plan, teacher_qc_registry, controls_plan, atlas)

    inputs_path = output_dir / "phase05_inputs.json"
    teacher_plan_path = output_dir / "teacher_observability_plan.json"
    teacher_qc_registry_path = output_dir / "teacher_qc_registry.json"
    controls_plan_path = output_dir / "controls_plan.json"
    atlas_path = output_dir / "observability_atlas_draft.json"
    report_path = output_dir / "phase05_report.md"
    summary_path = output_dir / "phase05_summary.json"

    _write_json(inputs_path, inputs)
    _write_json(teacher_plan_path, teacher_plan)
    _write_json(teacher_qc_registry_path, teacher_qc_registry)
    _write_json(controls_plan_path, controls_plan)
    _write_json(atlas_path, atlas)
    report_path.write_text(render_phase05_report(summary, teacher_plan, teacher_qc_registry, controls_plan), encoding="utf-8")
    _write_json(summary_path, summary)
    _write_latest_pointer(output_root, output_dir)

    return Phase05Result(
        output_dir=output_dir,
        inputs_path=inputs_path,
        teacher_plan_path=teacher_plan_path,
        teacher_qc_registry_path=teacher_qc_registry_path,
        controls_plan_path=controls_plan_path,
        atlas_path=atlas_path,
        report_path=report_path,
        summary_path=summary_path,
        summary=summary,
    )


def build_phase05_inputs(
    timestamp: str,
    prereg_bundle_path: Path,
    bundle: dict[str, Any],
    gate0_run: Path,
    gate1_run: Path,
    gate2_run: Path,
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    n_eff: dict[str, Any],
    threshold_registry: dict[str, Any],
    config: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase05_inputs_locked",
        "created_utc": timestamp,
        "phase_id": "phase05_real",
        "workflow": config["workflow"],
        "prereg_bundle_path": str(prereg_bundle_path),
        "prereg_bundle_hash_sha256": bundle["prereg_bundle_hash_sha256"],
        "source_runs": {
            "gate0": str(gate0_run),
            "gate1": str(gate1_run),
            "gate2": str(gate2_run),
        },
        "repo": _git_identity(repo_root),
        "n_eff": {
            "n_primary_eligible": n_eff["n_primary_eligible"],
            "primary_denominator": n_eff["primary_denominator"],
            "sessions_total": manifest["subjects"]["n_sessions"],
        },
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "threshold_registry_hash_sha256": threshold_registry["threshold_registry_hash_sha256"],
        "real_data_scope": "observability_only_predecoder",
        "does_not_train_decoder": True,
        "does_not_estimate_model_efficacy": True,
        "scientific_scope": config["scientific_scope"],
    }


def build_teacher_observability_plan(
    bundle: dict[str, Any],
    config: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    registries = bundle["artifact_hashes"]["registries_and_specs"]
    teacher_registry_path = Path(registries["teacher_registry"]["path"])
    teacher_registry = load_config(teacher_registry_path)
    enabled_groups = config["enabled_teacher_groups"]
    candidates = []
    for group_id, phase_status in teacher_registry.get("teacher_groups", {}).items():
        candidates.append(
            {
                "teacher_group": group_id,
                "registry_status": phase_status,
                "phase05_status": "enabled_for_observability_audit"
                if group_id in enabled_groups
                else "deferred_not_enabled_in_phase05",
                "metrics_to_compute_in_full_engine": [
                    "Q2_task",
                    "Q2_base",
                    "delta_Q2_obs",
                    "grouped_permutation_p",
                    "pass_spatial",
                    "pass_nuisance",
                    "pass_ica_ratio",
                ],
                "current_workflow_metric_status": "not_computed_by_registry_preflight",
            }
        )
    return {
        "status": "teacher_observability_plan_ready",
        "teacher_registry_path": str(teacher_registry_path),
        "teacher_registry_sha256": _sha256_file(teacher_registry_path),
        "enabled_teacher_groups": enabled_groups,
        "deferred_teacher_groups": config["deferred_teacher_groups"],
        "candidate_teacher_groups": candidates,
        "interpretation": (
            "This is the preregistered teacher/control plan. It does not compute real Q2 metrics until "
            "feature extraction and observability estimators are implemented under this bundle."
        ),
    }


def build_teacher_qc_registry(
    cohort_lock: dict[str, Any],
    manifest: dict[str, Any],
    teacher_plan: dict[str, Any],
) -> dict[str, Any]:
    fallback_sessions = cohort_lock.get("fallback_reader_registry", [])
    session_results = manifest.get("signal_audit", {}).get("session_results", [])
    passed_sessions = [item for item in session_results if item.get("status") == "ok"]
    return {
        "status": "teacher_qc_registry_preflight_ready",
        "participants_total": len(cohort_lock.get("participants", [])),
        "sessions_signal_passed": len(passed_sessions),
        "fallback_reader_sessions": fallback_sessions,
        "enabled_teacher_groups": teacher_plan["enabled_teacher_groups"],
        "qc_dimensions": [
            "support_m_e",
            "reliability_q_e",
            "observability_o_e",
            "admissibility_a_e",
            "viability_state",
        ],
        "metric_status": "not_computed_by_registry_preflight",
        "requires_next_engine": "feature_extraction_and_task_contrast_observability_estimation",
        "scientific_limit": "No teacher element is marked observable by this preflight registry.",
    }


def build_controls_plan(
    bundle: dict[str, Any],
    config: dict[str, Any],
    threshold_registry: dict[str, Any],
) -> dict[str, Any]:
    registries = bundle["artifact_hashes"]["registries_and_specs"]
    control_suite_path = Path(registries["control_suite"]["path"])
    nuisance_block_path = Path(registries["nuisance_block"]["path"])
    return {
        "status": "controls_plan_ready",
        "required_controls": config["required_controls"],
        "control_suite_path": str(control_suite_path),
        "control_suite_sha256": _sha256_file(control_suite_path),
        "nuisance_block_path": str(nuisance_block_path),
        "nuisance_block_sha256": _sha256_file(nuisance_block_path),
        "thresholds": threshold_registry["thresholds"],
        "pass_fail_policy": {
            "teacher_observable_requires_task_contrast": True,
            "spatial_control_required": True,
            "nuisance_control_required": True,
            "negative_controls_required_before_claim": True,
        },
    }


def build_observability_atlas_draft(
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    teacher_plan: dict[str, Any],
) -> dict[str, Any]:
    by_subject: dict[str, Any] = {}
    for session in manifest.get("signal_audit", {}).get("session_results", []):
        if session.get("status") != "ok":
            continue
        subject = session["subject"]
        record = by_subject.setdefault(
            subject,
            {
                "sessions": 0,
                "eeg_profiles": set(),
                "ieeg_profiles": set(),
            },
        )
        record["sessions"] += 1
        record["eeg_profiles"].add(_profile_label(session.get("eeg", {})))
        record["ieeg_profiles"].add(_profile_label(session.get("ieeg", {})))
    atlas_subjects = []
    participant_by_id = {item["participant_id"]: item for item in cohort_lock.get("participants", [])}
    for subject, record in sorted(by_subject.items()):
        participant = participant_by_id.get(subject, {})
        atlas_subjects.append(
            {
                "subject": subject,
                "primary_eligible": participant.get("primary_eligible"),
                "sessions": record["sessions"],
                "eeg_profiles": sorted(record["eeg_profiles"]),
                "ieeg_profiles": sorted(record["ieeg_profiles"]),
                "enabled_teacher_groups": teacher_plan["enabled_teacher_groups"],
                "observability_metric_status": "not_computed_by_registry_preflight",
            }
        )
    return {
        "status": "observability_atlas_draft_preflight",
        "subject_count": len(atlas_subjects),
        "subjects": atlas_subjects,
        "scientific_limit": (
            "This atlas draft summarizes Gate 0 modality/sampling readiness only. It does not contain "
            "task-contrast observability estimates."
        ),
    }


def build_phase05_summary(
    output_dir: Path,
    inputs: dict[str, Any],
    teacher_plan: dict[str, Any],
    teacher_qc_registry: dict[str, Any],
    controls_plan: dict[str, Any],
    atlas: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase05_observability_preflight_ready",
        "run_dir": str(output_dir),
        "phase_id": "phase05_real",
        "workflow": inputs["workflow"],
        "prereg_bundle_path": inputs["prereg_bundle_path"],
        "prereg_bundle_hash_sha256": inputs["prereg_bundle_hash_sha256"],
        "n_primary_eligible": inputs["n_eff"]["n_primary_eligible"],
        "sessions_total": inputs["n_eff"]["sessions_total"],
        "enabled_teacher_groups": teacher_plan["enabled_teacher_groups"],
        "required_controls": controls_plan["required_controls"],
        "atlas_subject_count": atlas["subject_count"],
        "teacher_metric_status": teacher_qc_registry["metric_status"],
        "does_not_train_decoder": True,
        "does_not_estimate_model_efficacy": True,
        "next_step": "implement_feature_extraction_and_task_contrast_observability_estimators",
        "real_data_phase_authorized_for_decoder": False,
        "scientific_integrity_limits": [
            "This is Phase 0.5 observability-only predecoder workflow.",
            "No Q2_task, permutation p-values, or teacher survival outcomes are computed yet.",
            "No privileged-transfer efficacy claim is allowed from this preflight output.",
        ],
    }


def render_phase05_report(
    summary: dict[str, Any],
    teacher_plan: dict[str, Any],
    teacher_qc_registry: dict[str, Any],
    controls_plan: dict[str, Any],
) -> str:
    lines = [
        "# Phase 0.5 Observability-Only Report",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Prereg bundle hash: `{summary['prereg_bundle_hash_sha256']}`",
        f"- N primary eligible: {summary['n_primary_eligible']}",
        f"- Sessions total: {summary['sessions_total']}",
        f"- Decoder training: `{not summary['does_not_train_decoder']}`",
        "",
        "## Teacher Plan",
        "",
        f"- Enabled teacher groups: {teacher_plan['enabled_teacher_groups']}",
        f"- Deferred teacher groups: {teacher_plan['deferred_teacher_groups']}",
        f"- Metric status: `{teacher_qc_registry['metric_status']}`",
        "",
        "## Controls",
        "",
        f"- Required controls: {controls_plan['required_controls']}",
        "",
        "## Scientific Integrity",
        "",
        "- This output is a predecoder observability registry/preflight.",
        "- It does not compute task-contrast Q2 or train a decoder.",
        "- It does not prove real EEG privileged transfer.",
        "",
    ]
    return "\n".join(lines)


def _validate_source_runs(gate0_run: Path, gate1_run: Path, gate2_run: Path) -> None:
    for path in [gate0_run, gate1_run, gate2_run]:
        if not path.exists():
            raise FileNotFoundError(f"Required source run not found: {path}")


def _validate_bundle_hashes(bundle: dict[str, Any]) -> None:
    for group_name, group in bundle.get("artifact_hashes", {}).items():
        if group_name == "threshold_registry":
            _validate_hash_entry(group)
            continue
        if not isinstance(group, dict):
            raise Phase05Error(f"Invalid artifact hash group: {group_name}")
        for item in group.values():
            _validate_hash_entry(item)


def _validate_hash_entry(item: dict[str, Any]) -> None:
    path = Path(item["path"])
    expected = item["sha256"]
    actual = _sha256_file(path)
    if actual != expected:
        raise Phase05Error(f"Hash mismatch for {path}: expected {expected}, got {actual}")


def _profile_label(info: dict[str, Any]) -> str:
    return f"{info.get('n_channels')}ch@{info.get('sfreq')}Hz:{info.get('reader')}"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Phase05Error(f"JSON root must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.joinpath("latest.txt").write_text(str(output_dir), encoding="utf-8")


def _sha256_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found for hashing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_identity(repo_root: Path) -> dict[str, Any]:
    commit = _safe_command(["git", "rev-parse", "HEAD"], repo_root)
    branch = _safe_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    status = _safe_command(["git", "status", "--short"], repo_root)
    return {
        "path": str(repo_root),
        "branch": branch,
        "commit": commit,
        "working_tree_clean": status == "",
        "git_status_short": status,
    }


def _safe_command(command: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(command, cwd=cwd, text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"
