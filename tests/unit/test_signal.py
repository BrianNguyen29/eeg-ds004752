from __future__ import annotations

import unittest
from unittest.mock import patch

from src.audit.signal import run_signal_audit


class SignalAuditTests(unittest.TestCase):
    def test_signal_audit_reports_missing_dependencies(self) -> None:
        with patch("src.audit.signal.importlib.util.find_spec", return_value=None):
            result = run_signal_audit("does-not-matter")

        self.assertEqual(result["status"], "dependency_missing")
        self.assertIn("mne", result["missing_dependencies"])
        self.assertIn("scipy", result["missing_dependencies"])


if __name__ == "__main__":
    unittest.main()

