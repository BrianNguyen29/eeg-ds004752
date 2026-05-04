from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main


ROOT = Path(__file__).resolve().parents[2]


class V56FeatureMatrixMaterializerSkeletonTests(unittest.TestCase):
    def test_materializer_skeleton_records_claim_closed_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            split_lock = _write_split_lock(root / "split_lock")
            provenance = _write_feature_provenance(root / "provenance")
            feature_plan = _write_feature_matrix_plan(root / "feature_plan")
            leakage_plan = _write_leakage_plan(root / "leakage_plan")
            output_root = root / "skeleton"

            exit_code = main(
                [
                    "v56-feature-matrix-materializer-skeleton",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-lock-run",
                    str(split_lock),
                    "--feature-provenance-run",
                    str(provenance),
                    "--feature-matrix-plan-run",
                    str(feature_plan),
                    "--leakage-audit-plan-run",
                    str(leakage_plan),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--materializer-skeleton-config",
                    str(ROOT / "configs" / "v56" / "feature_matrix_materializer_skeleton.json"),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            run_dir = Path(output_root.joinpath("latest.txt").read_text(encoding="utf-8"))
            skeleton = json.loads(
                run_dir.joinpath("v56_feature_matrix_materializer_skeleton.json").read_text(encoding="utf-8")
            )
            summary = json.loads(
                run_dir.joinpath("v56_feature_matrix_materializer_skeleton_summary.json").read_text(encoding="utf-8")
            )
            validation = json.loads(
                run_dir.joinpath("v56_feature_matrix_materializer_skeleton_validation.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(skeleton["status"], "planned_feature_matrix_materializer_skeleton_recorded")
            self.assertEqual(validation["status"], "v56_feature_matrix_materializer_skeleton_validation_passed")
            self.assertEqual(validation["blocking_errors"], [])
            self.assertTrue(skeleton["claim_closed"])
            self.assertFalse(skeleton["claim_ready"])
            self.assertFalse(skeleton["scientific_boundary"]["edf_payloads_read"])
            self.assertFalse(skeleton["scientific_boundary"]["feature_matrix_materialized"])
            self.assertFalse(skeleton["scientific_boundary"]["feature_values_written"])
            self.assertFalse(skeleton["scientific_boundary"]["model_training_run"])
            self.assertFalse(skeleton["scientific_boundary"]["efficacy_metrics_computed"])
            self.assertFalse(summary["edf_payloads_read"])
            self.assertFalse(summary["feature_matrix_materialized"])
            self.assertFalse(summary["feature_values_written"])

    def test_materializer_skeleton_rejects_leakage_plan_with_materialized_feature_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            split_lock = _write_split_lock(root / "split_lock")
            provenance = _write_feature_provenance(root / "provenance")
            feature_plan = _write_feature_matrix_plan(root / "feature_plan")
            leakage_plan = _write_leakage_plan(root / "leakage_plan", feature_matrix_materialized=True)

            exit_code = main(
                [
                    "v56-feature-matrix-materializer-skeleton",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-lock-run",
                    str(split_lock),
                    "--feature-provenance-run",
                    str(provenance),
                    "--feature-matrix-plan-run",
                    str(feature_plan),
                    "--leakage-audit-plan-run",
                    str(leakage_plan),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--materializer-skeleton-config",
                    str(ROOT / "configs" / "v56" / "feature_matrix_materializer_skeleton.json"),
                    "--output-root",
                    str(root / "skeleton"),
                ]
            )

            self.assertEqual(exit_code, 2)


def _write_gate0_run(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("manifest.json").write_text(
        json.dumps({"manifest_status": "signal_audit_ready", "gate0_blockers": []}), encoding="utf-8"
    )
    path.joinpath("cohort_lock.json").write_text(
        json.dumps({"cohort_lock_status": "signal_audit_ready", "n_primary_eligible": 3}), encoding="utf-8"
    )
    return path


def _write_split_lock(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("v56_split_registry_lock.json").write_text(
        json.dumps(
            {
                "status": "locked_subject_level_split_registry",
                "claim_closed": True,
                "test_time_inference": {
                    "modality": "scalp_eeg_only",
                    "allow_ieeg": False,
                    "allow_beamforming_bridge": False,
                },
                "folds": [{"fold_id": "fold_1"}],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_feature_provenance(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("v56_feature_provenance_populated.json").write_text(
        json.dumps({"status": "populated_source_hashes_and_split_links", "missing_sources": []}), encoding="utf-8"
    )
    return path


def _write_feature_matrix_plan(path: Path) -> Path:
    path.mkdir(parents=True)
    plan = {
        "status": "planned_feature_matrix_contract_recorded",
        "scientific_boundary": {
            "feature_matrix_materialized": False,
            "model_training_run": False,
            "comparator_execution_run": False,
            "efficacy_metrics_computed": False,
        },
        "primary_feature_sets": [{"id": "scalp_eeg_log_bandpower_v56"}],
    }
    path.joinpath("v56_feature_matrix_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    path.joinpath("v56_feature_matrix_plan_validation.json").write_text(
        json.dumps({"status": "v56_feature_matrix_plan_validation_passed"}), encoding="utf-8"
    )
    return path


def _write_leakage_plan(path: Path, *, feature_matrix_materialized: bool = False) -> Path:
    path.mkdir(parents=True)
    plan = {
        "status": "planned_feature_matrix_leakage_audit_recorded",
        "scientific_boundary": {
            "feature_matrix_materialized": feature_matrix_materialized,
            "runtime_comparator_logs_audited": False,
        },
    }
    path.joinpath("v56_feature_matrix_leakage_audit_plan.json").write_text(json.dumps(plan), encoding="utf-8")
    path.joinpath("v56_feature_matrix_leakage_audit_plan_validation.json").write_text(
        json.dumps({"status": "v56_feature_matrix_leakage_audit_plan_validation_passed"}), encoding="utf-8"
    )
    return path


if __name__ == "__main__":
    unittest.main()
