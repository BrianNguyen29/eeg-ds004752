from __future__ import annotations

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_feature_matrix import (
    Phase1FinalFeatureMatrixError,
    _feature_aliases_for_raw_channels,
    run_phase1_final_feature_matrix,
)


class Phase1FinalFeatureMatrixTests(unittest.TestCase):
    def test_final_feature_matrix_materializes_precomputed_rows_without_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)
            _write_runner_readiness_run(readiness_run)

            result = run_phase1_final_feature_matrix(
                prereg_bundle=prereg,
                final_split_run=split_run,
                final_feature_run=feature_run,
                final_leakage_run=leakage_run,
                runner_readiness_run=readiness_run,
                dataset_root=dataset_root,
                output_root=root / "phase1_final_feature_matrix",
                repo_root=Path.cwd(),
                precomputed_rows=_precomputed_rows(),
            )

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue(result.report_path.exists())
            self.assertTrue((result.output_dir / "final_feature_matrix.csv").exists())
            self.assertTrue((result.output_dir / "phase1_final_feature_matrix_schema.json").exists())
            self.assertTrue((result.output_dir / "final_feature_row_index.json").exists())
            self.assertFalse((result.output_dir / "phase1_final_feature_matrix_blocked.json").exists())

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_feature_matrix_materialized")
            self.assertTrue(summary["feature_matrix_ready"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertFalse(summary["contains_model_outputs"])
            self.assertFalse(summary["contains_logits"])
            self.assertFalse(summary["contains_metrics"])
            self.assertEqual(summary["n_rows"], 4)
            self.assertEqual(summary["n_expected_rows"], 4)
            self.assertEqual(summary["n_features"], 2)
            self.assertEqual(summary["feature_matrix_blockers"], [])
            self.assertIn("final_comparator_outputs_missing", summary["claim_blockers"])

            validation = _read_json(result.output_dir / "phase1_final_feature_matrix_validation.json")
            self.assertEqual(validation["status"], "phase1_final_feature_matrix_validation_passed")
            self.assertTrue(validation["feature_matrix_ready"])
            self.assertTrue(validation["feature_names_match_manifest"])
            self.assertEqual(validation["nonfinite_feature_values"], 0)
            self.assertFalse(validation["contains_metrics"])

            with (result.output_dir / "final_feature_matrix.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 4)
            self.assertEqual(rows[0]["row_id"], "row_000001")
            self.assertEqual(rows[0]["participant_id"], "sub-01")
            self.assertIn("Fz:theta", rows[0])
            self.assertIn("Cz:theta", rows[0])

            claim_state = _read_json(result.output_dir / "phase1_final_feature_matrix_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_feature_matrix_claim_state_blocked")
            self.assertTrue(claim_state["feature_matrix_ready"])
            self.assertFalse(claim_state["claim_ready"])
            self.assertIn("runtime_comparator_leakage_logs_missing_until_final_runners_execute", claim_state["blockers"])

    def test_final_feature_matrix_blocks_on_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)
            _write_runner_readiness_run(readiness_run)
            rows = _precomputed_rows()
            rows["rows"][0]["features"]["Fz:theta"] = float("nan")

            result = run_phase1_final_feature_matrix(
                prereg_bundle=prereg,
                final_split_run=split_run,
                final_feature_run=feature_run,
                final_leakage_run=leakage_run,
                runner_readiness_run=readiness_run,
                dataset_root=dataset_root,
                output_root=root / "phase1_final_feature_matrix",
                repo_root=Path.cwd(),
                precomputed_rows=rows,
            )

            self.assertFalse((result.output_dir / "final_feature_matrix.csv").exists())
            self.assertTrue((result.output_dir / "phase1_final_feature_matrix_blocked.json").exists())
            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_feature_matrix_blocked")
            self.assertFalse(summary["feature_matrix_ready"])
            self.assertIn("nonfinite_feature_values_present", summary["feature_matrix_blockers"])
            validation = _read_json(result.output_dir / "phase1_final_feature_matrix_validation.json")
            self.assertGreater(validation["nonfinite_feature_values"], 0)
            self.assertEqual(validation["nonfinite_feature_examples"][0]["feature_name"], "Fz:theta")

    def test_final_feature_matrix_channel_aliases_normalize_common_edf_labels(self) -> None:
        aliases = _feature_aliases_for_raw_channels(
            ["Fz", "Cz", "Pz"],
            ["EEG Fz-Ref", "Cz", "EEG_Pz_REF"],
        )

        self.assertEqual(aliases["Fz"], "EEG Fz-Ref")
        self.assertEqual(aliases["Cz"], "Cz")
        self.assertEqual(aliases["Pz"], "EEG_Pz_REF")

    def test_final_feature_matrix_rejects_feature_manifest_with_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run, contains_outputs=True)
            _write_leakage_run(leakage_run)
            _write_runner_readiness_run(readiness_run)

            with self.assertRaises(Phase1FinalFeatureMatrixError):
                run_phase1_final_feature_matrix(
                    prereg_bundle=prereg,
                    final_split_run=split_run,
                    final_feature_run=feature_run,
                    final_leakage_run=leakage_run,
                    runner_readiness_run=readiness_run,
                    dataset_root=dataset_root,
                    output_root=root / "phase1_final_feature_matrix",
                    repo_root=Path.cwd(),
                    precomputed_rows=_precomputed_rows(),
                )

    def test_cli_final_feature_matrix_writes_blocked_record_without_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_run = root / "phase1_final_split_manifest" / "run"
            feature_run = root / "phase1_final_feature_manifest" / "run"
            leakage_run = root / "phase1_final_leakage_audit" / "run"
            readiness_run = root / "phase1_final_comparator_runner_readiness" / "run"
            dataset_root = root / "ds004752"
            dataset_root.mkdir()
            _write_prereg(prereg)
            _write_split_run(split_run)
            _write_feature_run(feature_run)
            _write_leakage_run(leakage_run)
            _write_runner_readiness_run(readiness_run)

            exit_code = main(
                [
                    "phase1_final_feature_matrix",
                    "--config",
                    str(prereg),
                    "--final-split-run",
                    str(split_run),
                    "--final-feature-run",
                    str(feature_run),
                    "--final-leakage-run",
                    str(leakage_run),
                    "--runner-readiness-run",
                    str(readiness_run),
                    "--dataset-root",
                    str(dataset_root),
                    "--output-root",
                    str(root / "phase1_final_feature_matrix"),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = root / "phase1_final_feature_matrix" / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_feature_matrix_summary.json")
            self.assertEqual(summary["status"], "phase1_final_feature_matrix_blocked")
            self.assertFalse((run_dir / "final_feature_matrix.csv").exists())


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


def _write_split_run(split_run: Path) -> None:
    split_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        split_run / "phase1_final_split_manifest_summary.json",
        {"status": "phase1_final_split_manifest_recorded", "split_manifest_ready": True, "claim_ready": False},
    )
    _write_json(
        split_run / "final_split_manifest.json",
        {
            "status": "phase1_final_split_manifest_recorded",
            "eligible_subjects": ["sub-01", "sub-02"],
            "folds": [
                {"fold_id": "fold_01_sub-01", "outer_test_subject": "sub-01", "test_subjects": ["sub-01"], "train_subjects": ["sub-02"]},
                {"fold_id": "fold_02_sub-02", "outer_test_subject": "sub-02", "test_subjects": ["sub-02"], "train_subjects": ["sub-01"]},
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
            "no_subject_overlap_between_train_and_test": True,
        },
    )
    _write_json(split_run / "phase1_final_split_manifest_claim_state.json", {"claim_ready": False})


def _write_feature_run(feature_run: Path, *, contains_outputs: bool = False) -> None:
    feature_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        feature_run / "phase1_final_feature_manifest_summary.json",
        {"status": "phase1_final_feature_manifest_recorded", "feature_manifest_ready": True, "claim_ready": False},
    )
    _write_json(
        feature_run / "final_feature_manifest.json",
        {
            "status": "phase1_final_feature_manifest_recorded",
            "feature_set_id": "phase1_final_scalp_task_bandpower_v1",
            "feature_names": ["Fz:theta", "Cz:theta"],
            "feature_count": 2,
            "subjects": ["sub-01", "sub-02"],
            "sessions": ["sub-01/ses-01", "sub-02/ses-01"],
            "n_event_rows_planned": 4,
            "frequency_bands_hz": {"theta": [4.0, 8.0]},
            "signal_windows_sec": {"task_maintenance": [2.25, 4.75]},
            "trial_filter": {"artifact_values_allowed": ["0", "0.0", "", None], "set_size_values_allowed": [4, 8]},
            "contains_feature_matrix": contains_outputs,
            "contains_model_outputs": contains_outputs,
            "contains_metrics": contains_outputs,
            "claim_ready": False,
            "smoke_feature_rows_allowed_as_final": False,
        },
    )
    _write_json(
        feature_run / "phase1_final_feature_manifest_validation.json",
        {"status": "phase1_final_feature_manifest_validation_passed", "feature_manifest_ready": True},
    )
    _write_json(feature_run / "phase1_final_feature_manifest_claim_state.json", {"claim_ready": False})


def _write_leakage_run(leakage_run: Path) -> None:
    leakage_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        leakage_run / "phase1_final_leakage_audit_summary.json",
        {"status": "phase1_final_leakage_audit_recorded", "leakage_audit_ready": True, "claim_ready": False},
    )
    _write_json(
        leakage_run / "final_leakage_audit.json",
        {
            "status": "phase1_final_leakage_audit_recorded",
            "outer_test_subject_used_in_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "runtime_comparator_logs_audited": False,
            "contains_model_outputs": False,
            "contains_metrics": False,
            "claim_ready": False,
        },
    )
    _write_json(
        leakage_run / "phase1_final_leakage_audit_validation.json",
        {"status": "phase1_final_leakage_audit_validation_passed", "leakage_audit_ready": True},
    )
    _write_json(leakage_run / "phase1_final_leakage_audit_claim_state.json", {"claim_ready": False})


def _write_runner_readiness_run(readiness_run: Path) -> None:
    readiness_run.mkdir(parents=True, exist_ok=True)
    _write_json(
        readiness_run / "phase1_final_comparator_runner_readiness_summary.json",
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
        readiness_run / "phase1_final_comparator_runner_input_validation.json",
        {"status": "phase1_final_comparator_runner_inputs_ready", "blockers": []},
    )
    _write_json(
        readiness_run / "phase1_final_comparator_runner_manifest_status.json",
        {"status": "phase1_final_comparator_outputs_missing", "claim_evaluable": False},
    )
    _write_json(readiness_run / "phase1_final_comparator_runner_claim_state.json", {"claim_ready": False})


def _precomputed_rows() -> dict[str, object]:
    return {
        "feature_names": ["Fz:theta", "Cz:theta"],
        "rows": [
            {
                "row_id": "row_000001",
                "participant_id": "sub-01",
                "session_id": "ses-01",
                "trial_id": "1",
                "label": 0,
                "set_size": 4,
                "features": {"Fz:theta": 1.0, "Cz:theta": 2.0},
            },
            {
                "row_id": "row_000002",
                "participant_id": "sub-01",
                "session_id": "ses-01",
                "trial_id": "2",
                "label": 1,
                "set_size": 8,
                "features": {"Fz:theta": 1.5, "Cz:theta": 2.5},
            },
            {
                "row_id": "row_000003",
                "participant_id": "sub-02",
                "session_id": "ses-01",
                "trial_id": "1",
                "label": 0,
                "set_size": 4,
                "features": {"Fz:theta": 3.0, "Cz:theta": 4.0},
            },
            {
                "row_id": "row_000004",
                "participant_id": "sub-02",
                "session_id": "ses-01",
                "trial_id": "2",
                "label": 1,
                "set_size": 8,
                "features": {"Fz:theta": 3.5, "Cz:theta": 4.5},
            },
        ],
    }


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, allow_nan=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
