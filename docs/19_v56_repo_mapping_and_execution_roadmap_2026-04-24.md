# V5.6 Repo Mapping and Execution Roadmap

Ngay cap nhat: 2026-04-24

Pham vi: mapping huong V5.6 vao repo hien tai va de xuat roadmap trien khai theo
tranche, dua tren:

- `docs/17_v55_to_v56_transition_lock_2026-04-24.md`
- `docs/18_v55_to_v56_transition_lock_manifest_2026-04-24.json`
- bo tai lieu `docs/V5.6/`

Tai lieu nay docs-only. No khong doi record V5.5 va chua mo code implementation
moi cho V5.6.

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
6. Neu data van blocked, **Scenario D** la duong ra hop le.

## 3. Repo hien tai da co gi de tai su dung

Repo hien tai da co nhieu khoi co the tai su dung truc tiep:

### 3.1 Data / audit / gates

- `src/audit`
- `src/preprocess`
- `src/splits`
- `src/simulation`
- `src/synthetic`
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
- V5.6 co the duoc map vao repo nay bang cach them layer configs/modules moi,
  thay vi doi sang mot repo moi ten `nost_bench/`.

## 4. Mapping V5.6 vao repo hien tai

### 4.1 Data layer va Signal-Level Gate 0

V5.6 concept:

- data materialization
- signal-level Gate 0
- signal-ready cohort lock

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

- scaffold da co;
- blocker hien tai la payload materialization.

### 4.2 Split registry va feature provenance

V5.6 concept:

- split registry
- feature provenance
- benchmark track discipline

Map vao repo:

- code owner:
  - `src/splits`
  - `src/features`
  - mot phan `src/artifacts`
- config owner:
  - `configs/split`
  - `configs/preprocess`

Trang thai:

- phan split/provenance da co nen tang tu V5.5;
- can doi ten/contract de phu hop NOST-Bench tracks.

### 4.3 Controls / anti-teachers / control adequacy

V5.6 concept:

- control tiers
- anti-teachers
- control adequacy as claim blocker

Map vao repo:

- code owner:
  - `src/controls`
  - `src/evaluation`
  - mot phan `src/teacher`
- config owner:
  - `configs/controls`
  - `configs/gate2`

Trang thai:

- V5.5 da co kinh nghiem thuc te ve nuisance/spatial blocks;
- can chuyen hoa bai hoc do thanh benchmark contract trung tam cua V5.6.

### 4.4 CRTG statistics va claim-state

V5.6 concept:

- CRTG
- bootstrap CI
- max-T permutation
- claim-state taxonomy moi

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

- evaluation surface da co;
- nhung `CRTG` va `max-T permutation` can duoc bo sung ro rang, khong nen tron vao
  cac package V5.5 cu.

### 4.5 RIFT-Net Lite primary model

V5.6 concept:

- compact primary model
- residual teacher gate
- anti-circularity

Map vao repo:

- code owner:
  - `src/models`
  - `src/teacher`
  - `src/latent` neu can latent surfaces
- config owner:
  - `configs/models`

Trang thai:

- chua nen implement ngay;
- chi mo sau khi data/materialization/Gate 0 signal-ready da pass.

### 4.6 Optional extensions

V5.6 concept:

- RIFT-Mamba
- Riemannian branch
- RIFT-Bridge

Map vao repo:

- code owner:
  - `src/models`
  - `src/evaluation`
  - `src/features`
- config owner:
  - `configs/models`
  - `configs/eval`

Trang thai:

- tuyet doi khong la implementation tranche dau tien.

## 5. Roadmap trien khai de xuat

### Tranche 0 - Transition freeze

Muc tieu:

- khoa V5.5
- khoa transition policy
- khoa V5.6 mainline direction

Tai lieu:

- `docs/17`
- `docs/18`

Trang thai:

- **Da xong**

### Tranche 1 - Operational evidence only

Muc tieu:

- khong heavy modeling
- chi xac nhan data/materialization/signal-level readiness

Cong viec:

1. materialize sample payload
2. rerun Gate 0 voi `--include-signal`
3. tao artifact Gate 0 signal-level moi
4. khoa signal-ready cohort neu du dieu kien
5. cap nhat readiness / go-no-go docs

Tai lieu dieu hanh:

- `docs/12`
- `docs/14`
- `docs/15`
- `docs/16`

Exit gate:

- Gate 0 signal-level clean hoac blocker ro rang

### Tranche 2 - Benchmark skeleton

Chi mo neu Tranche 1 pass.

Muc tieu:

- dua V5.6 vao repo o muc benchmark-first skeleton

Cong viec:

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
   - `claim_state v2`
4. them policy tests cho:
   - signal-ready gate requirement
   - control adequacy blocker
   - test-time scalp-only

Exit gate:

- repo co benchmark skeleton v2.0 nhung chua heavy training

### Tranche 3 - Baseline leaderboard

Chi mo neu Tranche 2 on.

Muc tieu:

- tao baseline leaderboard control-aware

Cong viec:

1. split registry
2. feature provenance
3. baseline runs
4. control generators
5. raw BA + CRTG reporting

Exit gate:

- co baseline package theo NOST-Bench

### Tranche 4 - RIFT-Net Lite primary model

Chi mo neu Tranche 3 on.

Muc tieu:

- implement va danh gia `RIFT-Net Lite`

Cong viec:

1. residual teacher gate
2. anti-circularity policy tests
3. training logs
4. CRTG evaluation
5. calibration + influence
6. claim-state closeout

Exit gate:

- co ket qua claim-disciplined cho primary model

### Tranche 5 - Conditional extensions

Chi mo neu RIFT-Net Lite cho thay co ly do.

Extensions:

- RIFT-Mamba
- Riemannian branch
- RIFT-Bridge

Rule:

- chi promote neu CRTG/cali/influence/controls ung ho.

## 6. Scenario D mapping

Neu Tranche 1 van blocked vi data/materialization, map theo `Scenario D`:

1. khong mo heavy modeling
2. chuyen output sang:
   - benchmark specification paper
   - simulation validation paper
   - data-readiness report
   - reusable scaffold

Y nghia:

- V5.6 van co duong ra hop le;
- de tai khong bi ep phai co empirical gain moi duoc xem la thanh cong.

## 7. De xuat buoc tiep theo

Buoc tiep theo tot nhat trong repo hien tai:

1. **khong code model**
2. **thuc hien Tranche 1**
3. dung chinh duong van hanh trong `README.md`:
   - `bootstrap/get_data_colab.sh`
   - `python -m src.cli audit ... --include-signal`

Neu sample payload signal-audit pass:

- mo rong sang materialization theo subject
- update Gate 0 run
- review lai `GO/NO-GO`

Neu sample payload van blocked:

- dong mainline empirical branch
- chuyen sang `Scenario D`

## 8. One-line Mapping Decision

V5.6 nen duoc map vao repo hien tai theo huong benchmark-first, control-first va
tranche-based; tranche dau tien phai la data materialization + signal-level Gate 0,
khong phai RIFT-Net Lite training hay heavy model implementation.
