#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SESSIONS="${1:-3}"
RUNS="${2:-50}"
WARMUP="${3:-5}"
RESUMPTION="${4:-off}"
RUN_ID="${RUN_ID:-}"
RUN_SEED="${RUN_SEED:-}"
MODE_ORDER_STRATEGY="${MODE_ORDER_STRATEGY:-seeded_random}"
PROFILE_FILTER_CSV="${PROFILE_FILTER_CSV:-all}"
MODE_FILTER_CSV="${MODE_FILTER_CSV:-all}"
WORKLOAD_PARALLEL="${WORKLOAD_PARALLEL:-}"
WORKLOAD_ROUNDS="${WORKLOAD_ROUNDS:-}"
RUN_WORKLOAD_NAME="${RUN_WORKLOAD_NAME:-custom}"

PROFILES=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && PROFILES+=("${line}")
done < <(python3 "${SCRIPT_DIR}/config_query.py" profiles)

MODES=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && MODES+=("${line}")
done < <(python3 "${SCRIPT_DIR}/config_query.py" modes)

PROFILE_FILTER=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && PROFILE_FILTER+=("${line}")
done < <(python3 "${SCRIPT_DIR}/config_query.py" expand --field profiles --value "${PROFILE_FILTER_CSV}")

MODE_FILTER=()
while IFS= read -r line; do
  [[ -n "${line}" ]] && MODE_FILTER+=("${line}")
done < <(python3 "${SCRIPT_DIR}/config_query.py" expand --field modes --value "${MODE_FILTER_CSV}")

if [[ "${#PROFILE_FILTER[@]}" -gt 0 ]]; then
  FILTERED_PROFILES=()
  for val in "${PROFILES[@]}"; do
    for allowed in "${PROFILE_FILTER[@]}"; do
      if [[ "${val}" == "${allowed}" ]]; then
        FILTERED_PROFILES+=("${val}")
        break
      fi
    done
  done
  PROFILES=("${FILTERED_PROFILES[@]}")
fi

if [[ "${#MODE_FILTER[@]}" -gt 0 ]]; then
  FILTERED_MODES=()
  for val in "${MODES[@]}"; do
    for allowed in "${MODE_FILTER[@]}"; do
      if [[ "${val}" == "${allowed}" ]]; then
        FILTERED_MODES+=("${val}")
        break
      fi
    done
  done
  MODES=("${FILTERED_MODES[@]}")
fi

shuffle_modes() {
  local session_index="$1"
  local profile="$2"
  python3 - "${MODE_ORDER_STRATEGY}" "${RUN_SEED}" "${session_index}" "${profile}" "${MODES[@]}" <<'PY'
import random
import sys
import hashlib

strategy = sys.argv[1]
seed = sys.argv[2]
session_index = sys.argv[3]
profile = sys.argv[4]
vals = sys.argv[5:]

if strategy == "fixed":
    print(" ".join(vals))
    raise SystemExit(0)

if not seed:
    seed = "0"
material = f"{seed}:{session_index}:{profile}".encode("utf-8")
seed_int = int(hashlib.sha256(material).hexdigest()[:16], 16)
rng = random.Random(seed_int)
rng.shuffle(vals)
print(" ".join(vals))
PY
}

profile_parallel() {
  if [[ -n "${WORKLOAD_PARALLEL}" && -n "${WORKLOAD_ROUNDS}" ]]; then
    echo "${WORKLOAD_PARALLEL} ${WORKLOAD_ROUNDS}"
    return 0
  fi
  python3 "${SCRIPT_DIR}/config_query.py" profile-parallel --profile "$1"
}

log_mode_order() {
  local file="$1"
  local session="$2"
  local profile="$3"
  local order="$4"
  echo "${session},${profile},${order}" >>"${file}"
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
  python3 - "${run_root}/meta/manifest.json" "${run_id}" "${start_utc}" "${end_utc}" "${SESSIONS}" "${RUNS}" "${WARMUP}" "${RESUMPTION}" "${git_sha}" "${RUN_SEED}" "${MODE_ORDER_STRATEGY}" "${RUN_WORKLOAD_NAME}" "${PROFILE_FILTER_CSV}" "${MODE_FILTER_CSV}" <<'PY'
import json
import sys

out, run_id, start_utc, end_utc, sessions, runs, warmup, resumption, git_sha, run_seed, mode_order_strategy, workload_name, profile_filter, mode_filter = sys.argv[1:]
data = {
    "run_id": run_id,
    "started_utc": start_utc,
    "finished_utc": end_utc,
    "parameters": {
        "sessions": int(sessions),
        "latency_runs": int(runs),
        "warmup": int(warmup),
        "resumption_mode": resumption,
        "run_seed": run_seed,
        "mode_order_strategy": mode_order_strategy,
        "workload_name": workload_name,
        "profile_filter": profile_filter,
        "mode_filter": mode_filter,
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
  local started_utc="$3"
  local finished_utc="$4"
  local acceptance_overall="$5"
  local index_file="${RESULTS_DIR}/runs/index.csv"
  local latest_file="${RESULTS_DIR}/latest-run.txt"
  mkdir -p "${RESULTS_DIR}/runs"
  if [[ ! -f "${index_file}" ]]; then
    echo "run_id,run_root,started_utc,finished_utc,workload,sessions,latency_runs,resumption_mode,acceptance_overall" >"${index_file}"
  fi
  if ! grep -q "^run_id,run_root,started_utc" "${index_file}"; then
    local tmp_index
    tmp_index="$(mktemp)"
    echo "run_id,run_root,started_utc,finished_utc,workload,sessions,latency_runs,resumption_mode,acceptance_overall" >"${tmp_index}"
    tail -n +2 "${index_file}" | while IFS= read -r line; do
      [[ -z "${line}" ]] && continue
      echo "${line},N/A,N/A,N/A,N/A,N/A,N/A" >>"${tmp_index}"
    done
    mv "${tmp_index}" "${index_file}"
  fi
  echo "${run_id},${run_root},${started_utc},${finished_utc},${RUN_WORKLOAD_NAME},${SESSIONS},${RUNS},${RESUMPTION},${acceptance_overall}" >>"${index_file}"
  printf "%s\n" "${run_id}" >"${latest_file}"
}

main() {
  python3 "${SCRIPT_DIR}/validate_config.py"
  if [[ "${#PROFILES[@]}" -eq 0 ]]; then
    echo "No profiles selected after filtering." >&2
    exit 1
  fi
  if [[ "${#MODES[@]}" -eq 0 ]]; then
    echo "No modes selected after filtering." >&2
    exit 1
  fi
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
  local mode_order_file="${run_root}/meta/mode-order.csv"
  echo "session,profile,mode,step,status,reason" >"${status_file}"
  echo "session,profile,mode_order" >"${mode_order_file}"

  echo "Run ID: ${run_id}"
  echo "Run root: ${run_root}"
  echo "Run seed: ${RUN_SEED:-auto}"

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
      shuffled="$(shuffle_modes "${s}" "${profile}")"
      log_mode_order "${mode_order_file}" "${session_id}" "${profile}" "${shuffled}"

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
  python3 "${SCRIPT_DIR}/generate_phase3_analytics.py" --results-dir "${suite_root}" --report-dir "${reports_root}"
  python3 "${SCRIPT_DIR}/score_profiles.py" \
    --summary-csv "${reports_root}/summary.csv" \
    --compat-csv "${reports_root}/compatibility-status.csv" \
    --preset balanced \
    --output-md "${reports_root}/DECISION_BRIEF.md" \
    --output-csv "${reports_root}/decision-scores.csv"

  local acceptance_overall
  acceptance_overall="UNKNOWN"
  if grep -q "Overall: PASS" "${reports_root}/ACCEPTANCE.md"; then
    acceptance_overall="PASS"
  elif grep -q "Overall: FAIL" "${reports_root}/ACCEPTANCE.md"; then
    acceptance_overall="FAIL"
  fi

  local end_utc
  end_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_run_manifest "${run_root}" "${run_id}" "${start_utc}" "${end_utc}"
  update_run_index "${run_id}" "${run_root}" "${start_utc}" "${end_utc}" "${acceptance_overall}"
  python3 "${SCRIPT_DIR}/export_trends.py" --runs-index "${RESULTS_DIR}/runs/index.csv" --output-dir "${RESULTS_DIR}/trends"

  echo "Done. See ${reports_root}/SUMMARY.md"
}

main "$@"
