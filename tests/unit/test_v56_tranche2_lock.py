from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main


ROOT = Path(__file__).resolve().parents[2]


class V56Tranche2LockTests(unittest.TestCase):
    def test_v56_tranche2_lock_writes_locked_split_and_populated_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            scaffold_root = root / "scaffold"
            lock_root = root / "lock"

            scaffold_exit = main(
                [
                    "v56-scaffold",
                    "--gate0-run",
                    str(gate0),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--splits",
                    str(ROOT / "configs" / "v56" / "splits.json"),
                    "--controls",
                    str(ROOT / "configs" / "v56" / "controls.json"),
                    "--comparators",
                    str(ROOT / "configs" / "v56" / "comparators.json"),
                    "--output-root",
                    str(scaffold_root),
                ]
            )
            self.assertEqual(scaffold_exit, 0)

            lock_exit = main(
                [
                    "v56-tranche2-lock",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-run",
                    str(scaffold_root / "v56_split_registry" / "latest.txt"),
                    "--feature-provenance-run",
                    str(scaffold_root / "v56_feature_provenance" / "latest.txt"),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--splits",
                    str(ROOT / "configs" / "v56" / "splits.json"),
                    "--output-root",
                    str(lock_root),
                ]
            )
            self.assertEqual(lock_exit, 0)

            split_dir = Path((lock_root / "v56_split_registry_lock" / "latest.txt").read_text(encoding="utf-8"))
            feature_dir = Path(
                (lock_root / "v56_feature_provenance_populated" / "latest.txt").read_text(encoding="utf-8")
            )
            split_lock = json.loads(split_dir.joinpath("v56_split_registry_lock.json").read_text(encoding="utf-8"))
            provenance = json.loads(
                feature_dir.joinpath("v56_feature_provenance_populated.json").read_text(encoding="utf-8")
            )

            self.assertEqual(split_lock["status"], "locked_subject_level_split_registry")
            self.assertTrue(split_lock["claim_closed"])
            self.assertTrue(split_lock["subject_isolation_enforced"])
            self.assertEqual(split_lock["test_time_inference"]["modality"], "scalp_eeg_only")
            self.assertFalse(split_lock["test_time_inference"]["allow_ieeg"])
            self.assertEqual(len(split_lock["folds"]), 6)
            for fold in split_lock["folds"]:
                self.assertNotIn(fold["outer_test_subject"], fold["train_subjects"])
                self.assertFalse(fold["test_time_allow_ieeg"])

            self.assertEqual(provenance["status"], "populated_source_hashes_and_split_links")
            self.assertTrue(provenance["claim_closed"])
            self.assertTrue(provenance["required_links_satisfied"]["split_registry"])
            self.assertTrue(provenance["required_links_satisfied"]["source_hashes"])
            self.assertTrue(provenance["required_links_satisfied"]["manifest"])
            self.assertFalse(provenance["feature_matrix_materialized"])
            self.assertFalse(provenance["model_training_run"])
            self.assertFalse(provenance["efficacy_metrics_computed"])
            self.assertGreaterEqual(len(provenance["entries"]), 7)

    def test_v56_tranche2_lock_rejects_draft_gate0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(
                root / "gate0",
                manifest_status="draft_metadata_plus_signal_sample",
                cohort_lock_status="draft_not_primary_locked",
                primary_eligible=False,
            )
            split_run = _write_scaffold(root / "split", "v56_split_registry", "pending_registry_lock")
            provenance_run = _write_scaffold(
                root / "provenance",
                "v56_feature_provenance",
                "pending_feature_provenance_population",
            )

            exit_code = main(
                [
                    "v56-tranche2-lock",
                    "--gate0-run",
                    str(gate0),
                    "--split-registry-run",
                    str(split_run),
                    "--feature-provenance-run",
                    str(provenance_run),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--splits",
                    str(ROOT / "configs" / "v56" / "splits.json"),
                    "--output-root",
                    str(root / "lock"),
                ]
            )

            self.assertEqual(exit_code, 2)


def _write_gate0_run(
    path: Path,
    *,
    manifest_status: str = "signal_audit_ready",
    cohort_lock_status: str = "signal_audit_ready",
    primary_eligible: bool = True,
) -> Path:
    path.mkdir(parents=True)
    path.joinpath("manifest.json").write_text(
        json.dumps(
            {
                "manifest_status": manifest_status,
                "gate0_blockers": [] if manifest_status == "signal_audit_ready" else ["signal_audit_not_ready"],
            }
        ),
        encoding="utf-8",
    )
    path.joinpath("cohort_lock.json").write_text(
        json.dumps(
            {
                "cohort_lock_status": cohort_lock_status,
                "n_primary_eligible": 3 if primary_eligible else None,
                "participants": [
                    {
                        "participant_id": f"sub-{index:02d}",
                        "primary_eligible": primary_eligible,
                    }
                    for index in range(1, 4)
                ],
            }
        ),
        encoding="utf-8",
    )
    path.joinpath("materialization_report.json").write_text(
        json.dumps({"status": "complete", "payloads": {"edf": {"count": 6}, "mat": {"count": 3}}}),
        encoding="utf-8",
    )
    return path


def _write_scaffold(path: Path, family: str, status: str) -> Path:
    path.mkdir(parents=True)
    payload = {
        "artifact_family": family,
        "status": status,
        "claim_closed": True,
        "test_time_inference": "scalp_eeg_only",
    }
    path.joinpath(f"{family}.json").write_text(json.dumps(payload), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
