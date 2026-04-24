"""Control policy scaffolding for V5.6."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_config


class V56ControlPolicyError(RuntimeError):
    """Raised when V5.6 control policy weakens claim blocking."""


def load_control_policy(path: str | Path) -> dict[str, Any]:
    policy = load_config(path)
    if policy.get("claim_closed_by_default") is not True:
        raise V56ControlPolicyError("V5.6 control policy must remain claim-closed by default.")
    if "control_tiers" not in policy:
        raise V56ControlPolicyError("Missing control_tiers in V5.6 control policy.")
    return policy


def assert_claim_blocking_controls(policy: dict[str, Any]) -> None:
    tiers = policy["control_tiers"]
    blocker_ids = {tier["id"] for tier in tiers if tier.get("claim_blocking") is True}
    required = {"data_integrity", "control_adequacy", "reporting"}
    missing = sorted(required - blocker_ids)
    if missing:
        raise V56ControlPolicyError(f"Missing claim-blocking control tiers: {missing}")


def build_control_registry_skeleton(policy: dict[str, Any]) -> dict[str, Any]:
    assert_claim_blocking_controls(policy)
    return {
        "status": "pending_control_execution",
        "claim_closed": policy["claim_closed_by_default"],
        "tiers": [
            {
                "id": tier["id"],
                "claim_blocking": tier["claim_blocking"],
                "required_controls": tier["required_controls"],
                "status": "pending",
            }
            for tier in policy["control_tiers"]
        ],
    }
