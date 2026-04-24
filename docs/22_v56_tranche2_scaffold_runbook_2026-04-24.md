# V5.6 Tranche 2 Scaffold Runbook

Ngay cap nhat: 2026-04-24

Pham vi: chay V5.6 scaffold-only CLI de sinh artifact contract cho
benchmark/control-first layer. Tai lieu nay khong mo claim, khong train model,
khong tinh efficacy metric.

## 1. Source of Truth

Gate 0 authoritative run:

- `artifacts/gate0/20260424T100159866284Z`

Trang thai da dat:

- `manifest_status = signal_audit_ready`
- `cohort_lock_status = signal_audit_ready`
- `gate0_blockers = []`
- `n_primary_eligible = 15`
- EDF materialized: `136/136`
- MAT materialized: `15/15`

Code/config source:

- `configs/v56/benchmark_spec.json`
- `configs/v56/splits.json`
- `configs/v56/controls.json`
- `configs/v56/comparators.json`
- `src/v56/runner.py`
- `src/v56/artifacts.py`
- `src/cli.py`

## 2. Integrity Boundary

Tranche 2 scaffold chi duoc lam nhung viec sau:

- doc Gate 0 run da signal-ready;
- doc V5.6 benchmark/control configs;
- ghi scaffold artifacts;
- giu `claim_closed`;
- bao cao ro rang rang model training va efficacy metrics chua duoc thuc hien.

Tranche 2 scaffold khong duoc:

- train RIFT-Net Lite;
- train A3/A4;
- chay comparator execution;
- tinh BA/CI/p-value/CRTG;
- mo efficacy claim;
- dung V5.5 negative finding lam positive evidence.

## 3. Lenh Chay

Khuyen nghi tren Colab/Drive: dung script da dong goi de artifact duoc ghi
vao Drive thay vi runtime tam:

```bash
bash bootstrap/run_v56_tranche2_scaffold.sh \
  /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  /content/drive/MyDrive/eeg-ds004752/artifacts
```

Tu repo root:

```bash
python -m src.cli v56-scaffold \
  --gate0-run artifacts/gate0/20260424T100159866284Z \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --splits configs/v56/splits.json \
  --controls configs/v56/controls.json \
  --comparators configs/v56/comparators.json \
  --output-root artifacts
```

Neu chay tren Colab, dung Gate 0 path tren Drive:

```bash
python -m src.cli v56-scaffold \
  --gate0-run /content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --splits configs/v56/splits.json \
  --controls configs/v56/controls.json \
  --comparators configs/v56/comparators.json \
  --output-root /content/drive/MyDrive/eeg-ds004752/artifacts
```

## 4. Expected Outputs

CLI se ghi 4 artifact families:

- `artifacts/v56_split_registry/<run_id>`
- `artifacts/v56_feature_provenance/<run_id>`
- `artifacts/v56_control_registry/<run_id>`
- `artifacts/v56_leaderboard/<run_id>`

Moi family can co:

- `<family>.json`
- `<family>_summary.json`
- `<family>_report.md`
- `v56_benchmark_scaffold_record.json`
- `latest.txt` tai artifact root

Trang thai mong doi:

- split registry: `pending_registry_lock`
- feature provenance: `pending_feature_provenance_population`
- control registry: `pending_control_execution`
- leaderboard: `pending_comparator_execution`
- all leaderboard rows: `pending_not_run`
- claim state: closed

## 5. Review Checklist

Sau khi chay CLI, review:

1. Gate 0 fields:
   - `gate0_manifest_status = signal_audit_ready`
   - `cohort_lock_status = signal_audit_ready`
   - `n_primary_eligible = 15`

2. Claim boundary:
   - `claim_closed = true`
   - khong co metric efficacy nao duoc ghi
   - report noi ro model training chua chay

3. Split/test-time policy:
   - `test_time_inference = scalp_eeg_only`
   - `allow_ieeg = false`
   - `allow_beamforming_bridge = false`

4. Control registry:
   - claim-blocking tiers con nguyen:
     - `data_integrity`
     - `control_adequacy`
     - `reporting`

5. Leaderboard:
   - primary target la `A4_privileged`
   - tat ca rows con `pending_not_run`
   - khong co BA/CI/p-value/CRTG result

## 6. Decision Gate

Neu 4 artifact families dung checklist:

- ghi nhan Tranche 2 scaffold artifacts da duoc tao;
- chuyen sang buoc khoa split registry va feature provenance;
- van khong chay model.

Neu co mismatch:

- sua scaffold/config/writer;
- rerun `v56-scaffold`;
- khong chuyen sang comparator execution.

Khong duoc mo Tranche 3 neu:

- split registry chua lock;
- feature provenance chua co source hashes/link;
- control registry chua ro adequacy execution plan;
- leaderboard van chi la scaffold pending.

## 7. Next Implementation Recommendation

Sau khi scaffold artifact review pass, buoc code tiep theo nen la:

1. `v56_split_registry_lock`
   - lock subject-level split registry tu Gate 0 cohort lock;
   - tao artifact lock rieng;
   - enforce subject isolation.

2. `v56_feature_provenance_populate`
   - ghi feature source manifest;
   - hash source inputs/configs;
   - link den split registry lock.

3. Chi sau hai buoc nay moi xem xet baseline leaderboard execution.

RIFT-Net Lite va A4 privileged execution van chua thuoc buoc tiep theo truc
tiep.
