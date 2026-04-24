# Phase 1 Consistency Audit TODO

Ngay cap nhat: 2026-04-24

Muc tieu: kiem tra docs, notebook Colab, artifact lineage, code/config, va test
coverage de xac minh khong con bug, mismatch, hay dien giai sai trong nhanh
Phase 1 final controls hien tai.

## Phase 0 - Source of Truth Lock

- [x] Chot docs `06`, `07`, `08` la nguon dien giai chinh thuc.
- [x] Chot trang thai nhanh nay la `fail-closed` va `claim-closed`.
- [x] Xac nhan khong chay them notebook remediation/governance cho issue formula nay.

## Phase 1 - Docs Audit

- [x] Doi chieu `docs/03`, `docs/04`, `docs/05`, `docs/06`, `docs/07`, `docs/08`.
- [x] Kiem tra run ids co thong nhat.
- [x] Kiem tra blocking controls co thong nhat.
- [x] Kiem tra ket luan ve formula ambiguity da dong.
- [x] Kiem tra claim boundary va negative finding co thong nhat.

## Phase 2 - Colab Notebook Audit

- [x] Kiem tra notebook `28`.
- [x] Kiem tra notebook `32`.
- [x] Kiem tra notebook `35`.
- [x] Kiem tra notebook `36`.
- [x] Kiem tra notebook `37`.
- [x] Xac nhan khong con placeholder/run pin obsolete/assert cu.

## Phase 3 - Artifact Lineage Audit

- [x] Dung chuoi phu thuoc `32 -> 28 -> 35 -> 36 -> 37`.
- [x] Xac nhan notebook downstream dung run upstream da review.
- [x] Xac nhan remediation audit va metric contract audit dong bo voi final controls run moi.
- [x] Xac nhan artifact chain duoc governance-clean.

## Phase 4 - Code/Config Contract Audit

- [x] Doi chieu `src/phase1/final_controls.py`.
- [x] Doi chieu `src/phase1/final_dedicated_controls.py`.
- [x] Doi chieu `src/phase1/final_controls_metric_contract_audit.py`.
- [x] Doi chieu `configs/phase1/final_controls.json`.
- [x] Doi chieu `configs/phase1/final_dedicated_controls.json`.
- [x] Doi chieu `configs/gate2/synthetic_validation.json`.
- [x] Xac nhan threshold, formula, va claim boundary khong drift.

## Phase 5 - Test Coverage Audit

- [x] Kiem tra test unit cho dedicated controls.
- [x] Kiem tra test unit cho remediation audit.
- [x] Kiem tra test unit cho metric contract audit.
- [x] Kiem tra test unit cho final controls propagation.
- [x] Xac dinh neu con test gap nao can ghi nhan.

## Phase 6 - Mismatch Register va Ket luan

- [x] Lap danh sach mismatch neu co.
- [x] Phan loai mismatch theo muc do.
- [x] Chot ket luan:
  - clean and consistent; hoac
  - con mismatch can sua.
- [x] De xuat buoc tiep theo.

## Working Status

- Trang thai hien tai: `completed`
- Phase dang thuc hien: `Phase 6 - Hoan tat`

## Ghi chu tam thoi

- Phase 1 khong phat hien mismatch critical trong docs `06`, `07`, `08`.
- `docs/05` la tai lieu proposal/lich su cho trang thai formula ambiguity truoc khi dong,
  khong nen dung lam source-of-truth cho trang thai hien tai.
- Phase 2 phat hien 3 notebook pin mismatch:
  - `35` con pin final-controls run cu `20260422T155750203410Z`;
  - `36` chua pin explicit remediation/dedicated run da review;
  - `37` con pin metric-contract audit run cu `20260423T162755188322Z`.
- Ca 3 mismatch nay da duoc sua trong repo.
- Phase 3 xac nhan lineage da dong bo:
  - `32` -> dedicated controls run `20260423T161538578351Z`
  - `28` -> final controls run `20260423T165758332060Z`
  - `35` -> remediation audit run `20260423T170320725358Z`
  - `36` -> metric-contract audit run `20260423T170705285760Z`
  - `37` -> held-closeout tren metric-contract audit run da review.
- Phase 4 khong phat hien config drift hay contract drift:
  - `raw_ba_ratio` thong nhat giua config, runner, va audit;
  - threshold sources van khoa ve `configs/gate2/synthetic_validation.json`;
  - final controls van propagate `dedicated_final_control_suite_not_passed` va
    `required_final_control_results_missing` dung logic;
  - claim boundary van duoc khoa `claim_ready = false`.
- Phase 5: da chay targeted unit tests cho:
  - `test_phase1_final_dedicated_controls`
  - `test_phase1_final_controls`
  - `test_phase1_final_controls_remediation_audit`
  - `test_phase1_final_controls_metric_contract_audit`
  -> `Ran 12 tests ... OK`
- Test gap con lai:
  - notebook pin values va closeout text khong duoc unit-test tu dong;
  - phan nay hien duoc bao phu bang audit notebook thu cong.

## Mismatch Register

### Da phat hien va da sua

1. `P1` - Notebook 35 pin final-controls run cu
   - File: `notebooks/35_colab_phase1_final_controls_remediation_audit.ipynb`
   - Van de: con pin `20260422T155750203410Z` thay vi run da review `20260423T165758332060Z`
   - Trang thai: da sua

2. `P1` - Notebook 36 khong pin explicit reviewed runs
   - File: `notebooks/36_colab_phase1_final_controls_metric_contract_audit.ipynb`
   - Van de: de `None` cho remediation audit run va dedicated controls run
   - Trang thai: da sua bang explicit pins

3. `P1` - Notebook 37 pin metric-contract audit run cu
   - File: `notebooks/37_colab_phase1_final_controls_metric_formula_revision_plan.ipynb`
   - Van de: con pin `20260423T162755188322Z` thay vi run da review `20260423T170705285760Z`
   - Trang thai: da sua

### Khong coi la mismatch critical

1. `P3` - `docs/05_metric_formula_contract_revision_proposal_2026-04-23.md`
   - La tai lieu proposal/lich su cho trang thai formula ambiguity truoc khi dong
   - Khong dung lam source-of-truth cho trang thai hien tai

2. `P3` - local export directory va local docs untracked
   - `20260423T170320725358Z-20260423T172013Z-3-001/`
   - `docs/03_kiem_tra_tuan_tu_2026-04-23.md`
   - `docs/04_doc_colab_status_2026-04-23.md`
   - Khong anh huong runtime hay claim boundary
