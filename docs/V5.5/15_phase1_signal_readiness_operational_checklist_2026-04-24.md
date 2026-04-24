# Phase 1 Signal Readiness Operational Checklist

Ngay cap nhat: 2026-04-24

Pham vi: checklist van hanh de dua nhanh prospective tu trang thai
`metadata-ready only` sang trang thai co the danh gia lai `go/no-go` cho
signal-level Gate 0.

Tai lieu nay docs-only, khong sua code, khong mo claim, va khong thay doi record
Phase 1 hien tai.

## 1. Muc tieu

Checklist nay dung de hoan tat 3 viec:

1. payload materialization
2. signal-level Gate 0 rerun
3. cohort lock signal-ready

Exit target:

- du dieu kien review lai [docs/14_phase1_go_no_go_decision_memo_2026-04-24.md](D:/WorkSpace/EEG/eeg-ds004752/docs/14_phase1_go_no_go_decision_memo_2026-04-24.md)

## 2. Current Blockers

Blockers hien tai da biet:

- `edf_payloads_not_materialized`
- `mat_derivatives_not_materialized`
- `cohort_lock_is_draft_until_signal_level_audit`

## 3. Phase O1 - Payload Materialization

### Muc tieu

Bien payload tu trang thai pointer-like sang trang thai doc duoc o muc signal.

### Checklist

- [ ] Xac dinh ro co che luu tru hien tai:
  - DataLad
  - git-annex
  - local mirror
  - cloud mount
- [ ] Liet ke chinh xac cac duong dan `.edf` can materialize
- [ ] Liet ke chinh xac cac duong dan `.mat` can materialize
- [ ] Xac nhan dung luong can thiet va kha nang luu tru
- [ ] Materialize toan bo `.edf`
- [ ] Materialize toan bo `.mat`
- [ ] Kiem tra lai file sizes khong con pointer-like
- [ ] Ghi nhan log materialization:
  - so file thanh cong
  - so file that bai
  - file nao thieu
  - ly do that bai

### Exit criteria

- [ ] `edf materialized_count > 0` va tot nhat la full coverage
- [ ] `mat materialized_count > 0` va tot nhat la full coverage
- [ ] khong con trang thai `all_pointer_like`

## 4. Phase O2 - Signal-Level Gate 0 Rerun

### Muc tieu

Rerun Gate 0 voi payload that de kiem signal-level integrity.

### Checklist

- [ ] Chuan bi environment/runtime co the doc EDF/MAT
- [ ] Xac nhan duong dan dataset root sau materialization
- [ ] Rerun Gate 0 audit
- [ ] Tao artifact Gate 0 moi
- [ ] Kiem tra artifact moi co day du:
  - `manifest.json`
  - `audit_report.md`
  - `cohort_lock.json`
  - `bridge_availability.json`
  - materialization/signal reports neu co

### Signal audit checks can co

- [ ] EEG payload doc duoc
- [ ] iEEG payload doc duoc
- [ ] session duration hop le
- [ ] sampling frequency co the doi chieu bang payload that
- [ ] event-to-signal alignment hop le
- [ ] channel inventory hop le
- [ ] electrode inventory hop le
- [ ] bridge/beamforming availability duoc xac nhan o muc payload neu can

### Exit criteria

- [ ] Gate 0 moi khong con blocker `edf_payloads_not_materialized`
- [ ] Gate 0 moi khong con blocker `mat_derivatives_not_materialized` neu branch can bridge
- [ ] signal-level audit co ket luan ro rang, khong mo ho

## 5. Phase O3 - Cohort Lock Signal-Ready

### Muc tieu

Chuyen cohort lock tu draft metadata-only sang signal-ready.

### Checklist

- [ ] Xac dinh `n_primary_eligible`
- [ ] Ghi ro cac subject/session bi loai
- [ ] Ghi ro ly do loai:
  - missing payload
  - signal read failure
  - alignment failure
  - bridge unavailable
  - quality issue
- [ ] Kiem tra cohort lock khop voi signal-level audit moi
- [ ] Dong bang subject/session/trial usable cho nhanh prospective

### Exit criteria

- [ ] `cohort_lock.json` khong con o trang thai draft
- [ ] subject/session inclusion duoc khoa ro
- [ ] co the dung artifact nay lam input cho future-run proposal review

## 6. Phase O4 - Readiness Review Package

### Muc tieu

Lap goi review nho de quay lai quyet dinh `go/no-go`.

### Checklist

- [ ] Ghi lai duong dan Gate 0 run moi
- [ ] Tom tat blockers da dong
- [ ] Liet ke blockers con lai neu co
- [ ] Cap nhat `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- [ ] Neu can, cap nhat `docs/14_phase1_go_no_go_decision_memo_2026-04-24.md`

### Exit criteria

- [ ] du thong tin de danh gia lai `go/no-go`

## 7. Decision Rule

### Tiep tuc giu `NO-GO`

Neu con bat ky dieu nao sau day:

- payload chua materialize day du
- signal-level audit chua xong
- cohort lock van draft
- bridge readiness van mo ho

### Co the mo review lai `GO`

Chi khi:

- payload da san sang
- signal-level Gate 0 moi da tao artifact sach
- cohort lock signal-ready da khoa

## 8. Deliverables can thu ve

Toi thieu can thu ve:

1. Gate 0 run moi o muc signal-level
2. `audit_report.md` moi
3. `manifest.json` moi
4. `cohort_lock.json` signal-ready
5. `bridge_availability.json` da cap nhat neu ap dung
6. mot ghi chu tong hop blockers con lai

## 9. Operational Notes

- khong nhay sang code A3/A4 prospective truoc khi xong checklist nay
- khong dung payload materialization nhu mot co so de sua run Phase 1 da fail
- checklist nay phuc vu future-run readiness, khong phuc vu remediation cho record hien tai

## 10. One-line Checklist Status

Cho den khi checklist nay duoc hoan tat, nhanh prospective `iEEG-assisted`
van phai giu o trang thai `NO-GO for code`.
