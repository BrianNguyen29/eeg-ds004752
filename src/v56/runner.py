"""Runner for V5.6 scaffold-only artifact generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import load_config
from .artifacts import (
    V56ArtifactWriteResult,
    write_control_registry_artifact,
    write_feature_provenance_artifact,
    write_leaderboard_artifact,
    write_split_registry_artifact,
)
from .benchmark import load_benchmark_spec
from .controls import load_control_policy
from .splits import load_split_policy


class V56ScaffoldRunError(RuntimeError):
    """Raised when the V5.6 scaffold runner cannot build artifacts."""


@dataclass(frozen=True)
class V56ScaffoldRunResult:
    gate0_run: Path
    artifacts: dict[str, V56ArtifactWriteResult]

    @property
    def output_dirs(self) -> dict[str, Path]:
        return {name: result.output_dir for name, result in self.artifacts.items()}


def run_v56_scaffold(
    *,
    gate0_run: str | Path,
    benchmark_spec: str | Path = "configs/v56/benchmark_spec.json",
    splits: str | Path = "configs/v56/splits.json",
    controls: str | Path = "configs/v56/controls.json",
    comparators: str | Path = "configs/v56/comparators.json",
    output_root: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> V56ScaffoldRunResult:
    """Write V5.6 Tranche 2 scaffold artifacts without running models."""

    repo = Path(repo_root) if repo_root is not None else Path.cwd()
    gate0_path = _resolve_run_path(Path(gate0_run))
    manifest = _read_json_object(gate0_path / "manifest.json")
    cohort_lock = _read_json_object(gate0_path / "cohort_lock.json")

    benchmark = load_benchmark_spec(benchmark_spec)
    split_policy = load_split_policy(splits)
    control_policy = load_control_policy(controls)
    comparator_config = load_config(comparators)

    roots = _output_roots(output_root)
    artifacts = {
        "v56_split_registry": write_split_registry_artifact(
            benchmark_spec=benchmark,
            split_policy=split_policy,
            manifest=manifest,
            cohort_lock=cohort_lock,
            output_root=roots.get("v56_split_registry"),
            repo_root=repo,
        ),
        "v56_feature_provenance": write_feature_provenance_artifact(
            benchmark_spec=benchmark,
            split_policy=split_policy,
            manifest=manifest,
            cohort_lock=cohort_lock,
            output_root=roots.get("v56_feature_provenance"),
            repo_root=repo,
        ),
        "v56_control_registry": write_control_registry_artifact(
            benchmark_spec=benchmark,
            control_policy=control_policy,
            manifest=manifest,
            cohort_lock=cohort_lock,
            output_root=roots.get("v56_control_registry"),
            repo_root=repo,
        ),
        "v56_leaderboard": write_leaderboard_artifact(
            benchmark_spec=benchmark,
            comparators_config=comparator_config,
            manifest=manifest,
            cohort_lock=cohort_lock,
            output_root=roots.get("v56_leaderboard"),
            repo_root=repo,
        ),
    }
    return V56ScaffoldRunResult(gate0_run=gate0_path, artifacts=artifacts)


def _output_roots(output_root: str | Path | None) -> dict[str, Path]:
    if output_root is None:
        return {}
    root = Path(output_root)
    return {
        "v56_split_registry": root / "v56_split_registry",
        "v56_feature_provenance": root / "v56_feature_provenance",
        "v56_control_registry": root / "v56_control_registry",
        "v56_leaderboard": root / "v56_leaderboard",
    }


def _resolve_run_path(path: Path) -> Path:
    if path.is_file():
        path = Path(path.read_text(encoding="utf-8").strip())
    if not path.exists():
        raise FileNotFoundError(f"Gate 0 run not found: {path}")
    if not path.is_dir():
        raise V56ScaffoldRunError(f"Gate 0 run must be a directory or latest.txt pointer: {path}")
    return path


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required Gate 0 artifact not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise V56ScaffoldRunError(f"JSON root must be an object: {path}")
    return data
