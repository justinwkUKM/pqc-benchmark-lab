#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

RUNS="${1:-100}"
WARMUP="${2:-10}"
PARALLEL="${3:-200}"
ROUNDS="${4:-20}"

MODES=(classical kex_pqc cert_pqc hybrid pqc)
PROFILES=(stress_lan stress_cpu_bound stress_extreme)

set_server_limits() {
  local profile="$1"
  case "${profile}" in
    stress_lan)
      docker update --cpus 0 --memory 0 tls-server >/dev/null 2>&1 || true
      ;;
    stress_cpu_bound)
      docker update --cpus 0.5 --memory 256m tls-server >/dev/null
      ;;
    stress_extreme)
      docker update --cpus 0.75 --memory 512m tls-server >/dev/null
      ;;
    *)
      echo "Unknown profile: ${profile}" >&2
      return 1
      ;;
  esac
}

summarize_profile() {
  local profile="$1"
  local profile_dir="${RESULTS_DIR}/stress/${profile}"
  mkdir -p "${profile_dir}"
  python3 "${SCRIPT_DIR}/generate_report.py" --results-dir "${profile_dir}" --output "${profile_dir}/REPORT.md" >/dev/null
}

main() {
  ensure_up

  for profile in "${PROFILES[@]}"; do
    echo ""
    echo "=== Running profile: ${profile} ==="
    set_server_limits "${profile}"

    for mode in "${MODES[@]}"; do
      echo "-- ${profile} :: ${mode}"
      profile_results="${RESULTS_DIR}/stress/${profile}"
      mkdir -p "${profile_results}"

      if ! RESULTS_DIR="${profile_results}" "${SCRIPT_DIR}/run_latency.sh" "${mode}" "${RUNS}" "${WARMUP}"; then
        echo "WARN: latency run failed for ${profile}/${mode}"
      fi
      if ! RESULTS_DIR="${profile_results}" "${SCRIPT_DIR}/capture_handshake.sh" "${mode}"; then
        echo "WARN: capture run failed for ${profile}/${mode}"
      fi
      if ! RESULTS_DIR="${profile_results}" "${SCRIPT_DIR}/run_concurrency.sh" "${mode}" "${PARALLEL}" "${ROUNDS}"; then
        echo "WARN: concurrency run failed for ${profile}/${mode}"
      fi
    done

    RESULTS_DIR="${RESULTS_DIR}/stress/${profile}" "${SCRIPT_DIR}/run_speed.sh" || echo "WARN: speed run failed for ${profile}"
    summarize_profile "${profile}"
  done

  docker update --cpus 0 --memory 0 tls-server >/dev/null 2>&1 || true

  echo ""
  echo "Stress suite complete. Profile reports:"
  for profile in "${PROFILES[@]}"; do
    echo "- ${RESULTS_DIR}/stress/${profile}/REPORT.md"
  done
}

main "$@"
