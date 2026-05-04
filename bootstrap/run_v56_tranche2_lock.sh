#!/usr/bin/env bash
set -euo pipefail

GATE0_RUN="${1:-/content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z}"
SPLIT_REGISTRY_RUN="${2:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_split_registry/latest.txt}"
FEATURE_PROVENANCE_RUN="${3:-/content/drive/MyDrive/eeg-ds004752/artifacts/v56_feature_provenance/latest.txt}"
OUTPUT_ROOT="${4:-/content/drive/MyDrive/eeg-ds004752/artifacts}"
PROFILE="${5:-t4_safe}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

cat <<MSG
[V5.6 Tranche 2.1] Split lock and feature provenance population starting
  repo_root: ${REPO_ROOT}
  gate0_run: ${GATE0_RUN}
  split_registry_run: ${SPLIT_REGISTRY_RUN}
  feature_provenance_run: ${FEATURE_PROVENANCE_RUN}
  output_root: ${OUTPUT_ROOT}
  profile: ${PROFILE}
MSG

if [[ ! -d "${GATE0_RUN}" ]]; then
  echo "ERROR: Gate 0 run directory not found: ${GATE0_RUN}" >&2
  exit 2
fi

python -m src.cli v56-tranche2-lock \
  --profile "${PROFILE}" \
  --gate0-run "${GATE0_RUN}" \
  --split-registry-run "${SPLIT_REGISTRY_RUN}" \
  --feature-provenance-run "${FEATURE_PROVENANCE_RUN}" \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --splits configs/v56/splits.json \
  --output-root "${OUTPUT_ROOT}"

cat <<MSG

[V5.6 Tranche 2.1] Split lock and feature provenance population finished
Review these latest pointers under:
  ${OUTPUT_ROOT}/v56_split_registry_lock/latest.txt
  ${OUTPUT_ROOT}/v56_feature_provenance_populated/latest.txt

Integrity boundary:
  - feature matrix materialization was not run
  - model training was not run
  - efficacy metrics were not computed
  - claim state remains closed
MSG
