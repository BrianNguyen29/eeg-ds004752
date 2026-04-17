from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.audit.gate0 import _write_json
from src.audit.gate0 import run_gate0_audit


class Gate0AuditTests(unittest.TestCase):
    def test_gate0_audit_generates_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ds004752"
            _write_minimal_dataset(root)
            output_root = Path(tmp) / "artifacts" / "gate0"

            result = run_gate0_audit(root, output_root)

            self.assertTrue(result.manifest_path.exists())
            self.assertTrue(result.cohort_lock_path.exists())
            self.assertTrue(result.audit_report_path.exists())
            self.assertTrue(result.override_log_path.exists())
            self.assertTrue(result.bridge_availability_path.exists())

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["subjects"]["n_subjects"], 1)
            self.assertEqual(manifest["subjects"]["n_sessions"], 1)
            self.assertEqual(manifest["events_audit"]["eeg_trials_total"], 2)
            self.assertEqual(manifest["events_audit"]["ieeg_trials_total"], 2)
            self.assertEqual(manifest["events_audit"]["core_field_mismatch_count"], 0)
            self.assertEqual(manifest["payload_state"]["edf"]["pointer_like_count"], 2)
            self.assertEqual(manifest["payload_state"]["mat"]["pointer_like_count"], 1)
            self.assertEqual(manifest["signal_audit"]["status"], "not_requested")

    def test_gate0_audit_can_record_signal_dependency_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ds004752"
            _write_minimal_dataset(root)
            output_root = Path(tmp) / "artifacts" / "gate0"

            result = run_gate0_audit(root, output_root, include_signal=True)

            manifest = result.manifest
            self.assertIn(manifest["signal_audit"]["status"], {"dependency_missing", "failed"})
            self.assertIn("signal_level_audit_not_passed", manifest["gate0_blockers"])

    def test_write_json_handles_numpy_like_scalars(self) -> None:
        class NumpyLikeScalar:
            def item(self) -> int:
                return 7

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manifest.json"
            _write_json(path, {"value": NumpyLikeScalar(), "path": Path("x")})

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["value"], 7)
            self.assertEqual(data["path"], "x")


def _write_minimal_dataset(root: Path) -> None:
    eeg = root / "sub-01" / "ses-01" / "eeg"
    ieeg = root / "sub-01" / "ses-01" / "ieeg"
    deriv = root / "derivatives" / "sub-01" / "beamforming"
    eeg.mkdir(parents=True)
    ieeg.mkdir(parents=True)
    deriv.mkdir(parents=True)

    (root / "dataset_description.json").write_text(
        json.dumps(
            {
                "Name": "Dataset of intracranial EEG, scalp EEG and beamforming sources from epilepsy patients performing a verbal working memory task",
                "BIDSVersion": "1.4.0",
                "DatasetType": "raw",
                "License": "CC0",
                "DatasetDOI": "doi:10.18112/openneuro.ds004752.v1.0.1",
            }
        ),
        encoding="utf-8",
    )
    (root / "participants.tsv").write_text(
        "participant_id\tage\tsex\tpathology\nsub-01\t24\tf\ttest\n",
        encoding="utf-8",
    )
    events = (
        "onset\tduration\tnTrial\tbegSample\tendSample\tSetSize\tProbeLetter\tMatch\tCorrect\tResponseTime\tArtifact\n"
        "0.005\t8\t1\t1\t1600\t8\tH\tOUT\t1\t2.484\t0\n"
        "8.005\t8\t2\t1601\t3200\t4\tT\tIN\t1\t1.66775\t1\n"
    )
    eeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_events.tsv").write_text(events, encoding="utf-8")
    ieeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_events.tsv").write_text(
        events.replace("0.005", "0.0005").replace("8.005", "8.0005"),
        encoding="utf-8",
    )
    eeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_channels.tsv").write_text(
        "name\ttype\tunits\tlow_cutoff\thigh_cutoff\tsampling_frequency\nF3\tEEG\tuV\t1000\t0.5\t200\n",
        encoding="utf-8",
    )
    ieeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_channels.tsv").write_text(
        "name\ttype\tunits\tlow_cutoff\thigh_cutoff\tsampling_frequency\nA1\tSEEG\tuV\t1000\t0.5\t2000\n",
        encoding="utf-8",
    )
    ieeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_electrodes.tsv").write_text(
        "name\tx\ty\tz\tsize\tAnatomicalLocation\nA1\t1\t2\t3\t1.3\tno_label_found\n",
        encoding="utf-8",
    )
    eeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_eeg.edf").write_text(
        "../../../.git/annex/objects/example/SHA256E-s1--payload.edf\n",
        encoding="utf-8",
    )
    ieeg.joinpath("sub-01_ses-01_task-verbalWM_run-01_ieeg.edf").write_text(
        "../../../.git/annex/objects/example/SHA256E-s1--payload.edf\n",
        encoding="utf-8",
    )
    deriv.joinpath("sub-01-task-verbalWM-LCMVsources.mat").write_text(
        "../../../.git/annex/objects/example/SHA256E-s1--payload.mat\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
