# V5.6 Tranche 1 Signal Pilot Runbook

Ngay cap nhat: 2026-04-24

Pham vi: runbook ngan de thuc hien `Tranche 1` cua V5.6 theo huong:

- payload materialization pilot
- signal-level Gate 0 rerun
- quyet dinh tiep tuc `GO/NO-GO`

Tai lieu nay dua tren:

- `docs/17_v55_to_v56_transition_lock_2026-04-24.md`
- `docs/18_v55_to_v56_transition_lock_manifest_2026-04-24.json`
- `docs/19_v56_repo_mapping_and_execution_roadmap_2026-04-24.md`
- `README.md`
- `bootstrap/get_data_colab.sh`

Tai lieu nay khong mo claim va khong sua record V5.5.

## 1. Muc tieu cua pilot

Pilot nay chi tra loi 3 cau hoi:

1. co materialize duoc payload that tu ds004752 hay khong?
2. Gate 0 signal-level co chay duoc tren sample payload hay khong?
3. sau pilot, co du dieu kien mo rong sang materialization theo subject hay khong?

## 2. Tieu chi thanh cong

Pilot duoc xem la thanh cong neu:

- `bootstrap/get_data_colab.sh ... sample` tai duoc payload that;
- `python -m src.cli audit --include-signal` tao duoc Gate 0 run moi;
- Gate 0 run moi khong con blocker `edf_payloads_not_materialized` cho sample scope;
- co `materialization_report.json` va `audit_report.md` de review.

Pilot duoc xem la that bai neu:

- datalad/git-annex khong lay duoc payload;
- signal audit khong doc duoc EDF/MAT;
- Gate 0 van blocked o muc payload cho sample scope.

## 3. Colab preflight

### 3.1 Mount Drive

```python
from google.colab import drive
drive.mount('/content/drive')
```

### 3.2 Lay repo moi nhat

```python
%cd /content/drive/MyDrive
!git clone https://github.com/BrianNguyen29/eeg-ds004752.git
%cd /content/drive/MyDrive/eeg-ds004752
!git pull --ff-only
!git log --oneline -1
```

Neu repo da ton tai:

```python
%cd /content/drive/MyDrive/eeg-ds004752
!git pull --ff-only
!git log --oneline -1
```

### 3.3 Cai runtime

```bash
bash bootstrap/install_runtime.sh
```

Neu se chay signal-level audit:

```bash
INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh
```

## 4. Pilot materialization

### 4.0 Cach chay ngan nhat

Neu muon giam thao tac tay, chay script pilot da dong goi san:

```bash
bash bootstrap/run_v56_tranche1_signal_pilot.sh /content/drive/MyDrive/eeg-ds004752/data
```

Script nay se tu dong:

1. cai signal extras
2. materialize sample payload
3. chay Gate 0 voi `--include-signal`

### 4.1 Materialize sample payload

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data sample
```

Lenh nay theo `bootstrap/get_data_colab.sh` se co gang lay:

- `sub-01/ses-01/eeg`
- `sub-01/ses-01/ieeg`
- `derivatives/sub-01/beamforming`

### 4.2 Kiem tra file da khong con pointer

```bash
ls -lh /content/drive/MyDrive/eeg-ds004752/data/ds004752/sub-01/ses-01/eeg
ls -lh /content/drive/MyDrive/eeg-ds004752/data/ds004752/sub-01/ses-01/ieeg
ls -lh /content/drive/MyDrive/eeg-ds004752/data/ds004752/derivatives/sub-01/beamforming
```

Neu file van co size cuc nho va noi dung la duong dan `.git/annex/objects/...`,
pilot chua materialize thanh cong.

## 5. Signal-level Gate 0 rerun

### 5.1 Chay audit tren sample

```bash
python -m src.cli audit \
  --profile t4_safe \
  --config configs/data/snapshot_colab.yaml \
  --include-signal \
  --signal-max-sessions 1
```

### 5.2 Neu muon gioi han theo subject/session ro hon

```bash
python -m src.cli audit \
  --profile t4_safe \
  --config configs/data/snapshot_colab.yaml \
  --include-signal \
  --subjects sub-01 \
  --sessions ses-01 \
  --signal-max-sessions 1
```

## 6. Artifact can kiem tra sau pilot

Sau khi audit xong, vao thu muc Gate 0 moi nhat va kiem:

- `manifest.json`
- `audit_report.md`
- `cohort_lock.json`
- `bridge_availability.json`
- `materialization_report.json` neu co

Lenh goi y:

```python
from pathlib import Path

root = Path('/content/drive/MyDrive/eeg-ds004752/artifacts/gate0')
runs = sorted([p for p in root.iterdir() if p.is_dir()])
latest = runs[-1]
print(latest)
for p in sorted(latest.iterdir()):
    print(p.name)
```

## 7. Cach dien giai ket qua pilot

### Truong hop A - PASS cho sample

Dau hieu:

- sample EDF/iEEG/MAT doc duoc
- signal-level audit chay xong
- artifact Gate 0 moi duoc tao

Hanh dong tiep:

1. mo rong sang `subjects sub-01 sub-02 ...`
2. rerun Gate 0 voi scope rong hon
3. update `docs/12`, `docs/14`, `docs/15`
4. review lai `GO/NO-GO`

### Truong hop B - Partial pass

Dau hieu:

- mot so payload lay duoc;
- nhung signal audit con blocker ro rang

Hanh dong tiep:

1. ghi ro blocker trong review note
2. chua mo code V5.6
3. quyet dinh co tiep tuc materialize theo subject hay khong

### Truong hop C - FAIL / still blocked

Dau hieu:

- payload van pointer-like
- datalad/git-annex khong lay duoc data
- Gate 0 signal-level khong chay duoc

Hanh dong tiep:

1. giu `NO-GO for code`
2. kich hoat `Scenario D`
3. chuyen huong sang:
   - benchmark specification
   - simulation validation
   - data-readiness report

## 8. Mo rong sau pilot

Neu sample pass, chay tiep theo subject:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data subjects sub-01 sub-02
python -m src.cli audit \
  --profile t4_safe \
  --config configs/data/snapshot_colab.yaml \
  --include-signal \
  --subjects sub-01 sub-02 \
  --signal-max-sessions 11
```

Chi sau khi co artifact signal-level ro rang moi xem xet:

- cohort lock signal-ready
- benchmark skeleton V5.6
- RIFT-Net Lite tranche

## 9. Bao cao can thu ve sau pilot

Sau khi chay xong pilot, can thu ve toi thieu:

1. duong dan Gate 0 run moi
2. `audit_report.md`
3. `manifest.json`
4. `materialization_report.json` neu co
5. ghi chu ngan:
   - payload materialized hay chua
   - signal audit pass hay fail
   - blocker con lai la gi
   - khuyen nghi `continue` hay `Scenario D`

## 10. One-line Runbook

Tranche 1 cua V5.6 phai bat dau bang sample payload materialization va signal-level
Gate 0 pilot; chi khi pilot nay cho artifact sach moi duoc mo rong sang cohort
signal-ready va benchmark implementation.
