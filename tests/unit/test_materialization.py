from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.audit.materialization import build_materialization_report, payload_state_from_report


class MaterializationTests(unittest.TestCase):
    def test_report_distinguishes_materialized_and_missing_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            materialized = root / "sub-01" / "ses-01" / "eeg" / "ok_eeg.edf"
            missing = root / "sub-01" / "ses-02" / "eeg" / "missing_eeg.edf"
            mat = root / "derivatives" / "sub-01" / "beamforming" / "ok.mat"
            annex_internal = root / ".git" / "annex" / "objects" / "internal.edf"
            materialized.parent.mkdir(parents=True)
            missing.parent.mkdir(parents=True)
            mat.parent.mkdir(parents=True)
            annex_internal.parent.mkdir(parents=True)
            materialized.write_bytes(b"0" * 5000)
            missing.write_text(".git/annex/objects/SHA256E-s1--missing.edf\n", encoding="utf-8")
            mat.write_bytes(b"1" * 6000)
            annex_internal.write_bytes(b"2" * 5000)

            report = build_materialization_report(root)
            state = payload_state_from_report(report)

            self.assertEqual(report["status"], "incomplete")
            self.assertEqual(state["edf"]["count"], 2)
            self.assertEqual(state["edf"]["materialized_count"], 1)
            self.assertEqual(state["edf"]["pointer_like_count"], 1)
            self.assertEqual(state["mat"]["materialized_count"], 1)
            self.assertEqual(report["payloads"]["edf"]["missing_examples"][0]["relative_path"], "sub-01/ses-02/eeg/missing_eeg.edf")


if __name__ == "__main__":
    unittest.main()
