from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_controls import run_phase1_final_controls
from src.phase1.final_dedicated_controls import (
    Phase1FinalDedicatedControlsError,
    run_phase1_final_dedicated_controls,
)


COMPARATORS = ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]
DEDICATED = ["nuisance_shared_control", "spatial_control", "shuffled_teacher", "time_shifted_teacher"]


class Phase1FinalDedicatedControlsTests(unittest.TestCase):
    def test_dedicated_controls_write_manifest_and_final_controls_can_consume_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_manifest = root / "phase1_final_split_manifest" / "run" / "final_split_manifest.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            output_root = root / "phase1_final_dedicated_controls"
            configs = _write_configs(root)
            _write_prereg(prereg)
            _write_split_manifest(split_manifest)
            _write_feature_matrix_run(feature_matrix_run, split_manifest)
            _write_comparator_reconciliation(comparator_run)

            result = run_phase1_final_dedicated_controls(
                prereg_bundle=prereg,
                feature_matrix_run=feature_matrix_run,
                comparator_reconciliation_run=comparator_run,
                output_root=output_root,
                repo_root=Path.cwd(),
                config_paths=configs,
            )

            summary = _read_json(result.summary_path)
            manifest = _read_json(result.output_dir / "final_dedicated_control_manifest.json")
            leakage = _read_json(result.output_dir / "phase1_final_dedicated_controls_runtime_leakage_audit.json")
            nuisance = _read_json(result.output_dir / "nuisance_shared_control.json")
            spatial = _read_json(result.output_dir / "spatial_control.json")
            shuffled_teacher = _read_json(result.output_dir / "shuffled_teacher_control.json")
            time_shifted_teacher = _read_json(result.output_dir / "time_shifted_teacher_control.json")
            self.assertEqual(summary["status"], "phase1_final_dedicated_controls_complete_claim_closed")
            self.assertTrue(summary["dedicated_control_suite_passed"])
            self.assertEqual(manifest["results"], DEDICATED)
            self.assertEqual(manifest["relative_metric_contract"]["formula_id"], "raw_ba_ratio")
            self.assertFalse(manifest["relative_metric_contract"]["thresholds_changed"])
            self.assertFalse(manifest["relative_metric_contract"]["current_artifacts_reclassified"])
            self.assertFalse(manifest["relative_metric_contract"]["claims_opened"])
            self.assertTrue(manifest["dedicated_control_suite_passed"])
            self.assertFalse(manifest["claim_ready"])
            self.assertFalse(manifest["smoke_artifacts_promoted"])
            self.assertFalse(leakage["outer_test_subject_used_for_any_fit"])
            self.assertEqual(nuisance["threshold"]["relative_metric_formula_id"], "raw_ba_ratio")
            self.assertEqual(
                nuisance["threshold"]["relative_metric_formula_definition"],
                "control_balanced_accuracy / baseline_balanced_accuracy",
            )
            self.assertEqual(nuisance["threshold"]["relative_to_baseline"], round(nuisance["metrics"]["balanced_accuracy"], 6))
            self.assertEqual(spatial["threshold"]["relative_metric_formula_id"], "raw_ba_ratio")
            self.assertEqual(
                spatial["threshold"]["relative_metric_formula_definition"],
                "control_balanced_accuracy / baseline_balanced_accuracy",
            )
            self.assertEqual(spatial["threshold"]["relative_to_baseline"], round(spatial["metrics"]["balanced_accuracy"], 6))
            self.assertEqual(shuffled_teacher["threshold"]["max_gain_over_a3"], 1.0)
            self.assertEqual(time_shifted_teacher["threshold"]["max_gain_over_a3"], 1.0)

            final_controls = run_phase1_final_controls(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_controls",
                repo_root=Path.cwd(),
                config_paths={
                    "controls": "configs/phase1/final_controls.json",
                    "control_suite": "configs/controls/control_suite_spec.yaml",
                    "gate2": "configs/gate2/synthetic_validation.json",
                },
                dedicated_control_manifest=result.output_dir / "final_dedicated_control_manifest.json",
            )
            control_summary = _read_json(final_controls.summary_path)
            control_manifest = _read_json(final_controls.output_dir / "final_control_manifest.json")
            self.assertEqual(control_summary["status"], "phase1_final_controls_complete_claim_closed")
            self.assertTrue(control_manifest["control_suite_passed"])
            self.assertEqual(control_manifest["missing_results"], [])
            self.assertEqual(control_manifest["dedicated_control_results"], DEDICATED)
            self.assertFalse(control_manifest["claim_ready"])

    def test_cli_dedicated_controls_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_manifest = root / "phase1_final_split_manifest" / "run" / "final_split_manifest.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            output_root = root / "phase1_final_dedicated_controls"
            configs = _write_configs(root)
            _write_prereg(prereg)
            _write_split_manifest(split_manifest)
            _write_feature_matrix_run(feature_matrix_run, split_manifest)
            _write_comparator_reconciliation(comparator_run)

            exit_code = main(
                [
                    "phase1_final_dedicated_controls",
                    "--config",
                    str(prereg),
                    "--feature-matrix-run",
                    str(feature_matrix_run),
                    "--comparator-reconciliation-run",
                    str(comparator_run),
                    "--output-root",
                    str(output_root),
                    "--dedicated-controls-config",
                    configs["dedicated_controls"],
                    "--comparator-runner-config",
                    configs["comparator_runner"],
                    "--gate2-config",
                    configs["gate2"],
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_dedicated_controls_summary.json")
            self.assertFalse(summary["claim_ready"])

    def test_dedicated_controls_reject_unreviewed_relative_formula_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            split_manifest = root / "phase1_final_split_manifest" / "run" / "final_split_manifest.json"
            feature_matrix_run = root / "phase1_final_feature_matrix" / "run"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            configs = _write_configs(root)
            dedicated_config = _read_json(Path(configs["dedicated_controls"]))
            dedicated_config["relative_metric_contract"]["formula_id"] = "gain_over_chance_ratio"
            dedicated_config["relative_metric_contract"]["definition"] = (
                "abs(control_balanced_accuracy - 0.5) / abs(baseline_balanced_accuracy - 0.5)"
            )
            _write_json(Path(configs["dedicated_controls"]), dedicated_config)
            _write_prereg(prereg)
            _write_split_manifest(split_manifest)
            _write_feature_matrix_run(feature_matrix_run, split_manifest)
            _write_comparator_reconciliation(comparator_run)

            with self.assertRaisesRegex(Phase1FinalDedicatedControlsError, "raw_ba_ratio"):
                run_phase1_final_dedicated_controls(
                    prereg_bundle=prereg,
                    feature_matrix_run=feature_matrix_run,
                    comparator_reconciliation_run=comparator_run,
                    output_root=root / "phase1_final_dedicated_controls",
                    repo_root=Path.cwd(),
                    config_paths=configs,
                )


def _write_configs(root: Path) -> dict[str, str]:
    config_dir = root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    dedicated = config_dir / "final_dedicated_controls.json"
    runner = config_dir / "final_comparator_runner.json"
    gate2 = config_dir / "gate2.json"
    _write_json(
        dedicated,
        {
            "required_dedicated_controls": DEDICATED,
            "nuisance_control": {"metadata_columns": ["session_id", "trial_id"]},
            "spatial_control": {"permutation": "reverse_channel_order_within_band"},
            "relative_metric_contract": {
                "formula_id": "raw_ba_ratio",
                "definition": "control_balanced_accuracy / baseline_balanced_accuracy",
                "applies_to": [
                    "nuisance_shared_control.relative_to_baseline",
                    "spatial_control.relative_to_baseline",
                ],
                "default_baseline_comparator": "A2",
                "status": "prospective_contract_clarification",
                "current_artifacts_reclassified": False,
                "thresholds_changed": False,
                "claims_opened": False,
            },
        },
    )
    _write_json(
        runner,
        {
            "logistic_probe": {"learning_rate": 0.05, "n_steps": 30, "l2": 0.001},
            "a3_distillation": {"temperature": 2.0, "soft_label_clip": 0.02, "distillation_alpha_hard_label": 0.5},
        },
    )
    _write_json(
        gate2,
        {
            "negative_controls": {
                "shuffled_teacher_max_gain_over_a3": 1.0,
                "time_shifted_teacher_max_gain_over_a3": 1.0,
            },
            "frozen_threshold_defaults": {
                "nuisance_relative_ceiling": 10.0,
                "nuisance_absolute_ceiling": 10.0,
                "spatial_relative_ceiling": 10.0,
            },
        },
    )
    return {"dedicated_controls": str(dedicated), "comparator_runner": str(runner), "gate2": str(gate2)}


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
                {"fold_id": "fold_01_sub-01", "outer_test_subject": "sub-01", "train_subjects": ["sub-02"], "test_subjects": ["sub-01"]},
                {"fold_id": "fold_02_sub-02", "outer_test_subject": "sub-02", "train_subjects": ["sub-01"], "test_subjects": ["sub-02"]},
            ],
            "claim_ready": False,
        },
    )


def _write_feature_matrix_run(run_dir: Path, split_manifest: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = run_dir / "final_feature_matrix.csv"
    rows = [
        {"row_id": "row_000001", "participant_id": "sub-01", "session_id": "ses-01", "trial_id": "1", "label": 0, "set_size": 4, "Fz:theta": 0.1, "Cz:theta": 1.1},
        {"row_id": "row_000002", "participant_id": "sub-01", "session_id": "ses-01", "trial_id": "2", "label": 1, "set_size": 8, "Fz:theta": 0.9, "Cz:theta": 1.9},
        {"row_id": "row_000003", "participant_id": "sub-02", "session_id": "ses-01", "trial_id": "1", "label": 0, "set_size": 4, "Fz:theta": -0.1, "Cz:theta": 0.8},
        {"row_id": "row_000004", "participant_id": "sub-02", "session_id": "ses-01", "trial_id": "2", "label": 1, "set_size": 8, "Fz:theta": 1.2, "Cz:theta": 2.2},
    ]
    with matrix_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    _write_json(
        run_dir / "phase1_final_feature_matrix_summary.json",
        {
            "status": "phase1_final_feature_matrix_materialized",
            "feature_matrix_ready": True,
            "matrix_path": str(matrix_path),
            "contains_model_outputs": False,
            "contains_logits": False,
            "contains_metrics": False,
            "nonfinite_feature_values": 0,
            "claim_ready": False,
        },
    )
    _write_json(run_dir / "phase1_final_feature_matrix_validation.json", {"status": "phase1_final_feature_matrix_validation_passed"})
    _write_json(
        run_dir / "phase1_final_feature_matrix_schema.json",
        {
            "feature_matrix_ready": True,
            "row_identity_columns": ["row_id", "participant_id", "session_id", "trial_id", "label", "set_size"],
            "feature_names": ["Fz:theta", "Cz:theta"],
            "feature_count": 2,
            "contains_model_outputs": False,
            "contains_logits": False,
            "contains_metrics": False,
        },
    )
    _write_json(run_dir / "final_feature_row_index.json", {"status": "phase1_final_feature_row_index_recorded"})
    _write_json(run_dir / "phase1_final_feature_matrix_source_links.json", {"final_split_manifest": str(split_manifest)})
    _write_json(run_dir / "phase1_final_feature_matrix_claim_state.json", {"claim_ready": False})


def _write_comparator_reconciliation(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    logits_dir = run_dir / "logits"
    logits_dir.mkdir(parents=True, exist_ok=True)
    completeness_rows = []
    for comparator_id in COMPARATORS:
        path = logits_dir / f"{comparator_id}_final_logits.json"
        _write_json(path, _logits_payload(comparator_id))
        completeness_rows.append(
            {
                "comparator_id": comparator_id,
                "status": "completed_claim_closed",
                "runtime_leakage_passed": True,
                "files": {"logits": str(path)},
            }
        )
    _write_json(
        run_dir / "phase1_final_comparator_reconciliation_summary.json",
        {
            "status": "phase1_final_comparator_reconciliation_complete_claim_closed",
            "completed_comparators": COMPARATORS,
            "blocked_comparators": [],
            "all_final_comparator_outputs_present": True,
            "runtime_comparator_logs_audited_for_all_required_comparators": True,
            "smoke_artifacts_promoted": False,
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
        },
    )
    _write_json(run_dir / "phase1_final_comparator_reconciled_completeness_table.json", {"rows": completeness_rows})
    _write_json(
        run_dir / "phase1_final_comparator_reconciled_runtime_leakage_audit.json",
        {"runtime_logs_audited_for_all_required_comparators": True},
    )
    _write_json(run_dir / "phase1_final_comparator_reconciled_claim_state.json", {"claim_ready": False})
    _write_json(run_dir / "phase1_final_comparator_reconciliation_source_links.json", {})


def _logits_payload(comparator_id: str) -> dict[str, object]:
    rows = []
    labels = [0, 1, 0, 1]
    probs = [0.25, 0.75, 0.3, 0.7]
    subjects = ["sub-01", "sub-01", "sub-02", "sub-02"]
    for index, (label, prob, subject) in enumerate(zip(labels, probs, subjects), start=1):
        rows.append(
            {
                "row_id": f"row_{index:06d}",
                "participant_id": subject,
                "session_id": "ses-01",
                "trial_id": str(index),
                "outer_test_subject": subject,
                "y_true": label,
                "prob_load8": prob,
                "y_pred": 1 if prob >= 0.5 else 0,
            }
        )
    return {"claim_ready": False, "rows": rows, "comparator_id": comparator_id}


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
