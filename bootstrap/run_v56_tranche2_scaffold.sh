#!/usr/bin/env bash
set -euo pipefail

GATE0_RUN="${1:-/content/drive/MyDrive/eeg-ds004752/artifacts/gate0/20260424T100159866284Z}"
OUTPUT_ROOT="${2:-/content/drive/MyDrive/eeg-ds004752/artifacts}"
PROFILE="${3:-t4_safe}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

cat <<MSG
[V5.6 Tranche 2] Scaffold artifact generation starting
  repo_root: ${REPO_ROOT}
  gate0_run: ${GATE0_RUN}
  output_root: ${OUTPUT_ROOT}
  profile: ${PROFILE}
MSG

if [[ ! -d "${GATE0_RUN}" ]]; then
  echo "ERROR: Gate 0 run directory not found: ${GATE0_RUN}" >&2
  exit 2
fi

python -m src.cli v56-scaffold \
  --profile "${PROFILE}" \
  --gate0-run "${GATE0_RUN}" \
  --benchmark-spec configs/v56/benchmark_spec.json \
  --splits configs/v56/splits.json \
  --controls configs/v56/controls.json \
  --comparators configs/v56/comparators.json \
  --output-root "${OUTPUT_ROOT}"

cat <<MSG

[V5.6 Tranche 2] Scaffold artifact generation finished
Review these latest pointers under:
  ${OUTPUT_ROOT}/v56_split_registry/latest.txt
  ${OUTPUT_ROOT}/v56_feature_provenance/latest.txt
  ${OUTPUT_ROOT}/v56_control_registry/latest.txt
  ${OUTPUT_ROOT}/v56_leaderboard/latest.txt

Integrity boundary:
  - model training was not run
  - efficacy metrics were not computed
  - claim state remains closed
MSG
