# Phase 1 Prospective Execution Roadmap

Ngay cap nhat: 2026-04-24

Pham vi: roadmap ngan de dieu hanh thuc thi cho nhanh prospective
`iEEG-assisted for scalp EEG`, tong hop tu `docs/11` den `docs/15`.

Trang thai khoi dau:

- current Phase 1 record: `fail-closed`, `claim-closed`
- current prospective status: `NO-GO for code`

## 1. Roadmap ngan

### R1 - Khoa huong nghien cuu

Tai lieu nen dung:

- `docs/11_phase1_prospective_ieeg_assisted_proposal_2026-04-24.md`
- `docs/13_phase1_ieeg_assisted_contract_2026-04-24.md`

Muc tieu:

- chot claim target chinh la `A4_privileged`
- chot quy tac `train-time privileged, test-time scalp-only`
- chot rang current run khong duoc dung de ho tro claim moi

Exit gate:

- khong con mo ho giua `scalp proxy teacher` va `real iEEG teacher`

### R2 - Mo khoa du lieu signal-level

Tai lieu nen dung:

- `docs/12_phase1_signal_level_gate0_readiness_2026-04-24.md`
- `docs/15_phase1_signal_readiness_operational_checklist_2026-04-24.md`
- `README.md`

Muc tieu:

- materialize EDF/MAT payloads
- rerun Gate 0 o muc signal-level
- khoa `cohort_lock.json` o muc signal-ready

Exit gate:

- khong con blocker:
  - `edf_payloads_not_materialized`
  - `mat_derivatives_not_materialized`
  - `cohort_lock_is_draft_until_signal_level_audit`

### R3 - Review lai quyet dinh go/no-go

Tai lieu nen dung:

- `docs/14_phase1_go_no_go_decision_memo_2026-04-24.md`
- artifact Gate 0 moi sau khi signal-level rerun

Muc tieu:

- xac dinh xem da du dieu kien mo nhanh code prospective hay chua

Exit gate:

- quyet dinh:
  - `GO for code`, hoac
  - tiep tuc `NO-GO`

### R4 - Neu va chi neu duoc GO

Muc tieu:

- lap implementation plan prospective cho A3/A4 final
- chot artifact moi, test moi, leakage audit moi
- chi sau do moi patch code

Exit gate:

- code prospective duoc mo co kiem soat

## 2. Thu tu uu tien thuc thi

Thu tu dung:

1. `R1` - chot contract
2. `R2` - mo khoa payload va signal-level Gate 0
3. `R3` - review lai `go/no-go`
4. `R4` - chi mo neu `GO`

Thu tu khong dung:

1. patch code A3/A4 truoc
2. roi moi quay lai materialize payload
3. roi moi tim cach hop thuc hoa contract

## 3. Cong viec van hanh can lam ngay

Ba viec can lam ngay theo roadmap:

1. xac dinh co che lay du lieu that:
   - `bootstrap/get_data_colab.sh`
   - DataLad/git-annex payload retrieval
2. chay materialization o muc sample/subjects
3. rerun Gate 0 voi `--include-signal`

Theo `README.md`, repo da co san duong di van hanh:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data sample
python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml --include-signal --signal-max-sessions 1
```

Hoac theo subject:

```bash
bash bootstrap/get_data_colab.sh /content/drive/MyDrive/eeg-ds004752/data subjects sub-01 sub-02
python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml --include-signal --subjects sub-01 sub-02 --signal-max-sessions 11
```

## 4. Dieu hanh va quyet dinh

### Neu materialization that bai

- khong mo nhanh code
- ghi ro blocker du lieu/ha tang
- giu de tai o huong negative finding + methodological contribution

### Neu materialization thanh cong nhung signal audit fail

- khong mo nhanh code
- ghi ro blocker signal-level
- review lai cohort lock va bridge readiness

### Neu materialization va signal audit deu on

- quay lai `docs/14`
- danh gia lai `GO/NO-GO`

## 5. One-line Roadmap

Roadmap prospective dung cho dieu hanh thuc thi la:

> chot contract -> mo khoa payload signal-level -> rerun Gate 0 -> review lai
> go/no-go -> chi sau do moi xem xet code prospective cho A4 iEEG-assisted.
