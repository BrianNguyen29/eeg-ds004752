# Phase 1 iEEG-Assisted Contract

Ngay cap nhat: 2026-04-24

Pham vi: tai lieu docs-only de dinh nghia ro `iEEG-assisted` trong de tai nay co
nghia ky thuat gi, vao pipeline o dau, va bi rang buoc boi nhung quy tac nao.

Tai lieu nay khong cho phep sua code, khong mo claim, va khong duoc dung de
reclassify artifact hien tai.

## 1. Muc tieu

Tai lieu nay khoa ro:

1. khi nao mot nhanh duoc phep goi la `iEEG-assisted`;
2. real iEEG duoc dung o dau trong A3/A4;
3. dieu gi duoc phep o train-time;
4. dieu gi bi cam o test-time;
5. bang chung toi thieu nao can co de ho tro claim trong future runs.

## 2. Dinh nghia lam viec

Trong boi canh de tai nay, `iEEG-assisted for scalp EEG` chi nen duoc dung khi:

- thong tin co nguon goc tu real iEEG hoac bridge tuong ung thuc su tham gia vao
  train-time pipeline;
- thong tin do giup huong dan hoc cho scalp model;
- nhung test-time inference van scalp-only;
- va privileged path do duoc audit duoc, lock duoc, va bi rang buoc boi controls.

Neu chi dung:

- scalp proxy teacher
- synthetic proxy
- internal numpy privileged proxy

thi khong duoc goi la bang chung `iEEG-assisted` theo nghia claim-bearing.

## 3. Tach bach cac thanh phan

### 3.1 Khong duoc nham lan

Khong duoc nham lan giua:

1. `scalp proxy teacher`
2. `real iEEG teacher`
3. `privileged train-time branch`
4. `test-time decoder`

Run hien tai co the xac lap governance cho (1), nhung chua xac lap claim cho (2) va (3).

### 3.2 A3 va A4 co vai tro gi

- `A3_distillation`: comparator trung gian teacher/student
- `A4_privileged`: comparator claim-target manh nhat cho nhanh iEEG-assisted

Neu muon claim superiority, dich den chinh nen la:

> `A4_privileged` vuot tat ca strong scalp comparators duoi contract da khoa.

## 4. Contract cho real iEEG

De mot future run duoc xem la `real iEEG-assisted`, phai dat ca 4 dieu kien sau:

1. real iEEG payload duoc materialize va audit o muc signal-level
2. real iEEG chi di vao train-time path da duoc mo ta ro
3. khong co privileged/iEEG output nao duoc dung o test-time inference
4. artifact audit co the chi ro fold nao, subject nao, stage nao da dung iEEG

## 5. Train-time contract

Duoc phep o train-time:

- fit teacher bang real iEEG neu duoc contract cho phep
- fit privileged branch bang real iEEG/bridge neu duoc contract cho phep
- distillation tu teacher sang scalp student
- observability-constrained transfer neu duoc mo ta ro

Khong duoc phep o train-time:

- dung outer test subject trong teacher fit
- dung outer test subject trong privileged representation fit
- dung teacher path khong audit duoc provenance

## 6. Test-time contract

Bat buoc:

- test-time inference phai scalp-only
- khong real iEEG inputs
- khong bridge outputs dung de bo sung inference
- khong teacher outputs dung truc tiep o test time

Noi cach khac:

> iEEG chi duoc giup hoc; khong duoc giup suy luan tren mau test.

## 7. Comparator evidence contract

Future run chi co the duoc xem xet claim neu:

- endpoint la `memory_load_4_vs_8`
- split la `nested_leave_one_subject_out`
- primary metric la `balanced_accuracy`
- unit of inference la `subject_level_outer_fold`

Va bo comparator toi thieu phai co:

- `A2`
- `A2b`
- `A2c_CORAL`
- `A2d_riemannian`
- `A3_distillation`
- `A4_privileged`

## 8. Claim target contract

Claim manh nhat cho nhanh nay:

> `A4_privileged` vuot cac comparator scalp manh tren endpoint chinh, trong khi
> controls, calibration, influence, va reporting deu dat contract da khoa.

De claim nay hop le, can dong thoi co:

1. final comparator artifacts day du
2. final controls pass
3. final calibration pass
4. final influence pass
5. final reporting package complete
6. claim-state closeout mo claim hop le

## 9. Controls contract

Nhanh iEEG-assisted khong duoc mo claim neu:

- `nuisance_shared_control` fail
- `spatial_control` fail
- shuffled/time-shifted teacher controls fail

Ly do:

- negative controls chinh la co che veto de chan pseudo-gain.

## 10. Calibration va influence contract

Khong duoc coi co superiority neu:

- calibration xau di vuot delta ECE da khoa
- influence vuot ceiling
- leave-one-subject-out co the flip claim state

Dieu nay rat quan trong cho bai toan nho mau, subject heterogeneity cao.

## 11. Risk register

### Rui ro 1 - Nham lan proxy voi real iEEG

Neu teacher chi la scalp proxy ma van dien giai thanh iEEG-assisted, claim se sai ban chat.

### Rui ro 2 - Leakage qua privileged path

Neu outer test subject di vao teacher/privileged fit, claim mat gia tri.

### Rui ro 3 - Privileged path lo test-time

Neu privileged outputs di vao inference, claim khong con la scalp-only.

### Rui ro 4 - Raw gain nhung khong qua controls

Neu A4 tang metric thuan nhung negative controls/calibration/influence veto, claim khong duoc mo.

## 12. De xuat artifact moi cho future runs

Neu sau nay code prospective duoc phep, nen co them artifact contract cho:

1. `real_ieeg_teacher_manifest.json`
2. `privileged_path_audit.json`
3. `test_time_scalp_only_audit.json`
4. `ieeg_to_scalp_observability_contract.json`
5. `a4_privileged_claim_evidence_table.json`

## 13. Decision rule truoc khi code

Khong duoc patch code prospective neu chua co:

- Gate 0 signal-level readiness
- real iEEG entry-point contract
- test-time scalp-only contract
- risk register va artifact plan cho privileged path

## 14. One-line Contract

Trong de tai nay, `iEEG-assisted for scalp EEG` chi duoc xem la mot claim hop le
khi real iEEG tham gia o train-time path da duoc audit ro rang, test-time inference
van scalp-only, va A4 vuot cac comparator scalp manh trong khi van qua duoc toan bo
controls, calibration, influence, va reporting contracts.
