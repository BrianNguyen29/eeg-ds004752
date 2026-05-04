from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main


ROOT = Path(__file__).resolve().parents[2]


class V56FeatureMatrixLeakageAuditPlanTests(unittest.TestCase):
    def test_leakage_audit_plan_records_claim_closed_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            split_lock = _write_split_lock(root / "split_lock")
            provenance = _write_feature_provenance(root / "provenance")
            feature_plan = _write_feature_matrix_plan(root / "feature_plan")
            output_root = root / "leakage_plan"

            exit_code = main(
                [
                    "v56-feature-matrix-leakage-plan",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-lock-run",
                    str(split_lock),
                    "--feature-provenance-run",
                    str(provenance),
                    "--feature-matrix-plan-run",
                    str(feature_plan),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--leakage-audit-plan-config",
                    str(ROOT / "configs" / "v56" / "feature_matrix_leakage_audit_plan.json"),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            run_dir = Path(output_root.joinpath("latest.txt").read_text(encoding="utf-8"))
            plan = json.loads(
                run_dir.joinpath("v56_feature_matrix_leakage_audit_plan.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                run_dir.joinpath("v56_feature_matrix_leakage_audit_plan_summary.json").read_text(encoding="utf-8")
            )
            validation = json.loads(
                run_dir.joinpath("v56_feature_matrix_leakage_audit_plan_validation.json").read_text(encoding="utf-8")
            )

            self.assertEqual(plan["status"], "planned_feature_matrix_leakage_audit_recorded")
            self.assertEqual(validation["status"], "v56_feature_matrix_leakage_audit_plan_validation_passed")
            self.assertEqual(validation["blocking_errors"], [])
            self.assertTrue(plan["claim_closed"])
            self.assertFalse(plan["claim_ready"])
            self.assertFalse(plan["test_time_inference"]["allow_ieeg"])
            self.assertFalse(plan["test_time_inference"]["allow_beamforming_bridge"])
            self.assertFalse(plan["scientific_boundary"]["feature_matrix_materialized"])
            self.assertFalse(plan["scientific_boundary"]["runtime_comparator_logs_audited"])
            self.assertFalse(plan["scientific_boundary"]["model_training_run"])
            self.assertFalse(plan["scientific_boundary"]["efficacy_metrics_computed"])
            self.assertFalse(summary["feature_matrix_materialized"])
            self.assertFalse(summary["runtime_comparator_logs_audited"])

    def test_leakage_audit_plan_rejects_test_time_ieeg(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            split_lock = _write_split_lock(root / "split_lock", allow_ieeg=True)
            provenance = _write_feature_provenance(root / "provenance")
            feature_plan = _write_feature_matrix_plan(root / "feature_plan")

            exit_code = main(
                [
                    "v56-feature-matrix-leakage-plan",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-lock-run",
                    str(split_lock),
                    "--feature-provenance-run",
                    str(provenance),
                    "--feature-matrix-plan-run",
                    str(feature_plan),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--leakage-audit-plan-config",
                    str(ROOT / "configs" / "v56" / "feature_matrix_leakage_audit_plan.json"),
                    "--output-root",
                    str(root / "leakage_plan"),
                ]
            )

            self.assertEqual(exit_code, 2)


def _write_gate0_run(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("manifest.json").write_text(
        json.dumps({"manifest_status": "signal_audit_ready", "gate0_blockers": []}),
        encoding="utf-8",
    )
    path.joinpath("cohort_lock.json").write_text(
        json.dumps({"cohort_lock_status": "signal_audit_ready", "n_primary_eligible": 3}),
        encoding="utf-8",
    )
    return path


def _write_split_lock(path: Path, *, allow_ieeg: bool = False) -> Path:
    path.mkdir(parents=True)
    path.joinpath("v56_split_registry_lock.json").write_text(
        json.dumps(
            {
                "status": "locked_subject_level_split_registry",
                "claim_closed": True,
                "subject_isolation_enforced": True,
                "test_time_inference": {
                    "modality": "scalp_eeg_only",
                    "allow_ieeg": allow_ieeg,
                    "allow_beamforming_bridge": False,
                },
                "folds": [
                    {
                        "fold_id": "fold_1",
                        "outer_test_subject": "sub-01",
                        "train_subjects": ["sub-02", "sub-03"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_feature_provenance(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("v56_feature_provenance_populated.json").write_text(
        json.dumps(
            {
                "status": "populated_source_hashes_and_split_links",
                "claim_closed": True,
                "required_links_satisfied": {"split_registry": True, "source_hashes": True, "manifest": True},
                "missing_sources": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_feature_matrix_plan(path: Path) -> Path:
    path.mkdir(parents=True)
    plan = {
        "status": "planned_feature_matrix_contract_recorded",
        "plan_id": "v56_feature_matrix_plan_v1",
        "claim_closed": True,
        "privileged_train_time_sources": [
            {"id": "ieeg_teacher_train_time_only", "allowed_at_test_time": False, "requires_train_fold_fit_only": True}
        ],
        "scientific_boundary": {
            "feature_matrix_materialized": False,
            "model_training_run": False,
            "comparator_execution_run": False,
            "efficacy_metrics_computed": False,
        },
    }
    path.joinpath("v56_feature_matrix_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    path.joinpath("v56_feature_matrix_plan_summary.json").write_text(
        json.dumps({"claim_closed": True}), encoding="utf-8"
    )
    path.joinpath("v56_feature_matrix_plan_validation.json").write_text(
        json.dumps({"status": "v56_feature_matrix_plan_validation_passed"}), encoding="utf-8"
    )
    return path


if __name__ == "__main__":
    unittest.main()
