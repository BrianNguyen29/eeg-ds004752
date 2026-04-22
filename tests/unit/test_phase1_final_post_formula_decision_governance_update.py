from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_post_formula_decision_governance_update import (
    run_phase1_final_post_formula_decision_governance_update,
)


class Phase1FinalPostFormulaDecisionGovernanceUpdateTests(unittest.TestCase):
    def test_unresolved_formula_decision_adds_metric_formula_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance_run = root / "phase1_final_governance_reconciliation" / "run"
            formula_run = root / "phase1_final_controls_metric_formula_decision" / "run"
            _write_prereg(prereg)
            _write_governance(governance_run)
            _write_formula_decision(formula_run, decision="unresolved", selected=None)

            result = run_phase1_final_post_formula_decision_governance_update(
                prereg_bundle=prereg,
                final_governance_reconciliation_run=governance_run,
                formula_decision_run=formula_run,
                output_root=root / "phase1_final_post_formula_decision_governance_update",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            formula_status = _read_json(result.output_dir / "phase1_final_metric_formula_contract_status.json")
            claim_state = _read_json(result.output_dir / "phase1_final_post_formula_decision_governance_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_post_formula_decision_governance_update_recorded")
            self.assertEqual(summary["formula_decision"], "unresolved")
            self.assertIsNone(summary["selected_formula"])
            self.assertFalse(summary["metric_formula_contract_claim_evaluable"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["claims_opened"])
            self.assertIn("metric_formula_contract_unresolved", formula_status["blockers"])
            self.assertIn("metric_formula_contract:metric_formula_contract_unresolved", claim_state["blockers"])

    def test_cli_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            governance_run = root / "phase1_final_governance_reconciliation" / "run"
            formula_run = root / "phase1_final_controls_metric_formula_decision" / "run"
            output_root = root / "phase1_final_post_formula_decision_governance_update"
            _write_prereg(prereg)
            _write_governance(governance_run)
            _write_formula_decision(formula_run, decision="unresolved", selected=None)

            exit_code = main(
                [
                    "phase1_final_post_formula_decision_governance_update",
                    "--config",
                    str(prereg),
                    "--final-governance-reconciliation-run",
                    str(governance_run),
                    "--formula-decision-run",
                    str(formula_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_post_formula_decision_governance_update_summary.json")
            self.assertEqual(summary["formula_decision"], "unresolved")


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_governance(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "phase1_final_governance_reconciliation_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "comparator_outputs_complete": True,
        "runtime_logs_audited_for_all_required_comparators": True,
        "governance_surfaces": {
            "controls_claim_evaluable": False,
            "calibration_claim_evaluable": False,
            "influence_claim_evaluable": False,
            "reporting_claim_evaluable": True,
        },
        "claim_blockers": [
            "controls:final_control_suite_not_passed",
            "calibration:final_calibration_package_not_passed",
            "influence:final_influence_package_not_passed",
        ],
    }
    claim_state = {
        "status": "phase1_final_governance_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "blockers": summary["claim_blockers"],
    }
    status = {"status": "not_claim_evaluable", "claim_evaluable": False, "blockers": ["blocked"]}
    _write_json(run_dir / "phase1_final_governance_reconciliation_summary.json", summary)
    _write_json(run_dir / "phase1_final_governance_claim_state.json", claim_state)
    _write_json(run_dir / "phase1_final_controls_reconciliation_status.json", status)
    _write_json(run_dir / "phase1_final_calibration_reconciliation_status.json", status)
    _write_json(run_dir / "phase1_final_influence_reconciliation_status.json", status)
    _write_json(
        run_dir / "phase1_final_reporting_reconciliation_status.json",
        {"status": "claim_evaluable", "claim_evaluable": True, "blockers": []},
    )


def _write_formula_decision(run_dir: Path, *, decision: str, selected: str | None) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "phase1_final_controls_metric_formula_decision_recorded",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": decision,
        "selected_formula": selected,
        "code_config_revision_required": False,
        "code_change_allowed_by_this_runner": False,
        "controls_rerun_allowed_by_this_runner": False,
        "thresholds_changed": False,
        "logits_or_metrics_edited": False,
        "controls_rerun_by_decision_runner": False,
    }
    _write_json(run_dir / "phase1_final_controls_metric_formula_decision_summary.json", summary)
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_decision_record.json",
        {
            "status": "phase1_final_controls_metric_formula_decision_recorded",
            "formula_decision": decision,
            "selected_formula": selected,
            "decision_is_claim_closed": True,
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_implementation_boundary.json",
        {
            "status": "phase1_final_controls_metric_formula_implementation_boundary_recorded",
            "next_step": "keep_controls_fail_closed_until_metric_formula_contract_is_resolved",
            "claim_opening_allowed": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_decision_claim_state.json",
        {
            "status": "phase1_final_controls_metric_formula_decision_claim_state_closed",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "claims_opened": False,
        },
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
