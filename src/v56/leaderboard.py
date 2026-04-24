"""Comparator and leaderboard scaffolding for V5.6."""

from __future__ import annotations

from typing import Any


class V56LeaderboardError(RuntimeError):
    """Raised when comparator scaffolding violates the benchmark contract."""


def build_leaderboard_skeleton(
    benchmark_spec: dict[str, Any],
    comparators_config: dict[str, Any],
) -> dict[str, Any]:
    target_id = benchmark_spec["primary_target"]["id"]
    comparator_rows = comparators_config["comparators"]
    comparator_ids = {row["id"] for row in comparator_rows}
    if target_id not in comparator_ids:
        raise V56LeaderboardError(f"Primary target {target_id!r} is missing from comparators config.")
    return {
        "benchmark_name": benchmark_spec["benchmark_name"],
        "status": "pending_comparator_execution",
        "primary_target_id": target_id,
        "rows": [
            {
                "id": row["id"],
                "family": row["family"],
                "strength": row["strength"],
                "requires_privileged_train_time": row["requires_privileged_train_time"],
                "enabled_by_default": row["enabled_by_default"],
                "run_status": "pending_not_run",
            }
            for row in comparator_rows
        ],
    }
