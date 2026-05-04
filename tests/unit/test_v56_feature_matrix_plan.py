from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main


ROOT = Path(__file__).resolve().parents[2]


class V56FeatureMatrixPlanTests(unittest.TestCase):
    def test_v56_feature_matrix_plan_records_claim_closed_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            split_lock = _write_split_lock(root / "split_lock")
            provenance = _write_feature_provenance(root / "provenance")
            output_root = root / "feature_plan"

            exit_code = main(
                [
                    "v56-feature-matrix-plan",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-lock-run",
                    str(split_lock),
                    "--feature-provenance-run",
                    str(provenance),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--feature-matrix-plan-config",
                    str(ROOT / "configs" / "v56" / "feature_matrix_plan.json"),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            run_dir = Path(output_root.joinpath("latest.txt").read_text(encoding="utf-8"))
            plan = json.loads(run_dir.joinpath("v56_feature_matrix_plan.json").read_text(encoding="utf-8"))
            summary = json.loads(run_dir.joinpath("v56_feature_matrix_plan_summary.json").read_text(encoding="utf-8"))
            validation = json.loads(
                run_dir.joinpath("v56_feature_matrix_plan_validation.json").read_text(encoding="utf-8")
            )

            self.assertEqual(plan["status"], "planned_feature_matrix_contract_recorded")
            self.assertEqual(validation["status"], "v56_feature_matrix_plan_validation_passed")
            self.assertEqual(validation["blocking_errors"], [])
            self.assertTrue(plan["claim_closed"])
            self.assertFalse(plan["claim_ready"])
            self.assertFalse(plan["test_time_inference"]["allow_ieeg"])
            self.assertFalse(plan["test_time_inference"]["allow_beamforming_bridge"])
            self.assertFalse(plan["scientific_boundary"]["feature_matrix_materialized"])
            self.assertFalse(plan["scientific_boundary"]["model_training_run"])
            self.assertFalse(plan["scientific_boundary"]["efficacy_metrics_computed"])
            self.assertFalse(summary["feature_matrix_materialized"])
            self.assertFalse(summary["model_training_run"])
            self.assertFalse(summary["efficacy_metrics_computed"])

    def test_v56_feature_matrix_plan_rejects_non_scalp_test_time_feature(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            split_lock = _write_split_lock(root / "split_lock")
            provenance = _write_feature_provenance(root / "provenance")
            bad_config = root / "bad_feature_matrix_plan.json"
            config = json.loads((ROOT / "configs" / "v56" / "feature_matrix_plan.json").read_text(encoding="utf-8"))
            config["primary_feature_sets"][0]["source_modality"] = "ieeg"
            bad_config.write_text(json.dumps(config), encoding="utf-8")

            exit_code = main(
                [
                    "v56-feature-matrix-plan",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-lock-run",
                    str(split_lock),
                    "--feature-provenance-run",
                    str(provenance),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--feature-matrix-plan-config",
                    str(bad_config),
                    "--output-root",
                    str(root / "feature_plan"),
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
        json.dumps(
            {
                "cohort_lock_status": "signal_audit_ready",
                "n_primary_eligible": 3,
                "participants": [
                    {"participant_id": f"sub-{index:02d}", "primary_eligible": True}
                    for index in range(1, 4)
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_split_lock(path: Path) -> Path:
    path.mkdir(parents=True)
    path.joinpath("v56_split_registry_lock.json").write_text(
        json.dumps(
            {
                "status": "locked_subject_level_split_registry",
                "claim_closed": True,
                "subject_isolation_enforced": True,
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
        json.dumps(
            {
                "status": "populated_source_hashes_and_split_links",
                "claim_closed": True,
                "required_links_satisfied": {
                    "split_registry": True,
                    "source_hashes": True,
                    "manifest": True,
                },
                "missing_sources": [],
            }
        ),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
