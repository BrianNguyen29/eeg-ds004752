from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.simulation.decision import Gate1Error
from src.simulation.decision import run_gate1_decision


class Gate1DecisionTests(unittest.TestCase):
    def test_gate1_rejects_non_ready_gate0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            _write_gate0_run(gate0, manifest_status="draft_metadata_plus_signal_sample")

            with self.assertRaises(Gate1Error):
                run_gate1_decision(gate0, _small_config(), root / "gate1", repo_root=Path.cwd())

    def test_gate1_generates_governance_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            _write_gate0_run(gate0)

            result = run_gate1_decision(gate0, _small_config(), root / "gate1", repo_root=Path.cwd())

            self.assertTrue(result.inputs_path.exists())
            self.assertTrue(result.integrity_path.exists())
            self.assertTrue(result.n_eff_path.exists())
            self.assertTrue(result.simulation_registry_path.exists())
            self.assertTrue(result.sesoi_registry_path.exists())
            self.assertTrue(result.influence_rule_path.exists())
            self.assertTrue(result.decision_memo_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue((root / "gate1" / "latest.txt").exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            simulation = json.loads(result.simulation_registry_path.read_text(encoding="utf-8"))
            sesoi = json.loads(result.sesoi_registry_path.read_text(encoding="utf-8"))
            influence = json.loads(result.influence_rule_path.read_text(encoding="utf-8"))
            memo = result.decision_memo_path.read_text(encoding="utf-8")

            self.assertEqual(summary["status"], "gate1_decision_layer_ready")
            self.assertFalse(summary["real_data_phase_authorized"])
            self.assertEqual(summary["next_gate"], "gate2_synthetic_validation")
            self.assertEqual(simulation["scenario_count"], 8)
            self.assertTrue(simulation["not_a_model_result"])
            self.assertEqual(sesoi["primary_subject_level_sesoi"]["median_delta_ba_min"], 0.03)
            self.assertEqual(influence["influence_ceiling"], 0.40)
            self.assertIn("No real-data substantive phase is authorized", memo)

    def test_cli_gate1_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate0 = root / "gate0" / "run"
            config = root / "gate1_config.json"
            _write_gate0_run(gate0)
            config.write_text(json.dumps(_small_config()), encoding="utf-8")

            exit_code = main(
                [
                    "gate1",
                    "--gate0-run",
                    str(gate0),
                    "--config",
                    str(config),
                    "--output-root",
                    str(root / "gate1"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "gate1" / "latest.txt").exists())


def _small_config() -> dict[str, object]:
    return {
        "registry_status": "test",
        "random_seed": 4752,
        "n_repeats": 10,
        "bootstrap_draws": 10,
        "effect_grid_delta_ba": [0.02, 0.05],
        "teacher_survival_fraction_grid": [0.20, 0.60],
        "heterogeneity_levels": {
            "low": 0.02,
            "high": 0.08,
        },
        "primary_metric": "balanced_accuracy",
        "primary_comparator": "A2d_riemannian",
        "privileged_model": "A4_observability_constrained_privileged",
        "subject_level_sesoi_delta_ba": 0.03,
        "max_allowed_delta_ece": 0.02,
        "influence_ceiling": 0.40,
        "ci_alpha": 0.05,
    }


def _write_gate0_run(gate0: Path, manifest_status: str = "signal_audit_ready") -> None:
    gate0.mkdir(parents=True)
    manifest = {
        "manifest_status": manifest_status,
        "participants": {
            "n_raw_public": 15,
        },
        "subjects": {
            "n_sessions": 68,
        },
        "payload_state": {
            "edf": {
                "count": 136,
                "materialized_count": 136,
                "pointer_like_count": 0,
            },
            "mat": {
                "count": 15,
                "materialized_count": 15,
                "pointer_like_count": 0,
            },
        },
        "signal_audit": {
            "status": "ok",
            "subject_filter": [],
            "session_filter": [],
            "candidate_sessions": 68,
            "sessions_checked": 68,
            "candidate_mat_files": 15,
            "mat_files_checked": 15,
        },
        "gate0_blockers": [],
    }
    cohort_lock = {
        "cohort_lock_status": "signal_audit_ready",
        "n_primary_eligible": 15,
        "fallback_reader_registry": [
            {
                "subject": "sub-06",
                "session": "ses-04",
                "eeg_reader": "mne",
                "ieeg_reader": "edf_header_fallback",
                "eeg_warning": None,
                "ieeg_warning": "second must be in 0..59",
            }
        ],
        "participants": [
            {
                "participant_id": f"sub-{index:02d}",
                "primary_eligible": True,
            }
            for index in range(1, 16)
        ],
    }
    gate0.joinpath("manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    gate0.joinpath("cohort_lock.json").write_text(json.dumps(cohort_lock), encoding="utf-8")
    gate0.joinpath("materialization_report.json").write_text("{}", encoding="utf-8")
    gate0.joinpath("audit_report.md").write_text("# Gate 0\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
