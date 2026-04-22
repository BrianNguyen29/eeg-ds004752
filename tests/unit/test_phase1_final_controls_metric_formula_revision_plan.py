from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_controls_metric_formula_revision_plan import (
    run_phase1_final_controls_metric_formula_revision_plan,
)


class Phase1FinalControlsMetricFormulaRevisionPlanTests(unittest.TestCase):
    def test_revision_plan_records_manual_decision_without_selecting_formula(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            metric_audit_run = root / "phase1_final_controls_metric_contract_audit" / "run"
            _write_prereg(prereg)
            _write_metric_contract_audit(metric_audit_run)

            result = run_phase1_final_controls_metric_formula_revision_plan(
                prereg_bundle=prereg,
                metric_contract_audit_run=metric_audit_run,
                output_root=root / "phase1_final_controls_metric_formula_revision_plan",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            scope = _read_json(result.output_dir / "phase1_final_controls_metric_formula_revision_scope.json")
            options = _read_json(result.output_dir / "phase1_final_controls_metric_formula_options.json")
            requirements = _read_json(result.output_dir / "phase1_final_controls_metric_formula_decision_requirements.json")
            claim_state = _read_json(result.output_dir / "phase1_final_controls_metric_formula_revision_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_controls_metric_formula_revision_plan_recorded")
            self.assertTrue(summary["revision_required"])
            self.assertTrue(summary["manual_decision_required"])
            self.assertIsNone(summary["selected_formula"])
            self.assertFalse(summary["code_change_allowed_now"])
            self.assertFalse(summary["rerun_controls_allowed_now"])
            self.assertFalse(summary["threshold_change_allowed_now"])
            self.assertEqual(summary["controls_in_scope"], ["nuisance_shared_control"])
            self.assertEqual(options["selected_formula"], None)
            self.assertTrue(requirements["decision_must_be_made_before_code_change"])
            self.assertFalse(claim_state["headline_phase1_claim_open"])
            self.assertEqual(scope["revision_scope"], "metric_formula_contract_only")

    def test_cli_revision_plan_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            metric_audit_run = root / "phase1_final_controls_metric_contract_audit" / "run"
            output_root = root / "phase1_final_controls_metric_formula_revision_plan"
            _write_prereg(prereg)
            _write_metric_contract_audit(metric_audit_run)

            exit_code = main(
                [
                    "phase1_final_controls_metric_formula_revision_plan",
                    "--config",
                    str(prereg),
                    "--metric-contract-audit-run",
                    str(metric_audit_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_controls_metric_formula_revision_plan_summary.json")
            self.assertEqual(summary["status"], "phase1_final_controls_metric_formula_revision_plan_recorded")


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_metric_contract_audit(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_controls_metric_contract_audit_summary.json",
        {
            "status": "phase1_final_controls_metric_contract_audit_recorded",
            "claim_ready": False,
            "claims_opened": False,
            "headline_phase1_claim_open": False,
            "relative_formula_locked": False,
            "formula_ambiguity_detected": True,
            "controls_with_formula_dependent_pass_status": ["nuisance_shared_control"],
            "current_runtime_formula_ids": ["raw_ba_ratio"],
            "next_step": "open_revision_scoped_metric_formula_contract_review",
        },
    )
    _write_json(
        run_dir / "relative_metric_formula_review.json",
        {
            "status": "phase1_final_controls_relative_metric_formula_review_recorded",
            "relative_formula_locked": False,
            "locked_formula_source": [],
            "locked_formula_id": None,
            "formula_ambiguity_detected": True,
            "controls_with_formula_dependent_pass_status": ["nuisance_shared_control"],
            "rows": [
                {
                    "control_id": "nuisance_shared_control",
                    "runtime_formula_matches": "raw_ba_ratio",
                    "candidate_formulas": {"raw_ba_ratio": 0.997035, "gain_over_chance_ratio": 0.0},
                    "pass_under_raw_ba_ratio": False,
                    "pass_under_gain_over_chance_ratio": True,
                    "candidate_formula_changes_pass_status": True,
                }
            ],
        },
    )
    _write_json(
        run_dir / "controls_threshold_contract_review.json",
        {
            "status": "phase1_final_controls_threshold_contract_review_recorded",
            "all_runtime_thresholds_match_locked_config": True,
        },
    )
    _write_json(
        run_dir / "controls_metric_contract_remediation_recommendation.json",
        {
            "status": "phase1_final_controls_metric_contract_recommendation_recorded",
            "claims_opened": False,
            "claim_ready": False,
            "next_step": "open_revision_scoped_metric_formula_contract_review",
            "do_not_change_thresholds": True,
            "do_not_edit_logits_or_metrics": True,
            "do_not_reclassify_existing_controls": True,
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_metric_contract_claim_state.json",
        {
            "status": "phase1_final_controls_metric_contract_claim_state_closed",
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
