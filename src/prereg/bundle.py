"""Gate 2.5 preregistration bundle assembly.

The bundle links the frozen Gate 0/1/2 artefacts and configuration hashes.
It does not run real-data models and does not create scientific evidence.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PreregError(RuntimeError):
    """Raised when Gate 2.5 preregistration bundle assembly is invalid."""


@dataclass(frozen=True)
class PreregResult:
    output_dir: Path
    prereg_bundle_path: Path
    environment_lock_path: Path
    validation_report_path: Path
    revision_policy_path: Path
    summary_path: Path
    summary: dict[str, Any]


def run_prereg_assembly(
    gate2_run: str | Path,
    config: dict[str, Any],
    output_root: str | Path,
    repo_root: str | Path | None = None,
) -> PreregResult:
    gate2_run = Path(gate2_run)
    output_root = Path(output_root)
    repo_root = Path(repo_root) if repo_root is not None else Path.cwd()
    if not gate2_run.exists():
        raise FileNotFoundError(f"Gate 2 run not found: {gate2_run}")

    gate2_summary = _read_json(gate2_run / "gate2_summary.json")
    gate1_run = Path(gate2_summary["gate1_source_of_truth"])
    gate0_run = Path(gate2_summary["gate0_source_of_truth"])
    threshold_registry_path = gate2_run / "gate_threshold_registry.json"
    threshold_registry = _read_json(threshold_registry_path)

    validation = validate_prereg_inputs(gate0_run, gate1_run, gate2_run, gate2_summary, threshold_registry)
    if validation["errors"]:
        raise PreregError("; ".join(validation["errors"]))

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_dir = output_root / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    comparator_cards = build_comparator_cards(config, repo_root)
    comparator_card_paths = write_comparator_cards(output_dir / "comparator_cards", comparator_cards)
    environment_lock = build_environment_lock(timestamp, repo_root)
    artifact_hashes = build_artifact_hashes(
        gate0_run,
        gate1_run,
        gate2_run,
        threshold_registry_path,
        config,
        repo_root,
        comparator_card_paths,
    )
    bundle = build_prereg_bundle(
        timestamp,
        config,
        gate0_run,
        gate1_run,
        gate2_run,
        threshold_registry,
        artifact_hashes,
        environment_lock,
        comparator_cards,
    )
    validation_report = build_validation_report(bundle, validation, artifact_hashes)
    revision_policy = render_revision_policy(config)

    prereg_bundle_path = output_dir / "prereg_bundle.json"
    environment_lock_path = output_dir / "environment_lock.json"
    validation_report_path = output_dir / "prereg_validation_report.md"
    revision_policy_path = output_dir / "revision_policy.md"
    summary_path = output_dir / "gate25_summary.json"

    _write_json(prereg_bundle_path, bundle)
    _write_json(environment_lock_path, environment_lock)
    validation_report_path.write_text(validation_report, encoding="utf-8")
    revision_policy_path.write_text(revision_policy, encoding="utf-8")

    summary = {
        "status": "gate2_5_prereg_bundle_locked",
        "created_utc": timestamp,
        "run_dir": str(output_dir),
        "prereg_bundle": str(prereg_bundle_path),
        "prereg_bundle_hash_sha256": bundle["prereg_bundle_hash_sha256"],
        "gate0_source_of_truth": str(gate0_run),
        "gate1_source_of_truth": str(gate1_run),
        "gate2_source_of_truth": str(gate2_run),
        "threshold_registry_hash_sha256": threshold_registry["threshold_registry_hash_sha256"],
        "release_blocker_satisfied": True,
        "real_data_phase_authorized_by_prereg": True,
        "authorized_real_phases": config["allowed_real_phases_after_lock"],
        "scientific_integrity_limits": [
            "A locked prereg bundle is not empirical model evidence.",
            "Real-data phases must use this exact bundle and remain subject to CLI guards.",
            "Post-prereg claim-affecting changes require revision log and demotion unless refrozen.",
        ],
    }
    _write_json(summary_path, summary)
    _write_latest_pointer(output_root, output_dir)

    return PreregResult(
        output_dir=output_dir,
        prereg_bundle_path=prereg_bundle_path,
        environment_lock_path=environment_lock_path,
        validation_report_path=validation_report_path,
        revision_policy_path=revision_policy_path,
        summary_path=summary_path,
        summary=summary,
    )


def validate_prereg_inputs(
    gate0_run: Path,
    gate1_run: Path,
    gate2_run: Path,
    gate2_summary: dict[str, Any],
    threshold_registry: dict[str, Any],
) -> dict[str, Any]:
    errors = []
    for path in [gate0_run, gate1_run, gate2_run]:
        if not path.exists():
            errors.append(f"Required gate run not found: {path}")
    if gate2_summary.get("status") != "gate2_synthetic_ready":
        errors.append(f"Gate 2 status is not ready: {gate2_summary.get('status')}")
    if gate2_summary.get("recovery_status") != "passed":
        errors.append(f"Gate 2 recovery did not pass: {gate2_summary.get('recovery_status')}")
    if gate2_summary.get("threshold_registry_status") != "locked_after_gate2_pass":
        errors.append("Gate 2 threshold registry is not locked")
    if gate2_summary.get("real_data_phase_authorized") is not False:
        errors.append("Gate 2 must not authorize real-data phases before Gate 2.5")
    if threshold_registry.get("status") != "locked_after_gate2_pass":
        errors.append(f"Threshold registry status invalid: {threshold_registry.get('status')}")
    if threshold_registry.get("recovery_status") != "passed":
        errors.append("Threshold registry recovery_status is not passed")
    return {
        "status": "passed" if not errors else "failed",
        "errors": errors,
    }


def build_comparator_cards(config: dict[str, Any], repo_root: Path) -> dict[str, dict[str, Any]]:
    cards = {}
    for comparator_id, relative_path in config["comparator_configs"].items():
        path = repo_root / relative_path
        cards[comparator_id] = {
            "comparator_id": comparator_id,
            "config_path": relative_path,
            "config_sha256": _sha256_file(path),
            "status": "frozen_by_prereg_hash",
            "fairness_note": (
                "Comparator card freezes the referenced config hash. Full fairness depends on downstream "
                "implementation following split/preprocessing guards."
            ),
        }
    return cards


def write_comparator_cards(output_dir: Path, cards: dict[str, dict[str, Any]]) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for comparator_id, card in cards.items():
        path = output_dir / f"{comparator_id}.json"
        _write_json(path, card)
        paths[comparator_id] = path
    return paths


def build_environment_lock(timestamp: str, repo_root: Path) -> dict[str, Any]:
    return {
        "status": "locked_for_prereg",
        "created_utc": timestamp,
        "python": {
            "version": sys.version,
            "executable": sys.executable,
        },
        "platform": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "git": _git_identity(repo_root),
        "pip_freeze": _safe_command([sys.executable, "-m", "pip", "freeze"], repo_root).splitlines(),
    }


def build_artifact_hashes(
    gate0_run: Path,
    gate1_run: Path,
    gate2_run: Path,
    threshold_registry_path: Path,
    config: dict[str, Any],
    repo_root: Path,
    comparator_card_paths: dict[str, Path],
) -> dict[str, Any]:
    return {
        "gate0": _hash_required_files(
            gate0_run,
            [
                "manifest.json",
                "cohort_lock.json",
                "materialization_report.json",
                "audit_report.md",
            ],
        ),
        "gate1": _hash_required_files(
            gate1_run,
            [
                "gate1_summary.json",
                "gate1_inputs.json",
                "gate1_input_integrity.json",
                "n_eff_statement.json",
                "simulation_registry.json",
                "sesoi_registry.json",
                "influence_rule.json",
                "decision_memo.md",
            ],
        ),
        "gate2": _hash_required_files(
            gate2_run,
            [
                "gate2_summary.json",
                "synthetic_generator_spec.json",
                "synthetic_recovery_report.json",
                "synthetic_recovery_report.md",
                "gate_threshold_registry.json",
            ],
        ),
        "threshold_registry": _hash_entry(threshold_registry_path),
        "registries_and_specs": {
            name: _hash_entry(repo_root / relative_path)
            for name, relative_path in config["registry_configs"].items()
        },
        "comparator_configs": {
            name: _hash_entry(repo_root / relative_path)
            for name, relative_path in config["comparator_configs"].items()
        },
        "comparator_cards": {
            name: _hash_entry(path)
            for name, path in comparator_card_paths.items()
        },
    }


def build_prereg_bundle(
    timestamp: str,
    config: dict[str, Any],
    gate0_run: Path,
    gate1_run: Path,
    gate2_run: Path,
    threshold_registry: dict[str, Any],
    artifact_hashes: dict[str, Any],
    environment_lock: dict[str, Any],
    comparator_cards: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    bundle = {
        "status": "locked",
        "gate": "gate2_5_preregistration_bundle",
        "locked_at": timestamp,
        "study_id": config["study_id"],
        "version": config["version"],
        "parent_doc_ids": config["parent_doc_ids"],
        "annex_version": config["annex_version"],
        "dossier_version": config["dossier_version"],
        "revision_policy": config["revision_policy"],
        "source_runs": {
            "gate0": str(gate0_run),
            "gate1": str(gate1_run),
            "gate2": str(gate2_run),
        },
        "data_freeze": {
            "manifest_hash": artifact_hashes["gate0"]["manifest.json"]["sha256"],
            "cohort_lock_hash": artifact_hashes["gate0"]["cohort_lock.json"]["sha256"],
        },
        "decision_layer": {
            "decision_memo_hash": artifact_hashes["gate1"]["decision_memo.md"]["sha256"],
            "sesoi_registry_hash": artifact_hashes["gate1"]["sesoi_registry.json"]["sha256"],
            "influence_rule_hash": artifact_hashes["gate1"]["influence_rule.json"]["sha256"],
        },
        "synthetic_validation": {
            "gate2_summary_hash": artifact_hashes["gate2"]["gate2_summary.json"]["sha256"],
            "threshold_registry_hash": threshold_registry["threshold_registry_hash_sha256"],
            "generator_hash": threshold_registry["generator_hash_sha256"],
        },
        "thresholds": threshold_registry["thresholds"],
        "artifact_hashes": artifact_hashes,
        "environment_lock_hash": _sha256_json(environment_lock),
        "comparator_cards": comparator_cards,
        "allowed_real_phases": config["allowed_real_phases_after_lock"],
        "release_policy": {
            "release_blocker_satisfied": True,
            "phase_release_note": config["phase_release_note"],
            "real_phase_cli_guard_required": True,
            "exact_bundle_required_for_real_phases": True,
        },
        "scientific_integrity_limits": [
            "This prereg bundle is a governance artefact, not empirical evidence.",
            "A locked bundle does not prove real-data EEG model efficacy.",
            "All post-prereg claim-affecting changes require revision log and refreeze/rerun or demotion.",
        ],
    }
    bundle["prereg_bundle_hash_sha256"] = _sha256_json(bundle)
    return bundle


def build_validation_report(
    bundle: dict[str, Any],
    validation: dict[str, Any],
    artifact_hashes: dict[str, Any],
) -> str:
    lines = [
        "# Gate 2.5 Preregistration Validation Report",
        "",
        f"- Validation status: `{validation['status']}`",
        f"- Bundle status: `{bundle['status']}`",
        f"- Bundle hash: `{bundle['prereg_bundle_hash_sha256']}`",
        f"- Release blocker satisfied: `{bundle['release_policy']['release_blocker_satisfied']}`",
        "",
        "## Linked Gate Artefacts",
        "",
        f"- Gate 0 manifest hash: `{artifact_hashes['gate0']['manifest.json']['sha256']}`",
        f"- Gate 0 cohort lock hash: `{artifact_hashes['gate0']['cohort_lock.json']['sha256']}`",
        f"- Gate 1 decision memo hash: `{artifact_hashes['gate1']['decision_memo.md']['sha256']}`",
        f"- Gate 2 threshold registry hash: `{bundle['synthetic_validation']['threshold_registry_hash']}`",
        "",
        "## Scientific Integrity",
        "",
        "- The prereg bundle is a release-control artefact, not empirical evidence.",
        "- Real-data phases must use this exact bundle and remain subject to CLI guards.",
        "- Claim-affecting changes after lock require revision log and demotion unless refrozen.",
        "",
    ]
    return "\n".join(lines)


def render_revision_policy(config: dict[str, Any]) -> str:
    policy = config["revision_policy"]
    return (
        "# Revision Policy\n\n"
        "- Post-prereg changes require a revision log entry: "
        f"`{policy['post_prereg_changes_require_revision_log']}`.\n"
        "- Claim-affecting changes demote to post-hoc unless refrozen: "
        f"`{policy['claim_affecting_changes_demote_to_post_hoc_unless_refrozen']}`.\n"
        "- Silent changes to comparators, thresholds, teacher pool, controls, or reporting are forbidden: "
        f"`{policy['no_silent_changes_to_comparators_thresholds_teacher_pool_controls_or_reporting']}`.\n"
    )


def _hash_required_files(root: Path, names: list[str]) -> dict[str, dict[str, str]]:
    return {name: _hash_entry(root / name) for name in names}


def _hash_entry(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found for hashing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PreregError(f"JSON root must be an object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_latest_pointer(output_root: Path, output_dir: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_root.joinpath("latest.txt").write_text(str(output_dir), encoding="utf-8")


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
