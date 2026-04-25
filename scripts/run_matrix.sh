#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

RUNS="${1:-50}"
WARMUP="${2:-5}"
PARALLEL="${3:-100}"
ROUNDS="${4:-10}"

MODES=(
  classical
  kex_pqc
  cert_pqc
  hybrid
  pqc
)

for mode in "${MODES[@]}"; do
  "${SCRIPT_DIR}/run_latency.sh" "${mode}" "${RUNS}" "${WARMUP}"
  "${SCRIPT_DIR}/capture_handshake.sh" "${mode}"
  "${SCRIPT_DIR}/run_concurrency.sh" "${mode}" "${PARALLEL}" "${ROUNDS}"
done

echo "Completed matrix runs for: ${MODES[*]}"
