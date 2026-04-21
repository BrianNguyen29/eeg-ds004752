from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_comparator_artifacts import run_phase1_final_comparator_artifact_plan


class Phase1FinalComparatorArtifactPlanTests(unittest.TestCase):
    def test_final_comparator_artifact_plan_records_missing_manifests_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            claim_package = root / "phase1_final_claim_package_plan" / "run"
            _write_prereg(prereg)
            _write_claim_package_run(claim_package)

            result = run_phase1_final_comparator_artifact_plan(
                prereg_bundle=prereg,
                claim_package_run=claim_package,
                output_root=root / "phase1_final_comparator_artifact_plan",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_artifact_contract.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_manifest_status.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_missing_artifacts.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_leakage_requirements.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_claim_state.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_comparator_implementation_plan.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_comparator_artifact_plan_recorded")
            self.assertEqual(summary["artifact_plan_status"], "planning_non_claim")
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertFalse(summary["all_final_comparator_manifests_present"])
            self.assertFalse(summary["smoke_metrics_promoted"])
            self.assertIn("A4_privileged", summary["required_final_comparators"])

            contract = _read_json(result.output_dir / "phase1_final_comparator_artifact_contract.json")
            self.assertTrue(contract["comparator_contract_matches_claim_package"])
            self.assertTrue(contract["artifact_schema_matches_claim_package"])
            self.assertFalse(contract["manifest_schema"]["smoke_metrics_promoted"])

            manifest_status = _read_json(result.output_dir / "phase1_final_comparator_manifest_status.json")
            self.assertEqual(manifest_status["status"], "phase1_final_comparator_manifests_missing")
            self.assertFalse(manifest_status["claim_evaluable"])
            self.assertEqual(len(manifest_status["comparators"]), 6)
            for row in manifest_status["comparators"]:
                self.assertEqual(row["status"], "final_comparator_manifest_missing")
                self.assertFalse(row["claim_evaluable"])
                self.assertFalse(row["smoke_metrics_promoted"])
                self.assertIn("final_logits", row["missing_artifacts"])

            claim_state = _read_json(result.output_dir / "phase1_final_comparator_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_comparator_claim_state_blocked")
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("final_comparator_artifact_plan_not_locked", claim_state["blockers"])
            self.assertIn("final_comparator_artifact_manifests_missing", claim_state["blockers"])
            self.assertIn("A4 superiority over A2/A2b/A2c/A2d/A3", claim_state["not_ok_to_claim"])

    def test_cli_final_comparator_artifact_plan_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            claim_package = root / "phase1_final_claim_package_plan" / "run"
            _write_prereg(prereg)
            _write_claim_package_run(claim_package)

            exit_code = main(
                [
                    "phase1_final_comparator_artifact_plan",
                    "--config",
                    str(prereg),
                    "--claim-package-run",
                    str(claim_package),
                    "--output-root",
                    str(root / "phase1_final_comparator_artifact_plan"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_comparator_artifact_plan" / "latest.txt").exists())


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


def _write_claim_package_run(claim_package: Path) -> None:
    claim_package.mkdir(parents=True, exist_ok=True)
    required_comparators = ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]
    _write_json(
        claim_package / "phase1_final_claim_package_plan_summary.json",
        {
            "status": "phase1_final_claim_package_plan_recorded",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "required_final_comparators": required_comparators,
            "blockers": ["final_comparator_artifact_manifests_missing"],
        },
    )
    _write_json(
        claim_package / "phase1_final_claim_package_contract.json",
        {
            "status": "phase1_final_claim_package_contract_recorded",
            "required_final_comparators": required_comparators,
            "required_final_comparator_artifacts": [
                "final_fold_logs",
                "final_subject_level_metrics",
                "final_logits",
                "final_comparator_completeness_table",
                "final_split_manifest",
                "final_feature_manifest",
                "final_leakage_audit",
            ],
        },
    )
    _write_json(
        claim_package / "phase1_final_claim_state_plan.json",
        {
            "status": "phase1_final_claim_state_plan_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "blockers": ["final_comparator_artifact_manifests_missing"],
        },
    )
    _write_json(
        claim_package / "phase1_final_claim_blocker_inventory.json",
        {
            "status": "phase1_final_claim_blocker_inventory_recorded",
            "blockers": ["final_comparator_artifact_manifests_missing"],
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
