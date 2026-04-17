from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.audit.signal import _select_session_dirs, run_signal_audit


class SignalAuditTests(unittest.TestCase):
    def test_signal_audit_reports_missing_dependencies(self) -> None:
        with patch("src.audit.signal.importlib.util.find_spec", return_value=None):
            result = run_signal_audit("does-not-matter")

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("mne", result["missing_dependencies"])
        self.assertIn("scipy", result["missing_dependencies"])

    def test_select_session_dirs_filters_subjects_and_sessions(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            for subject in ("sub-01", "sub-02"):
                for session in ("ses-01", "ses-02"):
                    (root / subject / session).mkdir(parents=True)

            selected = _select_session_dirs(root, ["sub-02"], ["ses-01"])

            self.assertEqual([path.as_posix().split("/")[-2:] for path in selected], [["sub-02", "ses-01"]])


if __name__ == "__main__":
    unittest.main()
