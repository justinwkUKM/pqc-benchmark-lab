#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODE="${1:-classical}"
RUNS="${2:-30}"
WARMUP="${3:-5}"
RESUMPTION_MODE="${RESUMPTION_MODE:-off}"
CURL_HTTP_VERSION="${CURL_HTTP_VERSION:-http1.1}"
KEEPALIVE_MODE="${KEEPALIVE_MODE:-}"
MTLS_MODE="${MTLS_MODE:-off}"

if [[ -z "${KEEPALIVE_MODE}" ]]; then
  if [[ "${RESUMPTION_MODE}" == "off" ]]; then
    KEEPALIVE_MODE="close"
  else
    KEEPALIVE_MODE="keepalive"
  fi
fi

build_curl_flags() {
  local run_idx="$1"
  CURL_FLAGS=(--cacert /opt/nginx/certs/server.crt)
  case "${CURL_HTTP_VERSION}" in
    http2) CURL_FLAGS+=(--http2) ;;
    *) CURL_FLAGS+=(--http1.1) ;;
  esac
  if [[ "${MTLS_MODE}" == "on" && -f "${LAB_ROOT}/certs/client.crt" && -f "${LAB_ROOT}/certs/client.key" ]]; then
    CURL_FLAGS+=(--cert /opt/nginx/certs/client.crt --key /opt/nginx/certs/client.key)
  fi
  case "${KEEPALIVE_MODE}" in
    close)
      CURL_FLAGS+=(--no-keepalive -H "Connection: close")
      ;;
    keepalive)
      ;;
    mix30)
      if (( run_idx % 10 < 3 )); then
        CURL_FLAGS+=(--no-keepalive -H "Connection: close")
      fi
      ;;
    mix50)
      if (( run_idx % 2 == 0 )); then
        CURL_FLAGS+=(--no-keepalive -H "Connection: close")
      fi
      ;;
    mix70)
      if (( run_idx % 10 < 7 )); then
        CURL_FLAGS+=(--no-keepalive -H "Connection: close")
      fi
      ;;
    *)
      ;;
  esac
}

set_mode "${MODE}"

OUT_CSV="${RESULTS_DIR}/latency-${MODE}-$(timestamp).csv"
echo "run,success,error,dns_lookup,tcp_connect,tls_setup,first_byte,total" >"${OUT_CSV}"

echo "Warmup: ${WARMUP} handshakes (resumption=${RESUMPTION_MODE})"
for i in $(seq 1 "${WARMUP}"); do
  build_curl_flags "${i}"
  docker exec tls-client curl -o /dev/null -s "${CURL_FLAGS[@]}" https://tls-server:4433 >/dev/null 2>&1 || true
done

echo "Measuring latency: mode=${MODE}, runs=${RUNS}, keepalive=${KEEPALIVE_MODE}, http=${CURL_HTTP_VERSION}, mtls=${MTLS_MODE}"
for i in $(seq 1 "${RUNS}"); do
  TMP_ERR="$(mktemp)"
  build_curl_flags "${i}"
  if line="$(docker exec tls-client curl -w '%{time_namelookup},%{time_connect},%{time_appconnect},%{time_starttransfer},%{time_total}' -o /dev/null -s "${CURL_FLAGS[@]}" https://tls-server:4433 2>"${TMP_ERR}")"; then
    echo "${i},1,,${line}" >>"${OUT_CSV}"
  else
    err="$(tr '\n' ' ' <"${TMP_ERR}" | tr ',' ';' | sed 's/  */ /g')"
    err="${err:0:200}"
    echo "${i},0,${err},0,0,0,0,0" >>"${OUT_CSV}"
  fi
  rm -f "${TMP_ERR}"
done

python3 - "${OUT_CSV}" <<'PY'
import csv
import statistics
import sys

path = sys.argv[1]
rows = []
with open(path, newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        rows.append(row)

ok = [x for x in rows if x.get('success') == '1']
tls = sorted(float(x['tls_setup']) for x in ok)
tot = sorted(float(x['total']) for x in ok)
success_rate = (len(ok) / len(rows) * 100.0) if rows else 0.0

def p95(vals):
    if not vals:
        return float('nan')
    idx = int(round(0.95 * (len(vals) - 1)))
    return vals[idx]

print(f"samples={len(rows)}")
print(f"success={len(ok)}")
print(f"success_rate={success_rate:.2f}%")
if ok:
    print(f"tls_setup_median={statistics.median(tls):.6f}s")
    print(f"tls_setup_p95={p95(tls):.6f}s")
    print(f"total_median={statistics.median(tot):.6f}s")
    print(f"total_p95={p95(tot):.6f}s")
else:
    print("tls_setup_median=N/A")
    print("tls_setup_p95=N/A")
    print("total_median=N/A")
    print("total_p95=N/A")
PY

echo "Saved: ${OUT_CSV}"
