from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.a2d_smoke import run_phase1_a2d_smoke


class Phase1A2dSmokeTests(unittest.TestCase):
    def test_a2d_smoke_writes_non_claim_artifacts_and_alignment_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            result = run_phase1_a2d_smoke(
                prereg_bundle=prereg,
                readiness_run=readiness,
                dataset_root=dataset,
                output_root=root / "phase1_a2d_smoke",
                repo_root=Path.cwd(),
                max_outer_folds=2,
                precomputed_rows=_precomputed_covariance_rows(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "fold_logs").exists())
            self.assertTrue((result.output_dir / "a2d_logits_smoke").exists())
            self.assertTrue((result.output_dir / "a2d_metrics_smoke.json").exists())
            self.assertTrue((result.output_dir / "a2d_alignment_audit.json").exists())
            self.assertTrue((result.output_dir / "a2d_covariance_manifest.json").exists())
            self.assertTrue((result.output_dir / "calibration_a2d_smoke_report.json").exists())
            self.assertTrue((result.output_dir / "negative_controls_a2d_smoke_report.json").exists())
            self.assertTrue((result.output_dir / "influence_a2d_smoke_report.json").exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "phase1_a2d_riemannian_smoke_complete")
            self.assertEqual(summary["comparator"], "A2d_riemannian")
            self.assertEqual(summary["n_outer_folds"], 2)
            self.assertTrue(summary["decoder_trained"])
            self.assertTrue(summary["model_metrics_computed"])
            self.assertFalse(summary["final_a2d_comparator"])
            self.assertFalse(summary["claim_ready"])
            self.assertTrue(summary["does_not_estimate_privileged_transfer_efficacy"])

            alignment = json.loads((result.output_dir / "a2d_alignment_audit.json").read_text(encoding="utf-8"))
            self.assertFalse(alignment["outer_test_subject_used_for_fit"])
            for fold in alignment["folds"]:
                self.assertTrue(fold["no_outer_test_subject_in_any_fit"])
                self.assertNotIn(fold["outer_test_subject"], fold["reference_fit_subjects"])
                self.assertNotIn(fold["outer_test_subject"], fold["classifier_fit_subjects"])

    def test_cli_phase1_help_exposes_a2d_smoke_flag(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["phase1_real", "--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_a2d_smoke_aligns_covariances_to_common_channels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            result = run_phase1_a2d_smoke(
                prereg_bundle=prereg,
                readiness_run=readiness,
                dataset_root=dataset,
                output_root=root / "phase1_a2d_smoke",
                repo_root=Path.cwd(),
                max_outer_folds=2,
                precomputed_rows=_precomputed_covariance_rows_with_extra_channel(),
            )

            manifest = json.loads((result.output_dir / "a2d_covariance_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["matrix_shapes"], ["3x3"])


def _precomputed_covariance_rows() -> dict[str, object]:
    rows = []
    for subject_index, subject in enumerate(["sub-01", "sub-02", "sub-03"], start=1):
        for trial in range(8):
            label = trial % 2
            signal = 0.35 if label else -0.15
            offset = subject_index * 0.03 + trial * 0.002
            rows.append(
                {
                    "subject": subject,
                    "session": "ses-01",
                    "trial_id": f"{trial + 1}",
                    "set_size": 8 if label else 4,
                    "label": label,
                    "covariance": [
                        [1.2 + signal + offset, 0.08, 0.02],
                        [0.08, 1.1 - signal / 2.0 + offset, 0.03],
                        [0.02, 0.03, 0.9 + offset],
                    ],
                    "channel_names": ["C1", "C2", "C3"],
                }
            )
    return {
        "status": "test_precomputed_covariance_rows",
        "rows": rows,
        "skipped_sessions": [],
        "read_fallbacks": [],
    }


def _precomputed_covariance_rows_with_extra_channel() -> dict[str, object]:
    rows = _precomputed_covariance_rows()["rows"]
    expanded = []
    for index, row in enumerate(rows):
        item = dict(row)
        if index % 2 == 0:
            item["covariance"] = [
                [1.0, 0.02, 0.01, 0.0],
                [0.02, 1.1, 0.03, 0.0],
                [0.01, 0.03, 0.9, 0.0],
                [0.0, 0.0, 0.0, 0.8],
            ]
            item["channel_names"] = ["C1", "C2", "C3", "EXTRA"]
        expanded.append(item)
    return {
        "status": "test_precomputed_covariance_rows_with_extra_channel",
        "rows": expanded,
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
