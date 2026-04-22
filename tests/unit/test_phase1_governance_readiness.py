from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.claim_state import run_phase1_governance_readiness


class Phase1GovernanceReadinessTests(unittest.TestCase):
    def test_governance_readiness_writes_fail_closed_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            gap_review = root / "phase1_gap_review" / "run"
            _write_prereg(prereg)
            _write_gap_review(gap_review)

            result = run_phase1_governance_readiness(
                prereg_bundle=prereg,
                gap_review_run=gap_review,
                output_root=root / "phase1_governance_readiness",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "phase1_control_suite_status.json").exists())
            self.assertTrue((result.output_dir / "phase1_calibration_package_status.json").exists())
            self.assertTrue((result.output_dir / "phase1_influence_status.json").exists())
            self.assertTrue((result.output_dir / "phase1_reporting_readiness.json").exists())
            self.assertTrue((result.output_dir / "phase1_claim_state.json").exists())
            self.assertTrue((root / "phase1_governance_readiness" / "latest.txt").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_governance_readiness_blocked")
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertIn("A4_privileged", summary["completed_non_claim_smoke_reviews"])
            self.assertFalse(summary["governance_surfaces"]["controls_claim_evaluable"])
            self.assertFalse(summary["governance_surfaces"]["calibration_claim_evaluable"])
            self.assertFalse(summary["governance_surfaces"]["influence_claim_evaluable"])
            self.assertFalse(summary["governance_surfaces"]["reporting_claim_evaluable"])

            controls = _read_json(result.output_dir / "phase1_control_suite_status.json")
            self.assertEqual(controls["status"], "phase1_control_suite_not_claim_evaluable")
            self.assertEqual(controls["config_status"], "executable")
            self.assertIn("final_control_manifest_missing", controls["blockers"])
            self.assertIn("final_negative_control_results_missing", controls["blockers"])

            calibration = _read_json(result.output_dir / "phase1_calibration_package_status.json")
            self.assertEqual(calibration["status"], "phase1_calibration_package_not_claim_evaluable")
            self.assertIn("final_calibration_manifest_missing", calibration["blockers"])
            self.assertEqual(calibration["threshold_sources"]["max_allowed_delta_ece"], 0.02)

            influence = _read_json(result.output_dir / "phase1_influence_status.json")
            self.assertEqual(influence["status"], "phase1_influence_package_not_claim_evaluable")
            self.assertIn("leave_one_subject_out_claim_state_checks_missing", influence["blockers"])
            self.assertEqual(influence["threshold_sources"]["gate1_influence_ceiling"], 0.40)

            claim_state = _read_json(result.output_dir / "phase1_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_claim_state_blocked")
            self.assertFalse(claim_state["claim_ready"])
            self.assertFalse(claim_state["full_phase1_claim_bearing_run_allowed"])
            self.assertIn("decoder efficacy", claim_state["not_ok_to_claim"])
            self.assertIn(
                "headline_claim_blocked_until_final_governance_package_passes",
                claim_state["blockers"],
            )

            reporting = _read_json(result.output_dir / "phase1_reporting_readiness.json")
            self.assertEqual(reporting["status"], "phase1_reporting_not_claim_evaluable")
            self.assertIn("main_phase1_report", reporting["missing_reporting_artifacts"])

    def test_cli_governance_readiness_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            gap_review = root / "phase1_gap_review" / "run"
            _write_prereg(prereg)
            _write_gap_review(gap_review)

            exit_code = main(
                [
                    "phase1_governance_readiness",
                    "--config",
                    str(prereg),
                    "--gap-review-run",
                    str(gap_review),
                    "--output-root",
                    str(root / "phase1_governance_readiness"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_governance_readiness" / "latest.txt").exists())


def _write_prereg(prereg: Path) -> None:
    _write_json(
        prereg,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
            "source_runs": {"gate0": "test-gate0-run"},
        },
    )


def _write_gap_review(gap_review: Path) -> None:
    gap_review.mkdir(parents=True, exist_ok=True)
    completed = [
        "A2_A2b",
        "A2c_CORAL",
        "A2d_riemannian",
        "A3_distillation",
        "A4_privileged",
    ]
    blockers = [
        "a3_a4_final_comparator_configs_or_runners_missing",
        "phase1_control_claim_metric_inference_surfaces_still_draft",
        "phase1_final_runner_control_calibration_influence_modules_missing",
        "headline_claim_blocked_until_full_comparator_suite_controls_calibration_influence_reporting_pass",
    ]
    _write_json(
        gap_review / "phase1_comparator_suite_gap_review_summary.json",
        {
            "status": "phase1_comparator_suite_gap_review_complete",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "completed_non_claim_smoke_reviews": completed,
            "blockers": blockers,
        },
    )
    _write_json(
        gap_review / "claim_readiness_blockers.json",
        {
            "status": "phase1_claim_readiness_blocked",
            "blockers": blockers,
            "claim_state": {
                "claim_ready": False,
                "headline_phase1_claim_open": False,
                "full_phase1_claim_bearing_run_allowed": False,
            },
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
