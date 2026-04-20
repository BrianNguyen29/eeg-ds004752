"""Single CLI entrypoint required by the V5.5 Colab blueprint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit.gate0 import run_gate0_audit
from .config import load_config
from .guards import GuardError, assert_real_phase_allowed
from .phase1.a2c_smoke import Phase1A2cSmokeError, run_phase1_a2c_smoke
from .phase1.a2d_smoke import Phase1A2dSmokeError, run_phase1_a2d_smoke
from .phase1.model_smoke import Phase1ModelSmokeError, run_phase1_model_smoke
from .phase1.smoke import Phase1SmokeError, run_phase1_smoke
from .phase05.estimators import Phase05EstimatorError, run_phase05_estimators
from .phase05.observability import Phase05Error, run_phase05_observability
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

    phase05_estimators = subparsers.add_parser(
        "phase05_estimators",
        help="Run Phase 0.5 task-contrast observability estimator workflow",
    )
    phase05_estimators.add_argument("--profile", default="t4_safe")
    phase05_estimators.add_argument("--prereg-bundle", required=True)
    phase05_estimators.add_argument("--phase05-run", required=True)
    phase05_estimators.add_argument("--dataset-root", required=True)
    phase05_estimators.add_argument("--config", default="configs/phase05/estimators.json")
    phase05_estimators.add_argument("--output-root", default="artifacts/phase05_estimators")
    phase05_estimators.add_argument("--subjects", nargs="*")
    phase05_estimators.add_argument("--max-subjects", type=int)
    phase05_estimators.add_argument("--max-sessions", type=int)
    phase05_estimators.add_argument("--max-trials-per-session", type=int)
    phase05_estimators.add_argument("--n-permutations", type=int)

    for phase in ("phase05_real", "phase1_real", "phase2_real", "phase3_real"):
        phase_parser = subparsers.add_parser(phase, help=f"Guarded {phase} command")
        phase_parser.add_argument("--profile", default="a100_fast")
        phase_parser.add_argument("--config", default="configs/prereg/prereg_bundle.json")
        phase_parser.add_argument("--phase-config", default="configs/phase05/observability.json")
        phase_parser.add_argument("--output-root", default="artifacts/phase05")
        phase_parser.add_argument("--readiness-run")
        phase_parser.add_argument("--dataset-root")
        phase_parser.add_argument("--smoke", action="store_true")
        phase_parser.add_argument("--model-smoke", action="store_true")
        phase_parser.add_argument("--a2c-smoke", action="store_true")
        phase_parser.add_argument("--a2d-smoke", action="store_true")
        phase_parser.add_argument("--comparators", nargs="*")
        phase_parser.add_argument("--max-outer-folds", type=int, default=2)
        phase_parser.add_argument("--outer-test-subjects", nargs="*")
        phase_parser.add_argument("--max-trials-per-session", type=int)

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

        if args.command == "phase05_real":
            phase_config = load_config(args.phase_config)
            result = run_phase05_observability(
                prereg_bundle=args.config,
                config=phase_config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
            )
            print(f"Phase 0.5 observability-only workflow complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase05_estimators":
            estimator_config = load_config(args.config)
            result = run_phase05_estimators(
                prereg_bundle=args.prereg_bundle,
                phase05_run=args.phase05_run,
                dataset_root=args.dataset_root,
                config=estimator_config,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                subjects=args.subjects,
                max_subjects=args.max_subjects,
                max_sessions=args.max_sessions,
                max_trials_per_session=args.max_trials_per_session,
                n_permutations=args.n_permutations,
            )
            print(f"Phase 0.5 observability estimators complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and sum(
            bool(flag) for flag in [args.smoke, args.model_smoke, args.a2c_smoke, args.a2d_smoke]
        ) > 1:
            raise ValueError("phase1_real can use only one of --smoke, --model-smoke, --a2c-smoke or --a2d-smoke")

        if args.command == "phase1_real" and args.a2c_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --a2c-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --a2c-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/a2c_smoke.json"
            a2c_config = load_config(phase_config_path)
            result = run_phase1_a2c_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=a2c_config,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A2c CORAL smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.a2d_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --a2d-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --a2d-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/a2d_smoke.json"
            a2d_config = load_config(phase_config_path)
            result = run_phase1_a2d_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=a2d_config,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A2d Riemannian smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.model_smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --model-smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --model-smoke requires --dataset-root")
            phase_config_path = args.phase_config
            if phase_config_path == "configs/phase05/observability.json":
                phase_config_path = "configs/phase1/model_smoke.json"
            model_config = load_config(phase_config_path)
            result = run_phase1_model_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                config=model_config,
                repo_root=Path.cwd(),
                comparators=args.comparators,
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
                max_trials_per_session=args.max_trials_per_session,
            )
            print(f"Phase 1 A2/A2b model smoke complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command == "phase1_real" and args.smoke:
            if not args.readiness_run:
                raise ValueError("phase1_real --smoke requires --readiness-run")
            if not args.dataset_root:
                raise ValueError("phase1_real --smoke requires --dataset-root")
            result = run_phase1_smoke(
                prereg_bundle=args.config,
                readiness_run=args.readiness_run,
                dataset_root=args.dataset_root,
                output_root=args.output_root,
                repo_root=Path.cwd(),
                max_outer_folds=args.max_outer_folds,
                outer_test_subjects=args.outer_test_subjects,
            )
            print(f"Phase 1 decoder smoke contract complete: {result.output_dir}")
            print(f"Summary: {result.summary_path}")
            print(f"Report: {result.report_path}")
            return 0

        if args.command in {"phase1_real", "phase2_real", "phase3_real"}:
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

    except (
        FileNotFoundError,
        ValueError,
        GuardError,
        Gate1Error,
        Gate2Error,
        PreregError,
        Phase05Error,
        Phase05EstimatorError,
        Phase1SmokeError,
        Phase1ModelSmokeError,
        Phase1A2cSmokeError,
        Phase1A2dSmokeError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
