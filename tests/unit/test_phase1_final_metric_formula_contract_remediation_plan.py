from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_metric_formula_contract_remediation_plan import (
    run_phase1_final_metric_formula_contract_remediation_plan,
)


class Phase1FinalMetricFormulaContractRemediationPlanTests(unittest.TestCase):
    def test_plan_records_unresolved_contract_without_authorizing_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            post_formula_run = root / "phase1_final_post_formula_decision_governance_update" / "run"
            _write_prereg(prereg)
            _write_post_formula_governance(post_formula_run)

            result = run_phase1_final_metric_formula_contract_remediation_plan(
                prereg_bundle=prereg,
                post_formula_decision_governance_run=post_formula_run,
                output_root=root / "phase1_final_metric_formula_contract_remediation_plan",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            scope = _read_json(result.output_dir / "phase1_final_metric_formula_contract_remediation_scope.json")
            claim_state = _read_json(result.output_dir / "phase1_final_metric_formula_contract_remediation_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_metric_formula_contract_remediation_plan_recorded")
            self.assertEqual(summary["formula_decision"], "unresolved")
            self.assertIsNone(summary["selected_formula"])
            self.assertFalse(summary["code_change_allowed_now"])
            self.assertFalse(summary["runtime_formula_change_allowed_now"])
            self.assertFalse(summary["controls_rerun_allowed_now"])
            self.assertFalse(summary["threshold_change_allowed_now"])
            self.assertFalse(summary["claim_opening_allowed_now"])
            self.assertEqual(summary["next_step"], "draft_metric_formula_contract_revision_proposal")
            self.assertEqual(scope["remediation_scope"], "metric_formula_contract_docs_config_planning_only")
            self.assertIn("metric_formula_contract_unresolved", claim_state["blockers"])
            self.assertFalse(claim_state["headline_phase1_claim_open"])

    def test_cli_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            post_formula_run = root / "phase1_final_post_formula_decision_governance_update" / "run"
            output_root = root / "phase1_final_metric_formula_contract_remediation_plan"
            _write_prereg(prereg)
            _write_post_formula_governance(post_formula_run)

            exit_code = main(
                [
                    "phase1_final_metric_formula_contract_remediation_plan",
                    "--config",
                    str(prereg),
                    "--post-formula-decision-governance-run",
                    str(post_formula_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_metric_formula_contract_remediation_plan_summary.json")
            self.assertEqual(summary["status"], "phase1_final_metric_formula_contract_remediation_plan_recorded")


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_post_formula_governance(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "phase1_final_post_formula_decision_governance_update_recorded",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "formula_decision": "unresolved",
        "selected_formula": None,
        "metric_formula_contract_claim_evaluable": False,
        "metric_formula_next_step": "do_not_rerun_controls_until_metric_formula_contract_is_resolved",
        "claim_blockers": ["metric_formula_contract:metric_formula_contract_unresolved"],
    }
    input_validation = {
        "status": "phase1_final_post_formula_decision_governance_inputs_ready",
        "blockers": [],
    }
    metric_formula_status = {
        "status": "phase1_final_metric_formula_contract_not_claim_evaluable",
        "claim_evaluable": False,
        "formula_decision": "unresolved",
        "selected_formula": None,
        "blockers": ["metric_formula_contract_unresolved"],
        "next_step": "do_not_rerun_controls_until_metric_formula_contract_is_resolved",
    }
    claim_state = {
        "status": "phase1_final_post_formula_decision_governance_claim_state_blocked",
        "claim_ready": False,
        "headline_phase1_claim_open": False,
        "full_phase1_claim_bearing_run_allowed": False,
        "claims_opened": False,
        "blockers": ["metric_formula_contract:metric_formula_contract_unresolved"],
    }
    _write_json(run_dir / "phase1_final_post_formula_decision_governance_update_summary.json", summary)
    _write_json(run_dir / "phase1_final_post_formula_decision_governance_input_validation.json", input_validation)
    _write_json(run_dir / "phase1_final_metric_formula_contract_status.json", metric_formula_status)
    _write_json(run_dir / "phase1_final_post_formula_decision_governance_claim_state.json", claim_state)
    _write_json(run_dir / "phase1_final_post_formula_decision_governance_source_links.json", {"status": "recorded"})


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
