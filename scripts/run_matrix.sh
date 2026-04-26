#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

RUNS="${1:-50}"
WARMUP="${2:-5}"
PARALLEL="${3:-100}"
ROUNDS="${4:-10}"

python3 "${SCRIPT_DIR}/validate_config.py"
MODES=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && MODES+=("${line}")
done < <(python3 "${SCRIPT_DIR}/config_query.py" modes)

for mode in "${MODES[@]}"; do
  "${SCRIPT_DIR}/run_latency.sh" "${mode}" "${RUNS}" "${WARMUP}"
  "${SCRIPT_DIR}/capture_handshake.sh" "${mode}"
  "${SCRIPT_DIR}/run_concurrency.sh" "${mode}" "${PARALLEL}" "${ROUNDS}"
done

echo "Completed matrix runs for: ${MODES[*]}"
