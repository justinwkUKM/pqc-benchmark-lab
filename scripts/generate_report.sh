#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

RESULTS_DIR="${1:-${ROOT_DIR}/results}"
REPORT_DIR="${2:-${RESULTS_DIR}/reports}"
SLO_FILE="${3:-${ROOT_DIR}/config/slo.env}"

python3 "${SCRIPT_DIR}/generate_profiles_report.py" --results-dir "${RESULTS_DIR}" --report-dir "${REPORT_DIR}" --slo-file "${SLO_FILE}"
python3 "${SCRIPT_DIR}/check_acceptance.py" --results-dir "${RESULTS_DIR}" --report-dir "${REPORT_DIR}" --slo-file "${SLO_FILE}"
python3 "${SCRIPT_DIR}/generate_phase3_analytics.py" --results-dir "${RESULTS_DIR}" --report-dir "${REPORT_DIR}"
python3 "${SCRIPT_DIR}/score_profiles.py" \
  --summary-csv "${REPORT_DIR}/summary.csv" \
  --compat-csv "${REPORT_DIR}/compatibility-status.csv" \
  --preset balanced \
  --output-md "${REPORT_DIR}/DECISION_BRIEF.md" \
  --output-csv "${REPORT_DIR}/decision-scores.csv"
