from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_comparator_runner_readiness import (
    Phase1FinalComparatorRunnerReadinessError,
    run_phase1_final_comparator_runner_readiness,
)


class Phase1FinalComparatorRunnerReadinessTests(unittest.TestCase):
    def test_runner_readiness_records_missing_outputs_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)

            result = run_phase1_final_comparator_runner_readiness(
                prereg_bundle=prereg,
                final_split_run=split_run,
                final_feature_run=feature_run,
                final_leakage_run=leakage_run,
                output_root=root / "phase1_final_comparator_runner_readiness",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            required = [
                "phase1_final_comparator_runner_output_contract.json",
                "phase1_final_comparator_runner_manifest_status.json",
                "phase1_final_comparator_missing_outputs.json",
                "phase1_final_comparator_runtime_leakage_requirements.json",
                "phase1_final_comparator_completeness_table.json",
                "phase1_final_comparator_runner_claim_state.json",
            ]
            for filename in required:
                self.assertTrue((result.output_dir / filename).exists(), filename)

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_comparator_runner_readiness_recorded")
            self.assertTrue(summary["upstream_manifests_ready"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["final_comparator_outputs_present"])
            self.assertFalse(summary["runtime_comparator_logs_audited"])
            self.assertFalse(summary["smoke_artifacts_promoted"])
            self.assertEqual(summary["n_required_comparators"], 6)
            self.assertEqual(summary["n_comparator_output_manifests_present"], 0)

            manifest_status = _read_json(result.output_dir / "phase1_final_comparator_runner_manifest_status.json")
            self.assertEqual(manifest_status["status"], "phase1_final_comparator_outputs_missing")
            self.assertFalse(manifest_status["claim_evaluable"])
            self.assertFalse(manifest_status["final_comparator_outputs_present"])
            self.assertEqual(len(manifest_status["comparators"]), 6)
            for row in manifest_status["comparators"]:
                self.assertFalse(row["claim_evaluable"])
                self.assertEqual(row["final_fold_logs"], "missing")
                self.assertEqual(row["final_logits"], "missing")
                self.assertEqual(row["final_subject_level_metrics"], "missing")
                self.assertEqual(row["runtime_leakage_logs"], "missing")
                self.assertFalse(row["smoke_metrics_promoted"])
                self.assertIn("runtime_leakage_logs", row["missing_outputs"])

            completeness = _read_json(result.output_dir / "phase1_final_comparator_completeness_table.json")
            self.assertEqual(completeness["status"], "phase1_final_comparator_completeness_table_not_claim_evaluable")
            self.assertFalse(completeness["claim_evaluable"])
            self.assertFalse(completeness["all_required_outputs_present"])

            claim_state = _read_json(result.output_dir / "phase1_final_comparator_runner_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_comparator_runner_claim_state_blocked")
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("final_comparator_outputs_missing", claim_state["blockers"])
            self.assertIn("runtime_comparator_leakage_logs_missing_until_final_runners_execute", claim_state["blockers"])

    def test_runner_readiness_rejects_runtime_leakage_audit_claim_boundary_violation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run, runtime_logs_audited=True)

            with self.assertRaises(Phase1FinalComparatorRunnerReadinessError):
                run_phase1_final_comparator_runner_readiness(
                    prereg_bundle=prereg,
                    final_split_run=split_run,
                    final_feature_run=feature_run,
                    final_leakage_run=leakage_run,
                    output_root=root / "phase1_final_comparator_runner_readiness",
                    repo_root=Path.cwd(),
                )

    def test_cli_final_comparator_runner_readiness_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)

            exit_code = main(
                [
                    "phase1_final_comparator_runner_readiness",
                    "--config",
                    str(prereg),
                    "--final-split-run",
                    str(split_run),
                    "--final-feature-run",
                    str(feature_run),
                    "--final-leakage-run",
                    str(leakage_run),
                    "--output-root",
                    str(root / "phase1_final_comparator_runner_readiness"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_comparator_runner_readiness" / "latest.txt").exists())


def _write_prereg(prereg: Path) -> None:
    _write_json(
        prereg,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
            "source_runs": {"gate0": "test-gate0-run"},
        },
    )


def _write_split_run(split_run: Path) -> None:
    split_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        split_run / "phase1_final_split_manifest_summary.json",
        {
            "status": "phase1_final_split_manifest_recorded",
            "split_manifest_ready": True,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
        },
    )
    _write_json(
        split_run / "final_split_manifest.json",
        {
            "status": "phase1_final_split_manifest_recorded",
            "split_id": "loso_subject",
            "eligible_subjects": ["sub-01", "sub-02"],
            "folds": [
                {
                    "fold_id": "fold_01_sub-01",
                    "outer_test_subject": "sub-01",
                    "test_subjects": ["sub-01"],
                    "train_subjects": ["sub-02"],
                    "no_subject_overlap_between_train_and_test": True,
                },
                {
                    "fold_id": "fold_02_sub-02",
                    "outer_test_subject": "sub-02",
                    "test_subjects": ["sub-02"],
                    "train_subjects": ["sub-01"],
                    "no_subject_overlap_between_train_and_test": True,
                },
            ],
            "claim_ready": False,
            "smoke_artifacts_promoted": False,
        },
    )
    _write_json(
        split_run / "phase1_final_split_manifest_validation.json",
        {
            "status": "phase1_final_split_manifest_validation_passed",
            "split_manifest_ready": True,
            "no_subject_overlap_between_train_and_test": True,
        },
    )
    _write_json(
        split_run / "phase1_final_split_manifest_claim_state.json",
        {"status": "phase1_final_split_manifest_claim_state_blocked", "claim_ready": False},
    )


def _write_feature_run(feature_run: Path) -> None:
    feature_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        feature_run / "phase1_final_feature_manifest_summary.json",
        {
            "status": "phase1_final_feature_manifest_recorded",
            "feature_manifest_ready": True,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
        },
    )
    _write_json(
        feature_run / "final_feature_manifest.json",
        {
            "status": "phase1_final_feature_manifest_recorded",
            "feature_set_id": "phase1_final_scalp_task_bandpower_v1",
            "feature_count": 2,
            "feature_names": ["Fz:theta", "Cz:theta"],
            "contains_feature_matrix": False,
            "contains_model_outputs": False,
            "contains_metrics": False,
            "claim_ready": False,
            "smoke_feature_rows_allowed_as_final": False,
        },
    )
    _write_json(
        feature_run / "phase1_final_feature_manifest_validation.json",
        {
            "status": "phase1_final_feature_manifest_validation_passed",
            "feature_manifest_ready": True,
        },
    )
    _write_json(
        feature_run / "phase1_final_feature_manifest_claim_state.json",
        {"status": "phase1_final_feature_manifest_claim_state_blocked", "claim_ready": False},
    )


def _write_leakage_run(leakage_run: Path, *, runtime_logs_audited: bool = False) -> None:
    leakage_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        leakage_run / "phase1_final_leakage_audit_summary.json",
        {
            "status": "phase1_final_leakage_audit_recorded",
            "leakage_audit_ready": True,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "outer_test_subject_used_in_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "runtime_comparator_logs_audited": runtime_logs_audited,
        },
    )
    _write_json(
        leakage_run / "final_leakage_audit.json",
        {
            "status": "phase1_final_leakage_audit_recorded",
            "n_folds": 2,
            "outer_test_subject_used_in_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "runtime_comparator_logs_audited": runtime_logs_audited,
            "contains_model_outputs": False,
            "contains_metrics": False,
            "claim_ready": False,
        },
    )
    _write_json(
        leakage_run / "phase1_final_leakage_audit_input_validation.json",
        {"status": "phase1_final_leakage_audit_input_validation_passed", "blockers": []},
    )
    _write_json(
        leakage_run / "phase1_final_leakage_audit_validation.json",
        {
            "status": "phase1_final_leakage_audit_validation_passed",
            "leakage_audit_ready": True,
            "outer_test_subject_used_in_any_fit": False,
            "runtime_comparator_logs_audited": runtime_logs_audited,
            "blockers": [],
        },
    )
    _write_json(
        leakage_run / "phase1_final_leakage_audit_claim_state.json",
        {"status": "phase1_final_leakage_audit_claim_state_blocked", "claim_ready": False},
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
