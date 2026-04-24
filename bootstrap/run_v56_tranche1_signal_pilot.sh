#!/usr/bin/env bash
set -euo pipefail

DATA_ROOT="${1:-/content/drive/MyDrive/eeg-ds004752/data}"
PROFILE="${2:-t4_safe}"
CONFIG_PATH="${3:-configs/data/snapshot_colab.yaml}"
SIGNAL_MAX_SESSIONS="${SIGNAL_MAX_SESSIONS:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

cat <<MSG
[V5.6 Tranche 1] Signal pilot starting
  repo_root: ${REPO_ROOT}
  data_root: ${DATA_ROOT}
  profile: ${PROFILE}
  config: ${CONFIG_PATH}
  signal_max_sessions: ${SIGNAL_MAX_SESSIONS}
MSG

echo
echo "[1/3] Installing runtime with signal extras..."
INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh

echo
echo "[2/3] Materializing sample payload via DataLad/git-annex..."
bash bootstrap/get_data_colab.sh "${DATA_ROOT}" sample

echo
echo "[3/3] Running Gate 0 signal-level audit on the sample scope..."
python -m src.cli audit \
  --profile "${PROFILE}" \
  --config "${CONFIG_PATH}" \
  --include-signal \
  --signal-max-sessions "${SIGNAL_MAX_SESSIONS}"

cat <<MSG

[V5.6 Tranche 1] Signal pilot finished
Review the latest Gate 0 run under:
  ${DATA_ROOT%/data}/artifacts/gate0

Expected review targets:
  - audit_report.md
  - manifest.json
  - cohort_lock.json
  - bridge_availability.json
  - materialization_report.json
MSG
