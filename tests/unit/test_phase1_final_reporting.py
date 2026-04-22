from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_reporting import run_phase1_final_reporting


REPORTING_ARTIFACTS = [
    "final_comparator_completeness_table",
    "negative_controls_report",
    "calibration_package_report",
    "influence_package_report",
    "final_fold_logs",
    "claim_state_report",
    "main_phase1_report",
]


class Phase1FinalReportingTests(unittest.TestCase):
    def test_final_reporting_records_closed_claims_without_fabricating_governance_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance_run = root / "phase1_final_governance_reconciliation" / "run"
            _write_prereg(prereg)
            _write_blocked_governance_reconciliation(governance_run)

            result = run_phase1_final_reporting(
                prereg_bundle=prereg,
                final_governance_reconciliation_run=governance_run,
                output_root=root / "phase1_final_reporting",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            manifest = _read_json(result.output_dir / "final_reporting_manifest.json")
            controls_report = _read_json(result.output_dir / "negative_controls_report.json")
            claim_table = _read_json(result.output_dir / "phase1_final_reporting_claim_table.json")

            self.assertEqual(summary["status"], "phase1_final_reporting_complete_claim_closed")
            self.assertTrue(summary["reporting_package_passed"])
            self.assertTrue(manifest["reporting_package_passed"])
            self.assertTrue(manifest["claim_evaluable"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["claims_opened"])
            self.assertTrue(summary["upstream_governance_blocked"])
            self.assertIn("controls:final_control_suite_not_passed", summary["claim_blockers"])
            self.assertEqual(manifest["artifacts"], REPORTING_ARTIFACTS)
            self.assertEqual(manifest["blockers"], [])
            self.assertFalse(controls_report["controls_claim_evaluable"])
            self.assertIn("final_control_suite_not_passed", controls_report["blockers"])
            self.assertTrue(claim_table["claim_table_ready"])
            self.assertFalse(claim_table["claims_opened"])
            self.assertTrue(all(row["claim_open"] is False for row in claim_table["rows"]))

    def test_cli_final_reporting_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance_run = root / "phase1_final_governance_reconciliation" / "run"
            output_root = root / "phase1_final_reporting"
            _write_prereg(prereg)
            _write_blocked_governance_reconciliation(governance_run)

            exit_code = main(
                [
                    "phase1_final_reporting",
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
            summary = _read_json(run_dir / "phase1_final_reporting_summary.json")
            self.assertEqual(summary["status"], "phase1_final_reporting_complete_claim_closed")
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


def _write_blocked_governance_reconciliation(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    blockers = [
        "controls:final_control_suite_not_passed",
        "calibration:final_calibration_package_not_passed",
        "influence:final_influence_package_not_passed",
        "reporting:final_phase1_reporting_manifest_missing",
        "controls_calibration_influence_reporting_missing",
        "headline_claim_blocked_until_full_package_passes",
        "final_governance_reconciliation_incomplete",
    ]
    _write_json(
        run_dir / "phase1_final_governance_reconciliation_summary.json",
        {
            "status": "phase1_final_governance_reconciliation_blocked",
            "comparator_reconciliation_run": str(run_dir.parent / "phase1_final_comparator_reconciliation" / "run"),
            "comparator_outputs_complete": True,
            "runtime_logs_audited_for_all_required_comparators": True,
            "governance_surfaces": {
                "controls_claim_evaluable": False,
                "calibration_claim_evaluable": False,
                "influence_claim_evaluable": False,
                "reporting_claim_evaluable": False,
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
            "blockers": ["final_control_suite_not_passed"],
            "final_control_manifest_path": "/tmp/final_control_manifest.json",
        },
    )
    _write_json(
        run_dir / "phase1_final_calibration_reconciliation_status.json",
        {
            "status": "phase1_calibration_package_not_claim_evaluable",
            "claim_evaluable": False,
            "blockers": ["final_calibration_package_not_passed"],
            "final_calibration_manifest_path": "/tmp/final_calibration_manifest.json",
        },
    )
    _write_json(
        run_dir / "phase1_final_influence_reconciliation_status.json",
        {
            "status": "phase1_influence_package_not_claim_evaluable",
            "claim_evaluable": False,
            "blockers": ["final_influence_package_not_passed"],
            "final_influence_manifest_path": "/tmp/final_influence_manifest.json",
        },
    )
    _write_json(
        run_dir / "phase1_final_reporting_reconciliation_status.json",
        {
            "status": "phase1_final_reporting_not_claim_evaluable",
            "claim_evaluable": False,
            "claims_opened": False,
            "blockers": ["final_phase1_reporting_manifest_missing"],
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
        {
            "status": "phase1_final_governance_reconciliation_source_links_recorded",
            "comparator_reconciliation_run": "/tmp/phase1_final_comparator_reconciliation/run",
            "comparator_reconciliation_summary": "/tmp/phase1_final_comparator_reconciliation/run/summary.json",
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
