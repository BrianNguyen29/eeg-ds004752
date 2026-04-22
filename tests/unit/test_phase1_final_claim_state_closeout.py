from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_claim_state_closeout import run_phase1_final_claim_state_closeout


class Phase1FinalClaimStateCloseoutTests(unittest.TestCase):
    def test_closeout_records_fail_closed_disposition_without_opening_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance_run = root / "phase1_final_governance_reconciliation" / "run"
            _write_prereg(prereg)
            _write_governance_reconciliation(governance_run)

            result = run_phase1_final_claim_state_closeout(
                prereg_bundle=prereg,
                final_governance_reconciliation_run=governance_run,
                output_root=root / "phase1_final_claim_state_closeout",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            disposition = _read_json(result.output_dir / "phase1_final_claim_disposition.json")
            blocker_table = _read_json(result.output_dir / "phase1_final_blocker_table.json")
            manifest = _read_json(result.output_dir / "phase1_final_claim_state_closeout_manifest.json")

            self.assertEqual(summary["status"], "phase1_final_claim_blocked_fail_closed")
            self.assertTrue(summary["comparator_outputs_complete"])
            self.assertTrue(summary["runtime_logs_audited_for_all_required_comparators"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["claims_opened"])
            self.assertTrue(summary["final_claim_blocked"])
            self.assertEqual(summary["blocking_surfaces"], ["controls", "calibration", "influence"])
            self.assertIn("controls:final_control_suite_not_passed", summary["claim_blockers"])
            self.assertTrue(disposition["revision_required_for_remediation"])
            self.assertFalse(disposition["claims_opened"])
            self.assertEqual(blocker_table["blocking_surfaces"], ["controls", "calibration", "influence"])
            self.assertFalse(manifest["claim_ready"])
            self.assertTrue((result.output_dir / "phase1_final_revision_decision_memo.md").exists())

    def test_cli_closeout_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance_run = root / "phase1_final_governance_reconciliation" / "run"
            output_root = root / "phase1_final_claim_state_closeout"
            _write_prereg(prereg)
            _write_governance_reconciliation(governance_run)

            exit_code = main(
                [
                    "phase1_final_claim_state_closeout",
                    "--config",
                    str(prereg),
                    "--governance-reconciliation-run",
                    str(governance_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_claim_state_closeout_summary.json")
            self.assertEqual(summary["status"], "phase1_final_claim_blocked_fail_closed")
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


def _write_governance_reconciliation(run_dir: Path) -> None:
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
        run_dir / "phase1_final_governance_reconciliation_summary.json",
        {
            "status": "phase1_final_governance_reconciliation_blocked",
            "comparator_reconciliation_run": "/tmp/phase1_final_comparator_reconciliation/run",
            "comparator_outputs_complete": True,
            "runtime_logs_audited_for_all_required_comparators": True,
            "governance_surfaces": {
                "controls_claim_evaluable": False,
                "calibration_claim_evaluable": False,
                "influence_claim_evaluable": False,
                "reporting_claim_evaluable": True,
            },
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "claim_blockers": blockers,
        },
    )
    _write_json(
        run_dir / "phase1_final_governance_reconciliation_input_validation.json",
        {"status": "phase1_final_governance_comparator_inputs_ready", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_controls_reconciliation_status.json",
        {
            "status": "phase1_control_suite_not_claim_evaluable",
            "claim_evaluable": False,
            "blockers": ["final_control_manifest_status_not_claim_evaluable", "final_control_suite_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_calibration_reconciliation_status.json",
        {
            "status": "phase1_calibration_package_not_claim_evaluable",
            "claim_evaluable": False,
            "blockers": ["final_calibration_manifest_status_not_claim_evaluable", "final_calibration_package_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_influence_reconciliation_status.json",
        {
            "status": "phase1_influence_package_not_claim_evaluable",
            "claim_evaluable": False,
            "blockers": ["final_influence_manifest_status_not_claim_evaluable", "final_influence_package_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_reporting_reconciliation_status.json",
        {
            "status": "phase1_final_reporting_claim_evaluable",
            "claim_evaluable": True,
            "claim_table_ready": True,
            "claims_opened": False,
            "blockers": [],
        },
    )
    _write_json(
        run_dir / "phase1_final_governance_claim_state.json",
        {
            "status": "phase1_final_governance_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "blockers": blockers,
            "not_ok_to_claim": [
                "decoder efficacy",
                "A2d efficacy",
                "A3 distillation efficacy",
                "A4 privileged-transfer efficacy",
                "A4 superiority over A2/A2b/A2c/A2d/A3",
                "full Phase 1 neural comparator performance",
            ],
        },
    )
    _write_json(
        run_dir / "phase1_final_governance_reconciliation_source_links.json",
        {"status": "phase1_final_governance_reconciliation_source_links_recorded"},
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
