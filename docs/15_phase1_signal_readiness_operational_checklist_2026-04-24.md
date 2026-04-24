# Phase 1 Signal Readiness Operational Checklist

Ngay cap nhat: 2026-04-24

Pham vi: checklist van hanh de dua nhanh prospective tu trang thai
`metadata-ready only` sang trang thai signal-ready va chuyen tiep sang tranche
benchmark/control-first.

Tai lieu nay docs-only, khong mo claim, va khong thay doi record Phase 1 hien tai.

## 1. Muc tieu

Checklist nay dung de xac nhan 4 viec da hoan tat:

1. payload materialization
2. signal-level Gate 0 rerun
3. cohort lock signal-ready
4. readiness package cho tranche benchmark/control-first

Exit target:

- du dieu kien thi hanh `docs/16_phase1_prospective_execution_roadmap_2026-04-24.md`

## 2. Current Status

Theo Gate 0 run `20260424T092923202761Z`:

- [x] `edf_payloads_not_materialized` da dong
- [x] `mat_derivatives_not_materialized` da dong
- [x] `cohort_lock_is_draft_until_signal_level_audit` da dong
- [x] `gate0_blockers = []`

## 3. Phase O1 - Payload Materialization

### Checklist

- [x] Xac dinh co che lay du lieu that: DataLad/git-annex
- [x] Materialize toan bo `.edf`
- [x] Materialize toan bo `.mat`
- [x] Kiem tra lai file sizes khong con pointer-like
- [x] Ghi nhan `materialization_report.json`

### Exit criteria

- [x] `edf materialized_count = 136/136`
- [x] `mat materialized_count = 15/15`
- [x] khong con trang thai pointer-like trong payload state

## 4. Phase O2 - Signal-Level Gate 0 Rerun

### Checklist

- [x] Chuan bi environment/runtime doc EDF/MAT
- [x] Xac nhan dataset root sau materialization
- [x] Rerun Gate 0 audit voi `--include-signal`
- [x] Tao artifact Gate 0 moi
- [x] Kiem tra artifact moi co day du:
  - `manifest.json`
  - `audit_report.md`
  - `cohort_lock.json`
  - `bridge_availability.json`
  - `materialization_report.json`

### Signal audit checks

- [x] EEG payload doc duoc
- [x] iEEG payload doc duoc
- [x] session duration hop le
- [x] sampling frequency doi chieu duoc bang payload that
- [x] event-to-signal alignment hop le
- [x] beamforming MAT files check `15/15`

### Exit criteria

- [x] full-cohort signal audit `status = ok`
- [x] `sessions_checked = 68`
- [x] `mat_files_checked = 15`

## 5. Phase O3 - Cohort Lock Signal-Ready

### Checklist

- [x] Xac dinh `n_primary_eligible`
- [x] Khoa `cohort_lock.json`
- [x] Dong bang subject/session usability o muc Gate 0

### Exit criteria

- [x] `cohort_lock_status = signal_audit_ready`
- [x] `n_primary_eligible = 15`

## 6. Phase O4 - Readiness Review Package

### Checklist

- [x] Ghi lai duong dan Gate 0 run moi
- [x] Tom tat blockers da dong
- [x] Cap nhat `docs/12`
- [x] Cap nhat `docs/14`
- [x] Cap nhat `docs/16`
- [x] Cap nhat `docs/19`
- [x] Cap nhat `docs/20`

### Exit criteria

- [x] du thong tin de chuyen sang tranche benchmark/control-first

## 7. Decision Rule

### Trang thai hien tai

- `NO-GO for code due to data-readiness` khong con ap dung

### Trang thai moi

- `GO` cho implementation benchmark/control-first
- van `claim-closed` cho den khi evidence package day du

## 8. Deliverables thu duoc

1. Gate 0 run `20260424T092923202761Z`
2. `manifest.json` signal-ready
3. `cohort_lock.json` signal-ready
4. `materialization_report.json` complete
5. `audit_report.md` full-cohort signal audit

## 9. Operational Notes

- khong dung checklist nay de “cuu” V5.5
- checklist nay phuc vu future-run readiness cua V5.6
- buoc tiep theo la benchmark/control scaffolding, khong phai efficacy claim

## 10. One-line Checklist Status

Checklist signal-readiness da hoan tat; nhanh prospective `iEEG-assisted` da co
the chuyen sang tranche benchmark/control-first cua V5.6.
