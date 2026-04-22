from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.phase1.final_influence import run_phase1_final_influence
from src.phase1.influence import REQUIRED_FINAL_INFLUENCE_ARTIFACTS


COMPARATORS = ["A2", "A2b", "A2c_CORAL", "A2d_riemannian", "A3_distillation", "A4_privileged"]


class Phase1FinalInfluenceTests(unittest.TestCase):
    def test_final_influence_records_artifacts_claim_closed_when_loso_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run, logits_by_comparator=_uniform_logits())

            result = run_phase1_final_influence(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_influence",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_influence_complete_claim_closed")
            self.assertTrue(summary["influence_package_passed"])
            self.assertTrue(summary["leave_one_subject_out_executed"])
            self.assertFalse(summary["claim_ready"])
            self.assertFalse(summary["headline_phase1_claim_open"])
            self.assertEqual(summary["claim_blockers"], [])

            manifest = _read_json(result.output_dir / "final_influence_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_influence_manifest_recorded")
            self.assertEqual(manifest["artifacts"], REQUIRED_FINAL_INFLUENCE_ARTIFACTS)
            self.assertTrue(manifest["influence_package_passed"])
            self.assertTrue(manifest["leave_one_subject_out_executed"])
            self.assertFalse(manifest["smoke_artifacts_promoted"])
            self.assertFalse(manifest["claim_ready"])

            for filename in [
                "subject_level_fold_metrics.json",
                "leave_one_subject_out_deltas.json",
                "max_single_subject_contribution_share.json",
                "claim_state_leave_one_subject_out.json",
                "influence_veto_decision.json",
                "phase1_final_influence_claim_state.json",
            ]:
                self.assertTrue((result.output_dir / filename).exists(), filename)

    def test_final_influence_blocks_when_single_subject_exceeds_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            logits = _uniform_logits()
            logits["A4_privileged"] = _logit_rows("A4_privileged", subject_1_correct=False)
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run, logits_by_comparator=logits)

            result = run_phase1_final_influence(
                prereg_bundle=prereg,
                comparator_reconciliation_run=comparator_run,
                output_root=root / "phase1_final_influence",
                repo_root=Path.cwd(),
            )

            summary = _read_json(result.summary_path)
            self.assertEqual(summary["status"], "phase1_final_influence_blocked")
            self.assertFalse(summary["influence_package_passed"])
            self.assertTrue(summary["influence_vetoed"])
            self.assertIn("single_subject_influence_ceiling_exceeded", summary["claim_blockers"])
            self.assertIn("final_influence_package_not_passed", summary["claim_blockers"])

            manifest = _read_json(result.output_dir / "final_influence_manifest.json")
            self.assertEqual(manifest["status"], "phase1_final_influence_blocked_manifest_recorded")
            self.assertFalse(manifest["claim_evaluable"])

    def test_cli_final_influence_writes_latest_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prereg = root / "prereg_bundle.json"
            comparator_run = root / "phase1_final_comparator_reconciliation" / "run"
            output_root = root / "phase1_final_influence"
            _write_prereg(prereg)
            _write_comparator_reconciliation(comparator_run, logits_by_comparator=_uniform_logits())

            exit_code = main(
                [
                    "phase1_final_influence",
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
            summary = _read_json(run_dir / "phase1_final_influence_summary.json")
            self.assertEqual(summary["status"], "phase1_final_influence_complete_claim_closed")
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
    logits_by_comparator: dict[str, list[dict[str, object]]],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    logits_dir = run_dir / "logits"
    logits_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for comparator_id in COMPARATORS:
        path = logits_dir / f"{comparator_id}_final_logits.json"
        _write_json(path, _logits_payload(comparator_id, logits_by_comparator[comparator_id]))
        rows.append(
            {
                "comparator_id": comparator_id,
                "status": "completed_claim_closed",
                "logits_present": True,
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


def _uniform_logits() -> dict[str, list[dict[str, object]]]:
    return {comparator: _logit_rows(comparator) for comparator in COMPARATORS}


def _logit_rows(comparator_id: str, *, subject_1_correct: bool = True) -> list[dict[str, object]]:
    rows = []
    labels = [0, 1, 0, 1]
    for subject_index in range(1, 4):
        subject = f"sub-{subject_index:02d}"
        for trial_index, label in enumerate(labels, start=1):
            correct = subject_1_correct or subject_index != 1
            if correct:
                prob = 0.2 if label == 0 else 0.8
            else:
                prob = 0.8 if label == 0 else 0.2
            rows.append(
                {
                    "row_id": f"{comparator_id}_{subject}_{trial_index}",
                    "participant_id": subject,
                    "outer_test_subject": subject,
                    "y_true": label,
                    "prob_load8": prob,
                    "y_pred": 1 if prob >= 0.5 else 0,
                }
            )
    return rows


def _logits_payload(comparator_id: str, rows: list[dict[str, object]]) -> dict[str, object]:
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
