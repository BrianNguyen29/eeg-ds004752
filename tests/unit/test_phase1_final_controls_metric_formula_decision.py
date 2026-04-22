from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_controls_metric_formula_decision import (
    run_phase1_final_controls_metric_formula_decision,
)


class Phase1FinalControlsMetricFormulaDecisionTests(unittest.TestCase):
    def test_decision_records_gain_formula_without_rerun_or_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            revision_run = root / "phase1_final_controls_metric_formula_revision_plan" / "run"
            _write_prereg(prereg)
            _write_revision_plan(revision_run)

            result = run_phase1_final_controls_metric_formula_decision(
                prereg_bundle=prereg,
                formula_revision_plan_run=revision_run,
                formula_decision="gain_over_chance_ratio",
                decision_rationale=(
                    "Use gain-over-chance only as a contract decision because the control threshold is defined "
                    "against excess signal above chance, not to improve observed results."
                ),
                output_root=root / "phase1_final_controls_metric_formula_decision",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            boundary = _read_json(result.output_dir / "phase1_final_controls_metric_formula_implementation_boundary.json")
            claim_state = _read_json(result.output_dir / "phase1_final_controls_metric_formula_decision_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_controls_metric_formula_decision_recorded")
            self.assertEqual(summary["formula_decision"], "gain_over_chance_ratio")
            self.assertEqual(summary["selected_formula"], "gain_over_chance_ratio")
            self.assertTrue(summary["code_config_revision_required"])
            self.assertFalse(summary["code_change_allowed_by_this_runner"])
            self.assertFalse(summary["controls_rerun_allowed_by_this_runner"])
            self.assertFalse(summary["controls_rerun_by_decision_runner"])
            self.assertFalse(summary["thresholds_changed"])
            self.assertFalse(summary["logits_or_metrics_edited"])
            self.assertFalse(claim_state["headline_phase1_claim_open"])
            self.assertEqual(boundary["next_step"], "implement_scoped_metric_formula_contract_update_with_tests")

    def test_short_rationale_blocks_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            revision_run = root / "phase1_final_controls_metric_formula_revision_plan" / "run"
            _write_prereg(prereg)
            _write_revision_plan(revision_run)

            result = run_phase1_final_controls_metric_formula_decision(
                prereg_bundle=prereg,
                formula_revision_plan_run=revision_run,
                formula_decision="raw_ba_ratio",
                decision_rationale="too short",
                output_root=root / "phase1_final_controls_metric_formula_decision",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            validation = _read_json(result.output_dir / "phase1_final_controls_metric_formula_decision_input_validation.json")
            self.assertEqual(summary["status"], "phase1_final_controls_metric_formula_decision_blocked")
            self.assertIn("decision_rationale_too_short", validation["blockers"])
            self.assertFalse(summary["claims_opened"])

    def test_cli_decision_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            revision_run = root / "phase1_final_controls_metric_formula_revision_plan" / "run"
            output_root = root / "phase1_final_controls_metric_formula_decision"
            _write_prereg(prereg)
            _write_revision_plan(revision_run)

            exit_code = main(
                [
                    "phase1_final_controls_metric_formula_decision",
                    "--config",
                    str(prereg),
                    "--formula-revision-plan-run",
                    str(revision_run),
                    "--formula-decision",
                    "unresolved",
                    "--decision-rationale",
                    "Leave the formula unresolved because the current evidence is insufficient for a contract change.",
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_controls_metric_formula_decision_summary.json")
            self.assertEqual(summary["formula_decision"], "unresolved")
            self.assertIsNone(summary["selected_formula"])


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_revision_plan(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_revision_plan_summary.json",
        {
            "status": "phase1_final_controls_metric_formula_revision_plan_recorded",
            "claim_ready": False,
            "claims_opened": False,
            "headline_phase1_claim_open": False,
            "manual_decision_required": True,
            "selected_formula": None,
            "code_change_allowed_now": False,
            "rerun_controls_allowed_now": False,
            "threshold_change_allowed_now": False,
            "controls_in_scope": ["nuisance_shared_control"],
            "runtime_formula_ids": ["raw_ba_ratio"],
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_revision_scope.json",
        {
            "status": "phase1_final_controls_metric_formula_revision_scope_recorded",
            "revision_required": True,
            "controls_in_scope": ["nuisance_shared_control"],
            "selected_formula": None,
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_options.json",
        {
            "status": "phase1_final_controls_metric_formula_options_recorded",
            "runtime_formula_ids": ["raw_ba_ratio"],
            "selected_formula": None,
            "candidate_formulas": [
                {"formula_id": "raw_ba_ratio", "not_selected_by_this_plan": True},
                {"formula_id": "gain_over_chance_ratio", "not_selected_by_this_plan": True},
            ],
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_decision_requirements.json",
        {
            "status": "phase1_final_controls_metric_formula_decision_requirements_recorded",
            "manual_decision_required": True,
            "decision_must_be_made_before_code_change": True,
            "decision_must_be_made_before_control_rerun": True,
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_formula_revision_claim_state.json",
        {
            "status": "phase1_final_controls_metric_formula_revision_claim_state_closed",
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
