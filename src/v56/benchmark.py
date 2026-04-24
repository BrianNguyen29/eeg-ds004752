"""Benchmark contract helpers for V5.6.

These helpers only validate readiness and build scaffold records. They do not
run models or produce scientific claims.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_config


class V56BenchmarkError(RuntimeError):
    """Raised when the V5.6 benchmark contract is malformed."""


class V56ReadinessError(RuntimeError):
    """Raised when required Gate 0 readiness evidence is missing."""


def load_benchmark_spec(path: str | Path) -> dict[str, Any]:
    spec = load_config(path)
    required_keys = {
        "benchmark_name",
        "claim_boundary",
        "gate_requirements",
        "statistics",
        "implementation_policy",
        "primary_target",
        "artifact_roots",
    }
    missing = sorted(required_keys - set(spec))
    if missing:
        raise V56BenchmarkError(f"Missing benchmark spec fields: {missing}")
    if spec["claim_boundary"].get("claim_closed_by_default") is not True:
        raise V56BenchmarkError("V5.6 benchmark spec must remain claim-closed by default.")
    if spec["implementation_policy"].get("test_time_inference") != "scalp_eeg_only":
        raise V56BenchmarkError("V5.6 benchmark spec must enforce scalp-only test-time inference.")
    return spec


def assert_signal_ready_gate0(
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
    benchmark_spec: dict[str, Any],
) -> None:
    gate_requirements = benchmark_spec["gate_requirements"]
    expected_manifest = gate_requirements["gate0_manifest_status"]
    expected_cohort = gate_requirements["cohort_lock_status"]
    min_primary = gate_requirements["n_primary_eligible_min"]

    if manifest.get("manifest_status") != expected_manifest:
        raise V56ReadinessError(
            f"Gate 0 manifest status must be {expected_manifest}, got {manifest.get('manifest_status')!r}."
        )
    if manifest.get("gate0_blockers"):
        raise V56ReadinessError(f"Gate 0 blockers must be empty, got {manifest['gate0_blockers']!r}.")
    if cohort_lock.get("cohort_lock_status") != expected_cohort:
        raise V56ReadinessError(
            f"Cohort lock status must be {expected_cohort}, got {cohort_lock.get('cohort_lock_status')!r}."
        )
    n_primary = cohort_lock.get("n_primary_eligible")
    if not isinstance(n_primary, int) or n_primary < min_primary:
        raise V56ReadinessError(
            f"Cohort lock must expose at least {min_primary} primary-eligible participants, got {n_primary!r}."
        )


def build_benchmark_scaffold_record(
    benchmark_spec: dict[str, Any],
    manifest: dict[str, Any],
    cohort_lock: dict[str, Any],
) -> dict[str, Any]:
    assert_signal_ready_gate0(manifest, cohort_lock, benchmark_spec)
    return {
        "benchmark_name": benchmark_spec["benchmark_name"],
        "program_version": benchmark_spec["program_version"],
        "status": "ready_for_benchmark_control_scaffolding",
        "record_scope": benchmark_spec["record_scope"],
        "claim_closed": benchmark_spec["claim_boundary"]["claim_closed_by_default"],
        "primary_target_id": benchmark_spec["primary_target"]["id"],
        "test_time_inference": benchmark_spec["implementation_policy"]["test_time_inference"],
        "n_primary_eligible": cohort_lock["n_primary_eligible"],
        "gate0_manifest_status": manifest["manifest_status"],
    }
