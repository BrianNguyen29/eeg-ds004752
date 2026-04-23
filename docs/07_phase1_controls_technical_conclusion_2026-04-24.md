# Phase 1 Controls Technical Conclusion

Ngay cap nhat: 2026-04-24

Pham vi: ghi nhan ket luan ky thuat sau khi doi chieu artifact remediation audit,
artifact dedicated controls, source code runner, config threshold, va unit tests
cho hai blocking controls:

- `nuisance_shared_control`
- `spatial_control`

Tai lieu nay khong mo claim, khong thay doi code/config runtime, khong doi threshold,
khong doi formula, va khong phan loai lai artifact da fail.

## 1. Cau hoi danh gia

Cau hoi can tra loi:

> Failure hien tai cua `nuisance_shared_control` va `spatial_control` co cho thay
> mot bug trien khai ro rang hay day la negative finding hop le duoi contract da khoa?

## 2. Nguon da doi chieu

### 2.1 Artifact runs

- Final dedicated controls run:
  - `/content/drive/MyDrive/eeg-ds004752/artifacts/phase1_final_dedicated_controls/20260423T161538578351Z`
- Final controls run:
  - `/content/drive/MyDrive/eeg-ds004752/artifacts/phase1_final_controls/20260423T165758332060Z`
- Final controls remediation audit run:
  - `/content/drive/MyDrive/eeg-ds004752/artifacts/phase1_final_controls_remediation_audit/20260423T170320725358Z`
- Final controls metric contract audit run:
  - `/content/drive/MyDrive/eeg-ds004752/artifacts/phase1_final_controls_metric_contract_audit/20260423T170705285760Z`

### 2.2 Local export duoc kiem tra

- `D:\WorkSpace\EEG\eeg-ds004752\20260423T170320725358Z-20260423T172013Z-3-001`

### 2.3 Source code va config

- `src/phase1/final_dedicated_controls.py`
- `configs/phase1/final_dedicated_controls.json`
- `configs/gate2/synthetic_validation.json`
- `tests/unit/test_phase1_final_dedicated_controls.py`

## 3. Phat hien chinh

### 3.1 Khong con artifact gap

Remediation audit cho thay:

- `all_required_controls_present = true`
- `claim_ready = false`
- `claims_opened = false`

Y nghia:

- final controls chain da co du artifact can thiet;
- failure hien tai khong con do thieu ket qua.

### 3.2 Khong thay leakage signal o dedicated controls

Implementation review/remediation audit cho thay:

- `runtime_leakage_detected = false`
- `teacher_threshold_path_mismatch_suspected = false`

Source code cung phu hop boundary nay:

- nuisance control fit tren `training_subjects_only_metadata_nuisance_probe`
- spatial control fit tren training subjects only
- leakage audit check `no_outer_test_subject_in_any_fit`

Y nghia:

- chua thay dau hieu bug leakage hay su dung outer-test subject cho fit.

### 3.3 Threshold runtime khop voi locked config

Threshold source review cho thay cac nguong chinh khop lock tu Gate 2:

- `nuisance_relative_ceiling = 0.50`
- `nuisance_absolute_ceiling = 0.02`
- `spatial_relative_ceiling = 0.67`

Teacher thresholds cung khop.

Y nghia:

- chua thay dau hieu threshold drift hoac config mismatch la nguyen nhan gay fail.

### 3.4 Metric formula ambiguity da dong

Metric contract audit da xac nhan:

- `Relative formula locked = true`
- `Locked formula id = raw_ba_ratio`
- `Formula ambiguity detected = false`

Y nghia:

- failure hien tai khong con den tu ambiguity contract ve `relative_to_baseline`.

## 4. Doi chieu source code

### 4.1 Nuisance control

Trong `src/phase1/final_dedicated_controls.py`:

- metadata duoc dung la:
  - `session_id`
  - `trial_id`
- `relative_to_baseline` duoc tinh tu:
  - `control_balanced_accuracy / baseline_balanced_accuracy`
- pass chi xay ra khi dong thoi:
  - `relative_to_baseline <= nuisance_relative_ceiling`
  - `absolute_gain_over_chance <= nuisance_absolute_ceiling`
  - leakage audit pass

### 4.2 Spatial control

Trong `src/phase1/final_dedicated_controls.py`:

- feature rows duoc permute theo `reverse_channel_order_within_band`
- `relative_to_baseline` duoc tinh theo cung contract `raw_ba_ratio`
- pass khi:
  - `relative_to_baseline <= spatial_relative_ceiling`
  - leakage audit pass

### 4.3 Relative metric contract

Config dedicated controls khoa ro:

- `formula_id = raw_ba_ratio`
- `definition = control_balanced_accuracy / baseline_balanced_accuracy`
- `thresholds_changed = false`
- `claims_opened = false`

Unit tests hien co cung bao ve:

- formula metadata duoc ghi vao artifact
- formula khac `raw_ba_ratio` bi reject

## 5. Doi chieu voi ket qua quan sat

Theo failure table:

### `nuisance_shared_control`

- `balanced_accuracy = 0.5`
- `relative_to_baseline = 0.997035`
- `absolute_gain_over_chance = 0.0`
- fail reasons:
  - `control_threshold_not_passed`
  - `nuisance_relative_ceiling_exceeded`

### `spatial_control`

- `balanced_accuracy = 0.501487`
- `relative_to_baseline = 1.0`
- fail reasons:
  - `control_threshold_not_passed`
  - `spatial_relative_ceiling_exceeded`

## 6. Technical Interpretation

Dien giai ky thuat hop ly nhat voi bang chung hien tai:

1. Hai control nay gan chance level.
2. Comparator baseline `A2` cung gan chance level.
3. Vi contract hien tai dung `raw_ba_ratio`, nen control BA chia baseline BA van cho
   ti le cao, xap xi `1.0`.
4. Khi so sanh voi locked ceilings:
   - nuisance: `0.997035 > 0.50`
   - spatial: `1.0 > 0.67`
   nen hai control fail.

Ket qua nay giong mot substantive negative finding hon la mot bug trien khai.

## 7. Ket luan ky thuat

Ket luan hien tai:

- **Khong tim thay bug trien khai ro rang** trong cac bang chung da kiem tra.
- **Khong tim thay threshold mismatch** gay sai pass/fail.
- **Khong tim thay runtime leakage** du de giai thich failure.
- **Khong con metric-contract ambiguity** cho issue nay.

Vi vay:

> Failure cua `nuisance_shared_control` va `spatial_control` nen duoc xem la
> substantive failure hop le duoi contract da khoa, cho den khi co bang chung ky
> thuat moi cho thay implementation bug doc lap voi ket qua da quan sat.

## 8. Quy tac hanh dong tu ket luan nay

### 8.1 Duoc phep

- giu trang thai `claim-closed`;
- giu trang thai `fail-closed`;
- bao cao day la negative finding hop le;
- neu can, lap mot proposal prospective moi cho future runs ma khong reclassify run hien tai.

### 8.2 Khong duoc phep

- sua threshold hau nghiem;
- doi formula de thay doi pass/fail cua run hien tai;
- sua logits/metrics;
- bo subject post hoc;
- trinh bay run hien tai nhu bang chung efficacy.

## 9. De xuat buoc tiep theo

Hai lua chon hop le:

1. **Dong nhanh nay o trang thai fail-closed**
   - Dung ket qua hien tai lam limitation/negative finding.
   - Khong co code remediation ngay lap tuc.

2. **Neu muon di tiep, chi duoc mo mot proposal prospective moi**
   - Muc tieu la xem control design hoac governance design co can revise cho cac run
     tuong lai hay khong.
   - Proposal phai tach biet khoi run hien tai.
   - Proposal khong duoc reclassify artifact da fail.

## 10. One-line Conclusion

Voi bang chung ky thuat hien co, `nuisance_shared_control` va `spatial_control`
nen duoc xem la blocking failures hop le; nhanh nay phai giu `claim-closed` va
`fail-closed`, va chua co can cu de sua code/config runtime.
