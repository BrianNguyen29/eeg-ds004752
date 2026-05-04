# V5.6 Repo Mapping and Execution Roadmap

Ngay cap nhat: 2026-04-24

Pham vi: mapping huong V5.6 vao repo hien tai va de xuat roadmap trien khai theo
tranche, dua tren:

- `docs/17_v55_to_v56_transition_lock_2026-04-24.md`
- `docs/18_v55_to_v56_transition_lock_manifest_2026-04-24.json`
- bo tai lieu `docs/V5.6/`
- Gate 0 run `artifacts/gate0/20260424T100159866284Z`

Tai lieu nay docs-only. No khong doi record V5.5 va khong mo efficacy claim.

## 1. Transition rule truoc khi map V5.6

Quy tac bat buoc truoc khi map:

- `docs/17` la ban dien giai khoa cho bao cao/chuyen huong;
- `docs/18` la manifest may doc duoc de giu source-of-truth;
- V5.5 duoc dong vai tro:
  - historical negative finding
  - methodological lesson
  - design motivation
- V5.5 khong duoc carry-over thanh positive support cho V5.6 claim.

He qua:

- V5.6 la huong moi, khong phai ban "remediation" cho V5.5;
- mainline moi la `NOST-Bench + RIFT-Net Lite`;
- benchmark/control-first dung truoc heavy modeling.

## 2. Tinh than V5.6 can giu

Tu bo V5.6:

1. **NOST-Bench** la dong gop chinh.
2. **RIFT-Net Lite** la primary model.
3. **RIFT-Mamba**, **Riemannian branch**, **RIFT-Bridge** la extensions co dieu kien.
4. **CRTG + statistics + control adequacy** la trung tam claim logic.
5. **Signal-level Gate 0** la dieu kien mo moi empirical branch.

Trang thai hien tai:

- dieu kien Gate 0 nay da dat.

## 3. Repo hien tai da co gi de tai su dung

Repo hien tai da co nhieu khoi co the tai su dung truc tiep:

### 3.1 Data / audit / gates

- `src/audit`
- `src/preprocess`
- `src/splits`
- `src/prereg`

### 3.2 Feature / control / evaluation / reporting

- `src/features`
- `src/controls`
- `src/evaluation`
- `src/calibration`
- `src/reporting`
- `src/artifacts`

### 3.3 Model / latent / teacher surfaces

- `src/models`
- `src/latent`
- `src/teacher`

### 3.4 Config surfaces

- `configs/data`
- `configs/preprocess`
- `configs/split`
- `configs/models`
- `configs/controls`
- `configs/gate1`
- `configs/gate2`
- `configs/eval`
- `configs/prereg`

### 3.5 Tests

- `tests/unit`

Ket luan:

- repo hien tai **khong can doi layout lon** de vao V5.6;
- V5.6 co the duoc map vao repo nay bang cach them layer configs/modules moi.

## 4. Mapping V5.6 vao repo hien tai

### 4.1 Data layer va Signal-Level Gate 0

Map vao repo:

- code owner:
  - `src/audit`
  - `src/preprocess`
- config owner:
  - `configs/data`
  - `configs/preprocess`
- artifact owner:
  - `artifacts/gate0`

Trang thai:

- `Completed for readiness`
- Gate 0 da `signal_audit_ready`

### 4.2 Split registry va feature provenance

Map vao repo:

- code owner:
  - `src/splits`
  - `src/features`
  - mot phan `src/artifacts`
- config owner:
  - `configs/split`
  - `configs/preprocess`

Trang thai:

- la tranche implementation tiep theo

### 4.3 Controls / anti-teachers / control adequacy

Map vao repo:

- code owner:
  - `src/controls`
  - `src/evaluation`
  - mot phan `src/teacher`
- config owner:
  - `configs/controls`
  - `configs/gate2`

Trang thai:

- la tranche implementation tiep theo
- bai hoc tu V5.5 se duoc dua vao contract benchmark, khong dung de reclassify record cu

### 4.4 CRTG statistics va claim-state

Map vao repo:

- code owner:
  - `src/evaluation`
  - `src/reporting`
  - co the them schema/artifact helpers trong `src/artifacts`
- config owner:
  - `configs/eval`
  - `configs/gate1`
  - `configs/gate2`

Trang thai:

- can bo sung ro rang trong tranche benchmark/control-first

### 4.5 RIFT-Net Lite primary model

Map vao repo:

- code owner:
  - `src/models`
  - `src/teacher`
  - `src/latent`
- config owner:
  - `configs/models`

Trang thai:

- chua phai tranche ngay lap tuc
- chi mo sau benchmark/control scaffolding

## 5. Roadmap trien khai de xuat

### Tranche 0 - Transition freeze

Trang thai:

- **Da xong**

### Tranche 1 - Operational evidence only

Muc tieu:

- payload materialization
- full-cohort signal-level Gate 0
- signal-ready cohort lock

Trang thai:

- **Da xong** voi run `20260424T100159866284Z`

### Tranche 2 - Benchmark skeleton

Muc tieu:

1. them config skeleton cho:
   - `control_tiers`
   - `anti_teacher_generators`
   - `nost_bench_prereg_bundle`
   - `rift_net_lite`
2. them evaluation skeleton cho:
   - `crtg.py`
   - `maxT_permutation.py`
3. them artifact schemas cho:
   - `teacher_gate_table`
   - `control_results`
   - `crtg_bootstrap`
   - `claim_state_v2`
4. them policy tests cho:
   - signal-ready gate requirement
   - control adequacy blocker
   - test-time scalp-only

Trang thai:

- **Da co scaffold implementation**
- Da co config scaffold, module scaffold, artifact writers va CLI scaffold-only.
- Chua co model training, comparator execution hay efficacy metric.
- Da bo sung Tranche 2.1 implementation de khoa split registry va populate
  feature provenance sau khi scaffold artifact pass review.
- Da bo sung Tranche 2.2 implementation de record feature-matrix plan sau khi
  split lock/provenance pass, van khong materialize feature values.
- Da bo sung Tranche 2.3 implementation de record feature-matrix leakage-audit
  plan truoc khi materialize feature values hoac chay comparator.
- Da bo sung Tranche 2.4 implementation de record feature-matrix materializer
  skeleton, van chua doc EDF hoac write feature values.
- Buoc tiep theo van la review artifact theo tung tranche; khong chuyen sang
  comparator/model execution neu split lock va feature provenance chua pass.

### Tranche 3 - Baseline leaderboard

Chi mo neu Tranche 2 on.

Muc tieu:

1. split registry
2. feature provenance
3. baseline runs
4. control generators
5. raw BA + CRTG reporting

### Tranche 4 - RIFT-Net Lite primary model

Chi mo neu Tranche 3 on.

Muc tieu:

1. residual teacher gate
2. anti-circularity policy tests
3. training logs
4. CRTG evaluation
5. calibration + influence
6. claim-state closeout

### Tranche 5 - Conditional extensions

Chi mo neu RIFT-Net Lite cho thay co ly do.

Extensions:

- RIFT-Mamba
- Riemannian branch
- RIFT-Bridge

## 6. De xuat buoc tiep theo

Buoc tiep theo tot nhat trong repo hien tai sau leakage-audit plan:

1. **khong quay lai materialization pilot**
2. **khong mo efficacy claim**
3. **chay Tranche 2.4 feature matrix materializer skeleton**
4. **review skeleton artifact truoc khi implement real materializer/comparator/model execution**

Lenh du kien:

```bash
bash bootstrap/run_v56_feature_matrix_materializer_skeleton.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_leakage_audit_plan/latest.txt \
  /content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_materializer_skeleton
```

Ket qua can review:

- `artifacts/v56_feature_matrix_materializer_skeleton/latest.txt`

Decision gate sau review:

- neu materializer skeleton dung contract va claim-closed:
  chuyen sang real scalp feature matrix materializer;
- neu artifact thieu source/link/status: sua scaffold, khong chay model;
- khong mo Tranche 3 neu chua co review materializer skeleton.

## 7. One-line Mapping Decision

V5.6 nen duoc map vao repo hien tai theo huong benchmark-first, control-first va
tranche-based; sau khi Gate 0 da signal-ready, tranche tiep theo la
benchmark/control scaffolding, khong phai heavy model implementation.
