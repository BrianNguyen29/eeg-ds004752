"""Runtime profile loader used by notebooks and CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import load_config


def load_runtime_profile(name: str, config_root: str | Path = "configs/runtime") -> dict[str, Any]:
    path = Path(config_root) / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Runtime profile not found: {path}")
    data = load_config(path)
    data["profile_name"] = name
    data["profile_path"] = str(path)
    return data

