"""V5.6 Tranche 2.1 split-lock and feature-provenance runner.

This module records auditable registry/provenance state after the Tranche 2
scaffold artifacts pass review. It does not extract features, train models, run
comparators, compute statistics, or open efficacy claims.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..phase1.smoke import _write_json, _write_latest_pointer
from .benchmark import assert_signal_ready_gate0, load_benchmark_spec
from .splits import assert_scalp_only_test_time, load_split_policy


class V56Tranche2LockError(RuntimeError):
    """Raised when V5.6 Tranche 2.1 cannot write locked artifacts."""


@dataclass(frozen=True)
class V56Tranche2LockResult:
    gate0_run: Path
    split_registry_lock_dir: Path
    feature_provenance_dir: Path
    summary: dict[str, Any]


def run_v56_tranche2_lock(
    *,
    gate0_run: str | Path,
    split_registry_run: str | Path,
    feature_provenance_run: str | Path,
    benchmark_spec: str | Path = "configs/v56/benchmark_spec.json",
    splits: str | Path = "configs/v56/splits.json",
    output_root: str | Path = "artifacts",
    repo_root: str | Path | None = None,
) -> V56Tranche2LockResult:
    """Lock the subject-level split registry and populate source provenance."""

    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    gate0_path = _resolve_path(Path(gate0_run), must_be_dir=True)
    split_scaffold_path = _resolve_path(Path(split_registry_run), must_be_dir=True)
    provenance_scaffold_path = _resolve_path(Path(feature_provenance_run), must_be_dir=True)
    output = Path(output_root)

    benchmark = load_benchmark_spec(benchmark_spec)
    split_policy = load_split_policy(splits)
    assert_scalp_only_test_time(split_policy)

    manifest = _read_json(gate0_path / "manifest.json")
    cohort_lock = _read_json(gate0_path / "cohort_lock.json")
    assert_signal_ready_gate0(manifest, cohort_lock, benchmark)

    split_scaffold = _read_json(split_scaffold_path / "v56_split_registry.json")
    provenance_scaffold = _read_json(provenance_scaffold_path / "v56_feature_provenance.json")
    _validate_scaffold_artifacts(split_scaffold, provenance_scaffold)

    eligible_subjects = _eligible_subjects(cohort_lock)
    if len(eligible_subjects) < 2:
        raise V56Tranche2LockError(
            f"At least two primary-eligible subjects are required to lock subject-level splits; got {eligible_subjects}."
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    split_lock_dir = output / "v56_split_registry_lock" / timestamp
    feature_dir = output / "v56_feature_provenance_populated" / timestamp
    split_lock_dir.mkdir(parents=True, exist_ok=False)
    feature_dir.mkdir(parents=True, exist_ok=False)

    split_lock = _build_split_registry_lock(
        timestamp=timestamp,
        benchmark=benchmark,
        split_policy=split_policy,
        manifest=manifest,
        cohort_lock=cohort_lock,
        eligible_subjects=eligible_subjects,
        gate0_run=gate0_path,
        split_scaffold_run=split_scaffold_path,
        repo_root=repo,
    )
    split_summary = _summary(
        artifact_family="v56_split_registry_lock",
        status=split_lock["status"],
        timestamp=timestamp,
        output_dir=split_lock_dir,
        benchmark=benchmark,
        manifest=manifest,
        cohort_lock=cohort_lock,
        artifact=split_lock,
        repo_root=repo,
        next_step="review locked subject-level splits before feature extraction or comparator execution",
    )

    _write_json(split_lock_dir / "v56_split_registry_lock.json", split_lock)
    _write_json(split_lock_dir / "v56_split_registry_lock_summary.json", split_summary)
    (split_lock_dir / "v56_split_registry_lock_report.md").write_text(
        _render_report("V5.6 Split Registry Lock", split_summary, split_lock),
        encoding="utf-8",
    )
    _write_latest_pointer(output / "v56_split_registry_lock", split_lock_dir)

    feature_provenance = _build_feature_provenance(
        timestamp=timestamp,
        benchmark=benchmark,
        split_policy=split_policy,
        manifest=manifest,
        cohort_lock=cohort_lock,
        gate0_run=gate0_path,
        split_lock_dir=split_lock_dir,
        split_scaffold_run=split_scaffold_path,
        provenance_scaffold_run=provenance_scaffold_path,
        benchmark_spec=Path(benchmark_spec),
        splits=Path(splits),
        repo_root=repo,
    )
    feature_summary = _summary(
        artifact_family="v56_feature_provenance_populated",
        status=feature_provenance["status"],
        timestamp=timestamp,
        output_dir=feature_dir,
        benchmark=benchmark,
        manifest=manifest,
        cohort_lock=cohort_lock,
        artifact=feature_provenance,
        repo_root=repo,
        next_step="review provenance hashes and split-lock links before any feature matrix materialization",
    )

    _write_json(feature_dir / "v56_feature_provenance_populated.json", feature_provenance)
    _write_json(feature_dir / "v56_feature_provenance_populated_summary.json", feature_summary)
    (feature_dir / "v56_feature_provenance_populated_report.md").write_text(
        _render_report("V5.6 Feature Provenance Population", feature_summary, feature_provenance),
        encoding="utf-8",
    )
    _write_latest_pointer(output / "v56_feature_provenance_populated", feature_dir)

    closeout = {
        "status": "v56_tranche2_lock_recorded",
        "claim_closed": True,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "gate0_run": str(gate0_path),
        "split_registry_lock_dir": str(split_lock_dir),
        "feature_provenance_dir": str(feature_dir),
        "next_step": "manual_review_then_open_feature_matrix_or_baseline_plan_only_if_registry_and_provenance_pass",
    }
    _write_json(output / "v56_tranche2_lock_latest_summary.json", closeout)

    return V56Tranche2LockResult(
        gate0_run=gate0_path,
        split_registry_lock_dir=split_lock_dir,
        feature_provenance_dir=feature_dir,
        summary=closeout,
    )


def _resolve_path(path: Path, *, must_be_dir: bool) -> Path:
    if path.is_file() and path.name == "latest.txt":
        path = Path(path.read_text(encoding="utf-8").strip())
    if not path.exists():
        raise FileNotFoundError(f"Path not found: {path}")
    if must_be_dir and not path.is_dir():
        raise V56Tranche2LockError(f"Expected directory path, got: {path}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise V56Tranche2LockError(f"JSON root must be an object: {path}")
    return data


def _validate_scaffold_artifacts(split_scaffold: dict[str, Any], provenance_scaffold: dict[str, Any]) -> None:
    if split_scaffold.get("status") != "pending_registry_lock":
        raise V56Tranche2LockError(f"Split scaffold is not pending lock: {split_scaffold.get('status')!r}")
    if split_scaffold.get("test_time_inference") != "scalp_eeg_only":
        raise V56Tranche2LockError("Split scaffold must preserve scalp-only test-time inference.")
    if provenance_scaffold.get("status") != "pending_feature_provenance_population":
        raise V56Tranche2LockError(
            f"Feature provenance scaffold is not pending population: {provenance_scaffold.get('status')!r}"
        )
    if provenance_scaffold.get("claim_closed") is not True:
        raise V56Tranche2LockError("Feature provenance scaffold must remain claim-closed.")


def _eligible_subjects(cohort_lock: dict[str, Any]) -> list[str]:
    subjects = []
    for item in cohort_lock.get("participants", []):
        if item.get("primary_eligible") is True:
            subject = item.get("participant_id") or item.get("subject") or item.get("subject_id")
            if subject:
                subjects.append(subject)
    return sorted(dict.fromkeys(subjects))


def _build_split_registry_lock(
    *,
    timestamp: str,
    benchmark: dict[str, Any],
    split_policy: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    eligible_subjects: list[str],
    gate0_run: Path,
    split_scaffold_run: Path,
    repo_root: Path,
) -> dict[str, Any]:
    folds = []
    for track in split_policy["tracks"]:
        for fold_index, test_subject in enumerate(eligible_subjects, start=1):
            train_subjects = [subject for subject in eligible_subjects if subject != test_subject]
            folds.append(
                {
                    "fold_id": f"{track['id']}_outer_{fold_index:02d}_{test_subject}",
                    "track_id": track["id"],
                    "outer_test_subject": test_subject,
                    "train_subjects": train_subjects,
                    "test_subjects": [test_subject],
                    "train_subject_count": len(train_subjects),
                    "test_subject_count": 1,
                    "privileged_train_time": track["privileged_train_time"],
                    "test_time_modality": split_policy["test_time_inference"]["modality"],
                    "test_time_allow_ieeg": split_policy["test_time_inference"]["allow_ieeg"],
                    "test_time_allow_beamforming_bridge": split_policy["test_time_inference"][
                        "allow_beamforming_bridge"
                    ],
                    "status": "locked",
                }
            )

    return {
        "artifact_family": "v56_split_registry_lock",
        "created_utc": timestamp,
        "status": "locked_subject_level_split_registry",
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "benchmark_name": benchmark["benchmark_name"],
        "record_scope": benchmark["record_scope"],
        "gate0_run": str(gate0_run),
        "split_scaffold_run": str(split_scaffold_run),
        "gate0_manifest_status": manifest["manifest_status"],
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "eligible_subjects": eligible_subjects,
        "subject_isolation_required": split_policy["subject_isolation_required"],
        "subject_isolation_enforced": True,
        "test_time_inference": split_policy["test_time_inference"],
        "train_time_privileged": split_policy["train_time_privileged"],
        "tracks": split_policy["tracks"],
        "folds": folds,
        "split_policy_sha256": _sha256_json(split_policy),
        "repo": _repo_state(repo_root),
        "scientific_boundary": {
            "model_training_run": False,
            "efficacy_metrics_computed": False,
            "claim_ready": False,
            "purpose": "lock subject-level split contract before feature extraction or comparator execution",
        },
    }


def _build_feature_provenance(
    *,
    timestamp: str,
    benchmark: dict[str, Any],
    split_policy: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    gate0_run: Path,
    split_lock_dir: Path,
    split_scaffold_run: Path,
    provenance_scaffold_run: Path,
    benchmark_spec: Path,
    splits: Path,
    repo_root: Path,
) -> dict[str, Any]:
    source_paths = [
        repo_root / benchmark_spec,
        repo_root / splits,
        gate0_run / "manifest.json",
        gate0_run / "cohort_lock.json",
        gate0_run / "materialization_report.json",
        split_scaffold_run / "v56_split_registry.json",
        provenance_scaffold_run / "v56_feature_provenance.json",
        split_lock_dir / "v56_split_registry_lock.json",
    ]
    entries = [_source_entry(path) for path in source_paths if path.exists()]
    missing = [str(path) for path in source_paths if not path.exists()]

    return {
        "artifact_family": "v56_feature_provenance_populated",
        "created_utc": timestamp,
        "status": "populated_source_hashes_and_split_links",
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "benchmark_name": benchmark["benchmark_name"],
        "record_scope": benchmark["record_scope"],
        "gate0_run": str(gate0_run),
        "split_registry_lock_run": str(split_lock_dir),
        "feature_provenance_scaffold_run": str(provenance_scaffold_run),
        "gate0_manifest_status": manifest["manifest_status"],
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "required_links": {
            "split_registry": split_policy["feature_provenance"]["require_split_registry_link"],
            "source_hashes": split_policy["feature_provenance"]["require_source_hashes"],
            "manifest": split_policy["feature_provenance"]["require_manifest"],
        },
        "required_links_satisfied": {
            "split_registry": True,
            "source_hashes": len(entries) > 0 and not missing,
            "manifest": (gate0_run / "manifest.json").exists(),
        },
        "entries": entries,
        "missing_sources": missing,
        "feature_extraction_run": False,
        "feature_matrix_materialized": False,
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "claim_ready": False,
        "next_step": "manual_review_before_feature_matrix_materialization_or_baseline_execution",
    }


def _source_entry(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path),
        "name": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _summary(
    *,
    artifact_family: str,
    status: str,
    timestamp: str,
    output_dir: Path,
    benchmark: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    artifact: dict[str, Any],
    repo_root: Path,
    next_step: str,
) -> dict[str, Any]:
    return {
        "artifact_family": artifact_family,
        "status": status,
        "claim_closed": benchmark["claim_boundary"]["claim_closed_by_default"],
        "created_utc": timestamp,
        "output_dir": str(output_dir),
        "benchmark_name": benchmark["benchmark_name"],
        "gate0_manifest_status": manifest["manifest_status"],
        "cohort_lock_status": cohort_lock["cohort_lock_status"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "artifact_sha256": _sha256_json(artifact),
        "repo": _repo_state(repo_root),
        "model_training_run": False,
        "efficacy_metrics_computed": False,
        "claim_ready": False,
        "next_step": next_step,
    }


def _render_report(title: str, summary: dict[str, Any], artifact: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            "## Status",
            "",
            f"- Status: `{summary['status']}`",
            f"- Claim closed: `{summary['claim_closed']}`",
            f"- Gate 0 manifest: `{summary['gate0_manifest_status']}`",
            f"- Cohort lock: `{summary['cohort_lock_status']}`",
            f"- Primary-eligible participants: {summary['n_primary_eligible']}",
            "",
            "## Integrity Boundary",
            "",
            "- This artifact records registry/provenance state only.",
            "- No feature matrix was materialized here.",
            "- No model was trained.",
            "- No efficacy metric was computed.",
            "- No claim is opened by this artifact.",
            "",
            "## Next Step",
            "",
            f"- {summary['next_step']}",
            "",
            "## Snapshot",
            "",
            "```json",
            json.dumps(artifact, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )


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


def _sha256_json(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
