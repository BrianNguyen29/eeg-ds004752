from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import load_config


class ConfigTests(unittest.TestCase):
    def test_simple_yaml_with_nested_map_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "root:\n"
                "  child: 1\n"
                "items:\n"
                "  - alpha\n"
                "  - beta\n"
                "flag: true\n",
                encoding="utf-8",
            )
            data = load_config(path)

            self.assertEqual(data["root"]["child"], 1)
            self.assertEqual(data["items"], ["alpha", "beta"])
            self.assertTrue(data["flag"])


if __name__ == "__main__":
    unittest.main()

