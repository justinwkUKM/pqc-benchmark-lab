#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SESSIONS="${1:-3}"
RUNS="${2:-50}"
WARMUP="${3:-5}"
RESUMPTION="${4:-off}"

PROFILES=(dc_lan cross_region mobile_edge constrained_cpu burst_gateway)
MODES=(classical kex_pqc cert_pqc hybrid pqc)

shuffle_modes() {
  python3 - "${MODES[@]}" <<'PY'
import random
import sys

vals = sys.argv[1:]
random.shuffle(vals)
print(" ".join(vals))
PY
}

profile_parallel() {
  case "$1" in
    burst_gateway) echo "200 20" ;;
    *) echo "100 10" ;;
  esac
}

log_status() {
  local file="$1"
  local session="$2"
  local profile="$3"
  local mode="$4"
  local step="$5"
  local status="$6"
  local reason="$7"
  echo "${session},${profile},${mode},${step},${status},${reason}" >>"${file}"
}

run_step() {
  local status_file="$1"
  local session="$2"
  local profile="$3"
  local mode="$4"
  local step="$5"
  shift 5
  local log_file="$RESULTS_DIR/profiles/${profile}/sessions/${session}/${mode}-${step}.log"
  if "$@" >"${log_file}" 2>&1; then
    log_status "${status_file}" "${session}" "${profile}" "${mode}" "${step}" "pass" ""
    return 0
  fi
  reason="$(tr '\n' ' ' <"${log_file}" | tr ',' ';' | sed 's/  */ /g')"
  reason="${reason:0:240}"
  log_status "${status_file}" "${session}" "${profile}" "${mode}" "${step}" "fail" "${reason}"
  return 1
}

main() {
  ensure_up
  load_slo

  "${SCRIPT_DIR}/capture_env.sh"

  local suite_root="${RESULTS_DIR}/profiles"
  mkdir -p "${suite_root}"
  local status_file="${suite_root}/compatibility-status.csv"
  echo "session,profile,mode,step,status,reason" >"${status_file}"

  for s in $(seq 1 "${SESSIONS}"); do
    local session_id
    session_id="session-$(timestamp)-${s}"
    echo "Starting ${session_id}"

    # one raw throughput pass per session
    local speed_root="${suite_root}/_session-speed/${session_id}"
    mkdir -p "${speed_root}"
    RESULTS_DIR="${speed_root}" "${SCRIPT_DIR}/run_speed.sh" || true

    for profile in "${PROFILES[@]}"; do
      echo "Profile: ${profile}"
      apply_infra_profile "${profile}"

      local profile_dir="${suite_root}/${profile}/sessions/${session_id}"
      mkdir -p "${profile_dir}"

      read -r parallel rounds <<<"$(profile_parallel "${profile}")"
      local shuffled
      shuffled="$(shuffle_modes)"

      for mode in ${shuffled}; do
        echo "  ${profile} :: ${mode}"
        run_step "${status_file}" "${session_id}" "${profile}" "${mode}" "latency" \
          env RESULTS_DIR="${profile_dir}" RESUMPTION_MODE="${RESUMPTION}" "${SCRIPT_DIR}/run_latency.sh" "${mode}" "${RUNS}" "${WARMUP}" || true

        run_step "${status_file}" "${session_id}" "${profile}" "${mode}" "capture" \
          env RESULTS_DIR="${profile_dir}" RESUMPTION_MODE="${RESUMPTION}" "${SCRIPT_DIR}/capture_handshake.sh" "${mode}" || true

        run_step "${status_file}" "${session_id}" "${profile}" "${mode}" "concurrency" \
          env RESULTS_DIR="${profile_dir}" RESUMPTION_MODE="${RESUMPTION}" "${SCRIPT_DIR}/run_concurrency.sh" "${mode}" "${parallel}" "${rounds}" || true
      done
    done
  done

  reset_network_profile
  reset_server_limits

  python3 "${SCRIPT_DIR}/generate_profiles_report.py" --results-dir "${suite_root}" --slo-file "${SLO_FILE}"
  python3 "${SCRIPT_DIR}/check_acceptance.py" --results-dir "${suite_root}" --slo-file "${SLO_FILE}"

  echo "Done. See ${suite_root}/SUMMARY.md"
}

main "$@"
