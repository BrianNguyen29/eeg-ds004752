from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_claim_package import run_phase1_final_claim_package_plan


class Phase1FinalClaimPackagePlanTests(unittest.TestCase):
    def test_final_claim_package_plan_records_contract_and_keeps_claims_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance = root / "phase1_governance_readiness" / "run"
            _write_prereg(prereg)
            _write_governance_package(governance)

            result = run_phase1_final_claim_package_plan(
                prereg_bundle=prereg,
                governance_run=governance,
                output_root=root / "phase1_final_claim_package_plan",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "phase1_final_claim_package_contract.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_readiness.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_governance_boundary_review.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_claim_blocker_inventory.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_claim_state_plan.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_implementation_plan.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_claim_package_plan_recorded")
            self.assertEqual(summary["package_status"], "planning_non_claim")
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertIn("A4_privileged", summary["required_final_comparators"])
            self.assertIn("final_claim_package_config_not_locked", summary["blockers"])
            self.assertIn("a3_final_comparator_not_ready", summary["blockers"])
            self.assertIn("a4_final_comparator_not_ready", summary["blockers"])
            self.assertIn("final_control_results_missing", summary["blockers"])
            self.assertIn("final_calibration_package_missing", summary["blockers"])
            self.assertIn("final_influence_package_missing", summary["blockers"])
            self.assertIn("final_reporting_package_missing", summary["blockers"])

            contract = _read_json(result.output_dir / "phase1_final_claim_package_contract.json")
            self.assertEqual(contract["primary_endpoint"]["primary_metric"], "balanced_accuracy")
            self.assertEqual(contract["locked_threshold_references"]["subject_level_sesoi_delta_ba"], 0.03)
            self.assertEqual(contract["locked_threshold_references"]["max_allowed_delta_ece"], 0.02)
            self.assertEqual(contract["locked_threshold_references"]["gate1_influence_ceiling"], 0.40)
            self.assertFalse(contract["claim_opening_rules"]["smoke_metrics_allowed_as_claim_evidence"])

            claim_state = _read_json(result.output_dir / "phase1_final_claim_state_plan.json")
            self.assertEqual(claim_state["status"], "phase1_final_claim_state_plan_blocked")
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("A4 superiority over A2/A2b/A2c/A2d/A3", claim_state["not_ok_to_claim"])

    def test_cli_final_claim_package_plan_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance = root / "phase1_governance_readiness" / "run"
            _write_prereg(prereg)
            _write_governance_package(governance)

            exit_code = main(
                [
                    "phase1_final_claim_package_plan",
                    "--config",
                    str(prereg),
                    "--governance-run",
                    str(governance),
                    "--output-root",
                    str(root / "phase1_final_claim_package_plan"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_claim_package_plan" / "latest.txt").exists())


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


def _write_governance_package(governance: Path) -> None:
    governance.mkdir(parents=True, exist_ok=True)
    completed = ["A2_A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]
    blockers = [
        "a3_a4_final_comparator_configs_or_runners_missing",
        "phase1_control_claim_metric_inference_surfaces_still_draft",
        "phase1_final_runner_control_calibration_influence_modules_missing",
        "headline_claim_blocked_until_final_governance_package_passes",
    ]
    _write_json(
        governance / "phase1_governance_readiness_summary.json",
        {
            "status": "phase1_governance_readiness_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "completed_non_claim_smoke_reviews": completed,
            "governance_surfaces": {
                "controls_claim_evaluable": False,
                "calibration_claim_evaluable": False,
                "influence_claim_evaluable": False,
                "reporting_claim_evaluable": False,
            },
            "blockers": blockers,
        },
    )
    _write_json(
        governance / "phase1_claim_state.json",
        {
            "status": "phase1_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "completed_non_claim_smoke_reviews": completed,
            "blockers": blockers,
        },
    )
    _write_json(governance / "phase1_control_suite_status.json", {"claim_evaluable": False, "blockers": []})
    _write_json(governance / "phase1_calibration_package_status.json", {"claim_evaluable": False, "blockers": []})
    _write_json(governance / "phase1_influence_status.json", {"claim_evaluable": False, "blockers": []})
    _write_json(governance / "phase1_reporting_readiness.json", {"claim_evaluable": False, "blockers": []})


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
