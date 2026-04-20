from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.gap_review import run_phase1_gap_review


class Phase1GapReviewTests(unittest.TestCase):
    def test_gap_review_records_blockers_without_claiming_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            a2 = root / "a2"
            a2c = root / "a2c"
            a2d = root / "a2d"
            a3 = root / "a3"
            a4 = root / "a4"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)
            _write_review(a2, "phase1_a2_a2b_model_smoke_review_note.json", "phase1_a2_a2b_model_smoke_review_pass_non_claim")
            _write_review(a2c, "phase1_a2c_coral_smoke_review_note.json", "phase1_a2c_coral_smoke_review_pass_non_claim")
            _write_review(a2d, "phase1_a2d_riemannian_smoke_review_note.json", "phase1_a2d_riemannian_smoke_review_pass_non_claim")
            _write_review(a3, "phase1_a3_distillation_smoke_review_note.json", "phase1_a3_distillation_smoke_review_pass_non_claim")
            _write_review(a4, "phase1_a4_privileged_smoke_review_note.json", "phase1_a4_privileged_smoke_review_pass_non_claim")

            result = run_phase1_gap_review(
                prereg_bundle=prereg,
                readiness_run=readiness,
                output_root=root / "phase1_gap_review",
                repo_root=Path.cwd(),
                reviewed_runs={
                    "A2_A2b": a2,
                    "A2c_CORAL": a2c,
                    "A2d_riemannian": a2d,
                    "A3_distillation": a3,
                    "A4_privileged": a4,
                },
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "comparator_suite_status.json").exists())
            self.assertTrue((result.output_dir / "claim_readiness_blockers.json").exists())
            self.assertTrue((result.output_dir / "implementation_backlog.json").exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "phase1_comparator_suite_gap_review_complete")
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertIn("A2_A2b", summary["completed_non_claim_smoke_reviews"])
            self.assertIn("A2c_CORAL", summary["completed_non_claim_smoke_reviews"])
            self.assertIn("A2d_riemannian", summary["completed_non_claim_smoke_reviews"])
            self.assertIn("A3_distillation", summary["completed_non_claim_smoke_reviews"])
            self.assertIn("A4_privileged", summary["completed_non_claim_smoke_reviews"])
            self.assertIn("a3_a4_final_comparator_configs_or_runners_missing", summary["blockers"])
            self.assertIn("phase1_control_claim_metric_inference_surfaces_still_draft", summary["blockers"])
            self.assertNotIn("required_non_claim_smoke_reviews_not_all_passed", summary["blockers"])
            self.assertIn("controls", {item["surface"] for item in summary["draft_governance_surfaces"]})
            self.assertIn(
                "A3_distillation",
                {item["comparator"] for item in summary["missing_or_not_final_comparators"]},
            )
            self.assertIn(
                "A4_privileged",
                {item["comparator"] for item in summary["missing_or_not_final_comparators"]},
            )

            blockers = json.loads((result.output_dir / "claim_readiness_blockers.json").read_text(encoding="utf-8"))
            self.assertEqual(blockers["status"], "phase1_claim_readiness_blocked")
            self.assertFalse(blockers["claim_state"]["full_phase1_claim_bearing_run_allowed"])
            self.assertFalse(blockers["claim_state"]["headline_phase1_claim_open"])

    def test_cli_gap_review_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            readiness = root / "phase1_readiness" / "run"
            prereg = root / "prereg_bundle.json"
            a2 = root / "a2"
            a2c = root / "a2c"
            a2d = root / "a2d"
            a3 = root / "a3"
            a4 = root / "a4"
            _write_gate0(gate0)
            _write_prereg(prereg, gate0)
            _write_readiness(readiness, gate0, prereg)
            _write_review(a2, "phase1_a2_a2b_model_smoke_review_note.json", "phase1_a2_a2b_model_smoke_review_pass_non_claim")
            _write_review(a2c, "phase1_a2c_coral_smoke_review_note.json", "phase1_a2c_coral_smoke_review_pass_non_claim")
            _write_review(a2d, "phase1_a2d_riemannian_smoke_review_note.json", "phase1_a2d_riemannian_smoke_review_pass_non_claim")
            _write_review(a3, "phase1_a3_distillation_smoke_review_note.json", "phase1_a3_distillation_smoke_review_pass_non_claim")
            _write_review(a4, "phase1_a4_privileged_smoke_review_note.json", "phase1_a4_privileged_smoke_review_pass_non_claim")

            exit_code = main(
                [
                    "phase1_gap_review",
                    "--config",
                    str(prereg),
                    "--readiness-run",
                    str(readiness),
                    "--output-root",
                    str(root / "phase1_gap_review"),
                    "--a2-a2b-run",
                    str(a2),
                    "--a2c-run",
                    str(a2c),
                    "--a2d-run",
                    str(a2d),
                    "--a3-run",
                    str(a3),
                    "--a4-run",
                    str(a4),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_gap_review" / "latest.txt").exists())


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


def _write_review(run_dir: Path, filename: str, status: str) -> None:
    _write_json(run_dir / filename, {"status": status})


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
