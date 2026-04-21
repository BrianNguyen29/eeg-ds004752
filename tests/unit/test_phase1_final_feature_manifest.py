from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_feature_manifest import run_phase1_final_feature_manifest


class Phase1FinalFeatureManifestTests(unittest.TestCase):
    def test_final_feature_manifest_records_schema_without_feature_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            dataset_root = root / "ds004752"
            gate0_run = root / "gate0" / "run"
            split_run = root / "phase1_final_split_manifest" / "run"
            _write_prereg(prereg)
            _write_dataset(dataset_root)
            _write_gate0_run(gate0_run, materialized=True)
            _write_split_run(split_run, gate0_run)

            result = run_phase1_final_feature_manifest(
                prereg_bundle=prereg,
                final_split_run=split_run,
                dataset_root=dataset_root,
                output_root=root / "phase1_final_feature_manifest",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "final_feature_manifest.json").exists())
            self.assertFalse((result.output_dir / "phase1_final_feature_manifest_blocked.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_feature_inventory.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_feature_manifest_recorded")
            self.assertTrue(summary["feature_manifest_ready"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertEqual(summary["materialization_status"], "complete")
            self.assertEqual(summary["n_subjects"], 2)
            self.assertEqual(summary["n_features"], 6)
            self.assertEqual(summary["feature_manifest_blockers"], [])

            manifest = _read_json(result.output_dir / "final_feature_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_feature_manifest_recorded")
            self.assertEqual(manifest["feature_set_id"], "phase1_final_scalp_task_bandpower_v1")
            self.assertEqual(manifest["feature_count"], 6)
            self.assertEqual(
                manifest["feature_names"],
                ["Cz:alpha", "Cz:beta", "Cz:theta", "Fz:alpha", "Fz:beta", "Fz:theta"],
            )
            self.assertFalse(manifest["contains_feature_matrix"])
            self.assertFalse(manifest["contains_model_outputs"])
            self.assertFalse(manifest["contains_metrics"])
            self.assertFalse(manifest["claim_ready"])
            self.assertFalse(manifest["smoke_feature_rows_allowed_as_final"])
            self.assertEqual(manifest["n_event_rows_planned"], 4)

            validation = _read_json(result.output_dir / "phase1_final_feature_manifest_validation.json")
            self.assertEqual(validation["status"], "phase1_final_feature_manifest_validation_passed")
            self.assertTrue(validation["feature_manifest_ready"])
            self.assertFalse(validation["contains_feature_matrix"])
            self.assertFalse(validation["smoke_feature_rows_allowed_as_final"])

            claim_state = _read_json(result.output_dir / "phase1_final_feature_manifest_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_feature_manifest_claim_state_blocked")
            self.assertTrue(claim_state["feature_manifest_ready"])
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("final_leakage_audit_missing", claim_state["blockers"])
            self.assertIn("final_comparator_outputs_not_claim_evaluable", claim_state["blockers"])

    def test_final_feature_manifest_blocks_when_materialization_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            dataset_root = root / "ds004752"
            gate0_run = root / "gate0" / "run"
            split_run = root / "phase1_final_split_manifest" / "run"
            _write_prereg(prereg)
            _write_dataset(dataset_root)
            _write_gate0_run(gate0_run, materialized=False)
            _write_split_run(split_run, gate0_run)

            result = run_phase1_final_feature_manifest(
                prereg_bundle=prereg,
                final_split_run=split_run,
                dataset_root=dataset_root,
                output_root=root / "phase1_final_feature_manifest",
                repo_root=Path.cwd(),
            )

            self.assertFalse((result.output_dir / "final_feature_manifest.json").exists())
            self.assertTrue((result.output_dir / "phase1_final_feature_manifest_blocked.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_feature_manifest_blocked")
            self.assertFalse(summary["feature_manifest_ready"])
            self.assertIn("materialization_not_complete", summary["feature_manifest_blockers"])
            self.assertIn("final_feature_manifest_missing", summary["claim_blockers"])

            blocked = _read_json(result.output_dir / "phase1_final_feature_manifest_blocked.json")
            self.assertEqual(blocked["status"], "phase1_final_feature_manifest_not_written")
            self.assertIn("materialization_not_complete", blocked["blockers"])

    def test_cli_final_feature_manifest_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            dataset_root = root / "ds004752"
            gate0_run = root / "gate0" / "run"
            split_run = root / "phase1_final_split_manifest" / "run"
            _write_prereg(prereg)
            _write_dataset(dataset_root)
            _write_gate0_run(gate0_run, materialized=True)
            _write_split_run(split_run, gate0_run)

            exit_code = main(
                [
                    "phase1_final_feature_manifest",
                    "--config",
                    str(prereg),
                    "--final-split-run",
                    str(split_run),
                    "--dataset-root",
                    str(dataset_root),
                    "--output-root",
                    str(root / "phase1_final_feature_manifest"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase1_final_feature_manifest" / "latest.txt").exists())


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


def _write_dataset(dataset_root: Path) -> None:
    for subject in ["sub-01", "sub-02"]:
        eeg = dataset_root / subject / "ses-01" / "eeg"
        eeg.mkdir(parents=True, exist_ok=True)
        (eeg / f"{subject}_ses-01_task-verbalWM_run-01_channels.tsv").write_text(
            "name\ttype\tsampling_frequency\nFz\tEEG\t500\nCz\tEEG\t500\n",
            encoding="utf-8",
        )
        (eeg / f"{subject}_ses-01_task-verbalWM_run-01_events.tsv").write_text(
            "nTrial\tSetSize\tArtifact\n1\t4\t0\n2\t8\t0\n3\t6\t0\n4\t4\t1\n",
            encoding="utf-8",
        )


def _write_gate0_run(gate0_run: Path, *, materialized: bool) -> None:
    gate0_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        gate0_run / "manifest.json",
        {
            "manifest_status": "signal_audit_ready",
            "gate0_blockers": [],
            "participants": {"n_primary_eligible": 2},
        },
    )
    _write_json(
        gate0_run / "cohort_lock.json",
        {
            "cohort_lock_status": "signal_audit_ready",
            "n_primary_eligible": 2,
            "participants": [
                {"participant_id": "sub-01", "primary_eligible": True},
                {"participant_id": "sub-02", "primary_eligible": True},
            ],
        },
    )
    _write_json(
        gate0_run / "materialization_report.json",
        {
            "status": "complete" if materialized else "incomplete",
            "payloads": {
                "edf": {"count": 4, "materialized_count": 4 if materialized else 2, "missing_count": 0 if materialized else 2},
                "mat": {"count": 2, "materialized_count": 2 if materialized else 1, "missing_count": 0 if materialized else 1},
            },
        },
    )


def _write_split_run(split_run: Path, gate0_run: Path) -> None:
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
            "unit": "participant_id",
            "source_gate0_run": str(gate0_run),
            "source_gate0_manifest_status": "signal_audit_ready",
            "source_cohort_lock_status": "signal_audit_ready",
            "eligible_subjects": ["sub-01", "sub-02"],
            "n_folds": 2,
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
            "all_eligible_subjects_appear_once_as_outer_test": True,
            "no_subject_overlap_between_train_and_test": True,
            "blockers": [],
        },
    )
    _write_json(
        split_run / "phase1_final_split_manifest_claim_state.json",
        {
            "status": "phase1_final_split_manifest_claim_state_blocked",
            "split_manifest_ready": True,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
        },
    )
    _write_json(
        split_run / "phase1_final_split_manifest_source_links.json",
        {
            "status": "phase1_final_split_manifest_source_links_recorded",
            "gate0_run": str(gate0_run),
        },
    )


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
