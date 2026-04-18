"""Single CLI entrypoint required by the V5.5 Colab blueprint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit.gate0 import run_gate0_audit
from .config import load_config
from .guards import GuardError, assert_real_phase_allowed
from .prereg.bundle import PreregError, run_prereg_assembly
from .simulation.decision import Gate1Error, run_gate1_decision
from .synthetic.gate2 import Gate2Error, run_gate2_synthetic_validation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m src.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit", help="Run Gate 0 metadata audit")
    audit.add_argument("--profile", default="t4_safe")
    audit.add_argument("--config", default="configs/data/snapshot.yaml")
    audit.add_argument("--dataset-root")
    audit.add_argument("--output-root")
    audit.add_argument("--include-signal", action="store_true")
    audit.add_argument("--signal-max-sessions", type=int, default=4)
    audit.add_argument("--subjects", nargs="*", help="Restrict signal audit to subject IDs, e.g. sub-01 sub-02")
    audit.add_argument("--sessions", nargs="*", help="Restrict signal audit to session IDs, e.g. ses-01 ses-02")

    smoke = subparsers.add_parser("smoke", help="Validate config and project paths")
    smoke.add_argument("--profile", default="t4_safe")
    smoke.add_argument("--config", default="configs/data/snapshot.yaml")
    smoke.add_argument("--dataset-root")

    synthetic = subparsers.add_parser("synthetic", help="Create Gate 2 placeholder artefact")
    synthetic.add_argument("--profile", default="a100_fast")
    synthetic.add_argument("--config", default="configs/prereg/prereg_bundle.json")
    synthetic.add_argument("--output-root", default="artifacts/gate2")

    gate2 = subparsers.add_parser("gate2", help="Run Gate 2 synthetic validation and threshold registry")
    gate2.add_argument("--profile", default="t4_safe")
    gate2.add_argument("--gate1-run", required=True)
    gate2.add_argument("--config", default="configs/gate2/synthetic_validation.json")
    gate2.add_argument("--output-root", default="artifacts/gate2")

    gate25 = subparsers.add_parser("gate25", help="Assemble Gate 2.5 preregistration bundle")
    gate25.add_argument("--profile", default="t4_safe")
    gate25.add_argument("--gate2-run", required=True)
    gate25.add_argument("--config", default="configs/prereg/prereg_assembly.json")
    gate25.add_argument("--output-root", default="artifacts/prereg")

    gate1 = subparsers.add_parser("gate1", help="Run Gate 1 decision simulation and governance artefact generation")
    gate1.add_argument("--profile", default="t4_safe")
    gate1.add_argument("--gate0-run", required=True)
    gate1.add_argument("--config", default="configs/gate1/decision_simulation.json")
    gate1.add_argument("--output-root", default="artifacts/gate1")

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
            result = run_gate0_audit(
                dataset_root=dataset_root,
                output_root=output_root,
                include_signal=args.include_signal,
                signal_max_sessions=args.signal_max_sessions,
                signal_subjects=args.subjects,
                signal_sessions=args.sessions,
            )
            print(f"Gate 0 audit complete: {result.output_dir}")
            print(f"Manifest: {result.manifest_path}")
            print(f"Materialization report: {result.materialization_report_path}")
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

        if args.command == "gate1":
            config = load_config(args.config)
            result = run_gate1_decision(
                gate0_run=args.gate0_run,
                config=config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Gate 1 decision layer complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Decision memo: {result.decision_memo_path}")
            return 0

        if args.command == "gate2":
            config = load_config(args.config)
            result = run_gate2_synthetic_validation(
                gate1_run=args.gate1_run,
                config=config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Gate 2 synthetic validation complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Threshold registry: {result.threshold_registry_path}")
            return 0

        if args.command == "gate25":
            config = load_config(args.config)
            result = run_prereg_assembly(
                gate2_run=args.gate2_run,
                config=config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Gate 2.5 prereg bundle complete: {result.output_dir}")
            print(f"Prereg bundle: {result.prereg_bundle_path}")
            print(f"Summary: {result.summary_path}")
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

    except (FileNotFoundError, ValueError, GuardError, Gate1Error, Gate2Error, PreregError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
