# Phase 1 Prospective iEEG-Assisted Proposal

Ngay cap nhat: 2026-04-24

Pham vi: proposal docs-only cho nhanh prospective tiep theo sau khi nhanh Phase 1
hien tai da duoc chot o trang thai `fail-closed` va `claim-closed`.

Tai lieu nay **khong** sua code, **khong** doi threshold, **khong** doi formula,
**khong** reclassify artifact da fail, va **khong** mo claim cho run hien tai.

## 1. Muc tieu cua proposal

Muc tieu cua nhanh prospective moi:

1. xac dinh lieu de tai co the kiem dinh mot cach hop le claim
   `iEEG-assisted for scalp EEG` trong cac run tuong lai hay khong;
2. khoa ro thanh phan nao trong pipeline moi thuc su duoc xem la
   `iEEG-assisted`;
3. dat truoc contract bang chung va gate prerequisites truoc khi cho phep bat ky
   sua doi runtime nao.

## 2. Diem xuat phat

Trang thai da khoa cua nhanh hien tai:

- `fail-closed`
- `claim-closed`
- formula ambiguity da dong
- artifact chain da consistency-checked
- `nuisance_shared_control` va `spatial_control` van la blockers hop le

He qua:

- run hien tai khong du de ho tro efficacy claim;
- run hien tai khong du de ho tro iEEG-assisted superiority claim;
- moi viec di tiep phai la **prospective work**, khong phai remediation de "cuu" run.

## 3. Claim target duoc de xuat

Claim target chinh neu mo nhanh prospective:

> `A4_privileged` vuot cac comparator scalp manh trong Phase 1 tren endpoint chinh,
> trong khi van giu train-time privileged discipline, scalp-only inference, controls,
> calibration, influence va reporting deu dat contract da khoa.

Claim target phu co the xem xet:

- `A3_distillation` co gia tri nhu mot teacher-assisted comparator trung gian;
- `A2d_riemannian` la comparator scalp manh, khong phai iEEG-assisted claim target.

Nguyen tac:

- neu muon chung minh `iEEG-assisted superiority`, muc tieu chinh nen la `A4_privileged`;
- `A3` co the giup dien giai co che, nhung khong nen la dich den cuoi cung cho claim manh.

## 4. Cau hoi khoa hoc can tra loi

Nhanh prospective phai tra loi ro 5 cau hoi:

1. real iEEG se duoc dua vao pipeline o dau?
2. iEEG tro giup scalp model theo co che nao:
   - distillation
   - privileged train-time branch
   - observability-constrained bridge
3. test-time inference co van scalp-only hay khong?
4. A4 co that su vuot cac comparator scalp manh tren endpoint chinh hay khong?
5. neu co gain, gain do co qua duoc controls/calibration/influence hay khong?

## 5. Pham vi ky thuat cua nhanh prospective

Nhanh moi chi hop le neu tach ro 3 lop:

### 5.1 Lop du lieu

- materialized EDF payloads
- materialized MAT/beamforming derivatives neu dung bridge
- subject/session/trial lock o muc signal-level
- channel/electrode alignment audit

### 5.2 Lop model

- A2/A2b/A2c/A2d la strong scalp comparators
- A3 la teacher/distillation comparator
- A4 la privileged comparator

### 5.3 Lop governance

- negative controls
- calibration package
- influence package
- final reporting
- claim-state closeout

## 6. Gate prerequisites bat buoc

Nhanh prospective khong duoc phep sang code/runtime truoc khi xac nhan cac dieu kien sau:

### 6.1 Gate 0 signal-level readiness

Can giai quyet cac blocker hien tai:

- `edf_payloads_not_materialized`
- `mat_derivatives_not_materialized`
- `cohort_lock_is_draft_until_signal_level_audit`

Khong co signal-level readiness thi khong co nen vung cho real iEEG-assisted branch.

### 6.2 iEEG entry-point contract

Phai ghi ro bang van ban:

- real iEEG duoc dung hay khong;
- neu co, dung o fold nao, stage nao;
- co duoc dung cho student fit hay teacher fit hay khong;
- co bat ky privileged output nao duoc di qua test-time inference hay khong.

Yeu cau bat buoc:

- test-time inference phai scalp-only;
- outer test subject khong duoc di vao privileged fit path.

### 6.3 Comparator evidence contract

Phai khoa truoc:

- primary endpoint: `memory_load_4_vs_8`
- split: `nested_leave_one_subject_out`
- primary metric: `balanced_accuracy`
- unit of inference: `subject_level_outer_fold`

Phai giu dung contract trong
`configs/phase1/final_claim_package.json`.

## 7. Bang chung toi thieu de ho tro claim

De claim `iEEG-assisted superiority` co the duoc xem xet o future runs, toi thieu phai co:

1. du full final comparators:
   - `A2`
   - `A2b`
   - `A2c_CORAL`
   - `A2d_riemannian`
   - `A3_distillation`
   - `A4_privileged`
2. `A4_privileged` vuot tat ca strong scalp comparators theo contract da khoa
3. final controls pass
4. calibration khong xau di qua nguong delta ECE da khoa
5. influence khong vuot ceiling va khong flip claim state
6. final reporting package complete
7. final claim-state closeout mo claim theo dung contract

Neu thieu bat ky muc nao o tren, claim superiority khong duoc mo.

## 8. Nhung gi khong duoc lam

Nhanh prospective bi cam:

- sua threshold cho run hien tai
- doi formula cho run hien tai
- reclassify artifact da fail
- su dung smoke metrics lam claim evidence
- dien giai scalp-proxy teacher thanh real iEEG teacher
- mo claim truoc khi controls/calibration/influence/reporting deu dat

## 9. De xuat trinh tu thuc hien

### Phase P1 - Du lieu va freeze readiness

1. materialize EDF/MAT payloads
2. rerun Gate 0 signal-level audit
3. khoa `cohort_lock.json` o muc signal-ready
4. ghi ro bridge/beamforming availability neu co dung

Exit criterion:

- Gate 0 khong con blocker payload/materialization cho nhanh moi

### Phase P2 - iEEG-assisted contract design

1. viet spec cho real iEEG teacher / privileged branch
2. xac dinh ro A3 va A4 dung real iEEG hay scalp proxy
3. khoa observability boundary
4. khoa test-time scalp-only rule

Exit criterion:

- co mot contract van ban ro rang, audit duoc, khong mo ho ve privileged path

### Phase P3 - Final comparator implementation proposal

1. lap danh sach artifact moi can co cho A3/A4 final
2. xac dinh runner nao can them hoac sua cho future runs
3. xac dinh test coverage moi can them
4. review risk leakage va influence

Exit criterion:

- co implementation plan docs-only, chua patch code

### Phase P4 - Decision gate

Sau khi hoan tat P1-P3 moi duoc quyet dinh:

- `go`: cho phep patch code prospective cho future runs
- `no-go`: giu nguyen de tai o muc negative finding + methodological contribution

## 10. Tieu chi go / no-go

### Dieu kien `go`

- Gate 0 signal-level da san sang
- real iEEG entry-point da duoc khoa ro
- claim contract cho A4 da ro
- ke hoach test/leakage/control da du
- khong co diem nao xung dot voi docs V5.5 va claim boundary hien tai

### Dieu kien `no-go`

- payload van chua materialize
- van con mo ho giua scalp-proxy va real iEEG teacher
- khong the audit duoc privileged path
- khong the dat mot contract ma khong lam suy yeu liem chinh khoa hoc

## 11. Deliverables docs-only de xuat

Neu tiep tuc, nhanh prospective nen tao toi thieu:

1. `phase1_ieeg_assisted_contract.md`
2. `phase1_a3_a4_real_teacher_design.md`
3. `phase1_signal_level_gate0_readiness.md`
4. `phase1_future_run_evidence_contract.md`
5. `phase1_go_no_go_decision_memo.md`

## 12. Danh gia tong hop

Nhanh prospective nay co y nghia neu muc tieu cua de tai la:

- khong chi bao cao negative finding;
- ma con muon kiem dinh dung nghia claim `iEEG-assisted for scalp EEG`.

Tuy nhien, run hien tai khong duoc dung de ho tro claim do.

Proposal nay chi tao mot duong di nghiem tuc cho future runs:

- khong pha vo record hien tai;
- khong vi pham integrity;
- khong nham cuu artifact da fail.

## 13. One-line Proposal

Buoc tiep theo hop le nhat neu muon theo duoi `iEEG-assisted superiority` la mo
mot nhanh prospective docs-only, dat `A4_privileged` lam claim target chinh, va
khoa truoc signal-level readiness, real iEEG entry-point, evidence contract, va
go/no-go gate truoc khi cho phep bat ky thay doi runtime nao.
