"""Colab helper paths for the Drive-backed project layout."""

from __future__ import annotations

from pathlib import Path


DRIVE_PROJECT_ROOT = Path("/content/drive/MyDrive/eeg-ds004752")
DRIVE_DATA_ROOT = DRIVE_PROJECT_ROOT / "data"
DRIVE_DATASET_ROOT = DRIVE_DATA_ROOT / "ds004752"
DRIVE_ARTIFACT_ROOT = DRIVE_PROJECT_ROOT / "artifacts"
DRIVE_CACHE_ROOT = DRIVE_PROJECT_ROOT / "cache"
DRIVE_CHECKPOINT_ROOT = DRIVE_PROJECT_ROOT / "checkpoints"


def ensure_drive_layout() -> dict[str, str]:
    paths = {
        "project_root": DRIVE_PROJECT_ROOT,
        "data_root": DRIVE_DATA_ROOT,
        "dataset_root": DRIVE_DATASET_ROOT,
        "artifact_root": DRIVE_ARTIFACT_ROOT,
        "cache_root": DRIVE_CACHE_ROOT,
        "checkpoint_root": DRIVE_CHECKPOINT_ROOT,
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return {key: str(value) for key, value in paths.items()}


if __name__ == "__main__":  # pragma: no cover
    for key, value in ensure_drive_layout().items():
        print(f"{key}: {value}")

