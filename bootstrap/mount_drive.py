"""Small Colab helper for mounting Google Drive.

This file intentionally has no hard dependency on Colab so it can be
imported and tested outside notebooks.
"""

from __future__ import annotations

from pathlib import Path


def mount_drive(mount_point: str = "/content/drive") -> Path:
    try:
        from google.colab import drive  # type: ignore
    except Exception as exc:  # pragma: no cover - only used in Colab
        raise RuntimeError("Google Colab drive module is unavailable") from exc

    drive.mount(mount_point)
    return Path(mount_point)


if __name__ == "__main__":  # pragma: no cover
    print(mount_drive())

