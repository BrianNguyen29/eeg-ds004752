"""Phase 1 decoder smoke contract runner.

This module intentionally does not train a decoder. It verifies the locked
Phase 1 inputs, constructs 1-2 subject-level outer folds, checks data and
comparator contract availability, and writes the artifact family expected by
the Phase 1 smoke notebook.

Real decoder performance, calibration, permutation tests, and privileged
transfer efficacy remain uncomputed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..guards import assert_real_phase_allowed


class Phase1SmokeError(RuntimeError):
    """Raised when Phase 1 smoke contract cannot be created."""


@dataclass(frozen=True)
class Phase1SmokeResult:
    output_dir: Path
    inputs_path: Path
    comparator_table_path: Path
    calibration_report_path: Path
    negative_controls_report_path: Path
    influence_report_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


EXPECTED_COMPARATORS = [
    "A2",
    "A2b",
    "A2c",
    "A2d_riemannian",
    "A3_distillation",
    "A4_privileged",
]


def run_phase1_smoke(
    *,
    prereg_bundle: str | Path,
    readiness_run: str | Path,
    dataset_root: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    max_outer_folds: int = 2,
    outer_test_subjects: list[str] | None = None,
) -> Phase1SmokeResult:
    """Run a non-claim Phase 1 smoke contract check."""

    prereg_bundle = Path(prereg_bundle)
    readiness_run = Path(readiness_run)
    dataset_root = Path(dataset_root)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    readiness_path = _readiness_path(readiness_run)
    readiness = _read_json(readiness_path)
    _validate_readiness(readiness, bundle)

    source = readiness.get("source_of_truth", {})
    gate0_run = Path(source.get("gate0") or bundle.get("source_runs", {}).get("gate0", ""))
    if not gate0_run.exists():
        raise Phase1SmokeError(f"Gate 0 source not found: {gate0_run}")
    if not dataset_root.exists():
        raise FileNotFoundError(f"Dataset root not found: {dataset_root}")

    manifest = _read_json(gate0_run / "manifest.json")
    cohort_lock = _read_json(gate0_run / "cohort_lock.json")
    eligible_subjects = _eligible_subjects(cohort_lock)
    if len(eligible_subjects) < 2:
        raise Phase1SmokeError(f"At least two eligible subjects required for smoke folds; got {eligible_subjects}")

    selected_subjects = _select_outer_subjects(
        eligible_subjects=eligible_subjects,
        requested=outer_test_subjects or [],
        max_outer_folds=max_outer_folds,
    )
    sessions = _session_inventory(manifest, eligible_subjects)
    if not sessions:
        raise Phase1SmokeError("No signal-audit OK sessions found for eligible subjects")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root
    output_dir.mkdir(parents=True, exist_ok=True)
    # If output_root is an empty phase root rather than a run dir, create a timestamped run.
    if output_dir.name != timestamp and not any(output_dir.iterdir()):
        output_dir = output_dir / timestamp
        output_dir.mkdir(parents=True, exist_ok=False)

    fold_dir = output_dir / "fold_logs"
    fold_dir.mkdir(parents=True, exist_ok=True)

    comparator_table = _build_comparator_table(bundle, readiness)
    fold_logs = [
        _build_fold_log(
            fold_index=index,
            outer_subject=subject,
            eligible_subjects=eligible_subjects,
            sessions=sessions,
            dataset_root=dataset_root,
            comparator_table=comparator_table,
        )
        for index, subject in enumerate(selected_subjects, start=1)
    ]

    inputs = _build_inputs(
        timestamp=timestamp,
        prereg_bundle=prereg_bundle,
        readiness_run=readiness_run,
        readiness_path=readiness_path,
        dataset_root=dataset_root,
        output_dir=output_dir,
        selected_subjects=selected_subjects,
        bundle=bundle,
        readiness=readiness,
        repo_root=repo_root,
    )
    calibration_report = _placeholder_report(
        status="calibration_not_computed_contract_smoke",
        reason="Phase 1 smoke contract does not train models or produce logits.",
        expected_future_artifacts=["temperature_scaling", "ECE", "Brier", "NLL", "reliability_table"],
    )
    negative_controls_report = _placeholder_report(
        status="negative_controls_not_executed_contract_smoke",
        reason="Phase 1 smoke contract does not run shuffled/time-shifted teacher model fits.",
        expected_future_artifacts=["shuffled_teacher", "time_shifted_teacher", "nuisance_shared_control"],
    )
    influence_report = _placeholder_report(
        status="influence_not_computed_contract_smoke",
        reason="Influence requires fold-level performance deltas from a real Phase 1 run.",
        expected_future_artifacts=[
            "max_single_subject_absolute_contribution_share",
            "leave_one_subject_out_claim_state_change",
        ],
    )
    summary = _build_summary(
        output_dir=output_dir,
        inputs=inputs,
        fold_logs=fold_logs,
        comparator_table=comparator_table,
        calibration_report=calibration_report,
        negative_controls_report=negative_controls_report,
        influence_report=influence_report,
    )

    inputs_path = output_dir / "phase1_smoke_inputs.json"
    comparator_table_path = output_dir / "comparator_completeness_table.json"
    calibration_report_path = output_dir / "calibration_smoke_report.json"
    negative_controls_report_path = output_dir / "negative_controls_smoke_report.json"
    influence_report_path = output_dir / "influence_smoke_report.json"
    summary_path = output_dir / "phase1_smoke_summary.json"
    report_path = output_dir / "phase1_smoke_report.md"

    _write_json(inputs_path, inputs)
    for fold in fold_logs:
        _write_json(fold_dir / f"{fold['fold_id']}.json", fold)
    _write_json(comparator_table_path, comparator_table)
    _write_json(calibration_report_path, calibration_report)
    _write_json(negative_controls_report_path, negative_controls_report)
    _write_json(influence_report_path, influence_report)
    _write_json(summary_path, summary)
    report_path.write_text(_render_report(summary, comparator_table), encoding="utf-8")
    _write_latest_pointer(output_root, output_dir)

    return Phase1SmokeResult(
        output_dir=output_dir,
        inputs_path=inputs_path,
        comparator_table_path=comparator_table_path,
        calibration_report_path=calibration_report_path,
        negative_controls_report_path=negative_controls_report_path,
        influence_report_path=influence_report_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _readiness_path(readiness_run: Path) -> Path:
    if readiness_run.is_file():
        return readiness_run
    for name in ["phase1_input_freeze_revision.json", "phase1_input_freeze.json"]:
        path = readiness_run / name
        if path.exists():
            return path
    raise FileNotFoundError(f"No Phase 1 readiness JSON found under {readiness_run}")


def _validate_readiness(readiness: dict[str, Any], bundle: dict[str, Any]) -> None:
    status = readiness.get("status")
    allowed_statuses = {
        "phase1_input_freeze_revised_comparator_complete",
        "phase1_input_freeze_ready_for_decoder_smoke_and_full_comparator_run",
        "phase1_input_freeze_recorded_with_blockers_or_warnings",
    }
    if status not in allowed_statuses:
        raise Phase1SmokeError(f"Unsupported Phase 1 readiness status: {status}")
    authorization = readiness.get("authorization", {})
    if authorization.get("decoder_smoke_allowed_under_guard") is not True:
        raise Phase1SmokeError("Phase 1 readiness does not allow decoder smoke")
    expected_hash = bundle.get("prereg_bundle_hash_sha256")
    readiness_hash = readiness.get("source_of_truth", {}).get("base_prereg_bundle_hash_sha256") or readiness.get(
        "source_of_truth", {}
    ).get("prereg_bundle_hash_sha256")
    if expected_hash and readiness_hash and expected_hash != readiness_hash:
        raise Phase1SmokeError("Readiness prereg hash does not match locked bundle hash")


def _eligible_subjects(cohort_lock: dict[str, Any]) -> list[str]:
    subjects = []
    for item in cohort_lock.get("participants", []):
        subject = item.get("participant_id") or item.get("subject") or item.get("subject_id")
        if subject and item.get("primary_eligible") is True:
            subjects.append(subject)
    return sorted(set(subjects))


def _select_outer_subjects(
    *,
    eligible_subjects: list[str],
    requested: list[str],
    max_outer_folds: int,
) -> list[str]:
    if max_outer_folds < 1:
        raise Phase1SmokeError("max_outer_folds must be >= 1")
    requested = [item for item in requested if item]
    if requested:
        missing = sorted(set(requested) - set(eligible_subjects))
        if missing:
            raise Phase1SmokeError(f"Requested outer-test subjects are not eligible: {missing}")
        selected = sorted(dict.fromkeys(requested))
    else:
        selected = eligible_subjects
    return selected[:max_outer_folds]


def _session_inventory(manifest: dict[str, Any], eligible_subjects: list[str]) -> list[dict[str, str]]:
    eligible = set(eligible_subjects)
    sessions = []
    for item in manifest.get("signal_audit", {}).get("session_results", []):
        subject = item.get("subject")
        session = item.get("session")
        if item.get("status") == "ok" and subject in eligible and session:
            sessions.append({"subject": subject, "session": session})
    return sorted(sessions, key=lambda row: (row["subject"], row["session"]))


def _build_comparator_table(bundle: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    bundle_comparators = set((bundle.get("comparator_cards") or {}).keys())
    revised = readiness.get("revised_comparator_readiness", {})
    revision_comparators = set(revised.get("revision_available_comparator_ids", []))
    available_after_revision = set(revised.get("available_comparator_ids_after_revision", []))
    rows = []
    warnings = []
    for comparator_id in EXPECTED_COMPARATORS:
        if comparator_id in available_after_revision or comparator_id in bundle_comparators:
            status = "present_hash_linked_contract_only"
            source = "locked_bundle_or_revision"
        elif comparator_id == "A2" and "EEGNet" in bundle_comparators:
            status = "warning_backbone_available_but_a2_card_not_explicit"
            source = "EEGNet_backbone_card"
            warnings.append("A2 explicit comparator card is not present; EEGNet backbone card is available.")
        elif comparator_id in revision_comparators:
            status = "present_hash_linked_revision_contract_only"
            source = "phase1_comparator_revision"
        else:
            status = "missing_required_for_future_full_phase1"
            source = "missing"
            warnings.append(f"{comparator_id} is missing from locked comparator sources.")
        rows.append(
            {
                "comparator_id": comparator_id,
                "status": status,
                "source": source,
                "trained_in_smoke": False,
                "metrics_computed": False,
            }
        )
    blocking = [row["comparator_id"] for row in rows if row["status"] == "missing_required_for_future_full_phase1"]
    return {
        "status": "phase1_smoke_comparator_contract_complete" if not blocking else "phase1_smoke_comparator_contract_incomplete",
        "rows": rows,
        "blocking_missing_comparators": blocking,
        "warnings": warnings,
        "scientific_limit": "Comparator presence is a contract check only; no comparator was trained in this smoke.",
    }


def _build_fold_log(
    *,
    fold_index: int,
    outer_subject: str,
    eligible_subjects: list[str],
    sessions: list[dict[str, str]],
    dataset_root: Path,
    comparator_table: dict[str, Any],
) -> dict[str, Any]:
    train_subjects = [subject for subject in eligible_subjects if subject != outer_subject]
    train_sessions = [row for row in sessions if row["subject"] in set(train_subjects)]
    test_sessions = [row for row in sessions if row["subject"] == outer_subject]
    data_checks = [_session_data_check(dataset_root, row) for row in test_sessions]
    missing_payloads = [item for item in data_checks if not item["eeg_edf_exists"] or not item["ieeg_edf_exists"]]
    return {
        "status": "phase1_fold_contract_smoke_complete" if not missing_payloads else "phase1_fold_contract_missing_payloads",
        "fold_id": f"outer_fold_{fold_index:02d}_{outer_subject}",
        "outer_test_subject": outer_subject,
        "train_subject_count": len(train_subjects),
        "train_subjects": train_subjects,
        "outer_test_sessions": test_sessions,
        "outer_train_session_count": len(train_sessions),
        "outer_test_session_count": len(test_sessions),
        "leakage_checks": {
            "outer_test_subject_not_in_train_subjects": outer_subject not in set(train_subjects),
            "learned_transforms_fit": "not_fit_in_contract_smoke",
            "outer_test_adaptation": "not_performed",
        },
        "data_checks": data_checks,
        "missing_payloads": missing_payloads,
        "comparators": {
            row["comparator_id"]: {
                "status": row["status"],
                "trained": False,
                "metrics_computed": False,
            }
            for row in comparator_table["rows"]
        },
        "decoder_trained": False,
        "metrics_status": "not_computed_contract_smoke",
        "claim_ready": False,
    }


def _session_data_check(dataset_root: Path, row: dict[str, str]) -> dict[str, Any]:
    subject = row["subject"]
    session = row["session"]
    stem = f"{subject}_{session}_task-verbalWM_run-01"
    eeg = dataset_root / subject / session / "eeg" / f"{stem}_eeg.edf"
    ieeg = dataset_root / subject / session / "ieeg" / f"{stem}_ieeg.edf"
    events = dataset_root / subject / session / "eeg" / f"{stem}_events.tsv"
    return {
        "subject": subject,
        "session": session,
        "eeg_edf": str(eeg),
        "ieeg_edf": str(ieeg),
        "events_tsv": str(events),
        "eeg_edf_exists": eeg.exists(),
        "ieeg_edf_exists": ieeg.exists(),
        "events_tsv_exists": events.exists(),
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
    bundle: dict[str, Any],
    readiness: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase1_smoke_inputs_locked",
        "created_utc": timestamp,
        "scope": "smoke_non_claim_contract_only",
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "readiness_run": str(readiness_run),
        "readiness_path": str(readiness_path),
        "readiness_status": readiness.get("status"),
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "outer_test_subjects": selected_subjects,
        "repo": _repo_state(repo_root),
        "does_not_train_decoder": True,
        "does_not_compute_model_metrics": True,
    }


def _placeholder_report(*, status: str, reason: str, expected_future_artifacts: list[str]) -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "expected_future_artifacts": expected_future_artifacts,
        "computed_in_smoke": False,
        "claim_ready": False,
    }


def _build_summary(
    *,
    output_dir: Path,
    inputs: dict[str, Any],
    fold_logs: list[dict[str, Any]],
    comparator_table: dict[str, Any],
    calibration_report: dict[str, Any],
    negative_controls_report: dict[str, Any],
    influence_report: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    if comparator_table["blocking_missing_comparators"]:
        blockers.append("comparator_contract_missing")
    if any(fold["status"] != "phase1_fold_contract_smoke_complete" for fold in fold_logs):
        blockers.append("fold_contract_data_availability_issue")
    return {
        "status": "phase1_decoder_smoke_contract_complete" if not blockers else "phase1_decoder_smoke_contract_with_blockers",
        "output_dir": str(output_dir),
        "scope": inputs["scope"],
        "n_outer_folds": len(fold_logs),
        "outer_test_subjects": inputs["outer_test_subjects"],
        "comparator_contract_status": comparator_table["status"],
        "calibration_status": calibration_report["status"],
        "negative_controls_status": negative_controls_report["status"],
        "influence_status": influence_report["status"],
        "blockers": blockers,
        "warnings": comparator_table["warnings"],
        "decoder_trained": False,
        "model_metrics_computed": False,
        "claim_ready": False,
        "does_not_estimate_privileged_transfer_efficacy": True,
        "next_step": "implement_real_phase1_training_engine_after_contract_smoke_review",
    }


def _render_report(summary: dict[str, Any], comparator_table: dict[str, Any]) -> str:
    lines = [
        "# Phase 1 Decoder Smoke Contract Report",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Scope: `{summary['scope']}`",
        f"- Outer folds: {summary['n_outer_folds']}",
        f"- Comparator contract status: `{summary['comparator_contract_status']}`",
        f"- Blockers: `{summary['blockers']}`",
        f"- Decoder trained: `{summary['decoder_trained']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        "",
        "## Comparators",
        "",
    ]
    for row in comparator_table["rows"]:
        lines.append(f"- {row['comparator_id']}: `{row['status']}`")
    lines.extend(
        [
            "",
            "## Scientific Integrity",
            "",
            "- This is a contract smoke run only.",
            "- No decoder was trained.",
            "- No BA/ECE/p-value/influence metric was computed.",
            "- No privileged-transfer efficacy claim is allowed from this output.",
            "",
        ]
    )
    return "\n".join(lines)


def _repo_state(repo_root: Path) -> dict[str, Any]:
    return {
        "path": str(repo_root),
        "commit": _git_output(repo_root, ["git", "rev-parse", "HEAD"]),
        "branch": _git_output(repo_root, ["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "working_tree_clean": _git_output(repo_root, ["git", "status", "--short"]) == "",
    }


def _git_output(repo_root: Path, args: list[str]) -> str:
    try:
        return subprocess.check_output(args, cwd=repo_root, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unavailable"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Phase1SmokeError(f"JSON root must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.joinpath("latest.txt").write_text(str(output_dir), encoding="utf-8")

