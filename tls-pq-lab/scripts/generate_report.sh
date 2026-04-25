#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

python3 "${SCRIPT_DIR}/generate_report.py" --results-dir "${ROOT_DIR}/results" "$@"
