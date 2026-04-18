from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.prereg.bundle import run_prereg_assembly
from src.phase05.observability import Phase05Error
from src.phase05.observability import run_phase05_observability


class Phase05ObservabilityTests(unittest.TestCase):
    def test_phase05_generates_observability_preflight_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            gate2 = root / "gate2" / "run"
            _write_repo_configs(repo)
            _write_gate_chain(root)
            prereg = run_prereg_assembly(gate2, _prereg_config(), root / "prereg", repo_root=repo)

            result = run_phase05_observability(
                prereg.prereg_bundle_path,
                _phase05_config(),
                root / "phase05",
                repo_root=repo,
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.teacher_plan_path.exists())
            self.assertTrue(result.teacher_qc_registry_path.exists())
            self.assertTrue(result.controls_plan_path.exists())
            self.assertTrue(result.atlas_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue(result.summary_path.exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            atlas = json.loads(result.atlas_path.read_text(encoding="utf-8"))
            teacher_qc = json.loads(result.teacher_qc_registry_path.read_text(encoding="utf-8"))

            self.assertEqual(summary["status"], "phase05_observability_preflight_ready")
            self.assertTrue(summary["does_not_train_decoder"])
            self.assertTrue(summary["does_not_estimate_model_efficacy"])
            self.assertFalse(summary["real_data_phase_authorized_for_decoder"])
            self.assertEqual(atlas["status"], "observability_atlas_draft_preflight")
            self.assertEqual(atlas["subject_count"], 1)
            self.assertEqual(teacher_qc["metric_status"], "not_computed_by_registry_preflight")

    def test_phase05_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            gate2 = root / "gate2" / "run"
            _write_repo_configs(repo)
            _write_gate_chain(root)
            prereg = run_prereg_assembly(gate2, _prereg_config(), root / "prereg", repo_root=repo)

            # Mutate a hash-linked artifact after prereg lock.
            (root / "gate0" / "run" / "manifest.json").write_text('{"tampered": true}', encoding="utf-8")

            with self.assertRaises(Phase05Error):
                run_phase05_observability(
                    prereg.prereg_bundle_path,
                    _phase05_config(),
                    root / "phase05",
                    repo_root=repo,
                )

    def test_cli_phase05_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            gate2 = root / "gate2" / "run"
            phase_config = root / "phase05_config.json"
            _write_repo_configs(repo)
            _write_gate_chain(root)
            prereg = run_prereg_assembly(gate2, _prereg_config(), root / "prereg", repo_root=repo)
            phase_config.write_text(json.dumps(_phase05_config()), encoding="utf-8")

            cwd = Path.cwd()
            try:
                import os

                os.chdir(repo)
                exit_code = main(
                    [
                        "phase05_real",
                        "--config",
                        str(prereg.prereg_bundle_path),
                        "--phase-config",
                        str(phase_config),
                        "--output-root",
                        str(root / "phase05"),
                    ]
                )
            finally:
                os.chdir(cwd)

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "phase05" / "latest.txt").exists())


def _phase05_config() -> dict[str, object]:
    return {
        "phase_id": "phase05_real",
        "workflow": "observability_only_predecoder",
        "enabled_teacher_groups": ["group_a_roi_band_summaries", "group_b_visible_latent_subspace"],
        "deferred_teacher_groups": {
            "group_c_cross_frequency_descriptors": "deferred_until_marker_quality_gate",
            "group_d_marker_gated_targets": "deferred_until_marker_quality_gate",
            "group_e_bridge_targets": "deferred_until_phase3_sentinel",
        },
        "required_controls": [
            "task_contrast_observability",
            "grouped_permutation",
            "spatial_control",
            "nuisance_shared_control",
        ],
        "scientific_scope": [
            "Phase 0.5 is observability-only and does not train the Phase 1 decoder.",
        ],
    }


def _prereg_config() -> dict[str, object]:
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
            "nuisance_block": "configs/controls/nuisance_block_spec.yaml",
        },
    }


def _write_repo_configs(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    files = {
        "configs/models/riemannian_a2d.yaml": "model_id: riemannian_a2d\n",
        "configs/models/distill_a3.yaml": "model_id: distill_a3\n",
        "configs/teacher/teacher_registry.yaml": (
            "registry_status: test\n"
            "teacher_groups:\n"
            "  group_a_roi_band_summaries: phase1_candidate\n"
            "  group_b_visible_latent_subspace: phase1_candidate\n"
            "  group_c_cross_frequency_descriptors: phase2_candidate\n"
        ),
        "configs/teacher/admissibility_rubric.yaml": "rubric_status: test\n",
        "configs/controls/control_suite_spec.yaml": "control_suite_status: test\n",
        "configs/controls/nuisance_block_spec.yaml": "nuisance_block_status: test\n",
    }
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "test phase05 configs"], cwd=repo, check=True, stdout=subprocess.DEVNULL)


def _write_gate_chain(root: Path) -> None:
    gate0 = root / "gate0" / "run"
    gate1 = root / "gate1" / "run"
    gate2 = root / "gate2" / "run"
    for path in [gate0, gate1, gate2]:
        path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "subjects": {"n_sessions": 1},
        "signal_audit": {
            "session_results": [
                {
                    "status": "ok",
                    "subject": "sub-01",
                    "session": "ses-01",
                    "eeg": {"n_channels": 19, "sfreq": 200.0, "reader": "mne"},
                    "ieeg": {"n_channels": 48, "sfreq": 2000.0, "reader": "mne"},
                }
            ]
        },
    }
    cohort = {
        "cohort_lock_status": "signal_audit_ready",
        "fallback_reader_registry": [],
        "participants": [{"participant_id": "sub-01", "primary_eligible": True}],
    }
    _write_json(gate0 / "manifest.json", manifest)
    _write_json(gate0 / "cohort_lock.json", cohort)
    _write_json(gate0 / "materialization_report.json", {"status": "complete"})
    (gate0 / "audit_report.md").write_text("# Gate 0\n", encoding="utf-8")

    n_eff = {"n_primary_eligible": 1, "primary_denominator": "subject"}
    for name in [
        "gate1_summary.json",
        "gate1_inputs.json",
        "gate1_input_integrity.json",
        "simulation_registry.json",
        "sesoi_registry.json",
        "influence_rule.json",
    ]:
        _write_json(gate1 / name, {"status": "ok"})
    _write_json(gate1 / "n_eff_statement.json", n_eff)
    (gate1 / "decision_memo.md").write_text("# Gate 1\n", encoding="utf-8")

    gate2_summary = {
        "status": "gate2_synthetic_ready",
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
