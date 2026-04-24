from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.config import load_config
from src.v56.artifacts import (
    write_control_registry_artifact,
    write_feature_provenance_artifact,
    write_leaderboard_artifact,
    write_split_registry_artifact,
)
from src.v56.benchmark import V56ReadinessError, load_benchmark_spec
from src.v56.controls import load_control_policy
from src.v56.splits import load_split_policy


ROOT = Path(__file__).resolve().parents[2]


class V56ArtifactWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.benchmark_spec = load_benchmark_spec(ROOT / "configs" / "v56" / "benchmark_spec.json")
        self.split_policy = load_split_policy(ROOT / "configs" / "v56" / "splits.json")
        self.control_policy = load_control_policy(ROOT / "configs" / "v56" / "controls.json")
        self.comparators = load_config(ROOT / "configs" / "v56" / "comparators.json")
        self.manifest = {
            "manifest_status": "signal_audit_ready",
            "gate0_blockers": [],
        }
        self.cohort_lock = {
            "cohort_lock_status": "signal_audit_ready",
            "n_primary_eligible": 15,
        }

    def test_split_registry_writer_creates_latest_pointer_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "v56_split_registry"
            result = write_split_registry_artifact(
                benchmark_spec=self.benchmark_spec,
                split_policy=self.split_policy,
                manifest=self.manifest,
                cohort_lock=self.cohort_lock,
                output_root=output_root,
                repo_root=ROOT,
            )

            artifact = json.loads(result.artifact_path.read_text(encoding="utf-8"))
            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            latest = output_root.joinpath("latest.txt").read_text(encoding="utf-8").strip()

            self.assertEqual(artifact["artifact_family"], "v56_split_registry")
            self.assertEqual(artifact["status"], "pending_registry_lock")
            self.assertEqual(summary["gate0_manifest_status"], "signal_audit_ready")
            self.assertEqual(Path(latest), result.output_dir)

    def test_feature_provenance_writer_records_claim_closed_pending_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = write_feature_provenance_artifact(
                benchmark_spec=self.benchmark_spec,
                split_policy=self.split_policy,
                manifest=self.manifest,
                cohort_lock=self.cohort_lock,
                output_root=Path(tmpdir) / "v56_feature_provenance",
                repo_root=ROOT,
            )

            artifact = json.loads(result.artifact_path.read_text(encoding="utf-8"))
            self.assertTrue(artifact["claim_closed"])
            self.assertEqual(artifact["status"], "pending_feature_provenance_population")
            self.assertEqual(artifact["required_links"]["split_registry"], True)

    def test_control_registry_writer_preserves_claim_blocking_tiers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = write_control_registry_artifact(
                benchmark_spec=self.benchmark_spec,
                control_policy=self.control_policy,
                manifest=self.manifest,
                cohort_lock=self.cohort_lock,
                output_root=Path(tmpdir) / "v56_control_registry",
                repo_root=ROOT,
            )

            artifact = json.loads(result.artifact_path.read_text(encoding="utf-8"))
            blocking = [tier["id"] for tier in artifact["tiers"] if tier["claim_blocking"]]
            self.assertEqual(blocking, ["data_integrity", "control_adequacy", "reporting"])

    def test_leaderboard_writer_keeps_all_rows_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            result = write_leaderboard_artifact(
                benchmark_spec=self.benchmark_spec,
                comparators_config=self.comparators,
                manifest=self.manifest,
                cohort_lock=self.cohort_lock,
                output_root=Path(tmpdir) / "v56_leaderboard",
                repo_root=ROOT,
            )

            artifact = json.loads(result.artifact_path.read_text(encoding="utf-8"))
            self.assertEqual(artifact["primary_target_id"], "A4_privileged")
            self.assertTrue(all(row["run_status"] == "pending_not_run" for row in artifact["rows"]))

    def test_writers_refuse_non_signal_ready_gate0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(V56ReadinessError):
                write_split_registry_artifact(
                    benchmark_spec=self.benchmark_spec,
                    split_policy=self.split_policy,
                    manifest={
                        "manifest_status": "draft_metadata_plus_signal_sample",
                        "gate0_blockers": ["cohort_lock_is_draft_until_signal_level_audit"],
                    },
                    cohort_lock={
                        "cohort_lock_status": "draft_not_primary_locked",
                        "n_primary_eligible": None,
                    },
                    output_root=Path(tmpdir) / "v56_split_registry",
                    repo_root=ROOT,
                )


if __name__ == "__main__":
    unittest.main()
