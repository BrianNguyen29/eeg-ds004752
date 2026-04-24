# V5.6 Tranche 1 Signal Audit Runbook

Ngay cap nhat: 2026-04-24

Pham vi: runbook ngan de thuc hien `Tranche 1` cua V5.6 theo huong:

- payload materialization
- full-cohort signal-level Gate 0 rerun
- closeout readiness cho tranche benchmark/control-first

Tai lieu nay dua tren:

- `docs/17_v55_to_v56_transition_lock_2026-04-24.md`
- `docs/18_v55_to_v56_transition_lock_manifest_2026-04-24.json`
- `docs/19_v56_repo_mapping_and_execution_roadmap_2026-04-24.md`
- `README.md`
- `bootstrap/get_data_colab.sh`

Tai lieu nay khong mo claim va khong sua record V5.5.

## 1. Muc tieu cua tranche

Tranche nay chi tra loi 3 cau hoi:

1. co materialize duoc payload that tu ds004752 hay khong?
2. Gate 0 signal-level co chay duoc tren toan cohort hay khong?
3. sau tranche nay, co du dieu kien mo benchmark/control-first hay khong?

## 2. Tieu chi thanh cong

Tranche duoc xem la thanh cong neu:

- `bootstrap/get_data_colab.sh ... all` tai duoc payload that;
- `python -m src.cli audit --include-signal --signal-max-sessions 68` tao duoc Gate 0 run moi;
- Gate 0 run moi co:
  - `manifest_status = signal_audit_ready`
  - `cohort_lock_status = signal_audit_ready`
  - `gate0_blockers = []`
- co `materialization_report.json`, `cohort_lock.json`, `manifest.json`, `audit_report.md` de review.

## 3. Colab preflight

### 3.1 Mount Drive

```python
from google.colab import drive
drive.mount('/content/drive')
```

### 3.2 Lay repo moi nhat

```python
%cd /content/drive/MyDrive/eeg-ds004752
!git pull --ff-only
!git log --oneline -1
```

### 3.3 Cai runtime

```bash
INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh
```

## 4. Full materialization

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data all
```

Kiem tra nhanh:

```bash
ls -lh /content/drive/MyDrive/eeg-ds004752/data/ds004752/sub-01/ses-01/eeg
ls -lh /content/drive/MyDrive/eeg-ds004752/data/ds004752/sub-14/ses-08/ieeg
ls -lh /content/drive/MyDrive/eeg-ds004752/data/ds004752/derivatives/sub-14/beamforming
```

## 5. Full-cohort signal-level Gate 0 rerun

```bash
python -m src.cli audit \
  --profile t4_safe \
  --config configs/data/snapshot_colab.yaml \
  --include-signal \
  --signal-max-sessions 68
```

## 6. Artifact can kiem tra sau tranche

Sau khi audit xong, vao thu muc Gate 0 moi nhat va kiem:

- `manifest.json`
- `audit_report.md`
- `cohort_lock.json`
- `bridge_availability.json`
- `materialization_report.json`

## 7. Cach dien giai ket qua

### PASS full-cohort

Dau hieu:

- `manifest_status = signal_audit_ready`
- `cohort_lock_status = signal_audit_ready`
- `gate0_blockers = []`
- `n_primary_eligible = 15`

Hanh dong tiep:

1. cap nhat `docs/12`, `docs/14`, `docs/15`, `docs/16`, `docs/19`
2. mo tranche benchmark/control-first
3. giu `claim-closed`

### FAIL / still blocked

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

## 8. Closeout moi nhat

Run closeout da dat:

- Gate 0 run: `20260424T092923202761Z`
- `manifest_status = signal_audit_ready`
- `primary_eligibility_status = signal_audit_ready`
- `cohort_lock_status = signal_audit_ready`
- `n_primary_eligible = 15`
- `edf_materialized = 136/136`
- `mat_materialized = 15/15`

## 9. One-line Runbook Conclusion

Tranche 1 cua V5.6 da hoan tat o muc data/signal readiness; buoc tiep theo la
benchmark/control-first implementation, khong phai quay lai materialization
pilot.
