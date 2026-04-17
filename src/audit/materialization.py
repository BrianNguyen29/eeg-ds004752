"""Materialization inventory for DataLad/git-annex payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PAYLOAD_PATTERNS = {
    "edf": "*.edf",
    "mat": "*.mat",
}


def build_materialization_report(dataset_root: str | Path, max_examples: int = 40) -> dict[str, Any]:
    dataset_root = Path(dataset_root)
    payloads: dict[str, Any] = {}
    for payload_type, pattern in PAYLOAD_PATTERNS.items():
        files = sorted(dataset_root.rglob(pattern))
        records = [_payload_record(dataset_root, path) for path in files]
        missing = [record for record in records if not record["materialized"]]
        materialized = [record for record in records if record["materialized"]]
        payloads[payload_type] = {
            "count": len(records),
            "materialized_count": len(materialized),
            "missing_count": len(missing),
            "materialized_bytes": sum(record["target_size_bytes"] or 0 for record in materialized),
            "missing_examples": missing[:max_examples],
            "materialized_examples": materialized[:max_examples],
        }

    missing_paths = [
        record["relative_path"]
        for payload in payloads.values()
        for record in payload["missing_examples"]
    ]
    return {
        "status": "complete" if not any(payload["missing_count"] for payload in payloads.values()) else "incomplete",
        "dataset_root": str(dataset_root),
        "payloads": payloads,
        "datalad_get_suggestions": _datalad_get_suggestions(missing_paths),
    }


def payload_state_from_report(report: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    for payload_type, payload in report["payloads"].items():
        missing_count = payload["missing_count"]
        count = payload["count"]
        state[payload_type] = {
            "count": count,
            "pointer_like_count": missing_count,
            "materialized_count": payload["materialized_count"],
            "state": "all_pointer_like" if count and missing_count == count else "mixed_or_materialized",
        }
    return state


def _payload_record(dataset_root: Path, path: Path) -> dict[str, Any]:
    target = _resolve_target(path)
    target_exists = target.exists() if target else False
    target_size = target.stat().st_size if target_exists else None
    materialized = bool(target_exists and target_size and target_size > 4096)
    return {
        "relative_path": path.relative_to(dataset_root).as_posix(),
        "is_symlink": path.is_symlink(),
        "target_path": str(target) if target else None,
        "target_exists": target_exists,
        "target_size_bytes": target_size,
        "materialized": materialized,
        "datalad_get": f"datalad get {path.relative_to(dataset_root).as_posix()}",
    }


def _resolve_target(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except FileNotFoundError:
        if path.is_symlink():
            try:
                return path.parent / path.readlink()
            except OSError:
                return None
        return path if path.exists() else None


def _datalad_get_suggestions(missing_paths: list[str]) -> dict[str, Any]:
    if not missing_paths:
        return {
            "status": "none_needed",
            "commands": [],
        }

    first_examples = missing_paths[:20]
    return {
        "status": "missing_payloads",
        "commands": [
            "datalad get " + " ".join(first_examples),
            "datalad get .",
        ],
        "note": "The first command only fetches the first missing examples; use datalad get . for full materialization.",
    }
