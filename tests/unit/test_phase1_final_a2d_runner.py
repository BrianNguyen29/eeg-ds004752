from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_a2d_runner import Phase1FinalA2dRunnerError, run_phase1_final_a2d_runner


class Phase1FinalA2dRunnerTests(unittest.TestCase):
    def test_final_a2d_runner_writes_covariance_tangent_outputs_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            matrix_run = root / "phase1_final_feature_matrix" / "run"
            previous_runner_run = root / "phase1_final_comparator_runner" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)
            _write_feature_matrix_run(matrix_run, split_run, feature_run, leakage_run)
            _write_previous_runner_run(previous_runner_run, matrix_run)

            result = run_phase1_final_a2d_runner(
                prereg_bundle=prereg,
                final_split_run=split_run,
                final_feature_run=feature_run,
                final_leakage_run=leakage_run,
                feature_matrix_run=matrix_run,
                feature_matrix_comparator_run=previous_runner_run,
                dataset_root=dataset_root,
                output_root=root / "phase1_final_a2d_runner",
                repo_root=Path.cwd(),
                precomputed_rows=_precomputed_covariance_rows(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_a2d_covariance_tangent_runner_complete_claim_closed")
            self.assertTrue(summary["a2d_final_output_present"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertFalse(summary["smoke_artifacts_promoted"])
            self.assertEqual(summary["n_covariance_rows"], 4)
            self.assertEqual(summary["n_expected_rows"], 4)
            self.assertEqual(summary["n_folds"], 2)
            self.assertEqual(summary["blockers"], [])
            self.assertIn("controls_calibration_influence_reporting_missing", summary["claim_blockers"])

            for relative in [
                "a2d_final_covariance_manifest.json",
                "a2d_final_tangent_manifest.json",
                "final_logits/A2d_riemannian_final_logits.json",
                "final_subject_level_metrics/A2d_riemannian_subject_level_metrics.json",
                "runtime_leakage_logs/A2d_riemannian_runtime_leakage_audit.json",
                "comparator_output_manifests/A2d_riemannian_output_manifest.json",
                "phase1_final_a2d_completeness_patch.json",
                "phase1_final_a2d_claim_state.json",
            ]:
                self.assertTrue((result.output_dir / relative).exists(), relative)

            logits = _read_json(result.output_dir / "final_logits" / "A2d_riemannian_final_logits.json")
            self.assertEqual(logits["n_rows"], 4)
            self.assertFalse(logits["contains_covariance_values"])
            self.assertFalse(logits["contains_tangent_features"])
            self.assertNotIn("covariance", logits["rows"][0])
            self.assertNotIn("features", logits["rows"][0])

            leakage = _read_json(result.output_dir / "runtime_leakage_logs" / "A2d_riemannian_runtime_leakage_audit.json")
            self.assertEqual(leakage["status"], "phase1_final_a2d_runtime_leakage_audit_passed")
            self.assertFalse(leakage["outer_test_subject_used_for_any_fit"])
            self.assertFalse(leakage["test_time_privileged_or_teacher_outputs_allowed"])
            for fold in leakage["folds"]:
                self.assertTrue(fold["no_outer_test_subject_in_any_fit"])

            manifest = _read_json(result.output_dir / "comparator_output_manifests" / "A2d_riemannian_output_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_a2d_output_manifest_recorded")
            self.assertFalse(manifest["claim_evaluable"])
            self.assertEqual(manifest["n_logit_rows"], 4)
            self.assertTrue(manifest["runtime_leakage_passed"])

            patch = _read_json(result.output_dir / "phase1_final_a2d_completeness_patch.json")
            self.assertIn(
                "A2d_riemannian_final_covariance_runner_missing",
                patch["resolved_blockers_for_downstream_reconciliation"],
            )
            self.assertFalse(patch["claim_ready"])

    def test_final_a2d_runner_rejects_feature_matrix_with_logits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            matrix_run = root / "phase1_final_feature_matrix" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)
            _write_feature_matrix_run(matrix_run, split_run, feature_run, leakage_run, contains_logits=True)

            with self.assertRaises(Phase1FinalA2dRunnerError):
                run_phase1_final_a2d_runner(
                    prereg_bundle=prereg,
                    final_split_run=split_run,
                    final_feature_run=feature_run,
                    final_leakage_run=leakage_run,
                    feature_matrix_run=matrix_run,
                    dataset_root=dataset_root,
                    output_root=root / "phase1_final_a2d_runner",
                    repo_root=Path.cwd(),
                    precomputed_rows=_precomputed_covariance_rows(),
                )

    def test_cli_final_a2d_runner_writes_blocked_record_without_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            matrix_run = root / "phase1_final_feature_matrix" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)
            _write_feature_matrix_run(matrix_run, split_run, feature_run, leakage_run)

            exit_code = main(
                [
                    "phase1_final_a2d_runner",
                    "--config",
                    str(prereg),
                    "--final-split-run",
                    str(split_run),
                    "--final-feature-run",
                    str(feature_run),
                    "--final-leakage-run",
                    str(leakage_run),
                    "--feature-matrix-run",
                    str(matrix_run),
                    "--dataset-root",
                    str(dataset_root),
                    "--output-root",
                    str(root / "phase1_final_a2d_runner"),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = root / "phase1_final_a2d_runner" / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_a2d_runner_summary.json")
            self.assertEqual(summary["status"], "phase1_final_a2d_covariance_tangent_runner_blocked")
            self.assertFalse(summary["a2d_final_output_present"])
            self.assertTrue((run_dir / "phase1_final_a2d_runner_blocked.json").exists())


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_split_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_split_manifest_summary.json",
        {"status": "phase1_final_split_manifest_recorded", "split_manifest_ready": True, "claim_ready": False},
    )
    _write_json(
        run_dir / "final_split_manifest.json",
        {
            "status": "phase1_final_split_manifest_recorded",
            "split_id": "loso_subject",
            "eligible_subjects": ["sub-01", "sub-02"],
            "folds": [
                {
                    "fold_id": "fold_01_sub-01",
                    "outer_test_subject": "sub-01",
                    "test_subjects": ["sub-01"],
                    "train_subjects": ["sub-02"],
                },
                {
                    "fold_id": "fold_02_sub-02",
                    "outer_test_subject": "sub-02",
                    "test_subjects": ["sub-02"],
                    "train_subjects": ["sub-01"],
                },
            ],
            "claim_ready": False,
            "smoke_artifacts_promoted": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_split_manifest_validation.json",
        {
            "status": "phase1_final_split_manifest_validation_passed",
            "split_manifest_ready": True,
            "no_subject_overlap_between_train_and_test": True,
        },
    )
    _write_json(run_dir / "phase1_final_split_manifest_claim_state.json", {"claim_ready": False})


def _write_feature_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_feature_manifest_summary.json",
        {"status": "phase1_final_feature_manifest_recorded", "feature_manifest_ready": True, "claim_ready": False},
    )
    _write_json(
        run_dir / "final_feature_manifest.json",
        {
            "status": "phase1_final_feature_manifest_recorded",
            "feature_set_id": "phase1_final_scalp_task_bandpower_v1",
            "feature_names": ["Fz:theta", "Cz:theta"],
            "feature_count": 2,
            "signal_windows_sec": {"task_maintenance": [2.25, 4.75]},
            "contains_feature_matrix": False,
            "contains_model_outputs": False,
            "contains_metrics": False,
            "claim_ready": False,
            "smoke_feature_rows_allowed_as_final": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_feature_manifest_validation.json",
        {"status": "phase1_final_feature_manifest_validation_passed", "feature_manifest_ready": True},
    )
    _write_json(run_dir / "phase1_final_feature_manifest_claim_state.json", {"claim_ready": False})


def _write_leakage_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_leakage_audit_summary.json",
        {"status": "phase1_final_leakage_audit_recorded", "leakage_audit_ready": True, "claim_ready": False},
    )
    _write_json(
        run_dir / "final_leakage_audit.json",
        {
            "status": "phase1_final_leakage_audit_recorded",
            "outer_test_subject_used_in_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "runtime_comparator_logs_audited": False,
            "claim_ready": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_leakage_audit_validation.json",
        {"status": "phase1_final_leakage_audit_validation_passed", "leakage_audit_ready": True},
    )
    _write_json(run_dir / "phase1_final_leakage_audit_claim_state.json", {"claim_ready": False})


def _write_feature_matrix_run(
    run_dir: Path,
    split_run: Path,
    feature_run: Path,
    leakage_run: Path,
    *,
    contains_logits: bool = False,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_feature_matrix_summary.json",
        {
            "status": "phase1_final_feature_matrix_materialized",
            "feature_matrix_ready": True,
            "claim_ready": False,
            "n_rows": 4,
            "n_features": 2,
            "nonfinite_feature_values": 0,
            "contains_model_outputs": False,
            "contains_logits": contains_logits,
            "contains_metrics": False,
            "final_feature_run": str(feature_run),
        },
    )
    _write_json(
        run_dir / "phase1_final_feature_matrix_validation.json",
        {"status": "phase1_final_feature_matrix_validation_passed", "feature_matrix_ready": True, "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_feature_matrix_schema.json",
        {
            "status": "phase1_final_feature_matrix_schema_recorded",
            "feature_matrix_ready": True,
            "feature_names": ["Fz:theta", "Cz:theta"],
            "contains_model_outputs": False,
            "contains_logits": contains_logits,
            "contains_metrics": False,
        },
    )
    _write_json(
        run_dir / "final_feature_row_index.json",
        {
            "status": "phase1_final_feature_row_index_recorded",
            "feature_matrix_ready": True,
            "n_rows": 4,
            "rows": [
                _row("row_000001", "sub-01", 0, 4),
                _row("row_000002", "sub-01", 1, 8),
                _row("row_000003", "sub-02", 0, 4),
                _row("row_000004", "sub-02", 1, 8),
            ],
        },
    )
    _write_json(
        run_dir / "phase1_final_feature_matrix_source_links.json",
        {
            "status": "phase1_final_feature_matrix_source_links_recorded",
            "final_split_manifest": str(split_run / "final_split_manifest.json"),
            "final_feature_manifest": str(feature_run / "final_feature_manifest.json"),
            "final_leakage_audit": str(leakage_run / "final_leakage_audit.json"),
        },
    )
    _write_json(run_dir / "phase1_final_feature_matrix_claim_state.json", {"claim_ready": False})


def _write_previous_runner_run(run_dir: Path, matrix_run: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_comparator_runner_summary.json",
        {
            "status": "phase1_final_comparator_runner_partial_with_blockers",
            "feature_matrix_run": str(matrix_run),
            "blocked_comparators": ["A2d_riemannian"],
            "claim_ready": False,
            "smoke_artifacts_promoted": False,
        },
    )
    _write_json(run_dir / "phase1_final_comparator_runner_claim_state.json", {"claim_ready": False})
    _write_json(run_dir / "phase1_final_comparator_completeness_table.json", {"claim_ready": False})


def _row(row_id: str, subject: str, label: int, set_size: int) -> dict[str, object]:
    return {
        "row_id": row_id,
        "participant_id": subject,
        "session_id": "ses-01",
        "trial_id": row_id[-1],
        "label": label,
        "set_size": set_size,
        "event_onset_sample": 0,
        "event_onset_sec": 0.0,
        "source_eeg_file": f"{subject}/ses-01/eeg/{subject}_ses-01_task-verbalWM_run-01_eeg.edf",
        "source_events_file": f"{subject}/ses-01/eeg/{subject}_ses-01_task-verbalWM_run-01_events.tsv",
    }


def _precomputed_covariance_rows() -> dict[str, object]:
    return {
        "rows": [
            {
                "row_id": "row_000001",
                "participant_id": "sub-01",
                "session_id": "ses-01",
                "trial_id": "1",
                "label": 0,
                "set_size": 4,
                "covariance": [[1.2, 0.1], [0.1, 0.9]],
                "channel_names": ["Fz", "Cz"],
            },
            {
                "row_id": "row_000002",
                "participant_id": "sub-01",
                "session_id": "ses-01",
                "trial_id": "2",
                "label": 1,
                "set_size": 8,
                "covariance": [[1.8, 0.2], [0.2, 1.1]],
                "channel_names": ["Fz", "Cz"],
            },
            {
                "row_id": "row_000003",
                "participant_id": "sub-02",
                "session_id": "ses-01",
                "trial_id": "1",
                "label": 0,
                "set_size": 4,
                "covariance": [[0.8, 0.05], [0.05, 1.3]],
                "channel_names": ["Fz", "Cz"],
            },
            {
                "row_id": "row_000004",
                "participant_id": "sub-02",
                "session_id": "ses-01",
                "trial_id": "2",
                "label": 1,
                "set_size": 8,
                "covariance": [[1.4, 0.1], [0.1, 1.7]],
                "channel_names": ["Fz", "Cz"],
            },
        ]
    }


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
