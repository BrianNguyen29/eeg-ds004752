from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.model_smoke import run_phase1_model_smoke


class Phase1ModelSmokeTests(unittest.TestCase):
    def test_phase1_model_smoke_writes_non_claim_a2_a2b_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            result = run_phase1_model_smoke(
                prereg_bundle=prereg,
                readiness_run=readiness,
                dataset_root=dataset,
                output_root=root / "phase1_model_smoke",
                repo_root=Path.cwd(),
                comparators=["A2", "A2b"],
                max_outer_folds=2,
                precomputed_rows=_precomputed_rows(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "fold_logs").exists())
            self.assertTrue((result.output_dir / "a2_a2b_logits_smoke").exists())
            self.assertTrue((result.output_dir / "a2_metrics_smoke.json").exists())
            self.assertTrue((result.output_dir / "a2b_metrics_smoke.json").exists())
            self.assertTrue((result.output_dir / "calibration_model_smoke_report.json").exists())
            self.assertTrue((result.output_dir / "negative_controls_model_smoke_report.json").exists())
            self.assertTrue((result.output_dir / "influence_model_smoke_report.json").exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "phase1_a2_a2b_model_smoke_complete")
            self.assertTrue(summary["decoder_trained"])
            self.assertTrue(summary["model_metrics_computed"])
            self.assertFalse(summary["final_eegnet_comparator"])
            self.assertFalse(summary["claim_ready"])
            self.assertTrue(summary["does_not_estimate_privileged_transfer_efficacy"])
            self.assertEqual(summary["comparators"], ["A2", "A2b"])
            self.assertEqual(summary["n_outer_folds"], 2)

    def test_cli_phase1_help_exposes_model_smoke_flags(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["phase1_real", "--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_model_smoke_rejects_unsupported_comparator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            with self.assertRaisesRegex(Exception, "supports only A2/A2b"):
                run_phase1_model_smoke(
                    prereg_bundle=prereg,
                    readiness_run=readiness,
                    dataset_root=root / "data",
                    output_root=root / "phase1_model_smoke",
                    comparators=["A4_privileged"],
                    precomputed_rows=_precomputed_rows(),
                )


def _precomputed_rows() -> dict[str, object]:
    rows = []
    for subject_index, subject in enumerate(["sub-01", "sub-02", "sub-03"], start=1):
        for trial in range(8):
            label = trial % 2
            rows.append(
                {
                    "subject": subject,
                    "session": "ses-01",
                    "trial_id": f"{trial + 1}",
                    "set_size": 8 if label else 4,
                    "label": label,
                    "features": [
                        float(label) + subject_index * 0.01,
                        float(1 - label) + subject_index * 0.02,
                        float(trial) / 10.0,
                    ],
                }
            )
    return {
        "status": "test_precomputed_rows",
        "rows": rows,
        "feature_names": ["f1", "f2", "f3"],
        "skipped_sessions": [],
        "read_fallbacks": [],
    }


def _write_gate0(gate0: Path) -> None:
    gate0.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_status": "signal_audit_ready",
        "signal_audit": {
            "status": "ok",
            "session_results": [
                {"status": "ok", "subject": "sub-01", "session": "ses-01"},
                {"status": "ok", "subject": "sub-02", "session": "ses-01"},
                {"status": "ok", "subject": "sub-03", "session": "ses-01"},
            ],
        },
        "gate0_blockers": [],
    }
    cohort = {
        "cohort_lock_status": "signal_audit_ready",
        "n_primary_eligible": 3,
        "participants": [
            {"participant_id": "sub-01", "primary_eligible": True},
            {"participant_id": "sub-02", "primary_eligible": True},
            {"participant_id": "sub-03", "primary_eligible": True},
        ],
    }
    _write_json(gate0 / "manifest.json", manifest)
    _write_json(gate0 / "cohort_lock.json", cohort)


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
