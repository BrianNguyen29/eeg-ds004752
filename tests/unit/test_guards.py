from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.guards import GuardError, assert_real_phase_allowed


class GuardTests(unittest.TestCase):
    def test_draft_prereg_blocks_real_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prereg_bundle.json"
            path.write_text(json.dumps({"status": "draft_blocked", "artifact_hashes": {}}), encoding="utf-8")

            with self.assertRaises(GuardError):
                assert_real_phase_allowed("phase1_real", path)

    def test_locked_prereg_requires_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prereg_bundle.json"
            path.write_text(json.dumps({"status": "locked", "artifact_hashes": {}}), encoding="utf-8")

            with self.assertRaises(GuardError):
                assert_real_phase_allowed("phase1_real", path)

    def test_locked_prereg_with_hashes_allows_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "prereg_bundle.json"
            bundle = {"status": "locked", "artifact_hashes": {"manifest": "abc"}}
            path.write_text(json.dumps(bundle), encoding="utf-8")

            self.assertEqual(assert_real_phase_allowed("phase1_real", path), bundle)


if __name__ == "__main__":
    unittest.main()

