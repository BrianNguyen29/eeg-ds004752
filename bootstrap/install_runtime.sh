#!/usr/bin/env bash
set -euo pipefail

python --version
mkdir -p artifacts/cache artifacts/runs artifacts/gate0

cat <<'MSG'
Runtime bootstrap complete.

Gate 0 uses only Python standard library:
  python -m src.cli audit --profile t4_safe --config configs/data/snapshot.yaml

Signal-level phases need materialized DataLad/git-annex payloads and
additional scientific packages.
MSG

