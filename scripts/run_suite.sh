#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SUITE="broad_coverage"
SESSIONS_OVERRIDE=""
SEED_OVERRIDE=""
RUN_ID_PREFIX="suite"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_suite.sh [--suite <name>] [--sessions <n>] [--seed <int>] [--run-id-prefix <value>]

Examples:
  ./scripts/run_suite.sh --suite broad_coverage
  ./scripts/run_suite.sh --suite stress_pattern --seed 4242
  ./scripts/run_suite.sh --suite quick --sessions 1

List suites:
  python3 scripts/config_query.py suites
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite)
      SUITE="$2"
      shift 2
      ;;
    --sessions)
      SESSIONS_OVERRIDE="$2"
      shift 2
      ;;
    --seed)
      SEED_OVERRIDE="$2"
      shift 2
      ;;
    --run-id-prefix)
      RUN_ID_PREFIX="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

python3 "${SCRIPT_DIR}/validate_config.py" >/dev/null

suite_json="$(python3 "${SCRIPT_DIR}/config_query.py" suite-get --name "${SUITE}")"
read -r WORKLOAD SUITE_SESSIONS PROFILES_SPEC MODES_SPEC SEED_STRATEGY <<<"$(python3 - "${suite_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(
    payload.get("workload", ""),
    payload.get("sessions", "1"),
    payload.get("profiles", "all"),
    payload.get("modes", "all"),
    payload.get("seed_strategy", "seeded"),
)
PY
)"

workload_json="$(python3 "${SCRIPT_DIR}/config_query.py" workload-get --name "${WORKLOAD}")"
read -r LATENCY_RUNS WARMUP RESUMPTION_MODE PARALLEL ROUNDS HTTP_VERSION KEEPALIVE_MIX MTLS_MODE LOAD_PATTERN MODE_ORDER_STRATEGY <<<"$(python3 - "${workload_json}" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
print(
    payload.get("latency_runs", "50"),
    payload.get("warmup", "5"),
    payload.get("resumption_mode", "off"),
    payload.get("parallel", "100"),
    payload.get("rounds", "10"),
    payload.get("http_version", "http1.1"),
    payload.get("keepalive_mix", "close"),
    payload.get("mtls_mode", "off"),
    payload.get("load_pattern", "steady"),
    payload.get("mode_order_strategy", "seeded_random"),
)
PY
)"

if [[ -n "${SESSIONS_OVERRIDE}" ]]; then
  SUITE_SESSIONS="${SESSIONS_OVERRIDE}"
fi

RUN_SEED_VALUE=""
if [[ -n "${SEED_OVERRIDE}" ]]; then
  RUN_SEED_VALUE="${SEED_OVERRIDE}"
elif [[ "${SEED_STRATEGY}" == "fixed" ]]; then
  RUN_SEED_VALUE="1337"
else
  RUN_SEED_VALUE="$(date +%s)"
fi

RUN_ID_VALUE="${RUN_ID_PREFIX}-${SUITE}-$(timestamp)"

echo "Running suite: ${SUITE}"
echo "- workload: ${WORKLOAD}"
echo "- sessions: ${SUITE_SESSIONS}"
echo "- runs/warmup: ${LATENCY_RUNS}/${WARMUP}"
echo "- resumption: ${RESUMPTION_MODE}"
echo "- keepalive: ${KEEPALIVE_MIX}"
echo "- load pattern: ${LOAD_PATTERN}"
echo "- mode order: ${MODE_ORDER_STRATEGY}"
echo "- seed: ${RUN_SEED_VALUE}"

RUN_ID="${RUN_ID_VALUE}" \
RUN_SEED="${RUN_SEED_VALUE}" \
RUN_WORKLOAD_NAME="${WORKLOAD}" \
WORKLOAD_PARALLEL="${PARALLEL}" \
WORKLOAD_ROUNDS="${ROUNDS}" \
CURL_HTTP_VERSION="${HTTP_VERSION}" \
KEEPALIVE_MODE="${KEEPALIVE_MIX}" \
MTLS_MODE="${MTLS_MODE}" \
LOAD_PATTERN="${LOAD_PATTERN}" \
MODE_ORDER_STRATEGY="${MODE_ORDER_STRATEGY}" \
PROFILE_FILTER_CSV="${PROFILES_SPEC}" \
MODE_FILTER_CSV="${MODES_SPEC}" \
"${SCRIPT_DIR}/run_profiles.sh" "${SUITE_SESSIONS}" "${LATENCY_RUNS}" "${WARMUP}" "${RESUMPTION_MODE}"

echo "Suite completed."
echo "Run ID: ${RUN_ID_VALUE}"
echo "Reports: ${RESULTS_DIR}/runs/${RUN_ID_VALUE}/reports"
