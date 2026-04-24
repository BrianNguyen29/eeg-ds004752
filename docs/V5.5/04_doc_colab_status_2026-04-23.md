# Tinh trang du an qua docs va Colab

Ngay kiem tra: 2026-04-23

Pham vi: docx/markdown trong `docs/`, notebook Colab trong `notebooks/`, va mot so
artifact local/Drive-export hien co.

## 1. Ket luan ngan

Du an dang o trang thai scaffold/governance-heavy nhung Colab orchestration da tien
xa hon local artifacts. Tai lieu goc va notebook deu nhat quan o mot diem: moi ket
qua Phase 1 hien tai phai duoc xem la claim-closed/non-claim cho den khi full
comparator + controls + calibration + influence + reporting package pass theo
threshold da khoa.

Tren local repo:

- Source code va notebook orchestration da co day du cho chuoi Gate 0 -> Gate 2.5
  -> Phase 0.5 -> Phase 1 final package.
- `configs/prereg/prereg_bundle.json` trong repo van la `draft_blocked`.
- Gate 0 local moi nhat van `draft_metadata_only`, do EDF/MAT chua materialize.
- Co mot artifact export tu Drive cho `phase1_final_comparator_runner`, nhung
  artifact do tu bao cao `claim_ready=false`.

## 2. Vai tro cua cac tai lieu goc

| Tai lieu | Vai tro doc duoc | Trang thai/ham y |
|---|---|---|
| `V5_5_Integrated_Proposal_vi_complete.docx` | Khoa claim khoa hoc va claim boundary | Claim manh chi hop le neu A4 vuot robustly A3/A2b/A2c/A2d, calibration/influence/controls pass; neu khong thi pivot sang observability/atlas/transfer-frontier. |
| `V5_5_Technical_Implementation_Spec_vi_complete.docx` | Source of truth cao nhat cho execution rules | Cam leakage, cam fit tren outer-test, cam adaptation khong nhan, khoa cohort/split/threshold truoc substantive run. |
| `V5_5_Execution_Supplement_Implementation_Annex_vi.docx` | SOP gate, pass criteria, release blocker | Gate 0/1/2/2.5 la dieu kien truoc real substantive run; prereg bundle la release blocker. |
| `V5_5_Master_Artifact_Dossier_Freeze_Prereg_Reporting_Control.docx` | Binder artifact/freeze/prereg/reporting/control | Tat ca artifact phai giam degrees of freedom, khong tao freedom moi; cohort lock la denominator that. |
| `ds004752_dossier_trien_khai_vi.docx` | Cau noi dataset that voi V5.5 | ds004752 co scalp EEG + iEEG + beamforming; Gate 0 phai audit snapshot cuc bo, session heterogeneity, derivatives va payload materialization. |
| `blueprint_trien_khai_v1_colab.docx` | Blueprint code/Colab file-by-file | Notebook khong duoc la source of truth; logic phai o `src/`; artifact freeze phai hash-link vao prereg bundle. |

Nguyen tac lap lai trong nhieu tai lieu:

- Khong duoc de outer-test subject tham gia fit nao: preprocessing, ICA, PCA,
  latent coupling, observability predictor, calibration, A2d alignment, tuned QC.
- Khong duoc sua ngam code/config/notebook/report neu thay doi co the anh huong
  headline claim.
- Khong duoc chay substantive Phase 1/2/3 khi thieu Gate 0, Gate 1, Gate 2 va
  Gate 2.5 artifact.
- Preregistration la release blocker cho real substantive runs, nhung khong chan
  audit, synthetic, smoke tests, unit tests.

## 3. Markdown/runbook hien co

| File | Noi dung chinh |
|---|---|
| `docs/00_ke_hoach_tim_hieu_va_gate0.md` | Ke hoach doc tai lieu va Gate 0 ban dau; ghi nhan 15 participants, 68 sessions, 3353 EEG/iEEG trials, EDF/MAT la pointer. |
| `docs/01_v55_doc_code_crosswalk.md` | Crosswalk rat day giua docs, module `src/`, config, test va artifact contract. |
| `docs/02_colab_local_runbook.md` | Runbook local/Colab, data materialization modes, Gate 0 -> Gate 2.5 -> Phase 1 final chain. |
| `docs/03_kiem_tra_tuan_tu_2026-04-23.md` | Bao cao kiem tra tuan tu da chay local: smoke pass, Gate 0 metadata-only, guard fail-closed, 119 unit tests pass. |
| `docs/colab_deployment.md` | Deployment plan tren Google Drive; raw EDF/MAT va runtime artifacts khong duoc track trong repo. |

## 4. Notebook Colab: cau truc va muc do sach

Notebook inventory:

- 41 notebook `.ipynb`.
- Tat ca code cells dang `execution_count=null`.
- Tat ca notebook khong luu outputs.
- Notebook 01 la quickstart Gate 0.
- Notebook 02-04 la Gate 1, Gate 2, Gate 2.5.
- `EEG_Phase05_Observability_Estimators.ipynb` la Phase 0.5 estimator workflow.
- Notebook 06-40 la chuoi Phase 1 readiness, smoke, final comparator, final
  governance, controls, calibration, influence, reporting va remediation.

Dieu nay tot cho repo hygiene: notebook duoc commit nhu orchestration templates,
khong phai log output.

## 5. Notebook Colab: source-of-truth pinned runs

Nhieu notebook da pin artifact runs tren Drive:

| Stage | Pinned run/doc observed |
|---|---|
| Gate 0 | `artifacts/gate0/20260417T102811097110Z` |
| Gate 1 | `artifacts/gate1/20260418T153918409528Z` |
| Gate 2 | `artifacts/gate2/20260418T160143330194Z` |
| Gate 2.5 | `artifacts/prereg/20260418T161442014597Z` |
| Phase 0.5 preflight | `artifacts/phase05/20260418T163438037205Z` |
| Phase 0.5 estimators | `artifacts/phase05_estimators/20260419T130315366518Z` |
| Phase 1 readiness | `artifacts/phase1_readiness/20260419T154005857077Z` |
| Phase 1 model smoke | `artifacts/phase1_model_smoke/20260419T172746816598Z` |
| Phase 1 gap review | `artifacts/phase1_gap_review/20260420T101100749205Z` |
| Final feature matrix | `artifacts/phase1_final_feature_matrix/20260421T151617731994Z` |
| Final comparator reconciliation | `artifacts/phase1_final_comparator_reconciliation/20260422T014337472987Z` |
| Final governance reconciliation | `artifacts/phase1_final_governance_reconciliation/20260422T071329009670Z` and `20260422T082255821648Z` |
| Final claim-state closeout | `artifacts/phase1_final_claim_state_closeout/20260422T083855265838Z` |

Prereg identity hash used repeatedly:

```text
87e928ea747099c336a32121bc156655a1a160d666a251c7ac41228efba96af6
```

Interpretation: Colab notebooks assume a reviewed locked prereg bundle exists on
Drive. The repo-local `configs/prereg/prereg_bundle.json` is not that bundle; it
is intentionally `draft_blocked`.

## 6. Notebook Colab: manual holds va claim boundary

Nhieu notebook co manual hold mac dinh:

| Notebook group | Default run flag |
|---|---|
| A2/A2b model smoke | `RUN_A2_A2B_MODEL_SMOKE=False` |
| A2d smoke | `RUN_A2D_RIEMANNIAN_SMOKE=False` |
| A2c smoke | `RUN_A2C_CORAL_SMOKE=False` |
| A3 smoke | `RUN_A3_DISTILLATION_SMOKE=False` |
| A4 smoke | `RUN_A4_PRIVILEGED_SMOKE=False` |
| Final comparator runner | `RUN_FINAL_COMPARATOR_RUNNER=False` |
| Final A2d runner | `RUN_FINAL_A2D_RUNNER=False` |
| Final comparator reconciliation | `RUN_FINAL_COMPARATOR_RECONCILIATION=False` |
| Final governance reconciliation | `RUN_FINAL_GOVERNANCE_RECONCILIATION=False` |
| Final controls/calibration/influence/reporting | all default `False` where run flag exists |
| Final remediation/metric formula chain | all default `False` where run flag exists |

Notebook 06 tro di lap lai cac assertion dang:

- prereg bundle phai `locked`;
- locked prereg identity hash phai khop;
- upstream source run phai duoc review/pinned;
- `claim_ready` phai tiep tuc `False` khi final package chua du;
- failed controls/blockers khong duoc bien thanh claims;
- smoke artifacts khong duoc promote thanh evidence.

## 7. Local artifact reconciliation

Local `artifacts/` hien co:

- Nhieu Gate 0 metadata runs, moi nhat:
  `artifacts/gate0/20260423T134322736254Z`.
- Mot export/extract:
  `artifacts/phase1_final_comparator_runner-20260421T171049Z-3-001`.

Gate 0 local moi nhat:

- `manifest_status=draft_metadata_only`.
- `n_subjects=15`, `n_sessions=68`.
- EEG trials = `3353`, iEEG trials = `3353`.
- Core EEG/iEEG event mismatch = `0`.
- EDF materialized = `0/136`.
- MAT materialized = `0/15`.
- Blockers:
  - `edf_payloads_not_materialized`
  - `mat_derivatives_not_materialized`
  - `cohort_lock_is_draft_until_signal_level_audit`

Local `configs/prereg/prereg_bundle.json`:

- `status=draft_blocked`.
- `artifact_hashes={}`.
- `locked_at=null`.

## 8. Phase 1 final comparator runner export

Exported summary:

- Status: `phase1_final_comparator_runner_partial_with_blockers`.
- Feature matrix: `2223` rows, `24` features.
- Folds: `15`.
- Requested comparators:
  - `A2`
  - `A2b`
  - `A2c_CORAL`
  - `A2d_riemannian`
  - `A3_distillation`
  - `A4_privileged`
- Completed comparators:
  - `A2`
  - `A2b`
  - `A2c_CORAL`
  - `A3_distillation`
  - `A4_privileged`
- Blocked comparator:
  - `A2d_riemannian`

Claim state:

- `claim_ready=false`.
- `headline_phase1_claim_open=false`.
- `full_phase1_claim_bearing_run_allowed=false`.
- `smoke_artifacts_promoted=false`.

Blockers:

- `A2d_riemannian_not_executable_from_final_feature_matrix`
- `A2d_riemannian_final_covariance_runner_missing`
- `controls_calibration_influence_reporting_missing`
- `headline_claim_blocked_until_full_package_passes`
- `final_comparator_outputs_incomplete`

Interpretation: This artifact is useful engineering evidence that several
feature-matrix comparators run, but it is explicitly not scientific claim
evidence. It cannot support decoder efficacy, A3/A4 efficacy, A4 superiority or
full Phase 1 neural comparator performance.

## 9. Current project status

Best current reading:

1. The repo contains a mature governance scaffold with extensive CLI modules,
   config contracts, tests and Colab orchestration.
2. Local dataset state remains metadata-only unless Drive payloads are used.
3. A separate Drive/Colab execution chain appears to have reached far into
   Phase 1 final comparator/gov/remediation planning.
4. That Drive/Colab chain still keeps claims closed.
5. The strongest active blockers are A2d final covariance/tangent runner,
   final controls/calibration/influence/reporting completeness, and local
   payload materialization if continuing from this machine.

## 10. Immediate next checks

Recommended next checks in order:

1. Verify whether Drive artifact `artifacts/gate0/20260417T102811097110Z`
   actually has `manifest_status=signal_audit_ready`, empty blockers, and
   materialized EDF/MAT payloads. Notebook chain depends on this.
2. Inspect Drive prereg bundle
   `artifacts/prereg/20260418T161442014597Z/prereg_bundle.json` and confirm
   `status=locked`, source run hashes and identity hash
   `87e928ea747099c336a32121bc156655a1a160d666a251c7ac41228efba96af6`.
3. Inspect final A2d runner artifact if it exists after notebook 25; if absent,
   A2d remains a hard blocker.
4. Inspect final governance reconciliation and controls/calibration/influence
   manifests for actual pass/fail, not only existence.
5. Keep local repo changes limited to docs/code; do not commit runtime
   `artifacts/` or materialized `ds004752/**/*.edf` / `*.mat`.

