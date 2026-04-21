from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_leakage_audit import Phase1FinalLeakageAuditError, run_phase1_final_leakage_audit


class Phase1FinalLeakageAuditTests(unittest.TestCase):
    def test_final_leakage_audit_records_training_only_fit_scopes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)

            result = run_phase1_final_leakage_audit(
                prereg_bundle=prereg,
                final_split_run=split_run,
                final_feature_run=feature_run,
                output_root=root / "phase1_final_leakage_audit",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "final_leakage_audit.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_leakage_audit_validation.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_leakage_audit_claim_state.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_leakage_audit_recorded")
            self.assertTrue(summary["leakage_audit_ready"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["outer_test_subject_used_in_any_fit"])
            self.assertFalse(summary["test_time_privileged_or_teacher_outputs_allowed"])
            self.assertFalse(summary["runtime_comparator_logs_audited"])
            self.assertEqual(summary["n_folds"], 2)
            self.assertEqual(summary["n_stages"], 7)

            audit = _read_json(result.output_dir / "final_leakage_audit.json")
            self.assertEqual(audit["status"], "phase1_final_leakage_audit_recorded")
            self.assertFalse(audit["claim_ready"])
            self.assertFalse(audit["contains_model_outputs"])
            self.assertFalse(audit["contains_metrics"])
            self.assertFalse(audit["runtime_comparator_logs_audited"])
            self.assertFalse(audit["outer_test_subject_used_in_any_fit"])
            self.assertEqual(len(audit["folds"]), 2)
            for fold in audit["folds"]:
                outer = fold["outer_test_subject"]
                self.assertTrue(fold["no_outer_test_subject_in_any_fit"])
                self.assertFalse(fold["test_time_privileged_or_teacher_outputs_allowed"])
                for stage in fold["stages"]:
                    self.assertNotIn(outer, stage["fit_subjects"])
                    self.assertTrue(stage["fit_subjects_recorded"])
                    self.assertTrue(stage["transform_subjects_recorded"])
                    if stage["stage"] in {"teacher", "privileged"}:
                        self.assertEqual(stage["transform_subjects"], fold["train_subjects"])

            validation = _read_json(result.output_dir / "phase1_final_leakage_audit_validation.json")
            self.assertEqual(validation["status"], "phase1_final_leakage_audit_validation_passed")
            self.assertTrue(validation["leakage_audit_ready"])
            self.assertEqual(validation["blockers"], [])

            claim_state = _read_json(result.output_dir / "phase1_final_leakage_audit_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_leakage_audit_claim_state_blocked")
            self.assertTrue(claim_state["leakage_audit_ready"])
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("final_comparator_outputs_not_claim_evaluable", claim_state["blockers"])
            self.assertIn("runtime_comparator_leakage_logs_missing_until_final_runners_execute", claim_state["blockers"])

    def test_final_leakage_audit_rejects_feature_manifest_with_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run, contains_outputs=True)

            with self.assertRaises(Phase1FinalLeakageAuditError):
                run_phase1_final_leakage_audit(
                    prereg_bundle=prereg,
                    final_split_run=split_run,
                    final_feature_run=feature_run,
                    output_root=root / "phase1_final_leakage_audit",
                    repo_root=Path.cwd(),
                )

    def test_cli_final_leakage_audit_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)

            exit_code = main(
                [
                    "phase1_final_leakage_audit",
                    "--config",
                    str(prereg),
                    "--final-split-run",
                    str(split_run),
                    "--final-feature-run",
                    str(feature_run),
                    "--output-root",
                    str(root / "phase1_final_leakage_audit"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_leakage_audit" / "latest.txt").exists())


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


def _write_feature_run(feature_run: Path, *, contains_outputs: bool = False) -> None:
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
            "contains_feature_matrix": contains_outputs,
            "contains_model_outputs": contains_outputs,
            "contains_metrics": contains_outputs,
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


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
