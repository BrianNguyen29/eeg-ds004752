# Ke hoach tim hieu tai lieu va khoi dong Gate 0

Ngay lap: 2026-04-17

## Muc tieu ngan han

Chuyen bo tai lieu V5.5 tu trang thai "doc de hieu" sang trang thai "co the trien khai co kiem soat" cho dataset `ds004752`.

Trong giai doan dau, uu tien 3 viec:

- Nam ro claim khoa hoc, endpoint, comparator va dieu kien duoc phep cong bo.
- Khoa cac execution rules khong duoc vi pham: split, leakage control, influence ceiling, teacher viability, cohort lock.
- Khoi dong Gate 0 bang inventory dataset, audit marker, audit sidecar va tao manifest/cohort lock.

## Ban do tai lieu

| Tai lieu | Vai tro | Doc de lay gi |
|---|---|---|
| `V5_5_Integrated_Proposal_vi_complete.docx` | Nen khoa hoc | Claim, gia thuyet, phase, comparator, control suite, ket qua co the bao cao |
| `V5_5_Technical_Implementation_Spec_vi_complete.docx` | Nguon quy tac thuc thi cao nhat | Preprocessing, split protocol, leakage control, teacher space, Gate 1/2, threshold |
| `V5_5_Execution_Supplement_Implementation_Annex_vi.docx` | SOP van hanh | Trinh tu Gate 0-2.5, freeze package, decision memo, prereg blocker |
| `V5_5_Master_Artifact_Dossier_Freeze_Prereg_Reporting_Control.docx` | Danh muc artefact | File nao phai tao, ai so huu, bang chung exit cua moi gate |
| `ds004752_dossier_trien_khai_vi.docx` | Cau noi voi dataset that | Provenance, BIDS layout, subject/session, diem phai audit cuc bo |
| `blueprint_trien_khai_v1_colab.docx` | Cau noi sang code | Cau truc thu muc muc tieu, CLI entrypoints, runtime profile T4/A100 |

## Thu tu doc thuc dung

1. Doc `Integrated Proposal` de hieu "vi sao lam".
2. Doc `Technical Implementation Spec` de hieu "luat nao bat buoc".
3. Doc `Execution Supplement / Annex` de hieu "chay gate nhu the nao".
4. Doc `Master Artifact Dossier` de hieu "phai tao artefact nao".
5. Doc `ds004752 dossier` de noi voi du lieu that.
6. Doc `blueprint_colab` de chuyen thanh pipeline code.

## Khai niem can khoa som

| Khai niem | Dien giai ngan |
|---|---|
| Observability-constrained privileged transfer | iEEG/teacher chi duoc giup neu tin hieu do co lien he quan sat duoc voi scalp EEG; tranh claim vuot qua kha nang scalp |
| Teacher element | Dac trung hoac loss phu tu iEEG/bridge/latent dung de huong dan scalp model |
| Influence ceiling | Gioi han anh huong cua teacher len model de tranh teacher ap dao; tai lieu nhac moc `0.40` can khoa trong registry |
| Teacher-pool viability floor | Neu fold khong du teacher kha dung thi phai demote/no-teacher/weak-pool theo rule, khong duoc tuy tien |
| Cohort lock | Khoa subject/session/trial usable truoc substantive run |
| Gate 0 | Dataset freeze, manifest audit, marker diagnostics, sidecar audit, bridge availability |
| Gate 1 | Decision simulation, SESOI, influence governance |
| Gate 2 | Synthetic validation va threshold lock |
| Gate 2.5 | Preregistration bundle va release blocker truoc real substantive run |

## Khoi dong Gate 0: ket qua inventory ban dau

Dataset cuc bo: `ds004752`

Thong tin tu `dataset_description.json`:

- Ten dataset: Dataset of intracranial EEG, scalp EEG and beamforming sources from epilepsy patients performing a verbal working memory task.
- BIDS version: `1.4.0`.
- Dataset type: `raw`.
- License: `CC0`.
- DOI: `doi:10.18112/openneuro.ds004752.v1.0.1`.

Thong tin subject/session ban dau:

| Subject | Sessions | So session |
|---|---|---:|
| sub-01 | ses-01..ses-04 | 4 |
| sub-02 | ses-01..ses-07 | 7 |
| sub-03 | ses-01..ses-03 | 3 |
| sub-04 | ses-01..ses-02 | 2 |
| sub-05 | ses-01..ses-03 | 3 |
| sub-06 | ses-01..ses-07 | 7 |
| sub-07 | ses-01..ses-04 | 4 |
| sub-08 | ses-01..ses-04 | 4 |
| sub-09 | ses-01..ses-02 | 2 |
| sub-10 | ses-01..ses-02 | 2 |
| sub-11 | ses-01..ses-06 | 6 |
| sub-12 | ses-01..ses-06 | 6 |
| sub-13 | ses-01..ses-06 | 6 |
| sub-14 | ses-01..ses-08 | 8 |
| sub-15 | ses-01..ses-04 | 4 |

Nhan xet ban dau:

- Co 15 participant trong `participants.tsv`.
- Moi session quan sat ban dau co ca EEG va iEEG.
- Moi session co 2 file events TSV tuong ung EEG va iEEG; can kiem tra noi dung co dong nhat hay khong.
- So session khong dong deu, nen split/cross-session robustness phai subject-aware va session-aware.
- `N_raw public = 15` khong duoc xem la `N_primary_eligible` cho den khi Gate 0 audit xong.

Ket qua audit metadata dau tien:

- Tong so session: 68.
- Tong trial EEG theo `events.tsv`: 3353.
- Tong trial iEEG theo `events.tsv`: 3353.
- Session lech so trial EEG vs iEEG: 0.
- Trial co `Artifact = 1` theo EEG events: 168.
- Trial co `Correct = 1` theo EEG events: 3045.
- Schema `events.tsv`: `onset`, `duration`, `nTrial`, `begSample`, `endSample`, `SetSize`, `ProbeLetter`, `Match`, `Correct`, `ResponseTime`, `Artifact`.
- Schema `channels.tsv`: `name`, `type`, `units`, `low_cutoff`, `high_cutoff`, `sampling_frequency`.
- Schema `electrodes.tsv`: `name`, `x`, `y`, `z`, `size`, `AnatomicalLocation`.

Canh bao du lieu:

- Tat ca 136 file `.edf` va 15 file `.mat` dang la pointer Git-annex/DataLad, kich thuoc 207-211 byte.
- Chua the doc tin hieu EEG/iEEG hoac beamforming cho den khi materialize bang DataLad/git-annex.
- Gate 0 hien chi co the freeze metadata-level inventory; signal-level audit phai cho den khi co du lieu that.

## Artefact can tao sau Gate 0

| Artefact | Trang thai | Ghi chu |
|---|---|---|
| `manifest.json` | Chua tao | Can gom file identity, checksum, subject/session inventory, trial counts, marker diagnostics |
| `cohort_lock.json` | Chua tao | Can khoa subject/session/trial usable va ly do exclude |
| `audit_report.md` | Chua tao | Can bao cao bat thuong BIDS, marker, sidecar, derivatives |
| `override_log.md` | Chua tao | Ban dau rong; chi ghi khi co override duoc chap thuan |
| `bridge_availability.json` | Chua tao | Can map derivatives/beamforming ROI theo subject/session |

## Viec tiep theo

1. Tao `audit_report.md` ban nhap cho metadata-level Gate 0.
2. Tao `manifest.json` ban nhap gom dataset identity, file counts, subject/session inventory va trang thai pointer.
3. Kiem tra dong nhat noi dung EEG vs iEEG events theo tung session, khong chi dem so dong.
4. Materialize `.edf` va `.mat` bang DataLad/git-annex truoc signal-level audit.
5. Sau khi co du lieu that: audit sampling, channel count, EDF duration, bridge/beamforming ROI va trial-to-signal alignment.

## Nguyen tac trong khi trien khai

- Khong chay substantive model truoc Gate 2.5.
- Khong dung tat ca 15 subject lam primary cohort neu chua co `cohort_lock.json`.
- Khong de iEEG/teacher lam leakage vao scalp-only comparator.
- Khong thay doi threshold sau khi da thay ket qua real-data substantive run.
- Neu technical spec xung dot voi annex/dossier, uu tien technical spec.
