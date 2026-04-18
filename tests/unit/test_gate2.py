from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main
from src.synthetic.gate2 import Gate2Error
from src.synthetic.gate2 import run_gate2_synthetic_validation


class Gate2SyntheticTests(unittest.TestCase):
    def test_gate2_rejects_non_ready_gate1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate1 = root / "gate1" / "run"
            _write_gate1_run(gate1, status="gate1_not_ready")

            with self.assertRaises(Gate2Error):
                run_gate2_synthetic_validation(gate1, _small_config(), root / "gate2", repo_root=Path.cwd())

    def test_gate2_generates_synthetic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate1 = root / "gate1" / "run"
            _write_gate1_run(gate1)

            result = run_gate2_synthetic_validation(gate1, _small_config(), root / "gate2", repo_root=Path.cwd())

            self.assertTrue(result.generator_spec_path.exists())
            self.assertTrue(result.recovery_report_path.exists())
            self.assertTrue(result.recovery_json_path.exists())
            self.assertTrue(result.threshold_registry_path.exists())
            self.assertTrue(result.summary_path.exists())
            self.assertTrue((root / "gate2" / "latest.txt").exists())

            summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
            recovery = json.loads(result.recovery_json_path.read_text(encoding="utf-8"))
            registry = json.loads(result.threshold_registry_path.read_text(encoding="utf-8"))

            self.assertEqual(summary["status"], "gate2_synthetic_ready")
            self.assertEqual(recovery["status"], "passed")
            self.assertEqual(registry["status"], "locked_after_gate2_pass")
            self.assertFalse(summary["real_data_phase_authorized"])
            self.assertEqual(summary["next_gate"], "gate2_5_preregistration_bundle")

    def test_cli_gate2_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gate1 = root / "gate1" / "run"
            config = root / "gate2_config.json"
            _write_gate1_run(gate1)
            config.write_text(json.dumps(_small_config()), encoding="utf-8")

            exit_code = main(
                [
                    "gate2",
                    "--gate1-run",
                    str(gate1),
                    "--config",
                    str(config),
                    "--output-root",
                    str(root / "gate2"),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "gate2" / "latest.txt").exists())


def _small_config() -> dict[str, object]:
    return {
        "registry_status": "test",
        "random_seed": 7522,
        "n_subjects": 24,
        "trials_per_class_per_subject": 60,
        "classes": ["load_4", "load_8"],
        "n_repeats": 50,
        "effect_profiles": {
            "truly_observable": {
                "a2_mean_ba": 0.60,
                "a3_gain_over_a2": 0.015,
                "a4_gain_over_a3": 0.045,
                "subject_sd": 0.035,
                "expected_pattern": "A4 > A3 > A2",
            },
            "non_observable": {
                "a2_mean_ba": 0.60,
                "a3_gain_over_a2": 0.005,
                "a4_gain_over_a3": 0.000,
                "subject_sd": 0.035,
                "expected_pattern": "A4 does not robustly exceed A3",
            },
            "nuisance_shared": {
                "a2_mean_ba": 0.60,
                "a3_gain_over_a2": 0.010,
                "a4_gain_over_a3": 0.035,
                "subject_sd": 0.035,
                "expected_pattern": "raw A4 may rise but nuisance control must veto",
            },
        },
        "negative_controls": {
            "shuffled_teacher_max_gain_over_a3": 0.005,
            "time_shifted_teacher_max_gain_over_a3": 0.005,
            "nuisance_veto_required": True,
        },
        "pass_criteria": {
            "observable_min_median_a4_minus_a3": 0.03,
            "observable_min_median_a3_minus_a2": 0.005,
            "non_observable_max_median_a4_minus_a3": 0.01,
            "nuisance_requires_veto": True,
            "negative_control_max_abs_gain": 0.01,
        },
        "threshold_sweep": {
            "m_e": [0.20],
            "q_e": [0.20],
            "a_e": [0.67],
            "delta_obs": [0.02],
            "spatial_relative_ceiling": [0.67],
            "nuisance_relative_ceiling": [0.50],
            "tau_viable": [0.20],
            "influence_ceiling": [0.40],
        },
        "frozen_threshold_defaults": {
            "m_e_min": 0.20,
            "q_e_min": 0.20,
            "a_e_min": 0.67,
            "delta_obs_min": 0.02,
            "spatial_relative_ceiling": 0.67,
            "nuisance_relative_ceiling": 0.50,
            "nuisance_absolute_ceiling": 0.02,
            "tau_viable": 0.20,
            "influence_ceiling": 0.40,
        },
    }


def _write_gate1_run(gate1: Path, status: str = "gate1_decision_layer_ready") -> None:
    gate1.mkdir(parents=True)
    gate1_summary = {
        "status": status,
        "gate0_source_of_truth": "/gate0/run",
        "git_commit": "test-commit",
        "real_data_phase_authorized": False,
        "next_gate": "gate2_synthetic_validation",
        "n_eff": {
            "n_primary_eligible": 15,
        },
    }
    gate1_inputs = {
        "gate0_source_of_truth": "/gate0/run",
    }
    n_eff = {
        "n_primary_eligible": 15,
        "primary_denominator": "subject",
    }
    sesoi = {
        "primary_subject_level_sesoi": {
            "median_delta_ba_min": 0.03,
        },
        "calibration_tolerance": {
            "max_allowed_delta_ece": 0.02,
        },
    }
    influence = {
        "influence_ceiling": 0.40,
    }
    simulation = {
        "not_a_model_result": True,
    }
    gate1.joinpath("gate1_summary.json").write_text(json.dumps(gate1_summary), encoding="utf-8")
    gate1.joinpath("gate1_inputs.json").write_text(json.dumps(gate1_inputs), encoding="utf-8")
    gate1.joinpath("n_eff_statement.json").write_text(json.dumps(n_eff), encoding="utf-8")
    gate1.joinpath("sesoi_registry.json").write_text(json.dumps(sesoi), encoding="utf-8")
    gate1.joinpath("influence_rule.json").write_text(json.dumps(influence), encoding="utf-8")
    gate1.joinpath("simulation_registry.json").write_text(json.dumps(simulation), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
