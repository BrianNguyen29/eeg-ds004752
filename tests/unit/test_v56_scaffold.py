from __future__ import annotations

import unittest
from pathlib import Path

from src.config import load_config
from src.v56.benchmark import (
    V56ReadinessError,
    assert_signal_ready_gate0,
    build_benchmark_scaffold_record,
    load_benchmark_spec,
)
from src.v56.controls import assert_claim_blocking_controls, build_control_registry_skeleton, load_control_policy
from src.v56.leaderboard import build_leaderboard_skeleton
from src.v56.provenance import build_feature_provenance_skeleton
from src.v56.splits import assert_scalp_only_test_time, build_split_registry_skeleton, load_split_policy


ROOT = Path(__file__).resolve().parents[2]


class V56ScaffoldTests(unittest.TestCase):
    def test_benchmark_spec_requires_signal_ready_gate0(self) -> None:
        spec = load_benchmark_spec(ROOT / "configs" / "v56" / "benchmark_spec.json")
        manifest = {
            "manifest_status": "signal_audit_ready",
            "gate0_blockers": [],
        }
        cohort_lock = {
            "cohort_lock_status": "signal_audit_ready",
            "n_primary_eligible": 15,
        }

        record = build_benchmark_scaffold_record(spec, manifest, cohort_lock)

        self.assertEqual(record["status"], "ready_for_benchmark_control_scaffolding")
        self.assertTrue(record["claim_closed"])
        self.assertEqual(record["primary_target_id"], "A4_privileged")

    def test_benchmark_spec_rejects_draft_gate0(self) -> None:
        spec = load_benchmark_spec(ROOT / "configs" / "v56" / "benchmark_spec.json")
        manifest = {
            "manifest_status": "draft_metadata_plus_signal_sample",
            "gate0_blockers": ["cohort_lock_is_draft_until_signal_level_audit"],
        }
        cohort_lock = {
            "cohort_lock_status": "draft_not_primary_locked",
            "n_primary_eligible": None,
        }

        with self.assertRaises(V56ReadinessError):
            assert_signal_ready_gate0(manifest, cohort_lock, spec)

    def test_split_policy_keeps_test_time_scalp_only(self) -> None:
        policy = load_split_policy(ROOT / "configs" / "v56" / "splits.json")

        assert_scalp_only_test_time(policy)
        registry = build_split_registry_skeleton(policy)

        self.assertEqual(registry["split_registry_version"], "v56-tranche2")
        self.assertEqual(len(registry["tracks"]), 2)

    def test_control_policy_keeps_claim_blocking_tiers(self) -> None:
        policy = load_control_policy(ROOT / "configs" / "v56" / "controls.json")

        assert_claim_blocking_controls(policy)
        registry = build_control_registry_skeleton(policy)

        blocking = [tier["id"] for tier in registry["tiers"] if tier["claim_blocking"]]
        self.assertEqual(blocking, ["data_integrity", "control_adequacy", "reporting"])

    def test_leaderboard_and_provenance_start_pending(self) -> None:
        spec = load_benchmark_spec(ROOT / "configs" / "v56" / "benchmark_spec.json")
        comparators = load_config(ROOT / "configs" / "v56" / "comparators.json")
        split_policy = load_split_policy(ROOT / "configs" / "v56" / "splits.json")

        leaderboard = build_leaderboard_skeleton(spec, comparators)
        provenance = build_feature_provenance_skeleton(split_policy, spec)

        self.assertEqual(leaderboard["primary_target_id"], "A4_privileged")
        self.assertTrue(all(row["run_status"] == "pending_not_run" for row in leaderboard["rows"]))
        self.assertEqual(provenance["status"], "pending_feature_provenance_population")
        self.assertTrue(provenance["claim_closed"])


if __name__ == "__main__":
    unittest.main()
