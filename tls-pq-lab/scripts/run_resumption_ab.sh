#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SESSIONS="${1:-1}"
RUNS="${2:-50}"
WARMUP="${3:-5}"

OFF_DIR="${RESULTS_DIR}/resumption/off"
ON_DIR="${RESULTS_DIR}/resumption/on"

echo "Running resumption OFF suite..."
RESULTS_DIR="${OFF_DIR}" "${SCRIPT_DIR}/run_profiles.sh" "${SESSIONS}" "${RUNS}" "${WARMUP}" off

echo "Running resumption ON suite..."
RESULTS_DIR="${ON_DIR}" "${SCRIPT_DIR}/run_profiles.sh" "${SESSIONS}" "${RUNS}" "${WARMUP}" on

echo "A/B complete:"
echo "- OFF: ${OFF_DIR}/profiles/SUMMARY.md"
echo "- ON:  ${ON_DIR}/profiles/SUMMARY.md"
