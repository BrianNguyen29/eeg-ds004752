from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.cli import main


class CliTests(unittest.TestCase):
    def test_report_compile_accepts_latest_pointer_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "gate0" / "run"
            run_dir.mkdir(parents=True)
            run_dir.joinpath("manifest.json").write_text("{}", encoding="utf-8")
            latest = root / "latest.txt"
            latest.write_text(str(run_dir), encoding="utf-8")

            exit_code = main(["report_compile", "--profile", "t4_safe", "--run", str(latest)])

            self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()

