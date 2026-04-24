# Phase 1 Prospective Execution Roadmap

Ngay cap nhat: 2026-04-24

Pham vi: roadmap ngan de dieu hanh thuc thi cho nhanh prospective
`iEEG-assisted for scalp EEG`, tong hop tu `docs/11` den `docs/15`.

Trang thai khoi dau:

- current Phase 1 record: `fail-closed`, `claim-closed`
- current prospective status: `GO for benchmark/control-first implementation`

## 1. Roadmap ngan

### R1 - Khoa huong nghien cuu

Tai lieu nen dung:

- `docs/11_phase1_prospective_ieeg_assisted_proposal_2026-04-24.md`
- `docs/13_phase1_ieeg_assisted_contract_2026-04-24.md`

Muc tieu:

- chot claim target chinh la `A4_privileged`
- chot quy tac `train-time privileged, test-time scalp-only`
- chot rang current run khong duoc dung de ho tro claim moi

Trang thai:

- `Completed`

### R2 - Mo khoa du lieu signal-level

Tai lieu nen dung:

- `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- `docs/15_phase1_signal_readiness_operational_checklist_2026-04-24.md`

Muc tieu:

- materialize EDF/MAT payloads
- rerun Gate 0 o muc signal-level
- khoa `cohort_lock.json` o muc signal-ready

Trang thai:

- `Completed` qua run `20260424T092923202761Z`

### R3 - Review lai quyet dinh go/no-go

Tai lieu nen dung:

- `docs/14_phase1_go_no_go_decision_memo_2026-04-24.md`
- Gate 0 run `20260424T092923202761Z`

Muc tieu:

- chot co mo tranche implementation tiep theo hay khong

Trang thai:

- `Completed`
- ket qua: `GO for benchmark/control-first implementation`

### R4 - Benchmark / Control First Implementation

Muc tieu:

- tao split registry
- tao feature provenance skeleton
- tao comparator registry / leaderboard skeleton
- tao control generator scaffolding
- dat benchmark contract thanh source of truth truoc khi vao heavy modeling

Trang thai:

- `Next active tranche`

## 2. Thu tu uu tien thuc thi

Thu tu dung hien tai:

1. `R1` - chot contract
2. `R2` - khoa signal-level data readiness
3. `R3` - chot `GO`
4. `R4` - benchmark/control-first implementation
5. chi sau do moi xem xet model-heavy tranche

## 3. Cong viec van hanh can lam ngay

Ba viec can lam ngay theo roadmap:

1. tao benchmark spec skeleton trong repo
2. tao split registry / provenance scaffolding
3. tao comparator + control scaffolding cho tranche V5.6

## 4. Dieu hanh va quyet dinh

### Neu tranche benchmark/control-first clean

- tiep tuc sang implementation plan cho `RIFT-Net Lite`
- giu comparator contract va governance package

### Neu tranche benchmark/control-first lo ra blocker moi

- dung o muc scaffold
- cap nhat memo thay vi nhay sang claim/modeling

## 5. Claim boundary van giu nguyen

Du da `GO for code`, van phai giu:

- `claim-closed`
- `fail-closed` neu control package sau nay khong dat
- khong dien giai Gate 0 readiness nhu efficacy evidence

## 6. One-line Roadmap

Roadmap prospective hien tai la:

> contract da khoa -> Gate 0 signal-ready da xong -> GO cho benchmark/control-first
> implementation -> chi sau do moi xem xet tranche model cho A4 iEEG-assisted.
