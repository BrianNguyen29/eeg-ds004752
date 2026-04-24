# Phase 1 Prospective Go / No-Go Decision Memo

Ngay cap nhat: 2026-04-24

Pham vi: memo docs-only de ra quyet dinh co nen mo nhanh code prospective cho
huong `iEEG-assisted for scalp EEG` ngay luc nay hay khong.

Memo nay dua tren:

- `docs/11_phase1_prospective_ieeg_assisted_proposal_2026-04-24.md`
- `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- `docs/13_phase1_ieeg_assisted_contract_2026-04-24.md`

Memo nay khong mo claim, khong cho phep doi threshold/formula, khong reclassify
artifact da fail, va khong cho phep sua code runtime ngay lap tuc.

## 1. Cau hoi quyet dinh

Cau hoi can tra loi:

> Co nen mo nhanh code prospective ngay bay gio de theo duoi claim
> `iEEG-assisted superiority for scalp EEG` hay khong?

## 2. Tong hop bang chung dau vao

### 2.1 Trang thai nhanh hien tai

Nhanh Phase 1 hien tai da duoc khoa o trang thai:

- `fail-closed`
- `claim-closed`
- formula ambiguity da dong
- consistency audit da xong

Hai blockers controls van con:

- `nuisance_shared_control`
- `spatial_control`

### 2.2 Claim target cua nhanh prospective

Claim target hop le neu mo nhanh moi la:

> `A4_privileged` vuot cac comparator scalp manh duoi contract da khoa, trong khi
> test-time inference van scalp-only va tat ca governance packages deu dat.

### 2.3 Signal-level readiness

Theo `docs/12`, Gate 0 hien tai moi dat muc metadata-ready.

Blockers con ton tai:

- `edf_payloads_not_materialized`
- `mat_derivatives_not_materialized`
- `cohort_lock_is_draft_until_signal_level_audit`

### 2.4 iEEG-assisted contract readiness

Theo `docs/13`, contract ly thuyet da ro hon:

- phan biet duoc scalp proxy teacher va real iEEG teacher;
- khoa duoc nguyen tac train-time privileged / scalp-only inference;
- khoa duoc claim target va comparator evidence contract.

Nhung contract nay hien moi o muc docs-only.

## 3. Danh gia theo tieu chi go / no-go

### Tieu chi 1 - Co signal-level readiness chua?

Ket qua: **Chua**

Ly do:

- payload chua materialize;
- cohort lock chua signal-ready;
- chua co signal-level audit moi.

### Tieu chi 2 - Co the chi ro real iEEG entry-point chua?

Ket qua: **Chua du**

Ly do:

- contract da de xuat duoc;
- nhung chua co payload-level evidence de xac nhan entry-point thuc te.

### Tieu chi 3 - Co du co so de patch code prospective ma khong mo ho claim boundary khong?

Ket qua: **Chua**

Ly do:

- neu patch code ngay bay gio, se de nham giua:
  - prospective research
  - va no luc "cai thien" record hien tai;
- payload/signal gate chua san sang nen patch se thieu nen audit.

### Tieu chi 4 - Co du bo docs-only de chot huong nghien cuu tiep chua?

Ket qua: **Co**

Ly do:

- da co proposal
- da co Gate 0 readiness note
- da co iEEG-assisted contract

Tuc la:

- chua du de code;
- nhung da du de ra quyet dinh van hanh.

## 4. Decision

### Quyet dinh chinh thuc

**NO-GO cho nhanh code prospective o thoi diem hien tai.**

### Ly do quyet dinh

1. Gate 0 signal-level chua san sang.
2. Payload iEEG/derivative chua duoc materialize de audit thuc.
3. Cohort lock chua duoc khoa o muc signal-ready.
4. Real iEEG entry-point moi duoc mo ta o muc contract, chua co ha tang du lieu de
   xac nhan trien khai hop le.
5. Mo nhanh code bay gio co nguy co lam mo ranh gioi giua:
   - future-run research
   - va remediation cho run da fail.

## 5. Dieu kien de chuyen tu no-go sang go

Chi xem xet `go` neu dat du ca 5 dieu kien sau:

1. EDF payloads duoc materialize
2. MAT/bridge derivatives duoc materialize neu se dung
3. Gate 0 signal-level audit duoc rerun
4. `cohort_lock.json` duoc khoa o muc signal-ready
5. co artifact/ghi nhan ro real iEEG entry-point cho A3/A4 future runs

Neu thieu bat ky dieu kien nao, giu `no-go`.

## 6. Viec duoc phep lam sau memo nay

Duoc phep:

- tiep tuc hoan thien docs-only planning
- lap checklist materialization va signal-level audit
- chuan bi dataset/runtime prerequisites
- viet future-work section cho bao cao/luan van

Khong duoc phep:

- patch code A3/A4 prospective ngay
- doi config threshold/formula
- mo lai notebook remediation/governance cho issue formula
- dien giai current record nhu bang chung iEEG-assisted efficacy

## 7. De xuat buoc tiep theo sau memo

Buoc tiep theo hop le nhat:

1. lap mot checklist van hanh rieng cho:
   - payload materialization
   - signal-level Gate 0 rerun
   - cohort lock signal-ready
2. sau khi checklist do hoan tat moi review lai quyet dinh `go/no-go`

Neu khong the dat duoc cac dieu kien tren, nen giu de tai o huong:

- negative finding hop le
- methodological contribution
- future work de xuat, khong code

## 8. One-line Decision

Nhanh prospective `iEEG-assisted for scalp EEG` hien tai **NO-GO for code**; chi
sau khi Gate 0 dat muc signal-ready va real iEEG entry-point duoc rang buoc bang
artifact/audit ro rang moi duoc xem xet mo nhanh runtime prospective.
