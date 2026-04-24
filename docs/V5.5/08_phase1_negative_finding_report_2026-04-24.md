# Phase 1 Negative Finding Report

Ngay cap nhat: 2026-04-24

Pham vi: tai lieu rieng de ghi nhan negative finding cua nhanh Phase 1 final controls
theo dung tinh trung thuc khoa hoc, khong mo claim, khong thay doi runtime artifact,
va khong "cuu" run hien tai.

## 1. Muc dich

Tai lieu nay dung de:

1. ghi nhan ro rang negative finding hien tai;
2. tach negative finding khoi positive efficacy claim;
3. giup cap nhat bao cao/luan van ma khong dien giai vuot qua bang chung;
4. dat ra dieu kien neu sau nay muon mo mot nhanh prospective work moi.

## 2. Statement of Record

Ket luan chinh thuc cua nhanh nay:

- pipeline nhat quan;
- metric formula ambiguity da dong;
- `nuisance_shared_control` va `spatial_control` van fail hop le duoi locked thresholds;
- vi vay, bang chung hien tai **chua du de ho tro efficacy claim**.

## 3. Da xac lap duoc dieu gi

### 3.1 Pipeline nhat quan

Chuoi artifact hien tai da duoc refresh va dong bo:

- final dedicated controls run:
  - `20260423T161538578351Z`
- final controls run:
  - `20260423T165758332060Z`
- remediation audit run:
  - `20260423T170320725358Z`
- metric contract audit run:
  - `20260423T170705285760Z`

Ket qua governance:

- khong con artifact gap;
- khong thay leakage runtime;
- threshold runtime khop voi locked config;
- claim van dong.

### 3.2 Formula ambiguity da dong

Metric contract audit da xac nhan:

- `Relative formula locked = True`
- `Locked formula id = raw_ba_ratio`
- `Formula ambiguity detected = False`

Y nghia:

- failure hien tai khong con den tu metric-contract ambiguity.

### 3.3 Hai blocking controls van fail hop le

Blocking controls:

- `nuisance_shared_control`
- `spatial_control`

Theo artifact remediation audit va failure table:

- `nuisance_shared_control`
  - `balanced_accuracy = 0.5`
  - `relative_to_baseline = 0.997035`
  - fail hop le duoi `nuisance_relative_ceiling = 0.5`
- `spatial_control`
  - `balanced_accuracy = 0.501487`
  - `relative_to_baseline = 1.0`
  - fail hop le duoi `spatial_relative_ceiling = 0.67`

## 4. Negative Finding

Negative finding cua nhanh nay la:

> Mac du pipeline, artifact chain, formula contract, va governance da duoc lam sach,
> hai negative controls quan trong la `nuisance_shared_control` va `spatial_control`
> van khong dat locked thresholds. Do do, current Phase 1 artifact package chua du
> bang chung de ho tro efficacy claim.

Day la negative finding hop le va co gia tri, vi no duoc dat tren:

- artifact chain nhat quan;
- governance fail-closed;
- threshold lock ro rang;
- metric contract da dong;
- khong co bang chung bug trien khai ro rang trong pham vi da kiem tra.

## 5. Khong duoc dien giai thanh efficacy

Tai lieu nay khang dinh ro:

- ket qua hien tai **khong** chung minh decoder efficacy;
- ket qua hien tai **khong** chung minh A2d/A3/A4 efficacy;
- ket qua hien tai **khong** chung minh A4 superiority;
- ket qua hien tai **khong** chung minh full Phase 1 neural comparator performance.

No chi cho phep mot ket luan than trong:

> current evidence is governance-clean but not efficacy-supporting.

## 6. Gia tri cua negative finding

Negative finding nay co gia tri o 3 diem:

1. **Gia tri quy trinh**
   - cho thay pipeline co kha nang tu chan claim khong du bang chung.

2. **Gia tri phuong phap**
   - cho thay negative controls dang thuc su lam vai tro veto khi can.

3. **Gia tri bao cao**
   - cho phep viet limitation va implication mot cach trung thuc, khong can phai
     thao tac lai artifact da quan sat.

## 7. Final Reporting Rule

Quy tac bao cao chot:

- nhanh nay phai duoc ghi nhan la `fail-closed`;
- khong chay them notebook remediation/governance cho issue formula nay;
- khong doi threshold;
- khong doi formula de thay doi pass/fail;
- khong mo claim;
- khong trinh bay negative finding nay nhu bang chung efficacy.

## 8. Prospective Work Gate

Neu muon di tiep sau negative finding nay, thi chi duoc theo huong:

- `prospective work`
- khong nham "cuu" run hien tai
- khong nham reclassify artifact da fail

Muc tieu hop le duy nhat:

> tra loi cau hoi control design cho future runs co can revise hay khong.

## 9. Neu mo nhanh prospective work

Neu sau nay mo nhanh moi, quy tac bat buoc la:

1. bat dau bang **proposal docs-only**;
2. khong sua code/config runtime truoc;
3. khong doi threshold cho run hien tai;
4. khong doi formula cho run hien tai;
5. khong reclassify artifact da fail;
6. chi sau khi proposal docs-only duoc review moi xem xet co can patch prospective
   cho future runs hay khong.

## 10. One-line Negative Finding

Pipeline hien tai da nhat quan va metric formula ambiguity da dong, nhung
`nuisance_shared_control` va `spatial_control` van fail hop le; vi vay, current
Phase 1 evidence chua du de ho tro efficacy claim va nhanh nay phai duoc giu
o trang thai `fail-closed`.
