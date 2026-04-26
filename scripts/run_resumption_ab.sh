#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SESSIONS="${1:-1}"
RUNS="${2:-50}"
WARMUP="${3:-5}"

PARENT_RUN_ID="${RUN_ID:-resumption-$(timestamp)}"
OFF_RUN_ID="${PARENT_RUN_ID}-off"
ON_RUN_ID="${PARENT_RUN_ID}-on"

echo "Running resumption OFF suite..."
RUN_ID="${OFF_RUN_ID}" "${SCRIPT_DIR}/run_profiles.sh" "${SESSIONS}" "${RUNS}" "${WARMUP}" off

echo "Running resumption ON suite..."
RUN_ID="${ON_RUN_ID}" "${SCRIPT_DIR}/run_profiles.sh" "${SESSIONS}" "${RUNS}" "${WARMUP}" on

echo "A/B complete:"
echo "- OFF: ${RESULTS_DIR}/runs/${OFF_RUN_ID}/reports/SUMMARY.md"
echo "- ON:  ${RESULTS_DIR}/runs/${ON_RUN_ID}/reports/SUMMARY.md"
