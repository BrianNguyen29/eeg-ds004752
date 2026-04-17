#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${1:-/content/drive/MyDrive/eeg-ds004752/data}"
DATASET_DIR="${DATA_ROOT}/ds004752"
GET_TARGET="${2:-metadata}"
MIN_GIT_ANNEX_VERSION="10.20230126"

mkdir -p "${DATA_ROOT}"

python -m pip install --quiet --upgrade datalad datalad-installer

git_annex_version() {
  if ! command -v git-annex >/dev/null 2>&1; then
    return 1
  fi
  git-annex version | awk '/git-annex version:/ {print $3; exit}'
}

git_annex_ok() {
  local current
  current="$(git_annex_version || true)"
  if [ -z "${current}" ]; then
    return 1
  fi
  printf '%s\n%s\n' "${MIN_GIT_ANNEX_VERSION}" "${current}" | sort -V -C
}

if ! git_annex_ok; then
  echo "Installing recent git-annex with datalad-installer..."
  datalad-installer --sudo ok git-annex -m datalad/git-annex:release
  hash -r
fi

if ! git_annex_ok; then
  echo "git-annex >= ${MIN_GIT_ANNEX_VERSION} is required." >&2
  echo "Detected version: $(git_annex_version || echo 'not found')" >&2
  exit 2
fi

echo "Using git-annex $(git_annex_version)"

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
