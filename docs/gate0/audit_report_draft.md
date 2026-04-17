# Gate 0 audit report draft

Ngay audit: 2026-04-17

## Pham vi

Audit ban dau o muc metadata cho dataset cuc bo `ds004752`.

Chua audit duoc signal-level vi cac file `.edf` va `.mat` hien la pointer Git-annex/DataLad, chua phai binary data that.

## Dataset identity

| Truong | Gia tri |
|---|---|
| Name | Dataset of intracranial EEG, scalp EEG and beamforming sources from epilepsy patients performing a verbal working memory task |
| BIDSVersion | 1.4.0 |
| DatasetType | raw |
| License | CC0 |
| DatasetDOI | doi:10.18112/openneuro.ds004752.v1.0.1 |
| Participants | 15 |

## File inventory

| Loai file | So luong | Ghi chu |
|---|---:|---|
| `.tsv` | 424 | Metadata, events, channels, electrodes |
| `.json` | 342 | Sidecar metadata |
| `.edf` | 136 | Dang la Git-annex/DataLad pointer |
| `.mat` | 15 | Dang la Git-annex/DataLad pointer beamforming |

## Subject/session inventory

| Subject | So session | EEG runs | iEEG runs | Event TSV | Electrode TSV |
|---|---:|---:|---:|---:|---:|
| sub-01 | 4 | 4 | 4 | 8 | 4 |
| sub-02 | 7 | 7 | 7 | 14 | 7 |
| sub-03 | 3 | 3 | 3 | 6 | 3 |
| sub-04 | 2 | 2 | 2 | 4 | 2 |
| sub-05 | 3 | 3 | 3 | 6 | 3 |
| sub-06 | 7 | 7 | 7 | 14 | 7 |
| sub-07 | 4 | 4 | 4 | 8 | 4 |
| sub-08 | 4 | 4 | 4 | 8 | 4 |
| sub-09 | 2 | 2 | 2 | 4 | 2 |
| sub-10 | 2 | 2 | 2 | 4 | 2 |
| sub-11 | 6 | 6 | 6 | 12 | 6 |
| sub-12 | 6 | 6 | 6 | 12 | 6 |
| sub-13 | 6 | 6 | 6 | 12 | 6 |
| sub-14 | 8 | 8 | 8 | 16 | 8 |
| sub-15 | 4 | 4 | 4 | 8 | 4 |

Tong session: 68.

## Events audit

Schema `events.tsv`:

- `onset`
- `duration`
- `nTrial`
- `begSample`
- `endSample`
- `SetSize`
- `ProbeLetter`
- `Match`
- `Correct`
- `ResponseTime`
- `Artifact`

Ket qua dem dong:

| Metric | Gia tri |
|---|---:|
| EEG event trials | 3353 |
| iEEG event trials | 3353 |
| Sessions lech trial count EEG/iEEG | 0 |
| Artifact trials theo EEG events | 168 |
| Correct trials theo EEG events | 3045 |
| Sessions lech noi dung events EEG/iEEG tren truong chinh | 0 |

Nhan xet:

- EEG va iEEG events co cung so trial theo tung session.
- EEG sampling trong marker mau cho thay `begSample/endSample` theo 200 Hz.
- iEEG sampling trong marker mau cho thay `begSample/endSample` theo 2000 Hz.
- Noi dung EEG vs iEEG events khop tren 8 truong chinh: `nTrial`, `duration`, `SetSize`, `ProbeLetter`, `Match`, `Correct`, `ResponseTime`, `Artifact`.

## Channels/electrodes schema

Schema `channels.tsv`:

- `name`
- `type`
- `units`
- `low_cutoff`
- `high_cutoff`
- `sampling_frequency`

Schema `electrodes.tsv`:

- `name`
- `x`
- `y`
- `z`
- `size`
- `AnatomicalLocation`

Nhan xet:

- EEG channel sample co `type = EEG`, `sampling_frequency = 200`.
- iEEG channel sample co `type = SEEG`, `sampling_frequency = 2000`.
- iEEG electrodes co toa do MNI-like va nhan anatomical; co gia tri `no_label_found` can thong ke rieng truoc khi tao teacher/ROI registry.

## Derivatives/beamforming

Inventory ban dau:

- Co 15 file `.mat`, moi subject 1 file trong `derivatives/sub-*/beamforming`.
- Tat ca file `.mat` hien la pointer Git-annex/DataLad, chua co noi dung binary de audit ROI.

Trang thai:

- Bridge availability chi moi xac nhan duoc o muc "co pointer theo subject".
- Chua du dieu kien ket luan ROI availability, trial mapping, shape, sampling hoac encoding/maintenance content.

## Blockers

| Blocker | Anh huong | Cach xu ly |
|---|---|---|
| `.edf` la pointer Git-annex/DataLad | Khong doc duoc raw EEG/iEEG | Materialize bang DataLad/git-annex |
| `.mat` la pointer Git-annex/DataLad | Khong audit duoc beamforming/bridge | Materialize derivatives |
| Chua co manifest checksum cho binary that | Chua the freeze signal-level dataset | Tao checksum sau khi materialize |
| Chua audit onset/sample alignment sau khi doc EDF | Chua khoa signal-level alignment | Chay sau khi materialize EDF |

## Ket luan tam thoi

Metadata-level Gate 0 co tin hieu tot: 15 participant, 68 session, events EEG/iEEG khop so dong va khop noi dung tren cac truong chinh, schema events/channels/electrodes ro rang.

Chua du dieu kien `cohort_lock` hoac substantive preprocessing vi du lieu tin hieu va derivatives chua duoc materialize.
