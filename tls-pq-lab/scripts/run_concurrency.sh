#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODE="${1:-classical}"
PARALLEL="${2:-100}"
ROUNDS="${3:-10}"
RESUMPTION_MODE="${RESUMPTION_MODE:-off}"

CURL_FLAGS="--http1.1 --cacert /opt/nginx/certs/server.crt"
if [[ "${RESUMPTION_MODE}" == "off" ]]; then
  CURL_FLAGS+=" --no-keepalive -H 'Connection: close'"
fi

OUT_CSV="${RESULTS_DIR}/concurrency-${MODE}-$(timestamp).csv"
echo "round,ok,fail,cpu_perc,mem_usage,mem_perc,pids" >"${OUT_CSV}"

set_mode "${MODE}"

echo "Running concurrency test: mode=${MODE}, parallel=${PARALLEL}, rounds=${ROUNDS}, resumption=${RESUMPTION_MODE}"
for r in $(seq 1 "${ROUNDS}"); do
  counts="$(docker exec tls-client sh -lc "tmp=\$(mktemp -d); for i in \$(seq 1 ${PARALLEL}); do (if curl -s ${CURL_FLAGS} https://tls-server:4433 >/dev/null 2>/dev/null; then echo ok >\"\${tmp}/\${i}\"; else echo fail >\"\${tmp}/\${i}\"; fi) & done; wait; ok=\$(grep -c '^ok$' \"\${tmp}\"/* 2>/dev/null || true); fail=\$(grep -c '^fail$' \"\${tmp}\"/* 2>/dev/null || true); rm -rf \"\${tmp}\"; echo \"\${ok},\${fail}\"")"
  stat_line="$(docker stats tls-server --no-stream --format '{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.PIDs}}')"
  echo "${r},${counts},${stat_line}" >>"${OUT_CSV}"
done

echo "Saved: ${OUT_CSV}"
