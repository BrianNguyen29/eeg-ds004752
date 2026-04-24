# Kiem tra tuan tu du an

Ngay kiem tra: 2026-04-23

Pham vi: doc map, CLI entrypoints, Gate 0 metadata audit, data
materialization state, governance guards, va baseline test suite.

## 1. Ban do tai lieu va source of truth

Thu tu uu tien hien tai:

1. `docs/01_v55_doc_code_crosswalk.md` khoa crosswalk giua tai lieu V5.5 va code.
2. `docs/02_colab_local_runbook.md` khoa thu tu van hanh local/Colab.
3. `README.md` mo ta scaffold, CLI va trang thai du lieu.
4. `notebooks/README.md` mo ta notebook orchestration; notebook khong duoc la source of truth cho logic khoa hoc.
5. `src/` la noi giu durable scientific/governance logic.
6. `configs/` la noi giu threshold, runtime, comparator, control va prereg contract.

Quy tac quan trong:

- Technical spec co uu tien cao nhat khi co xung dot ve behavior.
- Notebook chi orchestration; logic co the tai su dung phai nam trong `src/` va co test.
- Real-data substantive phase khong duoc mo neu Gate 2.5 prereg bundle chua `locked`.
- `N_raw public = 15` khong duoc xem la primary cohort neu Gate 0 signal-level chua pass.

## 2. CLI va mapping van hanh

Entrypoint duy nhat: `python -m src.cli`.

| Layer | CLI command | Code owner | Config chinh | Artifact output |
|---|---|---|---|---|
| Gate 0 | `audit` | `src/audit/gate0.py`, `src/audit/materialization.py`, `src/audit/signal.py` | `configs/data/snapshot.yaml` | `artifacts/gate0/<run>` |
| Smoke | `smoke` | `src/cli.py`, `src/config.py` | `configs/data/snapshot.yaml` | console only |
| Gate 1 | `gate1` | `src/simulation/decision.py` | `configs/gate1/decision_simulation.json` | `artifacts/gate1/<run>` |
| Gate 2 | `gate2` | `src/synthetic/gate2.py` | `configs/gate2/synthetic_validation.json` | `artifacts/gate2/<run>` |
| Gate 2.5 | `gate25` | `src/prereg/bundle.py` | `configs/prereg/prereg_assembly.json` | `artifacts/prereg/<run>` |
| Guarded real phases | `phase05_real`, `phase1_real`, `phase2_real`, `phase3_real` | `src/guards.py`, `src/cli.py` | locked prereg bundle | blocked unless prereg locked |
| Phase 0.5 estimators | `phase05_estimators` | `src/phase05/estimators.py` | `configs/phase05/estimators.json` | `artifacts/phase05_estimators/<run>` |
| Phase 1 final chain | `phase1_final_*` | `src/phase1/final_*.py` | `configs/phase1/*.json` | `artifacts/phase1_*` |
| Report scan | `report_compile` | `src/cli.py` | run path | console summary |

Key frozen/draft values observed:

- Gate 1 SESOI subject-level delta BA: `0.03`.
- Gate 1 max allowed delta ECE: `0.02`.
- Gate 1 influence ceiling: `0.40`.
- Gate 2 frozen threshold defaults include `m_e_min=0.20`, `q_e_min=0.20`, `a_e_min=0.67`, `delta_obs_min=0.02`, `tau_viable=0.20`, `influence_ceiling=0.40`.

## 3. Local commands da chay

```powershell
python -m src.cli smoke --profile t4_safe --config configs/data/snapshot.yaml
python -m src.cli audit --profile t4_safe --config configs/data/snapshot.yaml
python -m src.cli gate1 --profile t4_safe --gate0-run artifacts/gate0/20260423T134322736254Z --config configs/gate1/decision_simulation.json --output-root artifacts/gate1_check
python -m src.cli phase05_real --profile t4_safe --config configs/prereg/prereg_bundle.json --phase-config configs/phase05/observability.json --output-root artifacts/phase05_guard_check
python -m unittest discover -s tests
```

Ket qua:

- `smoke`: pass.
- `audit`: tao Gate 0 run moi `artifacts/gate0/20260423T134322736254Z`.
- `gate1` tren Gate 0 metadata-only: fail dung ky vong.
- `phase05_real` voi prereg default: fail dung ky vong vi prereg chua locked.
- Unit tests: `119 tests` pass.

## 4. Gate 0 run moi

Run: `artifacts/gate0/20260423T134322736254Z`

File chinh:

- `manifest.json`
- `cohort_lock.json`
- `audit_report.md`
- `override_log.md`
- `bridge_availability.json`
- `materialization_report.json`

Manifest summary:

| Field | Value |
|---|---:|
| `manifest_status` | `draft_metadata_only` |
| `n_raw_public` | 15 |
| `n_primary_eligible` | null |
| `n_subjects` | 15 |
| `n_sessions` | 68 |
| EEG event trials | 3353 |
| iEEG event trials | 3353 |
| Core EEG/iEEG event mismatches | 0 |
| Artifact trials from EEG events | 168 |
| Correct trials from EEG events | 3045 |

Sidecar summary from latest audit:

- Channel sampling frequency counts: `200=448`, `2000=2270`, `4000=1418`, `4096=876`.
- Channel type counts: `EEG=1120`, `SEEG=3584`, `ECOG=308`.
- Electrode rows: `3892`.
- Electrodes with `no_label_found`: `1180`.

## 5. Materialization state

`materialization_report.json` status: `incomplete`.

| Payload | Count | Materialized | Missing |
|---|---:|---:|---:|
| EDF | 136 | 0 | 136 |
| MAT | 15 | 0 | 15 |

Current blocker list:

- `edf_payloads_not_materialized`
- `mat_derivatives_not_materialized`
- `cohort_lock_is_draft_until_signal_level_audit`

`cohort_lock.json` status: `draft_not_primary_locked`.

Reason: signal-level payloads or full signal audit are incomplete; primary eligibility cannot be locked.

## 6. Governance guard checks

Gate 1 was intentionally run against the metadata-only Gate 0 run and was rejected.
Important failure reasons:

- `manifest_status` is `draft_metadata_only`, not `signal_audit_ready`.
- `signal_audit.status` is `not_requested`, not `ok`.
- `candidate_sessions`, `sessions_checked`, `candidate_mat_files`, `mat_files_checked` do not match full expected counts.
- Gate 0 blockers are not empty.
- EDF and MAT payloads are not fully materialized.
- `cohort_lock_status` is not `signal_audit_ready`.
- `n_primary_eligible` is missing.

Default `configs/prereg/prereg_bundle.json` status is `draft_blocked` with no `artifact_hashes`.
`phase05_real` was rejected with:

```text
phase05_real blocked: prereg_bundle.json is not locked after Gate 2.5
```

This confirms the pipeline currently fails closed.

## 7. Current interpretation

The project is internally consistent at metadata/governance level:

- Metadata inventory is repeatable.
- EEG/iEEG event core fields match across 68 sessions.
- Required Gate 0 artifact family is generated.
- Local guard behavior prevents premature Gate 1 and real phase execution.
- Tests pass.

The project is not yet ready for signal-level Gate 0, Gate 1, Gate 2.5 real-phase unlocking, or claim-bearing Phase 1 work because all EDF/MAT payloads are still pointer-like.

## 8. Next sequential work

1. Materialize data payloads for a controlled sample first:

   ```bash
   bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data sample
   ```

2. Install signal extras in the runtime used for audit:

   ```bash
   INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh
   ```

3. Run sample signal audit:

   ```bash
   python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml --include-signal --signal-max-sessions 1
   ```

4. If sample passes, materialize by subject, then run subject-scoped signal audit:

   ```bash
   bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data subjects sub-01 sub-02
   python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml --include-signal --subjects sub-01 sub-02 --signal-max-sessions 11
   ```

5. Only after full materialization and full signal audit:

   - require `manifest_status=signal_audit_ready`;
   - require `cohort_lock_status=signal_audit_ready`;
   - require empty `gate0_blockers`;
   - then proceed to Gate 1.

