#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODE="${1:-classical}"
PARALLEL="${2:-100}"
ROUNDS="${3:-10}"
RESUMPTION_MODE="${RESUMPTION_MODE:-off}"
CURL_HTTP_VERSION="${CURL_HTTP_VERSION:-http1.1}"
KEEPALIVE_MODE="${KEEPALIVE_MODE:-}"
MTLS_MODE="${MTLS_MODE:-off}"
LOAD_PATTERN="${LOAD_PATTERN:-steady}"

if [[ -z "${KEEPALIVE_MODE}" ]]; then
  if [[ "${RESUMPTION_MODE}" == "off" ]]; then
    KEEPALIVE_MODE="close"
  else
    KEEPALIVE_MODE="keepalive"
  fi
fi

if [[ "${CURL_HTTP_VERSION}" == "http2" ]]; then
  HTTP_FLAGS="--http2"
else
  HTTP_FLAGS="--http1.1"
fi

MTLS_FLAGS=""
if [[ "${MTLS_MODE}" == "on" && -f "${LAB_ROOT}/certs/client.crt" && -f "${LAB_ROOT}/certs/client.key" ]]; then
  MTLS_FLAGS="--cert /opt/nginx/certs/client.crt --key /opt/nginx/certs/client.key"
fi

parallel_for_round() {
  local round="$1"
  case "${LOAD_PATTERN}" in
    ramp)
      python3 - "${PARALLEL}" "${ROUNDS}" "${round}" <<'PY'
import math
import sys
max_parallel = int(sys.argv[1])
rounds = int(sys.argv[2])
round_index = int(sys.argv[3])
step = max(1, math.ceil(max_parallel / max(1, rounds)))
value = min(max_parallel, step * round_index)
print(value)
PY
      ;;
    burst)
      if (( round % 3 == 0 )); then
        echo "$((PARALLEL * 2))"
      else
        echo "${PARALLEL}"
      fi
      ;;
    *)
      echo "${PARALLEL}"
      ;;
  esac
}

OUT_CSV="${RESULTS_DIR}/concurrency-${MODE}-$(timestamp).csv"
echo "round,target_parallel,ok,fail,cpu_perc,mem_usage,mem_perc,pids" >"${OUT_CSV}"

set_mode "${MODE}"

echo "Running concurrency test: mode=${MODE}, parallel=${PARALLEL}, rounds=${ROUNDS}, resumption=${RESUMPTION_MODE}, keepalive=${KEEPALIVE_MODE}, load_pattern=${LOAD_PATTERN}"
for r in $(seq 1 "${ROUNDS}"); do
  target_parallel="$(parallel_for_round "${r}")"
  counts="$(docker exec tls-client sh -lc "tmp=\$(mktemp -d); for i in \$(seq 1 ${target_parallel}); do keep=''; case '${KEEPALIVE_MODE}' in close) keep=\"--no-keepalive -H 'Connection: close'\" ;; keepalive) keep='' ;; mix30) if [ \$((i % 10)) -lt 3 ]; then keep=\"--no-keepalive -H 'Connection: close'\"; fi ;; mix50) if [ \$((i % 2)) -eq 0 ]; then keep=\"--no-keepalive -H 'Connection: close'\"; fi ;; mix70) if [ \$((i % 10)) -lt 7 ]; then keep=\"--no-keepalive -H 'Connection: close'\"; fi ;; esac; (if curl -s ${HTTP_FLAGS} --cacert /opt/nginx/certs/server.crt ${MTLS_FLAGS} \$keep https://tls-server:4433 >/dev/null 2>/dev/null; then echo ok >\"\${tmp}/\${i}\"; else echo fail >\"\${tmp}/\${i}\"; fi) & done; wait; ok=\$(grep -c '^ok$' \"\${tmp}\"/* 2>/dev/null || true); fail=\$(grep -c '^fail$' \"\${tmp}\"/* 2>/dev/null || true); rm -rf \"\${tmp}\"; echo \"\${ok},\${fail}\"")"
  stat_line="$(docker stats tls-server --no-stream --format '{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.PIDs}}')"
  echo "${r},${target_parallel},${counts},${stat_line}" >>"${OUT_CSV}"
done

echo "Saved: ${OUT_CSV}"
