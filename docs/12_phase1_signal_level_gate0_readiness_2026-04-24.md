# Phase 1 Signal-Level Gate 0 Readiness

Ngay cap nhat: 2026-04-24

Pham vi: tai lieu docs-only de xac dinh nhanh prospective iEEG-assisted da du
dieu kien du lieu va signal-level Gate 0 hay chua.

Tai lieu nay khong mo claim, khong sua artifact da khoa, va khong reclassify
record V5.5.

## 1. Muc tieu

Tai lieu nay tra loi 3 cau hoi:

1. Gate 0 hien tai da san sang o muc signal-level hay chua?
2. Cac blocker du lieu nao con ton tai cho nhanh prospective iEEG-assisted?
3. Buoc implementation nao duoc phep mo tiep theo?

## 2. Source of truth

Run duoc dung lam co so readiness:

- `artifacts/gate0/20260424T092923202761Z`

Truong authoritative:

- `manifest_status = signal_audit_ready`
- `primary_eligibility_status = signal_audit_ready`
- `gate0_blockers = []`
- `signal_status = ok`
- `sessions_checked = 68`
- `mat_files_checked = 15`
- `cohort_lock_status = signal_audit_ready`
- `n_primary_eligible = 15`
- `edf_materialized = 136/136`
- `mat_materialized = 15/15`

## 3. Trang thai hien tai

Theo Gate 0 run da khoa:

- dataset: `ds004752`
- subjects: `15`
- sessions: `68`
- EEG event trials: `3353`
- iEEG event trials: `3353`
- session trial-count mismatch: `0`
- core EEG/iEEG event field mismatch: `0`

Y nghia:

- metadata-level alignment cua dataset la tot;
- payload EDF/MAT da duoc materialize day du;
- signal-level audit da pass tren toan cohort;
- cohort lock da duoc khoa o muc signal-ready.

## 4. Blockers hien tai

Theo `manifest.json` cua run `20260424T092923202761Z`, blockers hien tai la:

- khong con blocker nao (`gate0_blockers = []`)

Blocker cu da dong:

1. `edf_payloads_not_materialized`
2. `mat_derivatives_not_materialized`
3. `cohort_lock_is_draft_until_signal_level_audit`

## 5. Danh gia readiness

### 5.1 Dieu da san sang

- BIDS identity da duoc ghi nhan
- subject/session inventory da co
- EEG/iEEG event alignment da duoc audit o muc metadata
- payload EDF da materialize day du
- payload MAT/beamforming da materialize day du
- signal-level audit da pass tren `68/68` sessions
- MAT derivatives da duoc check `15/15`
- cohort lock da signal-ready
- `n_primary_eligible = 15`

### 5.2 Dieu chua duoc chung minh

- readiness nay khong mo efficacy claim
- readiness nay khong chung minh iEEG-assisted superiority
- readiness nay khong cho phep sua lai record V5.5

No chi chung minh:

- du lieu da san sang cho nhanh prospective;
- Gate 0 khong con la blocker van hanh chinh.

## 6. Tac dong doi voi nhanh iEEG-assisted

Truoc run nay, contract iEEG-assisted moi o muc docs-only va bi chan boi
data-readiness.

Sau run nay:

- real signal payload da co the doc va audit;
- beamforming derivatives da co the inventory va signal-check;
- cohort lock da san sang de lam dau vao cho nhanh benchmark/control-first cua V5.6.

## 7. Readiness decision

Danh gia hien tai:

- `metadata_ready = true`
- `signal_ready = true`
- `cohort_ready = true`
- `prospective_ieeg_branch_ready = true` o muc data/readiness

Ket luan:

> Gate 0 hien tai da san sang o muc signal-level cho nhanh prospective
> iEEG-assisted.

## 8. Buoc tiep theo duoc phep

Sau Gate 0 run nay, nhanh prospective duoc phep mo sang:

1. benchmark/control layer implementation
2. split registry va feature provenance scaffolding
3. leaderboard/comparator scaffolding
4. contract-bound implementation planning cho `A4_privileged`

Khong nen nhay thang vao heavy modeling truoc khi benchmark/control layer duoc
lap day du theo V5.6.

## 9. Decision gate

### Trang thai cu

Trang thai `NO-GO do chua signal-ready` khong con hieu luc.

### Trang thai moi

`GO` cho:

- benchmark/control-first implementation tranche
- repo mapping va execution plan tiep theo

`Khong` tu dong co nghia la GO cho:

- mo efficacy claim
- bo qua governance
- heavy modeling khong co benchmark contract

## 10. One-line Conclusion

Gate 0 hien tai da dat muc signal-ready va cohort-ready; vi vay nhanh
prospective `iEEG-assisted` khong con bi chan boi data-readiness, va co the di
tiep sang tranche benchmark/control-first cua V5.6.
