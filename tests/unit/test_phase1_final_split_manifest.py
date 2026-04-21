from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_split_manifest import run_phase1_final_split_manifest


class Phase1FinalSplitManifestTests(unittest.TestCase):
    def test_final_split_manifest_records_loso_folds_from_signal_ready_gate0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            sfl_run = root / "phase1_final_split_feature_leakage_plan" / "run"
            gate0_run = root / "gate0" / "run"
            _write_prereg(prereg)
            _write_sfl_run(sfl_run)
            _write_gate0_run(gate0_run, signal_ready=True)

            result = run_phase1_final_split_manifest(
                prereg_bundle=prereg,
                split_feature_leakage_run=sfl_run,
                gate0_run=gate0_run,
                output_root=root / "phase1_final_split_manifest",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "final_split_manifest.json").exists())
            self.assertFalse((result.output_dir / "phase1_final_split_manifest_blocked.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_manifest_validation.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_manifest_claim_state.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_split_manifest_recorded")
            self.assertTrue(summary["split_manifest_ready"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertEqual(summary["n_eligible_subjects"], 3)
            self.assertEqual(summary["n_folds"], 3)
            self.assertEqual(summary["split_manifest_blockers"], [])

            manifest = _read_json(result.output_dir / "final_split_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_split_manifest_recorded")
            self.assertEqual(manifest["split_id"], "loso_subject")
            self.assertEqual(manifest["unit"], "participant_id")
            self.assertFalse(manifest["claim_ready"])
            self.assertFalse(manifest["standalone_claim_ready"])
            self.assertFalse(manifest["smoke_artifacts_promoted"])
            self.assertEqual(manifest["eligible_subjects"], ["sub-01", "sub-02", "sub-03"])
            self.assertEqual(len(manifest["folds"]), 3)
            for fold in manifest["folds"]:
                self.assertNotIn(fold["outer_test_subject"], fold["train_subjects"])
                self.assertEqual(fold["test_subjects"], [fold["outer_test_subject"]])
                self.assertTrue(fold["no_subject_overlap_between_train_and_test"])
                self.assertFalse(fold["fit_scope_rules"]["outer_test_subject_in_teacher_fit_allowed"])

            validation = _read_json(result.output_dir / "phase1_final_split_manifest_validation.json")
            self.assertEqual(validation["status"], "phase1_final_split_manifest_validation_passed")
            self.assertTrue(validation["all_eligible_subjects_appear_once_as_outer_test"])
            self.assertTrue(validation["no_subject_overlap_between_train_and_test"])
            self.assertEqual(validation["blockers"], [])

            claim_state = _read_json(result.output_dir / "phase1_final_split_manifest_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_split_manifest_claim_state_blocked")
            self.assertTrue(claim_state["split_manifest_ready"])
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("final_feature_manifest_missing", claim_state["blockers"])
            self.assertIn("final_leakage_audit_missing", claim_state["blockers"])
            self.assertIn("A4 superiority over A2/A2b/A2c/A2d/A3", claim_state["not_ok_to_claim"])

    def test_final_split_manifest_blocks_when_gate0_not_signal_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            sfl_run = root / "phase1_final_split_feature_leakage_plan" / "run"
            gate0_run = root / "gate0" / "run"
            _write_prereg(prereg)
            _write_sfl_run(sfl_run)
            _write_gate0_run(gate0_run, signal_ready=False)

            result = run_phase1_final_split_manifest(
                prereg_bundle=prereg,
                split_feature_leakage_run=sfl_run,
                gate0_run=gate0_run,
                output_root=root / "phase1_final_split_manifest",
                repo_root=Path.cwd(),
            )

            self.assertFalse((result.output_dir / "final_split_manifest.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_split_manifest_blocked.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_split_manifest_blocked")
            self.assertFalse(summary["split_manifest_ready"])
            self.assertEqual(summary["n_folds"], 0)
            self.assertIn("gate0_manifest_not_signal_audit_ready", summary["split_manifest_blockers"])
            self.assertIn("cohort_lock_not_signal_audit_ready", summary["split_manifest_blockers"])
            self.assertIn("gate0_blockers_present", summary["split_manifest_blockers"])
            self.assertIn("insufficient_primary_eligible_subjects_for_loso", summary["split_manifest_blockers"])

            blocked = _read_json(result.output_dir / "phase1_final_split_manifest_blocked.json")
            self.assertEqual(blocked["status"], "phase1_final_split_manifest_not_written")
            self.assertIn("final split manifest", blocked["scientific_limit"])

            claim_state = _read_json(result.output_dir / "phase1_final_split_manifest_claim_state.json")
            self.assertFalse(claim_state["split_manifest_ready"])
            self.assertIn("final_split_manifest_missing", claim_state["blockers"])
            self.assertIn("claim_blocked_until_final_split_manifest_exists", claim_state["blockers"])

    def test_cli_final_split_manifest_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            sfl_run = root / "phase1_final_split_feature_leakage_plan" / "run"
            gate0_run = root / "gate0" / "run"
            _write_prereg(prereg)
            _write_sfl_run(sfl_run)
            _write_gate0_run(gate0_run, signal_ready=True)

            exit_code = main(
                [
                    "phase1_final_split_manifest",
                    "--config",
                    str(prereg),
                    "--split-feature-leakage-run",
                    str(sfl_run),
                    "--gate0-run",
                    str(gate0_run),
                    "--output-root",
                    str(root / "phase1_final_split_manifest"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_split_manifest" / "latest.txt").exists())


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


def _write_sfl_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_split_feature_leakage_plan_summary.json",
        {
            "status": "phase1_final_split_feature_leakage_plan_recorded",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_artifacts_promoted": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_split_feature_leakage_contract.json",
        {
            "status": "phase1_final_split_feature_leakage_contract_recorded",
            "split_manifest_schema": {"split_id": "loso_subject", "unit": "participant_id"},
        },
    )
    _write_json(
        run_dir / "phase1_final_split_manifest_readiness.json",
        {
            "status": "phase1_final_split_manifest_not_ready",
            "split_id": "loso_subject",
            "group_key": "participant_id",
        },
    )
    _write_json(
        run_dir / "phase1_final_split_feature_leakage_claim_state.json",
        {
            "status": "phase1_final_split_feature_leakage_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_artifacts_promoted": False,
        },
    )


def _write_gate0_run(run_dir: Path, *, signal_ready: bool) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    participants = []
    for subject in ["sub-01", "sub-02", "sub-03"]:
        participants.append(
            {
                "participant_id": subject,
                "metadata_present": True,
                "n_sessions": 2,
                "primary_eligible": True if signal_ready else None,
                "exclusion_reason": None,
            }
        )
    _write_json(
        run_dir / "manifest.json",
        {
            "manifest_status": "signal_audit_ready" if signal_ready else "draft_metadata_only",
            "dataset_root": "ds004752",
            "participants": {
                "n_primary_eligible": 3 if signal_ready else None,
                "primary_eligibility_status": "signal_audit_ready"
                if signal_ready
                else "not_locked_pending_signal_level_gate0",
            },
            "gate0_blockers": [] if signal_ready else ["cohort_lock_is_draft_until_signal_level_audit"],
        },
    )
    _write_json(
        run_dir / "cohort_lock.json",
        {
            "cohort_lock_status": "signal_audit_ready" if signal_ready else "draft_not_primary_locked",
            "n_primary_eligible": 3 if signal_ready else None,
            "participants": participants,
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
