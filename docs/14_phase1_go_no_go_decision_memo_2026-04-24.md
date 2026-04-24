# Phase 1 Prospective Go / No-Go Decision Memo

Ngay cap nhat: 2026-04-24

Pham vi: memo docs-only de ra quyet dinh co nen mo nhanh implementation
prospective cho huong `iEEG-assisted for scalp EEG` ngay luc nay hay khong.

Memo nay dua tren:

- `docs/11_phase1_prospective_ieeg_assisted_proposal_2026-04-24.md`
- `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- `docs/13_phase1_ieeg_assisted_contract_2026-04-24.md`
- Gate 0 run `artifacts/gate0/20260424T092923202761Z`

Memo nay khong mo claim efficacy, khong cho phep doi threshold/formula, khong
reclassify artifact da fail, va khong cho phep dung V5.5 nhu positive support.

## 1. Cau hoi quyet dinh

> Co nen mo nhanh implementation prospective ngay bay gio de theo duoi huong
> `iEEG-assisted for scalp EEG` hay khong?

## 2. Tong hop bang chung dau vao

### 2.1 Trang thai nhanh hien tai

Nhanh Phase 1 hien tai da duoc khoa o trang thai:

- `fail-closed`
- `claim-closed`
- formula ambiguity da dong
- consistency audit da xong

Hai blockers controls cua V5.5 van la lich su da khoa:

- `nuisance_shared_control`
- `spatial_control`

### 2.2 Claim target cua nhanh prospective

Claim target hop le cua nhanh moi van la:

> `A4_privileged` vuot cac comparator scalp manh duoi contract da khoa, trong khi
> test-time inference van scalp-only va tat ca governance/control packages deu dat.

### 2.3 Signal-level readiness

Theo Gate 0 run `20260424T092923202761Z`:

- `manifest_status = signal_audit_ready`
- `gate0_blockers = []`
- `cohort_lock_status = signal_audit_ready`
- `n_primary_eligible = 15`

Nghia la blocker data-readiness da duoc dong.

### 2.4 iEEG-assisted contract readiness

Theo `docs/13`, contract ly thuyet da ro:

- phan biet duoc scalp proxy teacher va real iEEG teacher;
- khoa duoc nguyen tac train-time privileged / scalp-only inference;
- khoa duoc claim target va comparator evidence contract.

## 3. Danh gia theo tieu chi go / no-go

### Tieu chi 1 - Co signal-level readiness chua?

Ket qua: **Da co**

Ly do:

- payload da materialize day du;
- full-cohort signal audit da pass;
- cohort lock da signal-ready.

### Tieu chi 2 - Co the chi ro real iEEG entry-point chua?

Ket qua: **Da co o muc contract**

Ly do:

- contract docs-only da du ro de mo tranche benchmark/control-first;
- chua co ly do de mo ho claim boundary.

### Tieu chi 3 - Co du co so de mo implementation ma khong mo ho claim boundary khong?

Ket qua: **Co, nhung phai gioi han pham vi**

Pham vi duoc phep:

- benchmark/control layer
- split registry
- feature provenance
- comparator/leaderboard scaffolding
- implementation planning co rang buoc contract

Pham vi chua nen mo ngay:

- heavy modeling khong benchmark
- dien giai artifact moi nhu efficacy evidence

### Tieu chi 4 - Co du bo docs-only de chot huong nghien cuu tiep chua?

Ket qua: **Co**

## 4. Decision

### Quyet dinh chinh thuc

**GO cho tranche implementation benchmark/control-first cua V5.6.**

### Gioi han cua quyet dinh

Quyet dinh nay:

- la `GO for code` o muc benchmark/control scaffolding
- khong phai `GO for claim`
- khong phai `GO for unchecked heavy modeling`

## 5. Dieu kien ranh buoc

Nhanh implementation prospective chi duoc di tiep neu giu du cac dieu kien sau:

1. test-time inference van scalp-only
2. khong dung V5.5 de ho tro positive efficacy claim
3. moi implementation moi phai phuc vu benchmark/control contract cua V5.6
4. governance moi phai giu fail-closed/claim-closed cho den khi evidence package day du

## 6. Viec duoc phep lam sau memo nay

Duoc phep:

- mo repo mapping implementation cho V5.6
- tao split registry / feature provenance skeleton
- tao comparator registry / leaderboard skeleton
- tao control generator scaffolding
- chuan bi implementation plan cho `RIFT-Net Lite`

Khong duoc phep:

- mo efficacy claim
- bo qua comparator contract
- patch threshold/formula de thay doi record V5.5

## 7. De xuat buoc tiep theo sau memo

Buoc tiep theo hop le nhat:

1. cap nhat roadmap va operational checklist theo trang thai signal-ready moi
2. mo tranche benchmark/control-first trong repo
3. giu `claim-closed` cho den khi comparator + control + calibration + influence package day du

## 8. One-line Decision

Nhanh prospective `iEEG-assisted for scalp EEG` hien tai **GO for
benchmark/control-first implementation**, vi Gate 0 da signal-ready; tuy nhien
day van chua phai bang chung efficacy va chua mo claim.
