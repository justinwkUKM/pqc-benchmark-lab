#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

OUT_FILE="${RESULTS_DIR}/speed-$(timestamp).txt"

run_case() {
  local title="$1"
  shift

  {
    echo ""
    echo "===== ${title} ====="
    echo "cmd: $*"
  } >>"${OUT_FILE}"

  if docker exec tls-client "$@" >>"${OUT_FILE}" 2>&1; then
    echo "status: ok" >>"${OUT_FILE}"
  else
    echo "status: failed" >>"${OUT_FILE}"
  fi
}

ensure_up

echo "Recording algorithm throughput benchmarks..."
echo "timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"${OUT_FILE}"

run_case "ECDH P-256" openssl speed ecdhp256
run_case "ML-KEM-768" openssl speed -kem mlkem768
run_case "RSA-2048" openssl speed rsa2048
run_case "ML-DSA-65" openssl speed -sig mldsa65

echo "Saved: ${OUT_FILE}"
