from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_comparator_reconciliation import run_phase1_final_comparator_reconciliation


COMPARATORS = ["A2", "A2b", "A2c_CORAL", "A3_distillation", "A4_privileged"]


class Phase1FinalComparatorReconciliationTests(unittest.TestCase):
    def test_reconciliation_links_a2d_and_feature_matrix_outputs_without_opening_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            fm_runner = root / "phase1_final_comparator_runner" / "run"
            a2d_runner = root / "phase1_final_a2d_runner" / "run"
            _write_prereg(prereg)
            _write_feature_matrix_runner(fm_runner, feature_matrix_run)
            _write_a2d_runner(a2d_runner, feature_matrix_run, fm_runner)

            result = run_phase1_final_comparator_reconciliation(
                prereg_bundle=prereg,
                feature_matrix_comparator_run=fm_runner,
                final_a2d_run=a2d_runner,
                output_root=root / "phase1_final_comparator_reconciliation",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_comparator_reconciliation_complete_claim_closed")
            self.assertEqual(
                summary["completed_comparators"],
                ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"],
            )
            self.assertEqual(summary["blocked_comparators"], [])
            self.assertTrue(summary["all_final_comparator_outputs_present"])
            self.assertTrue(summary["runtime_comparator_logs_audited_for_all_required_comparators"])
            self.assertTrue(summary["a2d_missing_output_blocker_resolved_at_artifact_level"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertNotIn("final_comparator_outputs_incomplete", summary["claim_blockers"])
            self.assertNotIn("A2d_riemannian_final_covariance_runner_missing", summary["claim_blockers"])
            self.assertIn("controls_calibration_influence_reporting_missing", summary["claim_blockers"])

            completeness = _read_json(result.output_dir / "phase1_final_comparator_reconciled_completeness_table.json")
            self.assertEqual(completeness["status"], "phase1_final_comparator_reconciled_completeness_recorded")
            self.assertEqual(len(completeness["rows"]), 6)
            self.assertTrue(all(row["runtime_leakage_passed"] for row in completeness["rows"]))
            a2d_row = next(row for row in completeness["rows"] if row["comparator_id"] == "A2d_riemannian")
            self.assertEqual(a2d_row["source_package"], "final_a2d_covariance_tangent_runner")
            self.assertTrue(a2d_row["logits_present"])
            self.assertFalse(a2d_row["claim_evaluable"])

            leakage = _read_json(result.output_dir / "phase1_final_comparator_reconciled_runtime_leakage_audit.json")
            self.assertEqual(leakage["status"], "phase1_final_comparator_reconciled_runtime_leakage_audit_recorded")
            self.assertFalse(leakage["outer_test_subject_used_for_any_fit"])
            self.assertFalse(leakage["test_time_privileged_or_teacher_outputs_allowed"])

    def test_reconciliation_blocks_when_a2d_runtime_leakage_does_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            fm_runner = root / "phase1_final_comparator_runner" / "run"
            a2d_runner = root / "phase1_final_a2d_runner" / "run"
            _write_prereg(prereg)
            _write_feature_matrix_runner(fm_runner, feature_matrix_run)
            _write_a2d_runner(a2d_runner, feature_matrix_run, fm_runner, a2d_leakage=True)

            result = run_phase1_final_comparator_reconciliation(
                prereg_bundle=prereg,
                feature_matrix_comparator_run=fm_runner,
                final_a2d_run=a2d_runner,
                output_root=root / "phase1_final_comparator_reconciliation",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_comparator_reconciliation_blocked")
            self.assertIn("final_a2d_runtime_leakage_not_passed", summary["claim_blockers"])
            self.assertIn("A2d_riemannian_runtime_leakage_not_passed", summary["claim_blockers"])
            self.assertFalse(summary["claim_ready"])

    def test_cli_reconciliation_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            fm_runner = root / "phase1_final_comparator_runner" / "run"
            a2d_runner = root / "phase1_final_a2d_runner" / "run"
            output_root = root / "phase1_final_comparator_reconciliation"
            _write_prereg(prereg)
            _write_feature_matrix_runner(fm_runner, feature_matrix_run)
            _write_a2d_runner(a2d_runner, feature_matrix_run, fm_runner)

            exit_code = main(
                [
                    "phase1_final_comparator_reconciliation",
                    "--config",
                    str(prereg),
                    "--feature-matrix-comparator-run",
                    str(fm_runner),
                    "--final-a2d-run",
                    str(a2d_runner),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_comparator_reconciliation_summary.json")
            self.assertTrue(summary["all_final_comparator_outputs_present"])
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


def _write_feature_matrix_runner(run_dir: Path, feature_matrix_run: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for dirname in ["final_logits", "final_subject_level_metrics", "runtime_leakage_logs", "comparator_output_manifests", "blocked_comparators"]:
        (run_dir / dirname).mkdir(parents=True, exist_ok=True)

    for comparator in COMPARATORS:
        _write_comparator_outputs(run_dir, comparator)

    blocked = {
        "status": "phase1_final_comparator_blocked",
        "comparator_id": "A2d_riemannian",
        "claim_ready": False,
        "claim_evaluable": False,
        "smoke_artifacts_promoted": False,
        "logits_written": False,
        "metrics_written": False,
        "runtime_leakage_log_written": False,
        "blockers": ["A2d_riemannian_not_executable_from_final_feature_matrix"],
        "reason": "A2d requires covariance/tangent inputs.",
    }
    _write_json(run_dir / "blocked_comparators" / "A2d_riemannian_blocked.json", blocked)
    _write_json(run_dir / "comparator_output_manifests" / "A2d_riemannian_output_manifest.json", blocked)

    _write_json(
        run_dir / "phase1_final_comparator_runner_inputs.json",
        {
            "status": "phase1_final_comparator_runner_inputs_locked",
            "feature_matrix_run": str(feature_matrix_run),
            "prereg_bundle_hash_sha256": "test-prereg-hash",
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_runner_summary.json",
        {
            "status": "phase1_final_comparator_runner_partial_with_blockers",
            "feature_matrix_run": str(feature_matrix_run),
            "completed_comparators": COMPARATORS,
            "blocked_comparators": ["A2d_riemannian"],
            "final_comparator_outputs_present": False,
            "all_comparator_output_manifests_present": True,
            "runtime_comparator_logs_audited_for_completed_comparators": True,
            "runtime_comparator_logs_audited_for_all_required_comparators": False,
            "smoke_artifacts_promoted": False,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "claim_blockers": [
                "A2d_riemannian_not_executable_from_final_feature_matrix",
                "A2d_riemannian_final_covariance_runner_missing",
                "final_comparator_outputs_incomplete",
            ],
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_runner_source_links.json",
        {
            "status": "phase1_final_comparator_runner_source_links_recorded",
            "feature_matrix_run": str(feature_matrix_run),
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_runner_input_validation.json",
        {"status": "phase1_final_comparator_runner_inputs_ready", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_comparator_completeness_table.json",
        {
            "status": "phase1_final_comparator_completeness_partial",
            "all_final_comparator_outputs_present": False,
            "claim_ready": False,
            "claim_evaluable": False,
            "rows": [],
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_runtime_leakage_audit.json",
        {
            "status": "phase1_final_comparator_runtime_leakage_audit_partial_with_blockers",
            "runtime_logs_audited_for_completed_comparators": True,
            "runtime_logs_audited_for_all_required_comparators": False,
            "outer_test_subject_used_for_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "claim_ready": False,
            "claim_evaluable": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_runner_claim_state.json",
        {
            "status": "phase1_final_comparator_runner_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_artifacts_promoted": False,
            "blockers": ["final_comparator_outputs_incomplete"],
        },
    )


def _write_comparator_outputs(run_dir: Path, comparator: str) -> None:
    _write_json(
        run_dir / "final_logits" / f"{comparator}_final_logits.json",
        {
            "status": "phase1_final_comparator_logits_recorded",
            "comparator_id": comparator,
            "n_rows": 2,
            "contains_feature_values": False,
            "claim_ready": False,
            "claim_evaluable": False,
            "rows": [{"row_id": "row_000001", "prob_load8": 0.5}],
        },
    )
    _write_json(
        run_dir / "final_subject_level_metrics" / f"{comparator}_subject_level_metrics.json",
        {
            "status": "phase1_final_comparator_subject_metrics_recorded",
            "comparator_id": comparator,
            "claim_ready": False,
            "claim_evaluable": False,
        },
    )
    _write_json(
        run_dir / "runtime_leakage_logs" / f"{comparator}_runtime_leakage_audit.json",
        {
            "status": "phase1_final_comparator_runtime_leakage_audit_passed",
            "comparator_id": comparator,
            "outer_test_subject_used_for_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "claim_ready": False,
            "claim_evaluable": False,
        },
    )
    _write_json(
        run_dir / "comparator_output_manifests" / f"{comparator}_output_manifest.json",
        {
            "status": "phase1_final_comparator_output_manifest_recorded",
            "comparator_id": comparator,
            "claim_ready": False,
            "claim_evaluable": False,
            "smoke_artifacts_promoted": False,
            "runtime_leakage_passed": True,
            "files": {
                "logits": f"final_logits/{comparator}_final_logits.json",
                "subject_level_metrics": f"final_subject_level_metrics/{comparator}_subject_level_metrics.json",
                "runtime_leakage_audit": f"runtime_leakage_logs/{comparator}_runtime_leakage_audit.json",
            },
        },
    )


def _write_a2d_runner(
    run_dir: Path,
    feature_matrix_run: Path,
    previous_runner: Path,
    *,
    a2d_leakage: bool = False,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    for dirname in ["final_logits", "final_subject_level_metrics", "runtime_leakage_logs", "comparator_output_manifests"]:
        (run_dir / dirname).mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_a2d_runner_inputs.json",
        {
            "status": "phase1_final_a2d_runner_inputs_locked",
            "feature_matrix_run": str(feature_matrix_run),
            "feature_matrix_comparator_run": str(previous_runner),
        },
    )
    _write_json(
        run_dir / "phase1_final_a2d_runner_summary.json",
        {
            "status": "phase1_final_a2d_covariance_tangent_runner_complete_claim_closed",
            "comparator": "A2d_riemannian",
            "feature_matrix_run": str(feature_matrix_run),
            "a2d_final_output_present": True,
            "runtime_leakage_passed": not a2d_leakage,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_artifacts_promoted": False,
            "blockers": [],
            "claim_blockers": ["controls_calibration_influence_reporting_missing"],
        },
    )
    _write_json(run_dir / "phase1_final_a2d_runner_source_links.json", {"status": "phase1_final_a2d_runner_source_links_recorded"})
    _write_json(run_dir / "phase1_final_a2d_runner_input_validation.json", {"status": "phase1_final_a2d_runner_inputs_ready", "blockers": []})
    _write_json(
        run_dir / "phase1_final_a2d_covariance_validation.json",
        {"status": "phase1_final_a2d_covariance_validation_passed", "covariance_rows_ready": True, "blockers": []},
    )
    _write_json(run_dir / "a2d_final_covariance_manifest.json", {"status": "phase1_final_a2d_covariance_manifest_recorded"})
    _write_json(run_dir / "a2d_final_tangent_manifest.json", {"status": "phase1_final_a2d_tangent_manifest_recorded"})
    _write_json(
        run_dir / "phase1_final_a2d_completeness_patch.json",
        {
            "status": "phase1_final_a2d_completeness_patch_recorded",
            "previous_feature_matrix_comparator_run": str(previous_runner),
            "a2d_final_output_present": True,
            "resolved_blockers_for_downstream_reconciliation": [
                "A2d_riemannian_not_executable_from_final_feature_matrix",
                "A2d_riemannian_final_covariance_runner_missing",
            ],
            "claim_ready": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_a2d_claim_state.json",
        {
            "status": "phase1_final_a2d_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_artifacts_promoted": False,
            "blockers": ["controls_calibration_influence_reporting_missing"],
        },
    )
    _write_json(
        run_dir / "final_logits" / "A2d_riemannian_final_logits.json",
        {
            "status": "phase1_final_a2d_logits_recorded",
            "comparator_id": "A2d_riemannian",
            "n_rows": 2,
            "contains_covariance_values": False,
            "contains_tangent_features": False,
            "claim_ready": False,
            "claim_evaluable": False,
            "rows": [{"row_id": "row_000001", "prob_load8": 0.5}],
        },
    )
    _write_json(
        run_dir / "final_subject_level_metrics" / "A2d_riemannian_subject_level_metrics.json",
        {
            "status": "phase1_final_a2d_subject_metrics_recorded",
            "comparator_id": "A2d_riemannian",
            "claim_ready": False,
            "claim_evaluable": False,
        },
    )
    _write_json(
        run_dir / "runtime_leakage_logs" / "A2d_riemannian_runtime_leakage_audit.json",
        {
            "status": "phase1_final_a2d_runtime_leakage_audit_passed" if not a2d_leakage else "phase1_final_a2d_runtime_leakage_audit_blocked",
            "comparator_id": "A2d_riemannian",
            "outer_test_subject_used_for_any_fit": a2d_leakage,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "claim_ready": False,
            "claim_evaluable": False,
        },
    )
    _write_json(
        run_dir / "comparator_output_manifests" / "A2d_riemannian_output_manifest.json",
        {
            "status": "phase1_final_a2d_output_manifest_recorded",
            "comparator_id": "A2d_riemannian",
            "claim_ready": False,
            "claim_evaluable": False,
            "smoke_artifacts_promoted": False,
            "runtime_leakage_passed": not a2d_leakage,
            "files": {
                "logits": "final_logits/A2d_riemannian_final_logits.json",
                "subject_level_metrics": "final_subject_level_metrics/A2d_riemannian_subject_level_metrics.json",
                "runtime_leakage_audit": "runtime_leakage_logs/A2d_riemannian_runtime_leakage_audit.json",
                "covariance_manifest": "a2d_final_covariance_manifest.json",
                "tangent_manifest": "a2d_final_tangent_manifest.json",
            },
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
