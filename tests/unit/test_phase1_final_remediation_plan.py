from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_remediation_plan import run_phase1_final_remediation_plan


class Phase1FinalRemediationPlanTests(unittest.TestCase):
    def test_remediation_plan_preserves_fail_closed_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            closeout_run = root / "phase1_final_claim_state_closeout" / "run"
            _write_prereg(prereg)
            _write_closeout(closeout_run)

            result = run_phase1_final_remediation_plan(
                prereg_bundle=prereg,
                final_claim_state_closeout_run=closeout_run,
                output_root=root / "phase1_final_remediation_plan",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            blocker_review = _read_json(result.output_dir / "phase1_final_remediation_blocker_review.json")
            workplan = _read_json(result.output_dir / "phase1_final_remediation_workplan.json")
            claim_state = _read_json(result.output_dir / "phase1_final_remediation_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_remediation_plan_recorded")
            self.assertEqual(summary["blocking_surfaces"], ["controls", "calibration", "influence"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["claims_opened"])
            self.assertTrue(summary["final_claim_blocked"])
            self.assertTrue(summary["revision_required_for_remediation"])
            self.assertEqual(summary["next_step"], "start_revision_scoped_controls_remediation_audit")
            self.assertEqual(blocker_review["blocking_surfaces"], ["controls", "calibration", "influence"])
            self.assertEqual([item["surface"] for item in workplan["work_items"]], ["controls", "calibration", "influence"])
            self.assertIn("threshold_relaxation_after_observed_failure", workplan["work_items"][0]["must_not_do"])
            self.assertFalse(claim_state["headline_phase1_claim_open"])
            self.assertTrue((result.output_dir / "phase1_final_remediation_decision_memo.md").exists())

    def test_cli_remediation_plan_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            closeout_run = root / "phase1_final_claim_state_closeout" / "run"
            output_root = root / "phase1_final_remediation_plan"
            _write_prereg(prereg)
            _write_closeout(closeout_run)

            exit_code = main(
                [
                    "phase1_final_remediation_plan",
                    "--config",
                    str(prereg),
                    "--claim-state-closeout-run",
                    str(closeout_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_remediation_plan_summary.json")
            self.assertEqual(summary["status"], "phase1_final_remediation_plan_recorded")
            self.assertFalse(summary["claim_ready"])


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_closeout(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    blockers = [
        "controls:final_control_manifest_status_not_claim_evaluable",
        "controls:final_control_suite_not_passed",
        "calibration:final_calibration_manifest_status_not_claim_evaluable",
        "calibration:final_calibration_package_not_passed",
        "influence:final_influence_manifest_status_not_claim_evaluable",
        "influence:final_influence_package_not_passed",
        "controls_calibration_influence_reporting_missing",
        "headline_claim_blocked_until_full_package_passes",
        "final_governance_reconciliation_incomplete",
    ]
    _write_json(
        run_dir / "phase1_final_claim_state_closeout_summary.json",
        {
            "status": "phase1_final_claim_blocked_fail_closed",
            "final_governance_reconciliation_run": "/tmp/phase1_final_governance_reconciliation/run",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "claims_opened": False,
            "final_claim_blocked": True,
            "blocking_surfaces": ["controls", "calibration", "influence"],
            "claim_blockers": blockers,
            "revision_required_for_remediation": True,
        },
    )
    _write_json(
        run_dir / "phase1_final_claim_state_closeout_input_validation.json",
        {"status": "phase1_final_claim_state_closeout_inputs_ready", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_blocker_table.json",
        {
            "status": "phase1_final_blocker_table_recorded",
            "rows": [
                {
                    "surface": "controls",
                    "claim_evaluable": False,
                    "status": "phase1_control_suite_not_claim_evaluable",
                    "blockers": ["final_control_manifest_status_not_claim_evaluable", "final_control_suite_not_passed"],
                    "blocking": True,
                },
                {
                    "surface": "calibration",
                    "claim_evaluable": False,
                    "status": "phase1_calibration_package_not_claim_evaluable",
                    "blockers": [
                        "final_calibration_manifest_status_not_claim_evaluable",
                        "final_calibration_package_not_passed",
                    ],
                    "blocking": True,
                },
                {
                    "surface": "influence",
                    "claim_evaluable": False,
                    "status": "phase1_influence_package_not_claim_evaluable",
                    "blockers": ["final_influence_manifest_status_not_claim_evaluable", "final_influence_package_not_passed"],
                    "blocking": True,
                },
                {
                    "surface": "reporting",
                    "claim_evaluable": True,
                    "status": "phase1_final_reporting_claim_evaluable",
                    "blockers": [],
                    "blocking": False,
                },
            ],
            "global_blockers": [
                "controls_calibration_influence_reporting_missing",
                "headline_claim_blocked_until_full_package_passes",
                "final_governance_reconciliation_incomplete",
            ],
            "blocking_surfaces": ["controls", "calibration", "influence"],
        },
    )
    _write_json(
        run_dir / "phase1_final_claim_disposition.json",
        {
            "status": "phase1_final_claim_blocked_fail_closed",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "claims_opened": False,
            "final_claim_blocked": True,
            "revision_required_for_remediation": True,
            "blockers": blockers,
        },
    )
    _write_json(
        run_dir / "phase1_final_claim_state_closeout_manifest.json",
        {
            "status": "phase1_final_claim_state_closeout_manifest_recorded",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "claims_opened": False,
            "final_claim_blocked": True,
        },
    )
    _write_json(
        run_dir / "phase1_final_claim_state_closeout_source_links.json",
        {"status": "phase1_final_claim_state_closeout_source_links_recorded"},
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
