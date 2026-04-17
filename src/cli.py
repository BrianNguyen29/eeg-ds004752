"""Single CLI entrypoint required by the V5.5 Colab blueprint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit.gate0 import run_gate0_audit
from .config import load_config
from .guards import GuardError, assert_real_phase_allowed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Run Gate 0 metadata audit")
    audit.add_argument("--profile", default="t4_safe")
    audit.add_argument("--config", default="configs/data/snapshot.yaml")
    audit.add_argument("--dataset-root")
    audit.add_argument("--output-root")

    smoke = subparsers.add_parser("smoke", help="Validate config and project paths")
    smoke.add_argument("--profile", default="t4_safe")
    smoke.add_argument("--config", default="configs/data/snapshot.yaml")
    smoke.add_argument("--dataset-root")

    synthetic = subparsers.add_parser("synthetic", help="Create Gate 2 placeholder artefact")
    synthetic.add_argument("--profile", default="a100_fast")
    synthetic.add_argument("--config", default="configs/prereg/prereg_bundle.json")
    synthetic.add_argument("--output-root", default="artifacts/gate2")

    for phase in ("phase05_real", "phase1_real", "phase2_real", "phase3_real"):
        phase_parser = subparsers.add_parser(phase, help=f"Guarded {phase} command")
        phase_parser.add_argument("--profile", default="a100_fast")
        phase_parser.add_argument("--config", default="configs/prereg/prereg_bundle.json")

    report = subparsers.add_parser("report_compile", help="Compile available artefact summary")
    report.add_argument("--profile", default="t4_safe")
    report.add_argument("--run", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "audit":
            config = load_config(args.config)
            dataset_root = Path(args.dataset_root or config.get("dataset_root", "ds004752"))
            output_root = Path(args.output_root or config.get("gate0_output_root", "artifacts/gate0"))
            result = run_gate0_audit(dataset_root=dataset_root, output_root=output_root)
            print(f"Gate 0 audit complete: {result.output_dir}")
            print(f"Manifest: {result.manifest_path}")
            return 0

        if args.command == "smoke":
            config = load_config(args.config)
            dataset_root = Path(args.dataset_root or config.get("dataset_root", "ds004752"))
            if not dataset_root.exists():
                raise FileNotFoundError(f"Dataset root not found: {dataset_root}")
            print(f"Smoke OK: profile={args.profile} config={args.config} dataset={dataset_root}")
            return 0

        if args.command == "synthetic":
            output_root = Path(args.output_root)
            output_root.mkdir(parents=True, exist_ok=True)
            path = output_root / "synthetic_placeholder.json"
            path.write_text(
                '{\n'
                '  "status": "placeholder",\n'
                '  "message": "Implement Gate 2 generator/recovery before locking thresholds."\n'
                '}\n',
                encoding="utf-8",
            )
            print(f"Synthetic placeholder written: {path}")
            return 0

        if args.command in {"phase05_real", "phase1_real", "phase2_real", "phase3_real"}:
            assert_real_phase_allowed(args.command, args.config)
            print(f"{args.command} allowed by locked prereg bundle")
            return 0

        if args.command == "report_compile":
            run_path = Path(args.run)
            if run_path.is_file():
                run_path = Path(run_path.read_text(encoding="utf-8").strip())
            if not run_path.exists():
                raise FileNotFoundError(f"Run path not found: {run_path}")
            files = sorted(p for p in run_path.rglob("*") if p.is_file())
            print(f"Report compile input: {run_path}")
            print(f"Files discovered: {len(files)}")
            return 0

    except (FileNotFoundError, ValueError, GuardError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
