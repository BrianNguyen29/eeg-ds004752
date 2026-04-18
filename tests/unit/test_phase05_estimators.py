from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import src.phase05.estimators as estimators
from src.cli import main
from src.phase05.estimators import run_phase05_estimators
from src.phase05.observability import run_phase05_observability
from src.prereg.bundle import run_prereg_assembly


class Phase05EstimatorTests(unittest.TestCase):
    def test_phase05_estimators_generate_control_limited_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            gate2 = root / "gate2" / "run"
            dataset = root / "dataset" / "ds004752"
            _write_repo_configs(repo)
            _write_gate_chain(root)
            _write_fake_dataset(dataset)
            prereg = run_prereg_assembly(gate2, _prereg_config(), root / "prereg", repo_root=repo)
            phase05 = run_phase05_observability(
                prereg.prereg_bundle_path,
                _phase05_config(),
                root / "phase05",
                repo_root=repo,
            )

            original_imports = estimators._optional_signal_imports
            original_read_edf = estimators._read_edf
            original_ica = estimators._build_ica_features_by_outer_subject
            try:
                estimators._optional_signal_imports = _fake_signal_imports
                estimators._read_edf = _fake_read_edf
                estimators._build_ica_features_by_outer_subject = _fake_ica_features_by_outer_subject
                result = run_phase05_estimators(
                    prereg_bundle=prereg.prereg_bundle_path,
                    phase05_run=phase05.output_dir,
                    dataset_root=dataset,
                    config=_estimator_config(),
                    output_root=root / "phase05_estimators",
                    repo_root=repo,
                    max_subjects=2,
                    max_sessions=2,
                    max_trials_per_session=6,
                    n_permutations=3,
                )
            finally:
                estimators._optional_signal_imports = original_imports
                estimators._read_edf = original_read_edf
                estimators._build_ica_features_by_outer_subject = original_ica

            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.observability_path.exists())
            self.assertTrue(result.controls_report_path.exists())
            self.assertTrue(result.teacher_survival_path.exists())
            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            controls = json.loads(result.controls_report_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "phase05_estimators_smoke_complete")
            self.assertFalse(summary["claim_ready"])
            self.assertTrue(summary["does_not_train_decoder"])
            self.assertNotIn("spatial_permutation_control_not_computed", controls["blockers"])
            self.assertNotIn("ica_robustness_control_not_computed", controls["blockers"])
            self.assertEqual(controls["ica_control_status"], "computed")

    def test_cli_phase05_estimators_help(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["phase05_estimators", "--help"])
        self.assertEqual(raised.exception.code, 0)


class _FakeRaw:
    def __init__(self, data, sfreq, ch_names):
        self._data = data
        self.info = {"sfreq": sfreq}
        self.ch_names = ch_names

    def get_data(self):
        return self._data


def _fake_signal_imports():
    import numpy as np

    return np, object()


def _fake_read_edf(_mne, path: Path):
    import numpy as np

    rng = np.random.default_rng(123 if "_eeg" in path.name else 456)
    if "_eeg" in path.name:
        time = np.arange(12000) / 200.0
        data = np.vstack(
            [
                np.sin(2 * np.pi * 6 * time) + 0.01 * rng.normal(size=time.size),
                np.cos(2 * np.pi * 10 * time) + 0.01 * rng.normal(size=time.size),
            ]
        )
        return _FakeRaw(data, 200.0, ["F3", "F4"])
    time = np.arange(120000) / 2000.0
    data = np.vstack(
        [
            np.sin(2 * np.pi * 6 * time) + 0.01 * rng.normal(size=time.size),
            np.cos(2 * np.pi * 10 * time) + 0.01 * rng.normal(size=time.size),
            np.sin(2 * np.pi * 20 * time) + 0.01 * rng.normal(size=time.size),
        ]
    )
    return _FakeRaw(data, 2000.0, ["i1", "i2", "i3"])


def _fake_ica_features_by_outer_subject(*, np, rows, subjects, feature_names, **_kwargs):
    x_task = np.asarray([row["x_task"] for row in rows], dtype=float)
    return {
        subject: {
            "status": "ok",
            "reason": "fake_ica_for_unit_test",
            "x_ica": x_task,
            "n_common_channels": 2,
            "n_components": 1,
            "excluded_components": [],
        }
        for subject in subjects
    }


def _estimator_config() -> dict[str, object]:
    return {
        "phase_id": "phase05_real",
        "workflow": "task_contrast_observability_estimators",
        "signal_windows_sec": {
            "task_maintenance": [2.25, 4.75],
            "matched_temporal_control": [5.25, 7.75],
        },
        "frequency_bands_hz": {"theta": [4.0, 8.0], "alpha": [8.0, 13.0]},
        "ridge_alpha": 1.0,
        "default_n_permutations": 3,
        "final_min_n_permutations": 200,
        "random_seed": 75205,
        "default_max_subjects": 2,
        "default_max_sessions": 2,
        "default_max_trials_per_session": 6,
        "spatial_min_delta_q2": 0.02,
        "ica_robustness_min_ratio": 0.7,
        "ica_iclabel_artifact_probability": 0.9,
        "ica_target_sfreq": 200.0,
        "ica_max_components": 2,
        "ica_random_state": 752051,
        "teacher_target_family": "ieeg_roi_band_mean_log_power",
        "student_feature_family": "scalp_channel_band_log_power",
        "implemented_controls": [
            "task_vs_matched_temporal_control",
            "grouped_teacher_permutation",
            "nuisance_only_control",
            "rowwise_spatial_permutation_control",
            "ica_robustness_control",
        ],
        "pending_controls": [],
        "scientific_scope": ["test scope"],
    }


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
    subprocess.run(["git", "commit", "-m", "test phase05 estimator configs"], cwd=repo, check=True, stdout=subprocess.DEVNULL)


def _write_gate_chain(root: Path) -> None:
    gate0 = root / "gate0" / "run"
    gate1 = root / "gate1" / "run"
    gate2 = root / "gate2" / "run"
    for path in [gate0, gate1, gate2]:
        path.mkdir(parents=True, exist_ok=True)

    manifest = {
        "subjects": {"n_sessions": 2},
        "signal_audit": {
            "session_results": [
                {"status": "ok", "subject": "sub-01", "session": "ses-01"},
                {"status": "ok", "subject": "sub-02", "session": "ses-01"},
            ]
        },
    }
    cohort = {
        "cohort_lock_status": "signal_audit_ready",
        "fallback_reader_registry": [],
        "participants": [
            {"participant_id": "sub-01", "primary_eligible": True},
            {"participant_id": "sub-02", "primary_eligible": True},
        ],
    }
    _write_json(gate0 / "manifest.json", manifest)
    _write_json(gate0 / "cohort_lock.json", cohort)
    _write_json(gate0 / "materialization_report.json", {"status": "complete"})
    (gate0 / "audit_report.md").write_text("# Gate 0\n", encoding="utf-8")

    for name in [
        "gate1_summary.json",
        "gate1_inputs.json",
        "gate1_input_integrity.json",
        "simulation_registry.json",
        "sesoi_registry.json",
        "influence_rule.json",
    ]:
        _write_json(gate1 / name, {"status": "ok"})
    _write_json(gate1 / "n_eff_statement.json", {"n_primary_eligible": 2, "primary_denominator": "subject"})
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
        "thresholds": {
            "delta_obs_min": 0.02,
            "nuisance_relative_ceiling": 0.50,
            "nuisance_absolute_ceiling": 0.02,
        },
    }
    _write_json(gate2 / "gate2_summary.json", gate2_summary)
    _write_json(gate2 / "synthetic_generator_spec.json", {"status": "ok"})
    _write_json(gate2 / "synthetic_recovery_report.json", {"status": "passed"})
    (gate2 / "synthetic_recovery_report.md").write_text("# Gate 2\n", encoding="utf-8")
    _write_json(gate2 / "gate_threshold_registry.json", threshold_registry)


def _write_fake_dataset(dataset: Path) -> None:
    for subject in ["sub-01", "sub-02"]:
        eeg_dir = dataset / subject / "ses-01" / "eeg"
        ieeg_dir = dataset / subject / "ses-01" / "ieeg"
        eeg_dir.mkdir(parents=True, exist_ok=True)
        ieeg_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{subject}_ses-01_task-verbalWM_run-01"
        (eeg_dir / f"{stem}_eeg.edf").write_text("fake", encoding="utf-8")
        (ieeg_dir / f"{stem}_ieeg.edf").write_text("fake", encoding="utf-8")
        events = [
            "onset\tduration\tnTrial\tbegSample\tendSample\tSetSize\tProbeLetter\tMatch\tCorrect\tResponseTime\tArtifact",
        ]
        for index in range(1, 9):
            beg = 1 + (index - 1) * 1600
            end = index * 1600
            events.append(f"{(index - 1) * 8}.005\t8\t{index}\t{beg}\t{end}\t4\tA\tIN\t1\t1.0\t0")
        (eeg_dir / f"{stem}_events.tsv").write_text("\n".join(events) + "\n", encoding="utf-8")
        (ieeg_dir / f"{stem}_electrodes.tsv").write_text(
            "name\tx\ty\tz\tsize\tAnatomicalLocation\n"
            "i1\t0\t0\t0\t1\tHipp, hippocampus\n"
            "i2\t0\t0\t0\t1\tHipp, hippocampus\n"
            "i3\t0\t0\t0\t1\tSTG, superior temporal gyrus\n",
            encoding="utf-8",
        )


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
