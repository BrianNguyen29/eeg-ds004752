from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.calibration import REQUIRED_FINAL_CALIBRATION_ARTIFACTS
from src.phase1.controls import REQUIRED_CONTROL_CONFIGS, REQUIRED_FINAL_CONTROL_RESULTS
from src.phase1.final_governance_reconciliation import run_phase1_final_governance_reconciliation
from src.phase1.influence import REQUIRED_FINAL_INFLUENCE_ARTIFACTS


COMPARATORS = ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]
REPORTING_ARTIFACTS = [
    "final_comparator_completeness_table",
    "negative_controls_report",
    "calibration_package_report",
    "influence_package_report",
    "final_fold_logs",
    "claim_state_report",
    "main_phase1_report",
]


class Phase1FinalGovernanceReconciliationTests(unittest.TestCase):
    def test_governance_reconciliation_blocks_without_final_governance_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run)

            result = run_phase1_final_governance_reconciliation(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_governance_reconciliation",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_governance_reconciliation_blocked")
            self.assertTrue(summary["comparator_outputs_complete"])
            self.assertTrue(summary["runtime_logs_audited_for_all_required_comparators"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertIn("controls:final_control_manifest_missing", summary["claim_blockers"])
            self.assertIn("calibration:final_calibration_manifest_missing", summary["claim_blockers"])
            self.assertIn("influence:final_influence_manifest_missing", summary["claim_blockers"])
            self.assertIn("reporting:final_phase1_reporting_manifest_missing", summary["claim_blockers"])
            self.assertIn("final_governance_reconciliation_incomplete", summary["claim_blockers"])

    def test_governance_reconciliation_records_ready_claim_closed_with_complete_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            configs = _write_executable_configs(root)
            manifests = _write_complete_manifests(root)
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run)

            result = run_phase1_final_governance_reconciliation(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_governance_reconciliation",
                repo_root=Path.cwd(),
                config_paths=configs,
                final_control_manifest=manifests["controls"],
                final_calibration_manifest=manifests["calibration"],
                final_influence_manifest=manifests["influence"],
                final_reporting_manifest=manifests["reporting"],
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_governance_reconciliation_ready_claim_closed")
            self.assertTrue(summary["comparator_outputs_complete"])
            self.assertTrue(summary["governance_surfaces"]["controls_claim_evaluable"])
            self.assertTrue(summary["governance_surfaces"]["calibration_claim_evaluable"])
            self.assertTrue(summary["governance_surfaces"]["influence_claim_evaluable"])
            self.assertTrue(summary["governance_surfaces"]["reporting_claim_evaluable"])
            self.assertEqual(summary["claim_blockers"], [])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            claim_state = _read_json(result.output_dir / "phase1_final_governance_claim_state.json")
            self.assertEqual(claim_state["status"], "phase1_final_governance_claim_state_ready_claim_closed")
            self.assertFalse(claim_state["full_phase1_claim_bearing_run_allowed"])

    def test_cli_governance_reconciliation_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            output_root = root / "phase1_final_governance_reconciliation"
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run)

            exit_code = main(
                [
                    "phase1_final_governance_reconciliation",
                    "--config",
                    str(prereg),
                    "--comparator-reconciliation-run",
                    str(comparator_run),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            latest = output_root / "latest.txt"
            self.assertTrue(latest.exists())
            run_dir = Path(latest.read_text(encoding="utf-8"))
            summary = _read_json(run_dir / "phase1_final_governance_reconciliation_summary.json")
            self.assertEqual(summary["status"], "phase1_final_governance_reconciliation_blocked")
            self.assertFalse(summary["claim_ready"])


def _write_prereg(path: Path) -> None:
    _write_json(
        path,
        {
            "status": "locked",
            "prereg_bundle_hash_sha256": "test-prereg-hash",
            "artifact_hashes": {"gate0": {"manifest.json": {"sha256": "abc"}}},
        },
    )


def _write_comparator_reconciliation(run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
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
            "claim_blockers": [
                "controls_calibration_influence_reporting_missing",
                "headline_claim_blocked_until_full_package_passes",
            ],
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_reconciliation_input_validation.json",
        {"status": "phase1_final_comparator_reconciliation_inputs_ready", "blockers": []},
    )
    _write_json(
        run_dir / "phase1_final_comparator_reconciled_completeness_table.json",
        {
            "status": "phase1_final_comparator_reconciled_completeness_recorded",
            "all_final_comparator_outputs_present": True,
            "claim_ready": False,
            "claim_evaluable": False,
            "rows": [{"comparator_id": item, "status": "completed_claim_closed"} for item in COMPARATORS],
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_reconciled_runtime_leakage_audit.json",
        {
            "status": "phase1_final_comparator_reconciled_runtime_leakage_audit_recorded",
            "runtime_logs_audited_for_all_required_comparators": True,
            "outer_test_subject_used_for_any_fit": False,
            "test_time_privileged_or_teacher_outputs_allowed": False,
            "claim_ready": False,
            "claim_evaluable": False,
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_reconciled_claim_state.json",
        {
            "status": "phase1_final_comparator_reconciled_claim_state_blocked",
            "claim_ready": False,
            "headline_phase1_claim_open": False,
            "full_phase1_claim_bearing_run_allowed": False,
            "smoke_artifacts_promoted": False,
            "blockers": ["controls_calibration_influence_reporting_missing"],
        },
    )
    _write_json(
        run_dir / "phase1_final_comparator_reconciliation_source_links.json",
        {"status": "phase1_final_comparator_reconciliation_source_links_recorded"},
    )


def _write_executable_configs(root: Path) -> dict[str, str]:
    config_dir = root / "configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "governance": config_dir / "final_governance_reconciliation.json",
        "controls": config_dir / "control_suite_spec.json",
        "nuisance": config_dir / "nuisance_block_spec.json",
        "metrics": config_dir / "metrics.json",
        "inference": config_dir / "inference.json",
        "gate1": config_dir / "gate1.json",
        "gate2": config_dir / "gate2.json",
    }
    _write_json(
        paths["governance"],
        {
            "required_comparator_reconciliation": {
                "all_final_comparator_outputs_present": True,
                "runtime_comparator_logs_audited_for_all_required_comparators": True,
                "claim_ready": False,
                "headline_phase1_claim_open": False,
                "full_phase1_claim_bearing_run_allowed": False,
                "smoke_artifacts_promoted": False,
            },
            "required_reporting_artifacts": REPORTING_ARTIFACTS,
            "claim_blockers_when_incomplete": ["final_governance_reconciliation_incomplete"],
        },
    )
    _write_json(
        paths["controls"],
        {
            "control_suite_status": "executable",
            "controls": {key: {"status": "configured"} for key in REQUIRED_CONTROL_CONFIGS},
        },
    )
    _write_json(paths["nuisance"], {"nuisance_families": ["motion", "session"]})
    _write_json(paths["metrics"], {"metrics_status": "executable"})
    _write_json(paths["inference"], {"inference_status": "executable"})
    _write_json(paths["gate1"], {"max_allowed_delta_ece": 0.02, "influence_ceiling": 0.4})
    _write_json(
        paths["gate2"],
        {
            "pass_criteria": {"negative_control_max_abs_gain": 0.01},
            "frozen_threshold_defaults": {
                "nuisance_relative_ceiling": 0.5,
                "nuisance_absolute_ceiling": 0.02,
                "spatial_relative_ceiling": 0.67,
                "influence_ceiling": 0.4,
            },
        },
    )
    return {key: str(value) for key, value in paths.items()}


def _write_complete_manifests(root: Path) -> dict[str, Path]:
    manifest_dir = root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "controls": manifest_dir / "final_control_manifest.json",
        "calibration": manifest_dir / "final_calibration_manifest.json",
        "influence": manifest_dir / "final_influence_manifest.json",
        "reporting": manifest_dir / "final_reporting_manifest.json",
    }
    _write_json(
        paths["controls"],
        {
            "status": "phase1_final_controls_manifest_recorded",
            "results": REQUIRED_FINAL_CONTROL_RESULTS,
            "control_suite_passed": True,
            "claim_ready": False,
            "claim_evaluable": True,
            "smoke_artifacts_promoted": False,
        },
    )
    _write_json(paths["calibration"], {"artifacts": REQUIRED_FINAL_CALIBRATION_ARTIFACTS})
    _write_json(
        paths["influence"],
        {"artifacts": REQUIRED_FINAL_INFLUENCE_ARTIFACTS, "leave_one_subject_out_executed": True},
    )
    _write_json(paths["reporting"], {"artifacts": REPORTING_ARTIFACTS, "claim_table_ready": True, "claims_opened": False})
    return paths


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
