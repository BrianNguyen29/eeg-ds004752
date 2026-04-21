"""Final LOSO split manifest generator for Phase 1.

This module may write the final subject-level LOSO split manifest only when
Gate 0 has a signal-ready cohort lock. If Gate 0 is still metadata-only or
otherwise blocked, it writes blocked/readiness artifacts and does not create
``final_split_manifest.json``.
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
from .smoke import _read_json, _write_json, _write_latest_pointer


class Phase1FinalSplitManifestError(RuntimeError):
    """Raised when final split manifest generation cannot be evaluated."""


@dataclass(frozen=True)
class Phase1FinalSplitManifestResult:
    output_dir: Path
    inputs_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


DEFAULT_CONFIG_PATHS = {
    "manifest": "configs/phase1/final_split_manifest.json",
    "readiness": "configs/phase1/final_split_feature_leakage.json",
    "split": "configs/split/loso_subject.yaml",
}


def run_phase1_final_split_manifest(
    *,
    prereg_bundle: str | Path,
    split_feature_leakage_run: str | Path,
    gate0_run: str | Path,
    output_root: str | Path,
    repo_root: str | Path | None = None,
    config_paths: dict[str, str | Path] | None = None,
) -> Phase1FinalSplitManifestResult:
    """Write a final LOSO split manifest or a fail-closed blocked record."""

    prereg_bundle = Path(prereg_bundle)
    split_feature_leakage_run = _resolve_run_dir(Path(split_feature_leakage_run))
    gate0_run = _resolve_run_dir(Path(gate0_run))
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    config_paths = {**DEFAULT_CONFIG_PATHS, **{key: str(value) for key, value in (config_paths or {}).items()}}

    bundle = assert_real_phase_allowed("phase1_real", prereg_bundle)
    readiness_run = _read_split_feature_leakage_run(split_feature_leakage_run)
    _validate_split_feature_leakage_boundary(readiness_run)
    gate0 = _read_gate0_run(gate0_run)

    manifest_config = load_config(repo_root / config_paths["manifest"])
    readiness_config = load_config(repo_root / config_paths["readiness"])
    split_config = load_config(repo_root / config_paths["split"])

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    gate0_validation = _validate_gate0_for_final_split(gate0, manifest_config, split_config)
    eligible_subjects = _eligible_subjects(gate0["cohort_lock"], manifest_config)
    split_manifest = None
    split_ready = not gate0_validation["blockers"]
    if split_ready:
        split_manifest = _build_final_split_manifest(
            timestamp=timestamp,
            manifest_config=manifest_config,
            readiness_config=readiness_config,
            split_config=split_config,
            eligible_subjects=eligible_subjects,
            prereg_bundle=prereg_bundle,
            bundle=bundle,
            split_feature_leakage_run=split_feature_leakage_run,
            gate0_run=gate0_run,
            gate0=gate0,
        )
        manifest_validation = _validate_split_manifest(split_manifest, manifest_config)
    else:
        manifest_validation = _blocked_validation(gate0_validation, eligible_subjects, manifest_config)

    source_links = _build_source_links(
        prereg_bundle=prereg_bundle,
        bundle=bundle,
        split_feature_leakage_run=split_feature_leakage_run,
        gate0_run=gate0_run,
        gate0=gate0,
        config_paths=config_paths,
        repo_root=repo_root,
    )
    claim_state = _build_claim_state(manifest_config, split_ready, gate0_validation["blockers"])
    blocked_record = None if split_ready else _build_blocked_record(gate0_validation, eligible_subjects, manifest_config)

    status = "phase1_final_split_manifest_recorded" if split_ready else "phase1_final_split_manifest_blocked"
    summary = {
        "status": status,
        "output_dir": str(output_dir),
        "split_manifest_ready": split_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "split_id": manifest_config.get("split_id"),
        "group_key": manifest_config.get("group_key"),
        "gate0_run": str(gate0_run),
        "gate0_manifest_status": gate0["manifest"].get("manifest_status"),
        "cohort_lock_status": gate0["cohort_lock"].get("cohort_lock_status"),
        "n_eligible_subjects": len(eligible_subjects),
        "n_folds": len(split_manifest["folds"]) if split_manifest else 0,
        "split_manifest_path": str(output_dir / "final_split_manifest.json") if split_manifest else None,
        "split_manifest_blockers": gate0_validation["blockers"],
        "claim_blockers": claim_state["blockers"],
        "scientific_limit": (
            "Final split manifest generation only. This run does not extract features, run leakage audits, "
            "train models, compute metrics, or support Phase 1 claims."
        ),
    }
    inputs = {
        "status": "phase1_final_split_manifest_inputs_locked",
        "created_utc": timestamp,
        "prereg_bundle": str(prereg_bundle),
        "prereg_bundle_status": bundle.get("status"),
        "prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "split_feature_leakage_run": str(split_feature_leakage_run),
        "gate0_run": str(gate0_run),
        "config_paths": config_paths,
        "git": _git_record(repo_root),
    }

    inputs_path = output_dir / "phase1_final_split_manifest_inputs.json"
    summary_path = output_dir / "phase1_final_split_manifest_summary.json"
    report_path = output_dir / "phase1_final_split_manifest_report.md"
    _write_json(inputs_path, inputs)
    _write_json(output_dir / "phase1_final_split_manifest_source_links.json", source_links)
    _write_json(output_dir / "phase1_final_split_manifest_validation.json", manifest_validation)
    _write_json(output_dir / "phase1_final_split_manifest_claim_state.json", claim_state)
    if split_manifest is not None:
        _write_json(output_dir / "final_split_manifest.json", split_manifest)
    if blocked_record is not None:
        _write_json(output_dir / "phase1_final_split_manifest_blocked.json", blocked_record)
    _write_json(summary_path, summary)
    report_path.write_text(
        _render_report(summary, manifest_validation, source_links, claim_state, split_manifest, blocked_record),
        encoding="utf-8",
    )
    _write_latest_pointer(output_root, output_dir)

    return Phase1FinalSplitManifestResult(
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


def _read_split_feature_leakage_run(run_dir: Path) -> dict[str, Any]:
    required = {
        "summary": "phase1_final_split_feature_leakage_plan_summary.json",
        "contract": "phase1_final_split_feature_leakage_contract.json",
        "split_readiness": "phase1_final_split_manifest_readiness.json",
        "claim_state": "phase1_final_split_feature_leakage_claim_state.json",
    }
    payload = {}
    for key, filename in required.items():
        path = run_dir / filename
        if not path.exists():
            raise Phase1FinalSplitManifestError(f"Split/feature/leakage readiness file not found: {path}")
        payload[key] = _read_json(path)
    return payload


def _validate_split_feature_leakage_boundary(readiness_run: dict[str, Any]) -> None:
    summary = readiness_run["summary"]
    claim_state = readiness_run["claim_state"]
    if summary.get("status") != "phase1_final_split_feature_leakage_plan_recorded":
        raise Phase1FinalSplitManifestError("Final split manifest requires a recorded split/feature/leakage plan")
    if summary.get("claim_ready") is not False:
        raise Phase1FinalSplitManifestError("Split/feature/leakage plan must keep claim_ready=false")
    if summary.get("smoke_artifacts_promoted") is not False:
        raise Phase1FinalSplitManifestError("Split/feature/leakage plan must not promote smoke artifacts")
    if claim_state.get("full_phase1_claim_bearing_run_allowed") is not False:
        raise Phase1FinalSplitManifestError("Split/feature/leakage plan must keep claim-bearing runs blocked")


def _read_gate0_run(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    cohort_lock_path = run_dir / "cohort_lock.json"
    if not manifest_path.exists():
        raise Phase1FinalSplitManifestError(f"Gate 0 manifest not found: {manifest_path}")
    if not cohort_lock_path.exists():
        raise Phase1FinalSplitManifestError(f"Gate 0 cohort lock not found: {cohort_lock_path}")
    return {
        "manifest": _read_json(manifest_path),
        "cohort_lock": _read_json(cohort_lock_path),
        "manifest_path": manifest_path,
        "cohort_lock_path": cohort_lock_path,
    }


def _validate_gate0_for_final_split(
    gate0: dict[str, Any],
    manifest_config: dict[str, Any],
    split_config: dict[str, Any],
) -> dict[str, Any]:
    blockers = []
    manifest = gate0["manifest"]
    cohort_lock = gate0["cohort_lock"]
    required_manifest_status = manifest_config.get("require_gate0_manifest_status")
    required_cohort_status = manifest_config.get("require_cohort_lock_status")
    gate0_blockers = list(manifest.get("gate0_blockers", []))
    eligible_subjects = _eligible_subjects(cohort_lock, manifest_config)

    if split_config.get("split_id") != manifest_config.get("split_id"):
        blockers.append("split_config_does_not_match_final_split_manifest_config")
    if split_config.get("group_key") != manifest_config.get("group_key"):
        blockers.append("split_group_key_does_not_match_final_split_manifest_config")
    if manifest.get("manifest_status") != required_manifest_status:
        blockers.append("gate0_manifest_not_signal_audit_ready")
    if cohort_lock.get("cohort_lock_status") != required_cohort_status:
        blockers.append("cohort_lock_not_signal_audit_ready")
    if manifest_config.get("require_no_gate0_blockers") and gate0_blockers:
        blockers.append("gate0_blockers_present")
    if len(eligible_subjects) < int(manifest_config.get("minimum_eligible_subjects", 2)):
        blockers.append("insufficient_primary_eligible_subjects_for_loso")

    return {
        "status": "phase1_final_split_gate0_validation_passed" if not blockers else "phase1_final_split_gate0_validation_blocked",
        "gate0_manifest_status": manifest.get("manifest_status"),
        "cohort_lock_status": cohort_lock.get("cohort_lock_status"),
        "gate0_blockers": gate0_blockers,
        "n_eligible_subjects": len(eligible_subjects),
        "eligible_subjects": eligible_subjects,
        "blockers": _unique(blockers),
    }


def _eligible_subjects(cohort_lock: dict[str, Any], manifest_config: dict[str, Any]) -> list[str]:
    require_true = manifest_config.get("require_primary_eligible_true", True)
    subjects = []
    for row in cohort_lock.get("participants", []):
        participant_id = row.get("participant_id")
        if not participant_id:
            continue
        if require_true and row.get("primary_eligible") is not True:
            continue
        subjects.append(str(participant_id))
    return sorted(subjects)


def _build_final_split_manifest(
    *,
    timestamp: str,
    manifest_config: dict[str, Any],
    readiness_config: dict[str, Any],
    split_config: dict[str, Any],
    eligible_subjects: list[str],
    prereg_bundle: Path,
    bundle: dict[str, Any],
    split_feature_leakage_run: Path,
    gate0_run: Path,
    gate0: dict[str, Any],
) -> dict[str, Any]:
    folds = []
    for index, outer_subject in enumerate(eligible_subjects, start=1):
        train_subjects = [subject for subject in eligible_subjects if subject != outer_subject]
        folds.append(
            {
                "fold_id": f"fold_{index:02d}_{outer_subject}",
                "outer_test_subject": outer_subject,
                "test_subjects": [outer_subject],
                "train_subjects": train_subjects,
                "train_subject_count": len(train_subjects),
                "test_subject_count": 1,
                "no_subject_overlap_between_train_and_test": True,
                "held_out_unit": manifest_config.get("group_key"),
                "fit_scope_rules": manifest_config.get("fit_scope_rules", {}),
            }
        )
    return {
        "status": "phase1_final_split_manifest_recorded",
        "created_utc": timestamp,
        "split_manifest_id": manifest_config.get("manifest_id"),
        "split_id": manifest_config.get("split_id"),
        "unit": manifest_config.get("group_key"),
        "leakage_policy": manifest_config.get("leakage_policy"),
        "source_prereg_bundle": str(prereg_bundle),
        "source_prereg_bundle_hash_sha256": bundle.get("prereg_bundle_hash_sha256"),
        "source_split_feature_leakage_run": str(split_feature_leakage_run),
        "source_gate0_run": str(gate0_run),
        "source_gate0_manifest": str(gate0["manifest_path"]),
        "source_cohort_lock": str(gate0["cohort_lock_path"]),
        "source_gate0_manifest_status": gate0["manifest"].get("manifest_status"),
        "source_cohort_lock_status": gate0["cohort_lock"].get("cohort_lock_status"),
        "readiness_required_schema": readiness_config.get("split_manifest_schema", {}),
        "split_config": split_config,
        "eligible_subjects": eligible_subjects,
        "n_eligible_subjects": len(eligible_subjects),
        "n_folds": len(folds),
        "folds": folds,
        "claim_ready": False,
        "standalone_claim_ready": False,
        "smoke_artifacts_promoted": False,
        "scientific_limit": (
            "This is a deterministic final split manifest only. It does not create features, leakage audits, "
            "model outputs, metrics, controls, calibration, influence or reports."
        ),
    }


def _validate_split_manifest(split_manifest: dict[str, Any], manifest_config: dict[str, Any]) -> dict[str, Any]:
    eligible = set(split_manifest["eligible_subjects"])
    outer_subjects = []
    blockers = []
    for fold in split_manifest["folds"]:
        train = set(fold["train_subjects"])
        test = set(fold["test_subjects"])
        outer = fold["outer_test_subject"]
        outer_subjects.append(outer)
        if outer not in test or len(test) != 1:
            blockers.append(f"{fold['fold_id']}:outer_test_subject_not_single_test_subject")
        if train & test:
            blockers.append(f"{fold['fold_id']}:train_test_subject_overlap")
        if train != eligible - {outer}:
            blockers.append(f"{fold['fold_id']}:train_subjects_not_all_other_eligible_subjects")
    missing_outer = sorted(eligible - set(outer_subjects))
    duplicate_outer = sorted(subject for subject in set(outer_subjects) if outer_subjects.count(subject) > 1)
    if missing_outer:
        blockers.append("eligible_subjects_missing_as_outer_test_subject")
    if duplicate_outer:
        blockers.append("outer_test_subject_repeated")

    return {
        "status": "phase1_final_split_manifest_validation_passed" if not blockers else "phase1_final_split_manifest_validation_failed",
        "split_manifest_ready": not blockers,
        "split_id": split_manifest.get("split_id"),
        "unit": split_manifest.get("unit"),
        "n_eligible_subjects": len(eligible),
        "n_folds": len(split_manifest["folds"]),
        "all_eligible_subjects_appear_once_as_outer_test": not missing_outer and not duplicate_outer,
        "no_subject_overlap_between_train_and_test": not any(
            set(fold["train_subjects"]) & set(fold["test_subjects"]) for fold in split_manifest["folds"]
        ),
        "fit_scope_rules": manifest_config.get("fit_scope_rules", {}),
        "blockers": blockers,
        "scientific_limit": "Validation covers split integrity only; it is not model evidence.",
    }


def _blocked_validation(
    gate0_validation: dict[str, Any],
    eligible_subjects: list[str],
    manifest_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_split_manifest_validation_blocked",
        "split_manifest_ready": False,
        "split_id": manifest_config.get("split_id"),
        "unit": manifest_config.get("group_key"),
        "n_eligible_subjects": len(eligible_subjects),
        "n_folds": 0,
        "all_eligible_subjects_appear_once_as_outer_test": False,
        "no_subject_overlap_between_train_and_test": None,
        "fit_scope_rules": manifest_config.get("fit_scope_rules", {}),
        "blockers": gate0_validation["blockers"],
        "scientific_limit": "No final split manifest was written because Gate 0/cohort-lock prerequisites are not met.",
    }


def _build_source_links(
    *,
    prereg_bundle: Path,
    bundle: dict[str, Any],
    split_feature_leakage_run: Path,
    gate0_run: Path,
    gate0: dict[str, Any],
    config_paths: dict[str, str | Path],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "status": "phase1_final_split_manifest_source_links_recorded",
        "locked_prereg_bundle": str(prereg_bundle),
        "locked_prereg_bundle_hash": bundle.get("prereg_bundle_hash_sha256"),
        "split_feature_leakage_run": str(split_feature_leakage_run),
        "gate0_run": str(gate0_run),
        "gate0_manifest": str(gate0["manifest_path"]),
        "gate0_manifest_sha256": _sha256(gate0["manifest_path"]),
        "cohort_lock": str(gate0["cohort_lock_path"]),
        "cohort_lock_sha256": _sha256(gate0["cohort_lock_path"]),
        "config_paths": {key: str(value) for key, value in config_paths.items()},
        "config_hashes": {
            key: _sha256(repo_root / str(value))
            for key, value in config_paths.items()
            if (repo_root / str(value)).exists()
        },
        "scientific_limit": "Source links document provenance for the split manifest only.",
    }


def _build_claim_state(
    manifest_config: dict[str, Any],
    split_ready: bool,
    split_blockers: list[str],
) -> dict[str, Any]:
    remaining = list(manifest_config.get("remaining_required_manifests_after_split", []))
    blockers = list(split_blockers)
    if split_ready:
        blockers.extend(
            [
                "final_feature_manifest_missing",
                "final_leakage_audit_missing",
                "final_comparator_outputs_not_claim_evaluable",
                "headline_claim_blocked_until_full_package_passes",
            ]
        )
    else:
        blockers.append("final_split_manifest_missing")
        blockers.append("claim_blocked_until_final_split_manifest_exists")
    return {
        "status": "phase1_final_split_manifest_claim_state_blocked",
        "split_manifest_ready": split_ready,
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "standalone_claim_ready": manifest_config.get("standalone_claim_ready", False),
        "smoke_artifacts_promoted": False,
        "remaining_required_manifests_after_split": remaining,
        "blockers": _unique(blockers),
        "not_ok_to_claim": [
            "decoder efficacy",
            "A3 distillation efficacy",
            "A4 privileged-transfer efficacy",
            "A4 superiority over A2/A2b/A2c/A2d/A3",
            "full Phase 1 neural comparator performance",
        ],
        "allowed_interpretation": (
            "A final LOSO split manifest exists and may be used as an input contract for final comparator runners."
            if split_ready
            else "Final split manifest generation is blocked until Gate 0 and cohort lock are signal-ready."
        ),
    }


def _build_blocked_record(
    gate0_validation: dict[str, Any],
    eligible_subjects: list[str],
    manifest_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "phase1_final_split_manifest_not_written",
        "reason": "Gate 0/cohort-lock prerequisites for final split generation are not met.",
        "split_id": manifest_config.get("split_id"),
        "n_candidate_eligible_subjects": len(eligible_subjects),
        "gate0_validation": gate0_validation,
        "blockers": gate0_validation["blockers"],
        "scientific_limit": "Blocked record is not a final split manifest and must not be used by final comparator runners.",
    }


def _render_report(
    summary: dict[str, Any],
    validation: dict[str, Any],
    source_links: dict[str, Any],
    claim_state: dict[str, Any],
    split_manifest: dict[str, Any] | None,
    blocked_record: dict[str, Any] | None,
) -> str:
    lines = [
        "# Phase 1 Final Split Manifest",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Split manifest ready: `{summary['split_manifest_ready']}`",
        f"- Claim ready: `{summary['claim_ready']}`",
        f"- Headline Phase 1 claim open: `{summary['headline_phase1_claim_open']}`",
        f"- Gate 0 manifest status: `{summary['gate0_manifest_status']}`",
        f"- Cohort lock status: `{summary['cohort_lock_status']}`",
        f"- Eligible subjects: `{summary['n_eligible_subjects']}`",
        f"- Folds: `{summary['n_folds']}`",
        "",
        "## Source Links",
        "",
        f"- Prereg hash: `{source_links.get('locked_prereg_bundle_hash')}`",
        f"- Gate 0 manifest SHA256: `{source_links.get('gate0_manifest_sha256')}`",
        f"- Cohort lock SHA256: `{source_links.get('cohort_lock_sha256')}`",
        "",
        "## Split Validation",
        "",
        f"- Validation status: `{validation['status']}`",
        f"- All eligible subjects appear once as outer test: `{validation['all_eligible_subjects_appear_once_as_outer_test']}`",
        f"- No train/test subject overlap: `{validation['no_subject_overlap_between_train_and_test']}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in claim_state["blockers"]:
        lines.append(f"- `{blocker}`")
    lines.extend(["", "## Output Boundary", ""])
    if split_manifest is not None:
        lines.append("- `final_split_manifest.json` was written from a signal-ready Gate 0 cohort lock.")
    if blocked_record is not None:
        lines.append("- `final_split_manifest.json` was not written because prerequisites are blocked.")
    lines.append("- This run does not extract final features, run leakage audits, train models, compute metrics or open claims.")
    lines.append("- Smoke artifacts remain non-claim diagnostics and cannot satisfy final evidence requirements.")
    lines.extend(["", "## Not OK To Claim", ""])
    for item in claim_state["not_ok_to_claim"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


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
