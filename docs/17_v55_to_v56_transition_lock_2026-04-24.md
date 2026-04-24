# V5.5 to V5.6 Transition Lock

Ngay cap nhat: 2026-04-24

Pham vi: khoa record V5.5 va ket qua hien tai truoc khi chuyen sang huong V5.6.

Tai lieu nay duoc lap de:

1. khoa "su that lich su" cua nhanh V5.5;
2. ngan viec dien giai lai V5.5 sau khi da thay huong;
3. tach ro:
   - cai gi da duoc xac lap;
   - cai gi da fail;
   - bai hoc nao duoc phep mang sang V5.6;
4. giu claim boundary ro rang khi bat dau NOST-Bench / RIFT-Net / RIFT-Mamba.

## 1. Source-of-truth cua record V5.5

Record V5.5 duoc khoa dua tren:

- `docs/06_bao_cao_tien_do_ket_qua_va_claim_boundary_2026-04-24.md`
- `docs/07_phase1_controls_technical_conclusion_2026-04-24.md`
- `docs/08_phase1_negative_finding_report_2026-04-24.md`
- `docs/10_phase1_consistency_audit_report_2026-04-24.md`
- `docs/16_phase1_prospective_execution_roadmap_2026-04-24.md`

Va cac run da review:

- final dedicated controls:
  - `20260423T161538578351Z`
- final controls:
  - `20260423T165758332060Z`
- final controls remediation audit:
  - `20260423T170320725358Z`
- final controls metric contract audit:
  - `20260423T170705285760Z`

## 2. V5.5 record da khoa

### 2.1 Trang thai chot

Trang thai V5.5 duoc khoa la:

- `fail-closed`
- `claim-closed`
- `formula ambiguity closed`
- `consistency-checked`

### 2.2 Formula contract da khoa

Metric formula contract duoc khoa la:

- `raw_ba_ratio`
- definition:
  - `control_balanced_accuracy / baseline_balanced_accuracy`

Trang thai:

- `Relative formula locked = true`
- `Formula ambiguity detected = false`

### 2.3 Blockers da khoa

Hai blockers controls cua record V5.5 la:

- `nuisance_shared_control`
- `spatial_control`

Khong duoc phep dien giai lai hai blocker nay thanh:

- artifact gap
- formula ambiguity
- threshold mismatch
- leakage bug

trong khi chua co bang chung ky thuat moi doc lap.

### 2.4 Ket qua duoc phep ket luan

Duoc phep ket luan:

- pipeline/governance da nhat quan;
- artifact chain da duoc review;
- current runtime formula da duoc khoa;
- final controls run da day du artifact;
- failures con lai la substantive failures hop le trong record hien tai.

### 2.5 Ket qua khong duoc phep ket luan

Khong duoc phep ket luan:

- decoder efficacy
- A2d efficacy
- A3 efficacy
- A4 efficacy
- A4 superiority
- iEEG-assisted superiority
- full Phase 1 neural comparator success

## 3. Bai hoc duoc mang sang V5.6

V5.6 duoc phep mang sang cac bai hoc sau:

1. raw performance khong du de mo claim;
2. controls phai la core benchmark track, khong phai phu luc;
3. control adequacy phai la claim blocker, khong phai co che loai control hau nghiem;
4. signal-level Gate 0 readiness la dieu kien mo moi empirical branch;
5. smoke/proxy khong duoc dien giai thanh claim-bearing evidence;
6. benchmark-first va claim-state discipline la huong dung hon model-first rescue.

## 4. Thong tin duoc dong bang de tham chieu trong V5.6

Khi sang V5.6, chi duoc tham chieu V5.5 o 3 vai tro:

### 4.1 Historical empirical record

V5.5 la negative finding da audit sach.

### 4.2 Methodological lesson

V5.5 cho thay:

- governance fail-closed la can thiet;
- nuisance/spatial controls co suc veto that su;
- claim boundary phai duoc khoa bang artifact va policy tests.

### 4.3 Design motivation

V5.6 NOST-Bench co the dung V5.5 lam dong luc de:

- chuyen sang benchmark control-first;
- dua CRTG va control adequacy vao trung tam;
- uu tien signal-ready cohort truoc heavy modeling.

## 5. Thong tin khong duoc carry-over theo cach gay nham lan

Khong duoc carry-over V5.5 theo cac cach sau:

1. dung smoke/proxy artifacts de support claim moi;
2. dung current blocked run nhu bang chung iEEG-assisted gain;
3. xem `A4` cua V5.5 la bang chung superiority dang cho xac nhan;
4. xem scalp-proxy teacher la `real iEEG teacher`;
5. mo lai formula/governance remediation chain de "lam sach" V5.5 truoc khi sang V5.6.

## 6. Transition policy

Khi bat dau V5.6:

- V5.5 duoc dong vai tro empirical record;
- V5.5 khong con la mainline claim path;
- V5.6 la huong moi;
- moi empirical code path moi phai obey:
  - signal-level Gate 0
  - controls-first benchmark logic
  - CRTG + statistics
  - test-time scalp-only rule

## 7. Dieu can khoa truoc khi bat dau V5.6 implementation

Truoc khi bat dau implementation theo V5.6, can chap nhan ro:

1. V5.5 positive efficacy path da fail;
2. V5.5 khong can them remediation de "cai thien" record;
3. V5.6 duoc justify boi bai hoc tu V5.5, khong phai boi positive claim dang cho mo;
4. neu V5.6 tiep tuc bi data-blocked, van co duong Scenario D hop le.

## 8. One-line Transition Lock

V5.5 duoc khoa thanh mot negative finding da audit sach, fail-closed va claim-closed;
V5.6 chi duoc phep ke thua bai hoc phuong phap va claim discipline tu record nay,
khong duoc ke thua bat ky positive efficacy interpretation nao.
