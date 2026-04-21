from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_comparator_runner import (
    Phase1FinalComparatorRunnerError,
    run_phase1_final_comparator_runner,
)


class Phase1FinalComparatorRunnerTests(unittest.TestCase):
    def test_final_comparator_runner_writes_claim_closed_outputs_and_blocks_a2d(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_manifest = root / "phase1_final_split_manifest" / "run" / "final_split_manifest.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            _write_prereg(prereg)
            _write_split_manifest(split_manifest)
            _write_feature_matrix_run(feature_matrix_run, split_manifest)
            _write_runner_readiness_run(readiness_run)

            result = run_phase1_final_comparator_runner(
                prereg_bundle=prereg,
                feature_matrix_run=feature_matrix_run,
                runner_readiness_run=readiness_run,
                output_root=root / "phase1_final_comparator_runner",
                repo_root=Path.cwd(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_comparator_runner_partial_with_blockers")
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["full_phase1_claim_bearing_run_allowed"])
            self.assertFalse(summary["smoke_artifacts_promoted"])
            self.assertEqual(summary["n_rows"], 4)
            self.assertEqual(summary["n_features"], 2)
            self.assertIn("A2d_riemannian", summary["blocked_comparators"])
            self.assertFalse(summary["final_comparator_outputs_present"])
            self.assertIn("final_comparator_outputs_incomplete", summary["claim_blockers"])

            for comparator_id in ["A2", "A2b", "A2c_CORAL", "A3_distillation", "A4_privileged"]:
                self.assertTrue((result.output_dir / "comparator_output_manifests" / f"{comparator_id}_output_manifest.json").exists())
                self.assertTrue((result.output_dir / "final_logits" / f"{comparator_id}_final_logits.json").exists())
                self.assertTrue(
                    (result.output_dir / "runtime_leakage_logs" / f"{comparator_id}_runtime_leakage_audit.json").exists()
                )
                logits = _read_json(result.output_dir / "final_logits" / f"{comparator_id}_final_logits.json")
                self.assertFalse(logits["contains_feature_values"])
                self.assertNotIn("features", logits["rows"][0])
                leakage = _read_json(result.output_dir / "runtime_leakage_logs" / f"{comparator_id}_runtime_leakage_audit.json")
                self.assertFalse(leakage["outer_test_subject_used_for_any_fit"])
                self.assertFalse(leakage["test_time_privileged_or_teacher_outputs_allowed"])

            a2d = _read_json(result.output_dir / "comparator_output_manifests" / "A2d_riemannian_output_manifest.json")
            self.assertEqual(a2d["status"], "phase1_final_comparator_blocked")
            self.assertFalse(a2d["logits_written"])
            self.assertFalse(a2d["metrics_written"])
            self.assertIn("feature matrix", a2d["reason"])

            aggregate = _read_json(result.output_dir / "phase1_final_comparator_runtime_leakage_audit.json")
            self.assertTrue(aggregate["runtime_logs_audited_for_completed_comparators"])
            self.assertFalse(aggregate["runtime_logs_audited_for_all_required_comparators"])
            self.assertFalse(aggregate["outer_test_subject_used_for_any_fit"])

    def test_final_comparator_runner_rejects_feature_matrix_with_logits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_manifest = root / "phase1_final_split_manifest" / "run" / "final_split_manifest.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            _write_prereg(prereg)
            _write_split_manifest(split_manifest)
            _write_feature_matrix_run(feature_matrix_run, split_manifest, contains_logits=True)
            _write_runner_readiness_run(readiness_run)

            with self.assertRaises(Phase1FinalComparatorRunnerError):
                run_phase1_final_comparator_runner(
                    prereg_bundle=prereg,
                    feature_matrix_run=feature_matrix_run,
                    runner_readiness_run=readiness_run,
                    output_root=root / "phase1_final_comparator_runner",
                    repo_root=Path.cwd(),
                )

    def test_cli_final_comparator_runner_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_manifest = root / "phase1_final_split_manifest" / "run" / "final_split_manifest.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            output_root = root / "phase1_final_comparator_runner"
            _write_prereg(prereg)
            _write_split_manifest(split_manifest)
            _write_feature_matrix_run(feature_matrix_run, split_manifest)
            _write_runner_readiness_run(readiness_run)

            exit_code = main(
                [
                    "phase1_final_comparator_runner",
                    "--config",
                    str(prereg),
                    "--feature-matrix-run",
                    str(feature_matrix_run),
                    "--runner-readiness-run",
                    str(readiness_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_comparator_runner_summary.json")
            self.assertFalse(summary["claim_ready"])
            self.assertIn("A2d_riemannian", summary["blocked_comparators"])


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_split_manifest(path: Path) -> None:
    _write_json(
        path,
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


def _write_feature_matrix_run(run_dir: Path, split_manifest: Path, *, contains_logits: bool = False) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = run_dir / "final_feature_matrix.csv"
    rows = [
        {"row_id": "row_000001", "participant_id": "sub-01", "session_id": "ses-01", "trial_id": "1", "label": 0, "set_size": 4, "Fz:theta": 0.1, "Cz:theta": 1.1},
        {"row_id": "row_000002", "participant_id": "sub-01", "session_id": "ses-01", "trial_id": "2", "label": 1, "set_size": 8, "Fz:theta": 0.9, "Cz:theta": 1.9},
        {"row_id": "row_000003", "participant_id": "sub-02", "session_id": "ses-01", "trial_id": "1", "label": 0, "set_size": 4, "Fz:theta": -0.1, "Cz:theta": 0.8},
        {"row_id": "row_000004", "participant_id": "sub-02", "session_id": "ses-01", "trial_id": "2", "label": 1, "set_size": 8, "Fz:theta": 1.2, "Cz:theta": 2.2},
    ]
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    _write_json(
        run_dir / "phase1_final_feature_matrix_summary.json",
        {
            "status": "phase1_final_feature_matrix_materialized",
            "feature_matrix_ready": True,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "n_rows": 4,
            "n_features": 2,
            "nonfinite_feature_values": 0,
            "matrix_path": str(matrix_path),
            "contains_model_outputs": False,
            "contains_logits": contains_logits,
            "contains_metrics": False,
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
            "row_identity_columns": ["row_id", "participant_id", "session_id", "trial_id", "label", "set_size"],
            "feature_names": ["Fz:theta", "Cz:theta"],
            "feature_count": 2,
            "contains_model_outputs": False,
            "contains_logits": contains_logits,
            "contains_metrics": False,
        },
    )
    _write_json(
        run_dir / "final_feature_row_index.json",
        {"status": "phase1_final_feature_row_index_recorded", "feature_matrix_ready": True, "n_rows": 4},
    )
    _write_json(
        run_dir / "phase1_final_feature_matrix_source_links.json",
        {"status": "phase1_final_feature_matrix_source_links_recorded", "final_split_manifest": str(split_manifest)},
    )
    _write_json(run_dir / "phase1_final_feature_matrix_claim_state.json", {"claim_ready": False})


def _write_runner_readiness_run(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json(
        run_dir / "phase1_final_comparator_runner_readiness_summary.json",
        {
            "status": "phase1_final_comparator_runner_readiness_recorded",
            "upstream_manifests_ready": True,
            "final_comparator_outputs_present": False,
            "runtime_comparator_logs_audited": False,
            "smoke_artifacts_promoted": False,
            "claim_ready": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_runner_input_validation.json",
        {"status": "phase1_final_comparator_runner_inputs_ready", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_comparator_runner_manifest_status.json",
        {"status": "phase1_final_comparator_outputs_missing", "claim_evaluable": False},
    )
    _write_json(run_dir / "phase1_final_comparator_runner_claim_state.json", {"claim_ready": False})


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
