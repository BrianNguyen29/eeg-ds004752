#!/usr/bin/env bash
set -euo pipefail

python --version
mkdir -p artifacts/cache artifacts/runs artifacts/gate0

if [ "${INSTALL_SIGNAL_EXTRAS:-0}" = "1" ]; then
  python -m pip install --quiet --upgrade mne scipy numpy
fi

cat <<'MSG'
Runtime bootstrap complete.

Gate 0 uses only Python standard library:
  python -m src.cli audit --profile t4_safe --config configs/data/snapshot.yaml

Signal-level phases need materialized DataLad/git-annex payloads and
additional scientific packages.

For signal-level Gate 0 audit in Colab:
  INSTALL_SIGNAL_EXTRAS=1 bash bootstrap/install_runtime.sh
  python -m src.cli audit --profile t4_safe --config configs/data/snapshot_colab.yaml --include-signal --signal-max-sessions 1
MSG
