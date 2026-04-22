from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.calibration import REQUIRED_FINAL_CALIBRATION_ARTIFACTS
from src.phase1.final_calibration import run_phase1_final_calibration


COMPARATORS = ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]
DEFAULT_PROBS = [0.31, 0.67, 0.48, 0.55, 0.42, 0.61]


class Phase1FinalCalibrationTests(unittest.TestCase):
    def test_final_calibration_records_artifacts_claim_closed_when_threshold_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run)

            result = run_phase1_final_calibration(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_calibration",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_calibration_complete_claim_closed")
            self.assertTrue(summary["calibration_package_passed"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertEqual(summary["claim_blockers"], [])

            manifest = _read_json(result.output_dir / "final_calibration_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_calibration_manifest_recorded")
            self.assertEqual(manifest["artifacts"], REQUIRED_FINAL_CALIBRATION_ARTIFACTS)
            self.assertTrue(manifest["calibration_package_passed"])
            self.assertFalse(manifest["smoke_artifacts_promoted"])
            self.assertFalse(manifest["claim_ready"])

            for filename in [
                "final_comparator_logits_index.json",
                "pooled_ece_10_bins.json",
                "subject_level_ece.json",
                "brier_score.json",
                "negative_log_likelihood.json",
                "reliability_table.json",
                "reliability_diagram.json",
                "risk_coverage_curve.json",
                "calibration_delta_vs_baseline.json",
                "phase1_final_calibration_claim_state.json",
            ]:
                self.assertTrue((result.output_dir / filename).exists(), filename)

    def test_final_calibration_blocks_when_delta_ece_threshold_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            probabilities = {comparator: DEFAULT_PROBS for comparator in COMPARATORS}
            probabilities["A4_privileged"] = [0.95, 0.05, 0.90, 0.10, 0.85, 0.15]
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run, probabilities=probabilities)

            result = run_phase1_final_calibration(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_calibration",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_calibration_blocked")
            self.assertFalse(summary["calibration_package_passed"])
            self.assertIn("calibration_delta_threshold_not_passed", summary["claim_blockers"])
            manifest = _read_json(result.output_dir / "final_calibration_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_calibration_blocked_manifest_recorded")
            self.assertFalse(manifest["claim_evaluable"])

    def test_cli_final_calibration_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            output_root = root / "phase1_final_calibration"
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run)

            exit_code = main(
                [
                    "phase1_final_calibration",
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
            summary = _read_json(run_dir / "phase1_final_calibration_summary.json")
            self.assertEqual(summary["status"], "phase1_final_calibration_complete_claim_closed")
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


def _write_comparator_reconciliation(
    run_dir: Path,
    *,
    probabilities: dict[str, list[float]] | None = None,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    logits_dir = run_dir / "logits"
    logits_dir.mkdir(parents=True, exist_ok=True)
    probabilities = probabilities or {comparator: DEFAULT_PROBS for comparator in COMPARATORS}
    rows = []
    for comparator_id in COMPARATORS:
        path = logits_dir / f"{comparator_id}_final_logits.json"
        _write_json(path, _logits_payload(comparator_id, probabilities[comparator_id]))
        rows.append(
            {
                "comparator_id": comparator_id,
                "status": "completed_claim_closed",
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
    _write_json(
        run_dir / "phase1_final_comparator_reconciled_completeness_table.json",
        {
            "status": "phase1_final_comparator_reconciled_completeness_recorded",
            "all_final_comparator_outputs_present": True,
            "claim_ready": False,
            "claim_evaluable": False,
            "rows": rows,
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


def _logits_payload(comparator_id: str, probs: list[float]) -> dict[str, object]:
    rows = []
    labels = [0, 1, 0, 1, 0, 1]
    for index, (label, prob) in enumerate(zip(labels, probs), start=1):
        subject = f"sub-{((index - 1) % 3) + 1:02d}"
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
    return {
        "status": "phase1_final_comparator_logits_recorded",
        "comparator_id": comparator_id,
        "claim_ready": False,
        "claim_evaluable": False,
        "rows": rows,
    }


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
