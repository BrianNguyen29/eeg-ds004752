"""Split policy helpers for V5.6."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import load_config


class V56SplitPolicyError(RuntimeError):
    """Raised when the V5.6 split policy violates the contract."""


def load_split_policy(path: str | Path) -> dict[str, Any]:
    policy = load_config(path)
    for key in ("test_time_inference", "train_time_privileged", "tracks", "feature_provenance"):
        if key not in policy:
            raise V56SplitPolicyError(f"Missing split policy field: {key}")
    return policy


def assert_scalp_only_test_time(policy: dict[str, Any]) -> None:
    inference = policy["test_time_inference"]
    if inference.get("modality") != "scalp_eeg_only":
        raise V56SplitPolicyError("Test-time inference must remain scalp_eeg_only.")
    if inference.get("allow_ieeg") is not False:
        raise V56SplitPolicyError("Test-time inference must not allow iEEG inputs.")
    if inference.get("allow_beamforming_bridge") is not False:
        raise V56SplitPolicyError("Test-time inference must not allow beamforming bridge inputs.")


def build_split_registry_skeleton(policy: dict[str, Any]) -> dict[str, Any]:
    assert_scalp_only_test_time(policy)
    return {
        "split_registry_version": policy["split_registry_version"],
        "subject_isolation_required": policy["subject_isolation_required"],
        "tracks": [
            {
                "id": item["id"],
                "features": item["features"],
                "privileged_train_time": item["privileged_train_time"],
                "status": "pending_registry_lock",
            }
            for item in policy["tracks"]
        ],
        "feature_provenance_required": policy["feature_provenance"]["require_manifest"],
    }
