from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.prereg.bundle import PreregError
from src.prereg.bundle import run_prereg_assembly


class PreregAssemblyTests(unittest.TestCase):
    def test_prereg_rejects_failed_gate2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate2 = root / "gate2" / "run"
            repo = root / "repo"
            _write_repo_configs(repo)
            _write_gate_chain(root, gate2_status="gate2_synthetic_failed")

            with self.assertRaises(PreregError):
                run_prereg_assembly(gate2, _config(), root / "prereg", repo_root=repo)

    def test_prereg_generates_locked_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate2 = root / "gate2" / "run"
            repo = root / "repo"
            _write_repo_configs(repo)
            _write_gate_chain(root)

            result = run_prereg_assembly(gate2, _config(), root / "prereg", repo_root=repo)

            self.assertTrue(result.prereg_bundle_path.exists())
            self.assertTrue(result.environment_lock_path.exists())
            self.assertTrue(result.validation_report_path.exists())
            self.assertTrue(result.revision_policy_path.exists())
            self.assertTrue(result.summary_path.exists())

            bundle = json.loads(result.prereg_bundle_path.read_text(encoding="utf-8"))
            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))

            self.assertEqual(bundle["status"], "locked")
            self.assertEqual(bundle["gate"], "gate2_5_preregistration_bundle")
            self.assertTrue(bundle["artifact_hashes"])
            self.assertTrue(bundle["release_policy"]["release_blocker_satisfied"])
            self.assertEqual(summary["status"], "gate2_5_prereg_bundle_locked")
            self.assertTrue(summary["release_blocker_satisfied"])
            self.assertTrue((result.output_dir / "comparator_cards" / "A2d_riemannian.json").exists())

    def test_cli_gate25_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate2 = root / "gate2" / "run"
            repo = root / "repo"
            config_path = root / "prereg_config.json"
            _write_repo_configs(repo)
            _write_gate_chain(root)
            config_path.write_text(json.dumps(_config()), encoding="utf-8")

            cwd = Path.cwd()
            try:
                # main() passes Path.cwd() as repo_root, so run from the synthetic repo.
                import os

                os.chdir(repo)
                exit_code = main(
                    [
                        "gate25",
                        "--gate2-run",
                        str(gate2),
                        "--config",
                        str(config_path),
                        "--output-root",
                        str(root / "prereg"),
                    ]
                )
            finally:
                os.chdir(cwd)

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "prereg" / "latest.txt").exists())


def _config() -> dict[str, object]:
    return {
        "study_id": "test-study",
        "version": "test-version",
        "annex_version": "V5.5.1",
        "dossier_version": "V5.5",
        "parent_doc_ids": ["doc-a", "doc-b"],
        "revision_policy": {
            "post_prereg_changes_require_revision_log": True,
            "claim_affecting_changes_demote_to_post_hoc_unless_refrozen": True,
            "no_silent_changes_to_comparators_thresholds_teacher_pool_controls_or_reporting": True,
        },
        "allowed_real_phases_after_lock": ["phase05_real", "phase1_real"],
        "phase_release_note": "test release note",
        "comparator_configs": {
            "A2d_riemannian": "configs/models/riemannian_a2d.yaml",
            "A3_distillation": "configs/models/distill_a3.yaml",
        },
        "registry_configs": {
            "teacher_registry": "configs/teacher/teacher_registry.yaml",
            "admissibility_rubric": "configs/teacher/admissibility_rubric.yaml",
            "control_suite": "configs/controls/control_suite_spec.yaml",
        },
    }


def _write_repo_configs(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    files = [
        "configs/models/riemannian_a2d.yaml",
        "configs/models/distill_a3.yaml",
        "configs/teacher/teacher_registry.yaml",
        "configs/teacher/admissibility_rubric.yaml",
        "configs/controls/control_suite_spec.yaml",
    ]
    for name in files:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"id: {path.stem}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "test prereg configs"], cwd=repo, check=True, stdout=subprocess.DEVNULL)


def _write_gate_chain(root: Path, gate2_status: str = "gate2_synthetic_ready") -> None:
    gate0 = root / "gate0" / "run"
    gate1 = root / "gate1" / "run"
    gate2 = root / "gate2" / "run"
    for path in [gate0, gate1, gate2]:
        path.mkdir(parents=True, exist_ok=True)

    _write_json(gate0 / "manifest.json", {"status": "ok"})
    _write_json(gate0 / "cohort_lock.json", {"status": "ok"})
    _write_json(gate0 / "materialization_report.json", {"status": "ok"})
    (gate0 / "audit_report.md").write_text("# Gate 0\n", encoding="utf-8")

    for name in [
        "gate1_summary.json",
        "gate1_inputs.json",
        "gate1_input_integrity.json",
        "n_eff_statement.json",
        "simulation_registry.json",
        "sesoi_registry.json",
        "influence_rule.json",
    ]:
        _write_json(gate1 / name, {"status": "ok"})
    (gate1 / "decision_memo.md").write_text("# Gate 1\n", encoding="utf-8")

    gate2_summary = {
        "status": gate2_status,
        "gate0_source_of_truth": str(gate0),
        "gate1_source_of_truth": str(gate1),
        "recovery_status": "passed",
        "threshold_registry_status": "locked_after_gate2_pass",
        "real_data_phase_authorized": False,
    }
    threshold_registry = {
        "status": "locked_after_gate2_pass",
        "recovery_status": "passed",
        "threshold_registry_hash_sha256": "threshold-hash",
        "generator_hash_sha256": "generator-hash",
        "thresholds": {"delta_obs_min": 0.02, "influence_ceiling": 0.40},
    }
    _write_json(gate2 / "gate2_summary.json", gate2_summary)
    _write_json(gate2 / "synthetic_generator_spec.json", {"status": "ok"})
    _write_json(gate2 / "synthetic_recovery_report.json", {"status": "passed"})
    (gate2 / "synthetic_recovery_report.md").write_text("# Gate 2\n", encoding="utf-8")
    _write_json(gate2 / "gate_threshold_registry.json", threshold_registry)


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
