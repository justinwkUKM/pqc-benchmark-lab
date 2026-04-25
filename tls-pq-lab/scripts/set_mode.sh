#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODE="${1:-classical}"

if [[ "${MODE}" == "--help" || "${MODE}" == "-h" ]]; then
  cat <<'EOF'
Usage: ./scripts/set_mode.sh <mode>

Modes:
  classical        RSA-2048 cert + X25519 key exchange
  kex_pqc          RSA-2048 cert + ML-KEM-768 key exchange
  cert_pqc         ML-DSA-65 cert + X25519 key exchange
  hybrid           RSA-2048 cert + X25519MLKEM768 key exchange
  pqc              ML-DSA-65 cert + ML-KEM-768 key exchange
  hybrid_pqc_cert  ML-DSA-65 cert + X25519MLKEM768 key exchange
EOF
  exit 0
fi

echo "Switching mode to: ${MODE}"
set_mode "${MODE}"

echo "Mode '${MODE}' is active. Probe output:"
probe_connection "${MODE}"
