"""Artifact writers for V5.6 benchmark/control-first scaffolding.

These writers record scaffold-only artifacts after Gate 0 reaches
``signal_audit_ready``. They do not run models, compute scientific metrics, or
open efficacy claims.
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
from .benchmark import assert_signal_ready_gate0, build_benchmark_scaffold_record
from .controls import build_control_registry_skeleton
from .leaderboard import build_leaderboard_skeleton
from .provenance import build_feature_provenance_skeleton
from .splits import build_split_registry_skeleton


class V56ArtifactWriterError(RuntimeError):
    """Raised when a V5.6 artifact write request is malformed."""


@dataclass(frozen=True)
class V56ArtifactWriteResult:
    output_dir: Path
    artifact_path: Path
    summary_path: Path
    report_path: Path
    summary: dict[str, Any]


def write_split_registry_artifact(
    *,
    benchmark_spec: dict[str, Any],
    split_policy: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    output_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> V56ArtifactWriteResult:
    benchmark_record = _build_benchmark_record(benchmark_spec, manifest, cohort_lock)
    registry = build_split_registry_skeleton(split_policy)
    registry.update(
        {
            "artifact_family": "v56_split_registry",
            "benchmark_name": benchmark_spec["benchmark_name"],
            "status": "pending_registry_lock",
            "claim_closed": benchmark_spec["claim_boundary"]["claim_closed_by_default"],
            "test_time_inference": benchmark_spec["implementation_policy"]["test_time_inference"],
            "gate0_manifest_status": manifest["manifest_status"],
            "cohort_lock_status": cohort_lock["cohort_lock_status"],
            "n_primary_eligible": cohort_lock["n_primary_eligible"],
        }
    )
    return _write_artifact_bundle(
        artifact_key="split_registry",
        artifact_basename="v56_split_registry",
        artifact=registry,
        benchmark_spec=benchmark_spec,
        benchmark_record=benchmark_record,
        source_contracts={
            "split_registry_version": split_policy["split_registry_version"],
            "subject_isolation_required": split_policy["subject_isolation_required"],
            "track_count": len(split_policy["tracks"]),
        },
        output_root=output_root,
        repo_root=repo_root,
        report_title="V5.6 Split Registry Scaffold",
        next_step="populate and review a locked split registry before any comparator execution",
    )


def write_feature_provenance_artifact(
    *,
    benchmark_spec: dict[str, Any],
    split_policy: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    output_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> V56ArtifactWriteResult:
    benchmark_record = _build_benchmark_record(benchmark_spec, manifest, cohort_lock)
    provenance = build_feature_provenance_skeleton(split_policy, benchmark_spec)
    provenance.update(
        {
            "artifact_family": "v56_feature_provenance",
            "gate0_manifest_status": manifest["manifest_status"],
            "cohort_lock_status": cohort_lock["cohort_lock_status"],
            "n_primary_eligible": cohort_lock["n_primary_eligible"],
        }
    )
    return _write_artifact_bundle(
        artifact_key="feature_provenance",
        artifact_basename="v56_feature_provenance",
        artifact=provenance,
        benchmark_spec=benchmark_spec,
        benchmark_record=benchmark_record,
        source_contracts={
            "split_registry_version": split_policy["split_registry_version"],
            "source_hashes_required": split_policy["feature_provenance"]["require_source_hashes"],
            "manifest_link_required": split_policy["feature_provenance"]["require_manifest"],
        },
        output_root=output_root,
        repo_root=repo_root,
        report_title="V5.6 Feature Provenance Scaffold",
        next_step="populate source hashes and split links before feature extraction is treated as auditable",
    )


def write_control_registry_artifact(
    *,
    benchmark_spec: dict[str, Any],
    control_policy: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    output_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> V56ArtifactWriteResult:
    benchmark_record = _build_benchmark_record(benchmark_spec, manifest, cohort_lock)
    registry = build_control_registry_skeleton(control_policy)
    registry.update(
        {
            "artifact_family": "v56_control_registry",
            "benchmark_name": benchmark_spec["benchmark_name"],
            "gate0_manifest_status": manifest["manifest_status"],
            "cohort_lock_status": cohort_lock["cohort_lock_status"],
            "n_primary_eligible": cohort_lock["n_primary_eligible"],
        }
    )
    return _write_artifact_bundle(
        artifact_key="control_registry",
        artifact_basename="v56_control_registry",
        artifact=registry,
        benchmark_spec=benchmark_spec,
        benchmark_record=benchmark_record,
        source_contracts={
            "tier_count": len(control_policy["control_tiers"]),
            "claim_closed_by_default": control_policy["claim_closed_by_default"],
        },
        output_root=output_root,
        repo_root=repo_root,
        report_title="V5.6 Control Registry Scaffold",
        next_step="define execution manifests and adequacy rules before any claim-bearing interpretation",
    )


def write_leaderboard_artifact(
    *,
    benchmark_spec: dict[str, Any],
    comparators_config: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    output_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> V56ArtifactWriteResult:
    benchmark_record = _build_benchmark_record(benchmark_spec, manifest, cohort_lock)
    leaderboard = build_leaderboard_skeleton(benchmark_spec, comparators_config)
    leaderboard.update(
        {
            "artifact_family": "v56_leaderboard",
            "claim_closed": benchmark_spec["claim_boundary"]["claim_closed_by_default"],
            "gate0_manifest_status": manifest["manifest_status"],
            "cohort_lock_status": cohort_lock["cohort_lock_status"],
            "n_primary_eligible": cohort_lock["n_primary_eligible"],
        }
    )
    return _write_artifact_bundle(
        artifact_key="leaderboard",
        artifact_basename="v56_leaderboard",
        artifact=leaderboard,
        benchmark_spec=benchmark_spec,
        benchmark_record=benchmark_record,
        source_contracts={
            "primary_target_id": comparators_config["primary_target_id"],
            "comparator_count": len(comparators_config["comparators"]),
        },
        output_root=output_root,
        repo_root=repo_root,
        report_title="V5.6 Leaderboard Scaffold",
        next_step="run audited comparators and controls before any leaderboard row can leave pending_not_run",
    )


def _build_benchmark_record(
    benchmark_spec: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
) -> dict[str, Any]:
    assert_signal_ready_gate0(manifest, cohort_lock, benchmark_spec)
    return build_benchmark_scaffold_record(benchmark_spec, manifest, cohort_lock)


def _write_artifact_bundle(
    *,
    artifact_key: str,
    artifact_basename: str,
    artifact: dict[str, Any],
    benchmark_spec: dict[str, Any],
    benchmark_record: dict[str, Any],
    source_contracts: dict[str, Any],
    output_root: str | Path | None,
    repo_root: str | Path | None,
    report_title: str,
    next_step: str,
) -> V56ArtifactWriteResult:
    root = _resolve_output_root(benchmark_spec, artifact_key, output_root, repo_root)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = root / timestamp
    output_dir.mkdir(parents=True, exist_ok=False)

    artifact["created_utc"] = timestamp
    artifact["benchmark_record_status"] = benchmark_record["status"]

    summary = {
        "artifact_family": artifact_basename,
        "status": artifact["status"],
        "claim_closed": benchmark_spec["claim_boundary"]["claim_closed_by_default"],
        "benchmark_name": benchmark_spec["benchmark_name"],
        "created_utc": timestamp,
        "output_dir": str(output_dir),
        "primary_target_id": benchmark_spec["primary_target"]["id"],
        "gate0_manifest_status": benchmark_record["gate0_manifest_status"],
        "n_primary_eligible": benchmark_record["n_primary_eligible"],
        "source_contracts": source_contracts,
        "artifact_sha256": _sha256_json(artifact),
        "repo": _repo_state(Path(repo_root) if repo_root is not None else Path.cwd()),
        "next_step": next_step,
    }

    artifact_path = output_dir / f"{artifact_basename}.json"
    summary_path = output_dir / f"{artifact_basename}_summary.json"
    report_path = output_dir / f"{artifact_basename}_report.md"
    benchmark_record_path = output_dir / "v56_benchmark_scaffold_record.json"

    _write_json(artifact_path, artifact)
    _write_json(summary_path, summary)
    _write_json(benchmark_record_path, benchmark_record)
    report_path.write_text(_render_report(report_title, summary, artifact), encoding="utf-8")
    _write_latest_pointer(root, output_dir)

    return V56ArtifactWriteResult(
        output_dir=output_dir,
        artifact_path=artifact_path,
        summary_path=summary_path,
        report_path=report_path,
        summary=summary,
    )


def _resolve_output_root(
    benchmark_spec: dict[str, Any],
    artifact_key: str,
    output_root: str | Path | None,
    repo_root: str | Path | None,
) -> Path:
    if output_root is not None:
        return Path(output_root)
    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    configured = benchmark_spec["artifact_roots"].get(artifact_key)
    if not configured:
        raise V56ArtifactWriterError(f"Missing artifact root for {artifact_key!r} in benchmark spec.")
    return repo / configured


def _render_report(title: str, summary: dict[str, Any], artifact: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        "## Status",
        "",
        f"- Status: `{summary['status']}`",
        f"- Claim closed: `{summary['claim_closed']}`",
        f"- Gate 0 manifest: `{summary['gate0_manifest_status']}`",
        f"- Primary-eligible participants: {summary['n_primary_eligible']}",
        f"- Primary target: `{summary['primary_target_id']}`",
        "",
        "## Artifact",
        "",
        f"- Artifact family: `{summary['artifact_family']}`",
        f"- SHA256: `{summary['artifact_sha256']}`",
        f"- Next step: `{summary['next_step']}`",
        "",
        "## Integrity Boundary",
        "",
        "- This artifact records scaffold state only.",
        "- No model was trained and no efficacy metric was computed here.",
        "- Claim state remains closed until audited comparators and controls exist.",
        "",
        "## Snapshot",
        "",
        "```json",
        json.dumps(artifact, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
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


def _sha256_json(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
