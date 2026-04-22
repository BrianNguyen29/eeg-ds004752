from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_controls_remediation_audit import run_phase1_final_controls_remediation_audit


class Phase1FinalControlsRemediationAuditTests(unittest.TestCase):
    def test_audit_records_failed_controls_without_opening_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            remediation_run = root / "phase1_final_remediation_plan" / "run"
            controls_run = root / "phase1_final_controls" / "run"
            dedicated_run = root / "phase1_final_dedicated_controls" / "run"
            _write_prereg(prereg)
            _write_remediation_plan(remediation_run)
            _write_final_controls(controls_run, dedicated_run)
            _write_dedicated_controls(dedicated_run)

            result = run_phase1_final_controls_remediation_audit(
                prereg_bundle=prereg,
                final_remediation_plan_run=remediation_run,
                final_controls_run=controls_run,
                final_dedicated_controls_run=dedicated_run,
                output_root=root / "phase1_final_controls_remediation_audit",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            failure_table = _read_json(result.output_dir / "phase1_final_controls_failure_table.json")
            threshold_review = _read_json(result.output_dir / "phase1_final_controls_threshold_source_review.json")
            claim_state = _read_json(result.output_dir / "phase1_final_controls_remediation_claim_state.json")

            self.assertEqual(summary["status"], "phase1_final_controls_remediation_audit_recorded")
            self.assertFalse(summary["claims_opened"])
            self.assertFalse(summary["claim_ready"])
            self.assertTrue(summary["final_claim_blocked"])
            self.assertFalse(summary["control_suite_passed"])
            self.assertFalse(summary["dedicated_control_suite_passed"])
            self.assertEqual(
                summary["failed_dedicated_controls"],
                ["nuisance_shared_control", "spatial_control", "shuffled_teacher", "time_shifted_teacher"],
            )
            self.assertTrue(summary["teacher_threshold_path_mismatch_suspected"])
            self.assertIn("shuffled_teacher", summary["blocking_controls"])
            self.assertTrue(threshold_review["teacher_threshold_path_mismatch_suspected"])
            teacher_row = next(row for row in failure_table["rows"] if row["control_id"] == "shuffled_teacher")
            self.assertIn("teacher_control_gain_threshold_missing", teacher_row["failure_reasons"])
            self.assertFalse(claim_state["headline_phase1_claim_open"])
            self.assertTrue((result.output_dir / "phase1_final_controls_remediation_decision_memo.md").exists())

    def test_cli_audit_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            remediation_run = root / "phase1_final_remediation_plan" / "run"
            controls_run = root / "phase1_final_controls" / "run"
            dedicated_run = root / "phase1_final_dedicated_controls" / "run"
            output_root = root / "phase1_final_controls_remediation_audit"
            _write_prereg(prereg)
            _write_remediation_plan(remediation_run)
            _write_final_controls(controls_run, dedicated_run)
            _write_dedicated_controls(dedicated_run)

            exit_code = main(
                [
                    "phase1_final_controls_remediation_audit",
                    "--config",
                    str(prereg),
                    "--final-remediation-plan-run",
                    str(remediation_run),
                    "--final-controls-run",
                    str(controls_run),
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
            summary = _read_json(run_dir / "phase1_final_controls_remediation_audit_summary.json")
            self.assertEqual(summary["status"], "phase1_final_controls_remediation_audit_recorded")
            self.assertFalse(summary["claims_opened"])


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_remediation_plan(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_remediation_plan_summary.json",
        {
            "status": "phase1_final_remediation_plan_recorded",
            "claim_ready": False,
            "claims_opened": False,
            "final_claim_blocked": True,
            "blocking_surfaces": ["controls", "calibration", "influence"],
            "claim_blockers": ["controls:final_control_suite_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_remediation_blocker_review.json",
        {"status": "phase1_final_remediation_blocker_review_recorded", "blocking_surfaces": ["controls"]},
    )
    _write_json(
        run_dir / "phase1_final_remediation_workplan.json",
        {"status": "phase1_final_remediation_workplan_recorded", "next_step": "start_revision_scoped_controls_remediation_audit"},
    )
    _write_json(
        run_dir / "phase1_final_remediation_guardrails.json",
        {"status": "phase1_final_remediation_guardrails_recorded", "claims_opened": False},
    )
    _write_json(
        run_dir / "phase1_final_remediation_claim_state.json",
        {"status": "phase1_final_remediation_claim_state_closed", "claim_ready": False, "claims_opened": False},
    )


def _write_final_controls(run_dir: Path, dedicated_run: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    results = [
        "scalp_only_baseline",
        "grouped_permutation",
        "shuffled_labels",
        "transfer_consistency",
        "nuisance_shared_control",
        "spatial_control",
        "shuffled_teacher",
        "time_shifted_teacher",
    ]
    blockers = [
        "dedicated_final_control_suite_not_passed",
        "dedicated_final_control_thresholds_not_passed",
        "final_control_suite_not_passed",
    ]
    _write_json(
        run_dir / "phase1_final_controls_summary.json",
        {
            "status": "phase1_final_controls_blocked",
            "computed_control_results": results,
            "missing_control_results": [],
            "control_suite_passed": False,
            "claim_ready": False,
            "claim_blockers": blockers,
        },
    )
    _write_json(run_dir / "phase1_final_controls_input_validation.json", {"status": "phase1_final_controls_inputs_ready", "blockers": []})
    _write_json(
        run_dir / "phase1_final_logit_level_control_results.json",
        {"status": "phase1_final_logit_level_controls_recorded", "computed_control_ids": results[:4]},
    )
    _write_json(
        run_dir / "phase1_final_dedicated_control_requirements.json",
        {
            "status": "phase1_final_dedicated_control_reruns_required",
            "missing_control_ids": [],
            "dedicated_control_suite_passed": False,
            "dedicated_control_blockers": ["dedicated_final_control_thresholds_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_dedicated_control_manifest_review.json",
        {
            "status": "phase1_final_dedicated_controls_blocked_manifest_recorded",
            "manifest_path": str(dedicated_run / "final_dedicated_control_manifest.json"),
            "results": results[4:],
            "dedicated_control_suite_passed": False,
            "blockers": ["dedicated_final_control_thresholds_not_passed"],
        },
    )
    _write_json(
        run_dir / "final_control_manifest.json",
        {
            "status": "phase1_final_controls_blocked_manifest_recorded",
            "results": results,
            "missing_results": [],
            "dedicated_control_suite_passed": False,
            "control_suite_passed": False,
            "claim_ready": False,
            "claim_evaluable": False,
            "blockers": blockers[:-1],
        },
    )
    _write_json(
        run_dir / "phase1_final_controls_claim_state.json",
        {"status": "phase1_final_controls_claim_state_blocked", "claim_ready": False, "blockers": blockers},
    )


def _write_dedicated_controls(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    controls = {
        "nuisance_shared_control": _control_payload(
            "nuisance_shared_control",
            {
                "nuisance_relative_ceiling": 0.5,
                "nuisance_absolute_ceiling": 0.02,
                "relative_to_baseline": 0.7,
                "absolute_gain_over_chance": 0.03,
            },
        ),
        "spatial_control": _control_payload(
            "spatial_control",
            {"spatial_relative_ceiling": 0.67, "relative_to_baseline": 0.8},
        ),
        "shuffled_teacher": _control_payload(
            "shuffled_teacher",
            {"max_gain_over_a3": None, "gain_over_a3": 0.02, "baseline_comparator": "A3_distillation"},
        ),
        "time_shifted_teacher": _control_payload(
            "time_shifted_teacher",
            {"max_gain_over_a3": None, "gain_over_a3": 0.03, "baseline_comparator": "A3_distillation"},
        ),
    }
    _write_json(
        run_dir / "phase1_final_dedicated_controls_summary.json",
        {
            "status": "phase1_final_dedicated_controls_blocked",
            "computed_dedicated_control_results": list(controls.keys()),
            "failed_dedicated_control_results": list(controls.keys()),
            "dedicated_control_suite_passed": False,
            "claim_ready": False,
            "claim_blockers": ["dedicated_final_control_thresholds_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_dedicated_controls_input_validation.json",
        {"status": "phase1_final_dedicated_controls_inputs_ready", "blockers": []},
    )
    _write_json(run_dir / "nuisance_shared_control.json", controls["nuisance_shared_control"])
    _write_json(run_dir / "spatial_control.json", controls["spatial_control"])
    _write_json(run_dir / "shuffled_teacher_control.json", controls["shuffled_teacher"])
    _write_json(run_dir / "time_shifted_teacher_control.json", controls["time_shifted_teacher"])
    _write_json(
        run_dir / "phase1_final_dedicated_controls_runtime_leakage_audit.json",
        {"status": "phase1_final_dedicated_controls_runtime_leakage_audit_passed", "outer_test_subject_used_for_any_fit": False},
    )
    _write_json(
        run_dir / "final_dedicated_control_manifest.json",
        {
            "status": "phase1_final_dedicated_controls_blocked_manifest_recorded",
            "results": list(controls.keys()),
            "required_results": list(controls.keys()),
            "missing_results": [],
            "failed_results": list(controls.keys()),
            "dedicated_control_suite_passed": False,
            "claim_ready": False,
            "claim_evaluable": False,
            "blockers": ["dedicated_final_control_thresholds_not_passed"],
        },
    )
    _write_json(
        run_dir / "phase1_final_dedicated_controls_claim_state.json",
        {"status": "phase1_final_dedicated_controls_claim_state_blocked", "claim_ready": False, "blockers": ["dedicated_final_control_thresholds_not_passed"]},
    )


def _control_payload(control_id: str, threshold: dict[str, object]) -> dict[str, object]:
    return {
        "status": f"phase1_final_{control_id}_recorded",
        "control_id": control_id,
        "passed": False,
        "claim_ready": False,
        "claim_evaluable": False,
        "metrics": {"balanced_accuracy": 0.55},
        "threshold": threshold,
        "n_folds": 15,
        "n_logit_rows": 2223,
        "fold_logs": [{"no_outer_test_subject_in_any_fit": True, "teacher_used_at_inference": False}],
        "runtime_leakage_passed": True,
        "scientific_limit": "Test fixture only.",
    }


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
