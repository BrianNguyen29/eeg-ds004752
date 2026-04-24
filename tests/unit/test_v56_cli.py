from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.cli import main


ROOT = Path(__file__).resolve().parents[2]


class V56CliTests(unittest.TestCase):
    def test_v56_scaffold_writes_all_scaffold_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(root / "gate0")
            output_root = root / "v56"

            exit_code = main(
                [
                    "v56-scaffold",
                    "--gate0-run",
                    str(gate0),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--splits",
                    str(ROOT / "configs" / "v56" / "splits.json"),
                    "--controls",
                    str(ROOT / "configs" / "v56" / "controls.json"),
                    "--comparators",
                    str(ROOT / "configs" / "v56" / "comparators.json"),
                    "--output-root",
                    str(output_root),
                ]
            )

            self.assertEqual(exit_code, 0)
            for family in [
                "v56_split_registry",
                "v56_feature_provenance",
                "v56_control_registry",
                "v56_leaderboard",
            ]:
                latest = output_root / family / "latest.txt"
                self.assertTrue(latest.exists(), family)
                run_dir = Path(latest.read_text(encoding="utf-8").strip())
                self.assertTrue(run_dir.joinpath(f"{family}.json").exists())
                self.assertTrue(run_dir.joinpath(f"{family}_summary.json").exists())
                self.assertTrue(run_dir.joinpath(f"{family}_report.md").exists())

    def test_v56_scaffold_rejects_draft_gate0(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            gate0 = _write_gate0_run(
                root / "gate0",
                manifest_status="draft_metadata_plus_signal_sample",
                gate0_blockers=["cohort_lock_is_draft_until_signal_level_audit"],
                cohort_lock_status="draft_not_primary_locked",
                n_primary_eligible=None,
            )

            exit_code = main(
                [
                    "v56-scaffold",
                    "--gate0-run",
                    str(gate0),
                    "--benchmark-spec",
                    str(ROOT / "configs" / "v56" / "benchmark_spec.json"),
                    "--splits",
                    str(ROOT / "configs" / "v56" / "splits.json"),
                    "--controls",
                    str(ROOT / "configs" / "v56" / "controls.json"),
                    "--comparators",
                    str(ROOT / "configs" / "v56" / "comparators.json"),
                    "--output-root",
                    str(root / "v56"),
                ]
            )

            self.assertEqual(exit_code, 2)


def _write_gate0_run(
    path: Path,
    *,
    manifest_status: str = "signal_audit_ready",
    gate0_blockers: list[str] | None = None,
    cohort_lock_status: str = "signal_audit_ready",
    n_primary_eligible: int | None = 15,
) -> Path:
    path.mkdir(parents=True)
    path.joinpath("manifest.json").write_text(
        json.dumps(
            {
                "manifest_status": manifest_status,
                "gate0_blockers": gate0_blockers or [],
            }
        ),
        encoding="utf-8",
    )
    path.joinpath("cohort_lock.json").write_text(
        json.dumps(
            {
                "cohort_lock_status": cohort_lock_status,
                "n_primary_eligible": n_primary_eligible,
            }
        ),
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
