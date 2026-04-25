#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

echo "Starting containers..."
ensure_up

if [[ ! -f "${LAB_ROOT}/certs/curl-format.txt" ]]; then
  cat >"${LAB_ROOT}/certs/curl-format.txt" <<'EOF'

DNS Lookup:   %{time_namelookup}s
TCP Connect:  %{time_connect}s
TLS Setup:    %{time_appconnect}s
First Byte:   %{time_starttransfer}s
Total Time:   %{time_total}s
EOF
fi

echo "Initializing default mode: classical"
set_mode classical

echo "Lab is ready."
echo "- Project root: ${LAB_ROOT}"
echo "- Verify endpoint: docker exec tls-client curl -s -k https://tls-server:4433"
