from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_controls_metric_contract_audit import (
    run_phase1_final_controls_metric_contract_audit,
)


class Phase1FinalControlsMetricContractAuditTests(unittest.TestCase):
    def test_audit_records_formula_ambiguity_without_opening_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            remediation_run = root / "phase1_final_controls_remediation_audit" / "run"
            dedicated_run = root / "phase1_final_dedicated_controls" / "run"
            dedicated_config = root / "configs" / "final_dedicated_controls.json"
            _write_prereg(prereg)
            _write_remediation_audit(remediation_run)
            _write_dedicated_controls(dedicated_run)
            _write_dedicated_controls_config(dedicated_config, locked=False)

            result = run_phase1_final_controls_metric_contract_audit(
                prereg_bundle=prereg,
                controls_remediation_audit_run=remediation_run,
                final_dedicated_controls_run=dedicated_run,
                output_root=root / "phase1_final_controls_metric_contract_audit",
                repo_root=Path.cwd(),
                config_paths={"dedicated_controls": str(dedicated_config)},
            )

            summary = _read_json(result.summary_path)
            formula_review = _read_json(result.output_dir / "relative_metric_formula_review.json")
            recommendation = _read_json(
                result.output_dir / "controls_metric_contract_remediation_recommendation.json"
            )
            claim_state = _read_json(result.output_dir / "phase1_final_controls_metric_contract_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_controls_metric_contract_audit_recorded")
            self.assertFalse(summary["claims_opened"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["relative_formula_locked"])
            self.assertTrue(summary["formula_ambiguity_detected"])
            self.assertIn("nuisance_shared_control", summary["controls_with_formula_dependent_pass_status"])
            self.assertEqual(summary["current_runtime_formula_ids"], ["raw_ba_ratio"])
            nuisance = next(row for row in formula_review["rows"] if row["control_id"] == "nuisance_shared_control")
            self.assertEqual(nuisance["runtime_formula_matches"], "raw_ba_ratio")
            self.assertFalse(nuisance["pass_under_raw_ba_ratio"])
            self.assertTrue(nuisance["pass_under_gain_over_chance_ratio"])
            self.assertTrue(recommendation["do_not_change_thresholds"])
            self.assertTrue(recommendation["do_not_edit_logits_or_metrics"])
            self.assertFalse(claim_state["headline_phase1_claim_open"])

    def test_audit_records_prospective_contract_without_reclassifying_existing_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            remediation_run = root / "phase1_final_controls_remediation_audit" / "run"
            dedicated_run = root / "phase1_final_dedicated_controls" / "run"
            dedicated_config = root / "configs" / "final_dedicated_controls.json"
            _write_prereg(prereg)
            _write_remediation_audit(remediation_run)
            _write_dedicated_controls(dedicated_run)
            _write_dedicated_controls_config(dedicated_config, locked=True)

            result = run_phase1_final_controls_metric_contract_audit(
                prereg_bundle=prereg,
                controls_remediation_audit_run=remediation_run,
                final_dedicated_controls_run=dedicated_run,
                output_root=root / "phase1_final_controls_metric_contract_audit",
                repo_root=Path.cwd(),
                config_paths={"dedicated_controls": str(dedicated_config)},
            )

            summary = _read_json(result.summary_path)
            formula_review = _read_json(result.output_dir / "relative_metric_formula_review.json")
            self.assertFalse(summary["relative_formula_locked"])
            self.assertTrue(summary["formula_ambiguity_detected"])
            self.assertEqual(formula_review["prospective_formula_source"][0]["value"], "raw_ba_ratio")
            self.assertEqual(
                formula_review["prospective_formula_source"][0]["field"],
                "relative_metric_contract.formula_id",
            )

    def test_audit_locks_formula_when_artifacts_carry_formula_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            remediation_run = root / "phase1_final_controls_remediation_audit" / "run"
            dedicated_run = root / "phase1_final_dedicated_controls" / "run"
            dedicated_config = root / "configs" / "final_dedicated_controls.json"
            _write_prereg(prereg)
            _write_remediation_audit(remediation_run)
            _write_dedicated_controls(dedicated_run, formula_metadata=True)
            _write_dedicated_controls_config(dedicated_config, locked=True)

            result = run_phase1_final_controls_metric_contract_audit(
                prereg_bundle=prereg,
                controls_remediation_audit_run=remediation_run,
                final_dedicated_controls_run=dedicated_run,
                output_root=root / "phase1_final_controls_metric_contract_audit",
                repo_root=Path.cwd(),
                config_paths={"dedicated_controls": str(dedicated_config)},
            )

            summary = _read_json(result.summary_path)
            formula_review = _read_json(result.output_dir / "relative_metric_formula_review.json")
            self.assertTrue(summary["relative_formula_locked"])
            self.assertFalse(summary["formula_ambiguity_detected"])
            self.assertEqual(summary["current_runtime_formula_ids"], ["raw_ba_ratio"])
            self.assertEqual(formula_review["locked_formula_id"], "raw_ba_ratio")
            self.assertEqual(
                formula_review["locked_formula_source"][0]["field"],
                "threshold.relative_metric_formula_id",
            )

    def test_cli_audit_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            remediation_run = root / "phase1_final_controls_remediation_audit" / "run"
            dedicated_run = root / "phase1_final_dedicated_controls" / "run"
            output_root = root / "phase1_final_controls_metric_contract_audit"
            _write_prereg(prereg)
            _write_remediation_audit(remediation_run)
            _write_dedicated_controls(dedicated_run)

            exit_code = main(
                [
                    "phase1_final_controls_metric_contract_audit",
                    "--config",
                    str(prereg),
                    "--controls-remediation-audit-run",
                    str(remediation_run),
                    "--final-dedicated-controls-run",
                    str(dedicated_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_controls_metric_contract_audit_summary.json")
            self.assertEqual(summary["status"], "phase1_final_controls_metric_contract_audit_recorded")


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_remediation_audit(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "status": "phase1_final_controls_remediation_audit_recorded",
        "claim_ready": False,
        "claims_opened": False,
        "final_claim_blocked": True,
        "control_suite_passed": False,
        "dedicated_control_suite_passed": False,
        "failed_dedicated_controls": ["nuisance_shared_control", "spatial_control"],
        "blocking_controls": ["nuisance_shared_control", "spatial_control"],
        "teacher_threshold_path_mismatch_suspected": False,
    }
    failure_table = {
        "status": "phase1_final_controls_failure_table_recorded",
        "control_suite_passed": False,
        "dedicated_control_suite_passed": False,
        "failed_dedicated_controls": ["nuisance_shared_control", "spatial_control"],
        "rows": [
            {
                "control_id": "nuisance_shared_control",
                "control_type": "dedicated",
                "present": True,
                "passed": False,
                "blocking": True,
                "failure_reasons": ["control_threshold_not_passed", "nuisance_relative_ceiling_exceeded"],
            },
            {
                "control_id": "spatial_control",
                "control_type": "dedicated",
                "present": True,
                "passed": False,
                "blocking": True,
                "failure_reasons": ["control_threshold_not_passed", "spatial_relative_ceiling_exceeded"],
            },
        ],
        "blocking_controls": ["nuisance_shared_control", "spatial_control"],
        "claim_ready": False,
        "claims_opened": False,
    }
    _write_json(run_dir / "phase1_final_controls_remediation_audit_summary.json", summary)
    _write_json(run_dir / "phase1_final_controls_failure_table.json", failure_table)
    _write_json(
        run_dir / "phase1_final_controls_threshold_source_review.json",
        {"status": "phase1_final_controls_threshold_source_review_recorded"},
    )
    _write_json(
        run_dir / "phase1_final_controls_implementation_review.json",
        {"status": "phase1_final_controls_implementation_review_recorded", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_controls_remediation_claim_state.json",
        {"status": "phase1_final_controls_remediation_claim_state_closed", "headline_phase1_claim_open": False},
    )


def _write_dedicated_controls(run_dir: Path, *, formula_metadata: bool = False) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    nuisance_threshold = {
        "nuisance_relative_ceiling": 0.5,
        "nuisance_absolute_ceiling": 0.02,
        "baseline_comparator": "A2",
        "relative_to_baseline": 0.997035,
        "absolute_gain_over_chance": 0.0,
    }
    spatial_threshold = {
        "spatial_relative_ceiling": 0.67,
        "baseline_comparator": "A2",
        "relative_to_baseline": 1.0,
    }
    if formula_metadata:
        formula = {
            "relative_metric_formula_id": "raw_ba_ratio",
            "relative_metric_formula_definition": "control_balanced_accuracy / baseline_balanced_accuracy",
            "relative_metric_formula_source": "configs/phase1/final_dedicated_controls.json:relative_metric_contract",
        }
        nuisance_threshold.update(formula)
        spatial_threshold.update(formula)
    _write_json(
        run_dir / "phase1_final_dedicated_controls_summary.json",
        {
            "status": "phase1_final_dedicated_controls_blocked",
            "dedicated_control_suite_passed": False,
            "claim_ready": False,
        },
    )
    _write_json(run_dir / "phase1_final_dedicated_controls_source_links.json", {})
    _write_json(
        run_dir / "nuisance_shared_control.json",
        {
            "control_id": "nuisance_shared_control",
            "passed": False,
            "runtime_leakage_passed": True,
            "metrics": {"balanced_accuracy": 0.5},
            "threshold": nuisance_threshold,
        },
    )
    _write_json(
        run_dir / "spatial_control.json",
        {
            "control_id": "spatial_control",
            "passed": False,
            "runtime_leakage_passed": True,
            "metrics": {"balanced_accuracy": 0.501487},
            "threshold": spatial_threshold,
        },
    )
    _write_json(
        run_dir / "phase1_final_dedicated_controls_runtime_leakage_audit.json",
        {"status": "phase1_final_dedicated_controls_runtime_leakage_audit_passed", "outer_test_subject_used_for_any_fit": False},
    )
    _write_json(
        run_dir / "final_dedicated_control_manifest.json",
        {
            "status": "phase1_final_dedicated_controls_blocked_manifest_recorded",
            "results": ["nuisance_shared_control", "spatial_control", "shuffled_teacher", "time_shifted_teacher"],
            "failed_results": ["nuisance_shared_control", "spatial_control"],
            "dedicated_control_suite_passed": False,
            "claim_ready": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_dedicated_controls_claim_state.json",
        {"status": "phase1_final_dedicated_controls_claim_state_blocked", "claim_ready": False, "headline_phase1_claim_open": False},
    )


def _write_dedicated_controls_config(path: Path, *, locked: bool) -> None:
    payload: dict[str, object] = {
        "required_dedicated_controls": [
            "nuisance_shared_control",
            "spatial_control",
            "shuffled_teacher",
            "time_shifted_teacher",
        ]
    }
    if locked:
        payload["relative_metric_contract"] = {
            "formula_id": "raw_ba_ratio",
            "definition": "control_balanced_accuracy / baseline_balanced_accuracy",
            "applies_to": [
                "nuisance_shared_control.relative_to_baseline",
                "spatial_control.relative_to_baseline",
            ],
            "default_baseline_comparator": "A2",
            "status": "prospective_contract_clarification",
            "current_artifacts_reclassified": False,
            "thresholds_changed": False,
            "claims_opened": False,
        }
    _write_json(path, payload)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))
