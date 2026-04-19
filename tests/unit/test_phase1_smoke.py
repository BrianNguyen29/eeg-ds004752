from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.smoke import run_phase1_smoke


class Phase1SmokeTests(unittest.TestCase):
    def test_phase1_smoke_writes_contract_artifacts_without_training(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_dataset(dataset)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            result = run_phase1_smoke(
                prereg_bundle=prereg,
                readiness_run=readiness,
                dataset_root=dataset,
                output_root=root / "phase1_smoke",
                repo_root=Path.cwd(),
                max_outer_folds=2,
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue((result.output_dir / "fold_logs").exists())
            self.assertTrue(result.comparator_table_path.exists())
            self.assertTrue(result.calibration_report_path.exists())
            self.assertTrue(result.negative_controls_report_path.exists())
            self.assertTrue(result.influence_report_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            comparator_table = json.loads(result.comparator_table_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "phase1_decoder_smoke_contract_complete")
            self.assertFalse(summary["decoder_trained"])
            self.assertFalse(summary["model_metrics_computed"])
            self.assertFalse(summary["claim_ready"])
            self.assertEqual(summary["n_outer_folds"], 2)
            self.assertEqual(comparator_table["blocking_missing_comparators"], [])

    def test_cli_phase1_smoke_help_exposes_contract_flags(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["phase1_real", "--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_cli_phase1_smoke_runs_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_dataset(dataset)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            exit_code = main(
                [
                    "phase1_real",
                    "--config",
                    str(prereg),
                    "--readiness-run",
                    str(readiness),
                    "--dataset-root",
                    str(dataset),
                    "--output-root",
                    str(root / "phase1_smoke"),
                    "--smoke",
                    "--max-outer-folds",
                    "1",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_smoke" / "latest.txt").exists())


def _write_gate0(gate0: Path) -> None:
    gate0.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_status": "signal_audit_ready",
        "signal_audit": {
            "status": "ok",
            "session_results": [
                {"status": "ok", "subject": "sub-01", "session": "ses-01"},
                {"status": "ok", "subject": "sub-02", "session": "ses-01"},
            ],
        },
        "gate0_blockers": [],
    }
    cohort = {
        "cohort_lock_status": "signal_audit_ready",
        "n_primary_eligible": 2,
        "participants": [
            {"participant_id": "sub-01", "primary_eligible": True},
            {"participant_id": "sub-02", "primary_eligible": True},
        ],
    }
    _write_json(gate0 / "manifest.json", manifest)
    _write_json(gate0 / "cohort_lock.json", cohort)


def _write_dataset(dataset: Path) -> None:
    for subject in ["sub-01", "sub-02"]:
        eeg = dataset / subject / "ses-01" / "eeg"
        ieeg = dataset / subject / "ses-01" / "ieeg"
        eeg.mkdir(parents=True, exist_ok=True)
        ieeg.mkdir(parents=True, exist_ok=True)
        stem = f"{subject}_ses-01_task-verbalWM_run-01"
        (eeg / f"{stem}_eeg.edf").write_text("fake edf", encoding="utf-8")
        (ieeg / f"{stem}_ieeg.edf").write_text("fake edf", encoding="utf-8")
        (eeg / f"{stem}_events.tsv").write_text(
            "onset\tduration\tSetSize\n0\t8\t4\n",
            encoding="utf-8",
        )


def _write_prereg(prereg: Path, gate0: Path) -> None:
    bundle = {
        "status": "locked",
        "prereg_bundle_hash_sha256": "test-prereg-hash",
        "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        "source_runs": {"gate0": str(gate0)},
        "comparator_cards": {
            "EEGNet": {},
            "A2d_riemannian": {},
            "A3_distillation": {},
            "A4_privileged": {},
        },
    }
    _write_json(prereg, bundle)


def _write_readiness(readiness: Path, gate0: Path, prereg: Path) -> None:
    readiness.mkdir(parents=True, exist_ok=True)
    data = {
        "status": "phase1_input_freeze_revised_comparator_complete",
        "source_of_truth": {
            "gate0": str(gate0),
            "base_prereg_bundle": str(prereg),
            "base_prereg_bundle_hash_sha256": "test-prereg-hash",
        },
        "authorization": {
            "decoder_smoke_allowed_under_guard": True,
            "full_phase1_substantive_run_allowed": True,
        },
        "revised_comparator_readiness": {
            "revision_available_comparator_ids": ["A2b", "A2c"],
            "available_comparator_ids_after_revision": [
                "A2b",
                "A2c",
                "A2d_riemannian",
                "A3_distillation",
                "A4_privileged",
            ],
        },
    }
    _write_json(readiness / "phase1_input_freeze_revision.json", data)


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

