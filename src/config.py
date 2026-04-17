"""Small config loader for JSON and simple YAML files.

The project keeps Gate 0 dependency-free, so this parser only supports the
simple YAML subset used by the repository configs: nested mappings, scalar
values, and list items.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    text = config_path.read_text(encoding="utf-8")
    if config_path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = _parse_simple_yaml(text)
    if not isinstance(data, dict):
        raise ValueError(f"Config root must be a mapping: {config_path}")
    return data


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    return _parse_yaml_lines(text)


def _parse_yaml_lines(text: str) -> dict[str, Any]:
    """Parse the repository's simple YAML subset."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]
    lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    for index, raw_line in enumerate(lines):
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"List item without list parent: {raw_line}")
            parent.append(_parse_scalar(line[2:].strip()))
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not isinstance(parent, dict):
            raise ValueError(f"Mapping entry inside list is unsupported: {raw_line}")
        if value:
            parent[key] = _parse_scalar(value)
            continue
        next_is_list = False
        if index + 1 < len(lines):
            next_raw = lines[index + 1]
            next_indent = len(next_raw) - len(next_raw.lstrip(" "))
            next_is_list = next_indent > indent and next_raw.strip().startswith("- ")
        child: Any = [] if next_is_list else {}
        parent[key] = child
        stack.append((indent, child))
    return root


def _parse_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value
