#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${1:-/content/drive/MyDrive/eeg-ds004752/data}"
DATASET_DIR="${DATA_ROOT}/ds004752"
GET_TARGET="${2:-metadata}"
MIN_GIT_ANNEX_VERSION="10.20230126"

mkdir -p "${DATA_ROOT}"

python -m pip install --quiet --upgrade datalad datalad-installer

ensure_apt_dependency() {
  local package="$1"
  if ! dpkg -s "${package}" >/dev/null 2>&1; then
    echo "Installing missing system dependency: ${package}"
    sudo apt-get update -y
    sudo apt-get install -y "${package}"
  fi
}

# DataLad/git-annex creates local git commits during dataset initialization.
# Fresh Colab runtimes usually have no Git identity configured, which makes
# `git annex init` fail unless we set a harmless local automation identity.
if [ -z "$(git config --global user.email || true)" ]; then
  git config --global user.email "colab-runner@example.invalid"
fi

if [ -z "$(git config --global user.name || true)" ]; then
  git config --global user.name "Colab Runner"
fi

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
  ensure_apt_dependency netbase
  echo "Installing recent git-annex with datalad-installer..."
  if ! datalad-installer --sudo ok git-annex -m datalad/git-annex:release; then
    echo "Retrying git-annex install after repairing system dependencies..."
    ensure_apt_dependency netbase
    sudo apt-get install -f -y
    datalad-installer --sudo ok git-annex -m datalad/git-annex:release
  fi
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
  subjects)
    if [ "$#" -lt 3 ]; then
      echo "Usage: $0 DATA_ROOT subjects sub-01 [sub-02 ...]" >&2
      exit 2
    fi
    for subject in "${@:3}"; do
      datalad get "${subject}" "derivatives/${subject}/beamforming"
    done
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
