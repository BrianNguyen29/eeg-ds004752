#!/usr/bin/env bash
set -euo pipefail

GATE0_RUN="${1:-/content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z}"
SPLIT_REGISTRY_LOCK_RUN="${2:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry_lock/latest.txt}"
FEATURE_PROVENANCE_RUN="${3:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance_populated/latest.txt}"
FEATURE_MATRIX_PLAN_RUN="${4:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_plan/latest.txt}"
LEAKAGE_AUDIT_PLAN_RUN="${5:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_leakage_audit_plan/latest.txt}"
OUTPUT_ROOT="${6:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_matrix_materializer_skeleton}"
PROFILE="${7:-t4_safe}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

cat <<MSG
[V5.6 Tranche 2.4] Feature-matrix materializer skeleton starting
  repo_root: ${REPO_ROOT}
  gate0_run: ${GATE0_RUN}
  split_registry_lock_run: ${SPLIT_REGISTRY_LOCK_RUN}
  feature_provenance_run: ${FEATURE_PROVENANCE_RUN}
  feature_matrix_plan_run: ${FEATURE_MATRIX_PLAN_RUN}
  leakage_audit_plan_run: ${LEAKAGE_AUDIT_PLAN_RUN}
  output_root: ${OUTPUT_ROOT}
  profile: ${PROFILE}
MSG

python -m src.cli v56-feature-matrix-materializer-skeleton \
  --profile "${PROFILE}" \
  --gate0-run "${GATE0_RUN}" \
  --split-registry-lock-run "${SPLIT_REGISTRY_LOCK_RUN}" \
  --feature-provenance-run "${FEATURE_PROVENANCE_RUN}" \
  --feature-matrix-plan-run "${FEATURE_MATRIX_PLAN_RUN}" \
  --leakage-audit-plan-run "${LEAKAGE_AUDIT_PLAN_RUN}" \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --materializer-skeleton-config configs/v56/feature_matrix_materializer_skeleton.json \
  --output-root "${OUTPUT_ROOT}"

cat <<MSG

[V5.6 Tranche 2.4] Feature-matrix materializer skeleton finished
Review latest pointer:
  ${OUTPUT_ROOT}/latest.txt

Integrity boundary:
  - EDF payloads were not read
  - feature values were not written
  - model training was not run
  - comparator execution was not run
  - efficacy metrics were not computed
  - claim state remains closed
MSG
