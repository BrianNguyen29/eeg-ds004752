from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.audit.signal import _read_edf_header_info, _select_session_dirs, run_signal_audit


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

    def test_read_edf_header_info_minimal_uniform_channels(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "minimal.edf"
            _write_minimal_edf(path, n_records=2, record_duration=1.0, n_channels=3, samples_per_record=200)

            info = _read_edf_header_info(path)

            self.assertEqual(info.n_channels, 3)
            self.assertEqual(info.n_times, 400)
            self.assertEqual(info.sfreq, 200.0)
            self.assertEqual(info.duration_sec, 2.0)


def _field(value: str, width: int) -> bytes:
    encoded = value.encode("ascii")
    if len(encoded) > width:
        raise ValueError(value)
    return encoded.ljust(width, b" ")


def _write_minimal_edf(
    path: Path,
    n_records: int,
    record_duration: float,
    n_channels: int,
    samples_per_record: int,
) -> None:
    header_bytes = 256 + (256 * n_channels)
    fixed = b"".join(
        [
            _field("0", 8),
            _field("X", 80),
            _field("Y", 80),
            _field("01.01.01", 8),
            _field("01.02.03", 8),
            _field(str(header_bytes), 8),
            _field("", 44),
            _field(str(n_records), 8),
            _field(str(record_duration), 8),
            _field(str(n_channels), 4),
        ]
    )
    per_signal = b"".join(
        [
            b"".join(_field(f"ch{i}", 16) for i in range(n_channels)),
            b"".join(_field("", 80) for _ in range(n_channels)),
            b"".join(_field("uV", 8) for _ in range(n_channels)),
            b"".join(_field("-1", 8) for _ in range(n_channels)),
            b"".join(_field("1", 8) for _ in range(n_channels)),
            b"".join(_field("-32768", 8) for _ in range(n_channels)),
            b"".join(_field("32767", 8) for _ in range(n_channels)),
            b"".join(_field("", 80) for _ in range(n_channels)),
            b"".join(_field(str(samples_per_record), 8) for _ in range(n_channels)),
            b"".join(_field("", 32) for _ in range(n_channels)),
        ]
    )
    path.write_bytes(fixed + per_signal)


if __name__ == "__main__":
    unittest.main()
