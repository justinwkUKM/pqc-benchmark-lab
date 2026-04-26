#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SESSIONS="${1:-3}"
RUNS="${2:-50}"
WARMUP="${3:-5}"
RESUMPTION="${4:-off}"
RUN_ID="${RUN_ID:-}"

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
  local run_root="$2"
  local session="$3"
  local profile="$4"
  local mode="$5"
  local step="$6"
  shift 6
  local log_file="${run_root}/profiles/${profile}/sessions/${session}/${mode}-${step}.log"
  if "$@" >"${log_file}" 2>&1; then
    log_status "${status_file}" "${session}" "${profile}" "${mode}" "${step}" "pass" ""
    return 0
  fi
  reason="$(tr '\n' ' ' <"${log_file}" | tr ',' ';' | sed 's/  */ /g')"
  reason="${reason:0:240}"
  log_status "${status_file}" "${session}" "${profile}" "${mode}" "${step}" "fail" "${reason}"
  return 1
}

resolve_run_id() {
  if [[ -n "${RUN_ID}" ]]; then
    echo "${RUN_ID}"
    return
  fi
  local short_sha
  short_sha="$(git rev-parse --short HEAD 2>/dev/null || true)"
  if [[ -z "${short_sha}" ]]; then
    short_sha="nogit"
  fi
  echo "run-$(timestamp)-${short_sha}"
}

write_run_manifest() {
  local run_root="$1"
  local run_id="$2"
  local start_utc="$3"
  local end_utc="$4"
  local git_sha
  git_sha="$(git rev-parse HEAD 2>/dev/null || true)"
  python3 - "${run_root}/meta/manifest.json" "${run_id}" "${start_utc}" "${end_utc}" "${SESSIONS}" "${RUNS}" "${WARMUP}" "${RESUMPTION}" "${git_sha}" <<'PY'
import json
import sys

out, run_id, start_utc, end_utc, sessions, runs, warmup, resumption, git_sha = sys.argv[1:]
data = {
    "run_id": run_id,
    "started_utc": start_utc,
    "finished_utc": end_utc,
    "parameters": {
        "sessions": int(sessions),
        "latency_runs": int(runs),
        "warmup": int(warmup),
        "resumption_mode": resumption,
    },
    "git_commit": git_sha,
    "paths": {
        "profiles": "profiles",
        "speed": "speed",
        "reports": "reports",
        "meta": "meta",
    },
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

update_run_index() {
  local run_id="$1"
  local run_root="$2"
  local index_file="${RESULTS_DIR}/runs/index.csv"
  local latest_file="${RESULTS_DIR}/latest-run.txt"
  mkdir -p "${RESULTS_DIR}/runs"
  if [[ ! -f "${index_file}" ]]; then
    echo "run_id,run_root" >"${index_file}"
  fi
  echo "${run_id},${run_root}" >>"${index_file}"
  printf "%s\n" "${run_id}" >"${latest_file}"
}

main() {
  ensure_up
  load_slo

  local run_id
  run_id="$(resolve_run_id)"
  local run_root="${RESULTS_DIR}/runs/${run_id}"
  local reports_root="${run_root}/reports"
  mkdir -p "${run_root}/profiles" "${run_root}/speed" "${run_root}/meta" "${reports_root}"

  local start_utc
  start_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  RESULTS_DIR="${run_root}" "${SCRIPT_DIR}/capture_env.sh"
  cp "${SLO_FILE}" "${run_root}/meta/slo-snapshot.env"

  local suite_root="${run_root}"
  local status_file="${reports_root}/compatibility-status.csv"
  echo "session,profile,mode,step,status,reason" >"${status_file}"

  echo "Run ID: ${run_id}"
  echo "Run root: ${run_root}"

  for s in $(seq 1 "${SESSIONS}"); do
    local session_id
    session_id="session-$(timestamp)-${s}"
    echo "Starting ${session_id}"

    # one raw throughput pass per session
    local speed_root="${suite_root}/speed/${session_id}"
    mkdir -p "${speed_root}"
    RESULTS_DIR="${speed_root}" "${SCRIPT_DIR}/run_speed.sh" || true

    for profile in "${PROFILES[@]}"; do
      echo "Profile: ${profile}"
      apply_infra_profile "${profile}"

      local profile_dir="${suite_root}/profiles/${profile}/sessions/${session_id}"
      mkdir -p "${profile_dir}"

      read -r parallel rounds <<<"$(profile_parallel "${profile}")"
      local shuffled
      shuffled="$(shuffle_modes)"

      for mode in ${shuffled}; do
        echo "  ${profile} :: ${mode}"
        run_step "${status_file}" "${suite_root}" "${session_id}" "${profile}" "${mode}" "latency" \
          env RESULTS_DIR="${profile_dir}" RESUMPTION_MODE="${RESUMPTION}" "${SCRIPT_DIR}/run_latency.sh" "${mode}" "${RUNS}" "${WARMUP}" || true

        run_step "${status_file}" "${suite_root}" "${session_id}" "${profile}" "${mode}" "capture" \
          env RESULTS_DIR="${profile_dir}" RESUMPTION_MODE="${RESUMPTION}" "${SCRIPT_DIR}/capture_handshake.sh" "${mode}" || true

        run_step "${status_file}" "${suite_root}" "${session_id}" "${profile}" "${mode}" "concurrency" \
          env RESULTS_DIR="${profile_dir}" RESUMPTION_MODE="${RESUMPTION}" "${SCRIPT_DIR}/run_concurrency.sh" "${mode}" "${parallel}" "${rounds}" || true
      done
    done
  done

  reset_network_profile
  reset_server_limits

  python3 "${SCRIPT_DIR}/generate_profiles_report.py" --results-dir "${suite_root}" --report-dir "${reports_root}" --slo-file "${SLO_FILE}"
  python3 "${SCRIPT_DIR}/check_acceptance.py" --results-dir "${suite_root}" --report-dir "${reports_root}" --slo-file "${SLO_FILE}"

  local end_utc
  end_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_run_manifest "${run_root}" "${run_id}" "${start_utc}" "${end_utc}"
  update_run_index "${run_id}" "${run_root}"

  echo "Done. See ${reports_root}/SUMMARY.md"
}

main "$@"
