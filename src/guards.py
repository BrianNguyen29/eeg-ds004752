"""Execution guards for preregistered real-data phases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class GuardError(RuntimeError):
    """Raised when a phase is blocked by governance rules."""


REAL_PHASES = {"phase05_real", "phase1_real", "phase2_real", "phase3_real"}


def load_prereg_bundle(path: str | Path) -> dict[str, Any]:
    prereg_path = Path(path)
    if not prereg_path.exists():
        raise GuardError(f"Missing prereg bundle: {prereg_path}")
    try:
        data = json.loads(prereg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GuardError(f"Invalid prereg JSON: {prereg_path}") from exc
    if not isinstance(data, dict):
        raise GuardError("Prereg bundle root must be an object")
    return data


def assert_real_phase_allowed(phase: str, prereg_path: str | Path) -> dict[str, Any]:
    if phase not in REAL_PHASES:
        raise GuardError(f"Unknown real phase: {phase}")
    bundle = load_prereg_bundle(prereg_path)
    if bundle.get("status") != "locked":
        raise GuardError(
            f"{phase} blocked: prereg_bundle.json is not locked after Gate 2.5"
        )
    hashes = bundle.get("artifact_hashes")
    if not isinstance(hashes, dict) or not hashes:
        raise GuardError(f"{phase} blocked: locked prereg bundle has no artifact_hashes")
    return bundle

