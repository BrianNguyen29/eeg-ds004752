from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_split_feature_leakage import run_phase1_final_split_feature_leakage_plan


class Phase1FinalSplitFeatureLeakagePlanTests(unittest.TestCase):
    def test_split_feature_leakage_plan_records_missing_manifests_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_artifact = root / "phase1_final_comparator_artifact_plan" / "run"
            _write_prereg(prereg)
            _write_comparator_artifact_run(comparator_artifact)

            result = run_phase1_final_split_feature_leakage_plan(
                prereg_bundle=prereg,
                comparator_artifact_run=comparator_artifact,
                output_root=root / "phase1_final_split_feature_leakage_plan",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "phase1_final_split_feature_leakage_contract.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_manifest_readiness.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_feature_manifest_readiness.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_leakage_audit_readiness.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_feature_leakage_source_links.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_feature_leakage_missing_manifests.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_feature_leakage_claim_state.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_feature_leakage_implementation_plan.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_split_feature_leakage_plan_recorded")
            self.assertEqual(summary["readiness_status"], "planning_non_claim")
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertFalse(summary["all_required_manifests_present"])
            self.assertFalse(summary["smoke_artifacts_promoted"])
            self.assertIn("final_split_manifest", summary["required_manifests"])

            contract = _read_json(result.output_dir / "phase1_final_split_feature_leakage_contract.json")
            self.assertTrue(contract["schema_matches_comparator_artifact_plan"])
            self.assertEqual(contract["split_manifest_schema"]["split_id"], "loso_subject")
            self.assertTrue(contract["feature_manifest_schema"]["payload_materialization_required_for_final"])
            self.assertFalse(contract["feature_manifest_schema"]["smoke_feature_rows_allowed_as_final"])

            split = _read_json(result.output_dir / "phase1_final_split_manifest_readiness.json")
            self.assertEqual(split["status"], "phase1_final_split_manifest_not_ready")
            self.assertEqual(split["split_id"], "loso_subject")
            self.assertIn("final_split_manifest_missing", split["blockers"])

            feature = _read_json(result.output_dir / "phase1_final_feature_manifest_readiness.json")
            self.assertEqual(feature["status"], "phase1_final_feature_manifest_not_ready")
            self.assertFalse(feature["smoke_feature_rows_allowed_as_final"])
            self.assertIn("materialized_payload_signal_audit_for_final_scope_missing", feature["blockers"])

            leakage = _read_json(result.output_dir / "phase1_final_leakage_audit_readiness.json")
            self.assertEqual(leakage["status"], "phase1_final_leakage_audit_not_ready")
            self.assertFalse(leakage["required_schema"]["outer_test_subject_in_teacher_fit_allowed"])
            self.assertFalse(leakage["required_schema"]["test_time_privileged_or_teacher_outputs_allowed"])

            claim_state = _read_json(result.output_dir / "phase1_final_split_feature_leakage_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_split_feature_leakage_claim_state_blocked")
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("final_split_feature_leakage_plan_not_locked", claim_state["blockers"])
            self.assertIn("final_split_manifest_missing", claim_state["blockers"])
            self.assertIn("final_feature_manifest_missing", claim_state["blockers"])
            self.assertIn("final_leakage_audit_missing", claim_state["blockers"])
            self.assertIn("A4 superiority over A2/A2b/A2c/A2d/A3", claim_state["not_ok_to_claim"])

    def test_cli_split_feature_leakage_plan_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_artifact = root / "phase1_final_comparator_artifact_plan" / "run"
            _write_prereg(prereg)
            _write_comparator_artifact_run(comparator_artifact)

            exit_code = main(
                [
                    "phase1_final_split_feature_leakage_plan",
                    "--config",
                    str(prereg),
                    "--comparator-artifact-run",
                    str(comparator_artifact),
                    "--output-root",
                    str(root / "phase1_final_split_feature_leakage_plan"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_split_feature_leakage_plan" / "latest.txt").exists())


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


def _write_comparator_artifact_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    comparators = ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]
    required = [
        "final_fold_logs",
        "final_subject_level_metrics",
        "final_logits",
        "final_split_manifest",
        "final_feature_manifest",
        "final_leakage_audit",
    ]
    _write_json(
        run_dir / "phase1_final_comparator_artifact_plan_summary.json",
        {
            "status": "phase1_final_comparator_artifact_plan_recorded",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "required_final_comparators": comparators,
            "smoke_metrics_promoted": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_artifact_contract.json",
        {
            "status": "phase1_final_comparator_artifact_contract_recorded",
            "source_claim_package_run_status": "phase1_final_claim_package_plan_recorded",
            "required_final_comparators": comparators,
            "required_artifacts_per_comparator": required,
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_manifest_status.json",
        {"status": "phase1_final_comparator_manifests_missing", "claim_evaluable": False},
    )
    _write_json(
        run_dir / "phase1_final_comparator_missing_artifacts.json",
        {"status": "phase1_final_comparator_missing_artifacts_recorded", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_comparator_leakage_requirements.json",
        {
            "status": "phase1_final_comparator_leakage_requirements_recorded",
            "requirements": {
                "outer_test_subject_in_teacher_fit_allowed": False,
                "test_time_privileged_or_teacher_outputs_allowed": False,
            },
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_claim_state.json",
        {
            "status": "phase1_final_comparator_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_metrics_promoted": False,
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
