"""Feature provenance scaffolding for V5.6."""

from __future__ import annotations

from typing import Any


def build_feature_provenance_skeleton(
    split_policy: dict[str, Any],
    benchmark_spec: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "pending_feature_provenance_population",
        "benchmark_name": benchmark_spec["benchmark_name"],
        "record_scope": benchmark_spec["record_scope"],
        "claim_closed": benchmark_spec["claim_boundary"]["claim_closed_by_default"],
        "required_links": {
            "split_registry": split_policy["feature_provenance"]["require_split_registry_link"],
            "source_hashes": split_policy["feature_provenance"]["require_source_hashes"],
            "manifest": split_policy["feature_provenance"]["require_manifest"],
        },
        "entries": [],
    }
