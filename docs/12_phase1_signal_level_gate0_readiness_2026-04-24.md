# Phase 1 Signal-Level Gate 0 Readiness

Ngay cap nhat: 2026-04-24

Pham vi: tai lieu docs-only de xac dinh nhanh prospective iEEG-assisted da du
dieu kien du lieu va signal-level Gate 0 hay chua.

Tai lieu nay khong sua code, khong mo claim, khong doi artifact da khoa, va khong
reclassify run hien tai.

## 1. Muc tieu

Tai lieu nay tra loi 3 cau hoi:

1. Gate 0 hien tai da san sang o muc signal-level hay chua?
2. Cac blocker du lieu nao dang chan nhanh prospective iEEG-assisted?
3. Dieu kien toi thieu nao phai dat truoc khi cho phep nhanh code prospective?

## 2. Trang thai hien tai

Theo Gate 0 audit da khoa:

- dataset: `ds004752`
- subjects: `15`
- sessions: `68`
- EEG event trials: `3353`
- iEEG event trials: `3353`
- session trial-count mismatch: `0`
- core EEG/iEEG event field mismatch: `0`

Y nghia:

- metadata-level alignment cua dataset la tot;
- EEG va iEEG da dong bo o muc event/session;
- nhung dieu nay chua du de xem Gate 0 la signal-ready.

## 3. Blockers hien tai

Theo `artifacts/gate0/20260417T082814Z/audit_report.md`, cac blocker hien tai la:

1. `edf_payloads_not_materialized`
2. `mat_derivatives_not_materialized`
3. `cohort_lock_is_draft_until_signal_level_audit`

Day la blockers that su, khong phai ghi chu phu.

## 4. Danh gia readiness

### 4.1 Dieu da san sang

- BIDS identity da duoc ghi nhan
- subject/session inventory da co
- EEG/iEEG event alignment da duoc audit o muc metadata
- channel/electrode sidecars da duoc thong ke
- bridge/beamforming files da duoc thay o muc pointer inventory

### 4.2 Dieu chua san sang

- EDF payload chua duoc materialize de doc tin hieu that
- MAT derivatives chua duoc materialize de doc bridge/beamforming that
- cohort lock van o muc draft, chua duoc khoa signal-level
- chua co audit signal-level cho:
  - sampling consistency
  - duration consistency
  - signal readability
  - trial-to-signal alignment
  - bridge availability o muc payload

## 5. Tai sao blocker nay quan trong cho nhanh iEEG-assisted

Nhanh `iEEG-assisted` khong chi can metadata alignment.

No can:

- real signal payload
- real iEEG availability
- neu dung bridge/beamforming, phai co derivative payload that
- kha nang audit duoc privileged path bang artifact signal-level

Neu khong dat muc nay, moi contract ve:

- real iEEG teacher
- privileged branch
- observability bridge

deu se mo ho va kho audit.

## 6. Danh sach readiness check can vuot qua

Nhanh prospective chi nen duoc xem la signal-ready neu dat du cac check sau:

### 6.1 Payload materialization

- EDF files co the doc duoc o muc signal
- MAT derivative files co the doc duoc o muc noi dung
- khong con trang thai `pointer_like_only`

### 6.2 Signal audit

- sampling frequencies hop le va doc duoc bang payload that
- session durations hop le
- EEG/iEEG signal co the map voi event windows
- channel inventory va electrode inventory co the doi chieu voi payload

### 6.3 Cohort lock

- `n_primary_eligible` duoc khoa
- subject/session exclusion reasons duoc ghi ro
- cohort lock khong con o trang thai draft

### 6.4 Bridge readiness

Neu dung beamforming/bridge:

- payload bridge co mat that su
- subject/session bridge availability duoc xac nhan o muc signal
- co audit cho missing bridge va su dong bo voi scalp/iEEG rows

## 7. Readiness decision

Danh gia hien tai:

- `metadata_ready = true`
- `signal_ready = false`
- `prospective_ieeg_branch_ready = false`

Ket luan:

> Gate 0 hien tai chua san sang o muc signal-level cho nhanh prospective
> iEEG-assisted.

## 8. De xuat buoc tiep theo

Truoc khi lam bat ky thiet ke A3/A4 real iEEG nao, can:

1. materialize EDF payloads
2. materialize MAT/beamforming derivatives neu se dung bridge
3. rerun Gate 0 o muc signal-level
4. khoa cohort lock o muc signal-ready
5. cap nhat bridge availability artifact

## 9. Decision gate

### `No-go` hien tai

Khong nen mo nhanh code prospective neu:

- payload van chua materialize
- cohort lock van draft
- khong co signal-level audit moi

### `Go` toi thieu

Chi sau khi co:

- Gate 0 signal-level audit clean hoac co blocker duoc dinh danh ro;
- cohort lock signal-ready;
- bridge/payload readiness duoc ghi bang artifact.

## 10. One-line Conclusion

Gate 0 hien tai moi dat muc metadata-ready, chua dat muc signal-ready; vi vay
nhanh prospective `iEEG-assisted` chua du dieu kien de di vao code/runtime, va
can uu tien payload materialization + signal-level audit truoc.
