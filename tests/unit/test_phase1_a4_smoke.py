from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.a4_smoke import Phase1A4SmokeError, run_phase1_a4_smoke


class Phase1A4SmokeTests(unittest.TestCase):
    def test_a4_smoke_writes_non_claim_artifacts_and_privileged_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            result = run_phase1_a4_smoke(
                prereg_bundle=prereg,
                readiness_run=readiness,
                dataset_root=dataset,
                output_root=root / "phase1_a4_smoke",
                repo_root=Path.cwd(),
                max_outer_folds=2,
                precomputed_rows=_precomputed_feature_rows(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "fold_logs").exists())
            self.assertTrue((result.output_dir / "a4_logits_smoke").exists())
            self.assertTrue((result.output_dir / "a4_metrics_smoke.json").exists())
            self.assertTrue((result.output_dir / "a4_privileged_train_time_audit.json").exists())
            self.assertTrue((result.output_dir / "a4_privileged_manifest.json").exists())
            self.assertTrue((result.output_dir / "a4_gate_manifest.json").exists())
            self.assertTrue((result.output_dir / "a4_feature_manifest.json").exists())
            self.assertTrue((result.output_dir / "calibration_a4_smoke_report.json").exists())
            self.assertTrue((result.output_dir / "negative_controls_a4_smoke_report.json").exists())
            self.assertTrue((result.output_dir / "influence_a4_smoke_report.json").exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "phase1_a4_privileged_smoke_complete")
            self.assertEqual(summary["comparator"], "A4_privileged")
            self.assertEqual(summary["n_outer_folds"], 2)
            self.assertTrue(summary["decoder_trained"])
            self.assertTrue(summary["model_metrics_computed"])
            self.assertFalse(summary["final_a4_comparator"])
            self.assertFalse(summary["claim_ready"])
            self.assertTrue(summary["does_not_estimate_privileged_transfer_efficacy"])

            audit = json.loads((result.output_dir / "a4_privileged_train_time_audit.json").read_text(encoding="utf-8"))
            self.assertFalse(audit["outer_test_subject_used_for_any_fit"])
            self.assertFalse(audit["real_ieeg_privileged_used"])
            self.assertFalse(audit["privileged_used_at_inference"])
            for fold in audit["folds"]:
                self.assertTrue(fold["no_outer_test_subject_in_any_fit"])
                self.assertTrue(fold["no_outer_test_subject_in_normalization_fit"])
                self.assertTrue(fold["no_outer_test_subject_in_gate_weight_fit"])
                self.assertTrue(fold["no_outer_test_subject_in_privileged_proxy_fit"])
                self.assertTrue(fold["no_outer_test_subject_in_privileged_outputs_for_student_fit"])
                self.assertTrue(fold["no_outer_test_subject_in_student_fit"])
                self.assertTrue(fold["student_inference_uses_scalp_only"])
                self.assertFalse(fold["privileged_used_at_inference"])
                self.assertFalse(fold["teacher_used_at_inference"])
                self.assertFalse(fold["real_ieeg_privileged_used"])
                self.assertNotIn(fold["outer_test_subject"], fold["normalization_fit_subjects"])
                self.assertNotIn(fold["outer_test_subject"], fold["gate_weight_fit_subjects"])
                self.assertNotIn(fold["outer_test_subject"], fold["privileged_proxy_fit_subjects"])
                self.assertNotIn(fold["outer_test_subject"], fold["privileged_outputs_for_student_fit_subjects"])
                self.assertNotIn(fold["outer_test_subject"], fold["student_fit_subjects"])

            privileged_manifest = json.loads((result.output_dir / "a4_privileged_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(privileged_manifest["status"], "a4_privileged_manifest_smoke")
            self.assertFalse(privileged_manifest["real_ieeg_privileged_used"])
            self.assertFalse(privileged_manifest["privileged_used_at_inference"])
            self.assertEqual(privileged_manifest["student_inference_policy"], "scalp_features_only")

            gate_manifest = json.loads((result.output_dir / "a4_gate_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(gate_manifest["status"], "a4_gate_manifest_smoke")
            self.assertFalse(gate_manifest["uses_outer_test_subject"])

    def test_a4_smoke_requires_both_classes_per_fold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            dataset = root / "data" / "ds004752"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)

            rows = _precomputed_feature_rows()
            for row in rows["rows"]:
                if row["subject"] == "sub-01":
                    row["label"] = 1
                    row["set_size"] = 8

            with self.assertRaises(Phase1A4SmokeError):
                run_phase1_a4_smoke(
                    prereg_bundle=prereg,
                    readiness_run=readiness,
                    dataset_root=dataset,
                    output_root=root / "phase1_a4_smoke",
                    repo_root=Path.cwd(),
                    max_outer_folds=1,
                    precomputed_rows=rows,
                )

    def test_cli_phase1_help_exposes_a4_smoke_flag(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["phase1_real", "--help"])
        self.assertEqual(raised.exception.code, 0)


def _precomputed_feature_rows() -> dict[str, object]:
    rows = []
    for subject_index, subject in enumerate(["sub-01", "sub-02", "sub-03"], start=1):
        domain_shift = subject_index * 0.09
        for trial in range(8):
            label = trial % 2
            signal = 0.52 if label else -0.42
            rows.append(
                {
                    "subject": subject,
                    "session": "ses-01",
                    "trial_id": f"{trial + 1}",
                    "set_size": 8 if label else 4,
                    "label": label,
                    "features": [
                        signal + domain_shift + trial * 0.01,
                        -signal * 0.3 + domain_shift * 0.25,
                        subject_index * 0.04 + label * 0.06,
                        0.07 * trial,
                    ],
                }
            )
    return {
        "status": "test_precomputed_feature_rows",
        "rows": rows,
        "feature_names": ["f0", "f1", "f2", "f3"],
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
            "A2c_CORAL": {},
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
