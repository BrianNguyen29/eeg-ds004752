#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${1:-/content/drive/MyDrive/eeg-ds004752/data}"
DATASET_DIR="${DATA_ROOT}/ds004752"
GET_TARGET="${2:-metadata}"

mkdir -p "${DATA_ROOT}"

python -m pip install --quiet --upgrade datalad

if ! command -v git-annex >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq
    apt-get install -y -qq git-annex
  else
    echo "git-annex is required but apt-get is unavailable." >&2
    exit 2
  fi
fi

if [ ! -d "${DATASET_DIR}/.datalad" ]; then
  datalad clone https://github.com/OpenNeuroDatasets/ds004752.git "${DATASET_DIR}"
fi

cd "${DATASET_DIR}"

case "${GET_TARGET}" in
  metadata)
    echo "Dataset metadata installed at ${DATASET_DIR}. EDF/MAT payloads remain pointers."
    ;;
  sample)
    datalad get \
      sub-01/ses-01/eeg \
      sub-01/ses-01/ieeg \
      derivatives/sub-01/beamforming
    ;;
  all)
    datalad get .
    ;;
  *)
    echo "Unknown target: ${GET_TARGET}. Use metadata, sample, or all." >&2
    exit 2
    ;;
esac

echo "Data bootstrap complete: ${DATASET_DIR}"
