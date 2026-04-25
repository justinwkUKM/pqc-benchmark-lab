#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pqc_common.sh"

adapter_list() {
  local backend="$1"
  local family="$2"
  local script_path
  script_path="$(adapter_script "${backend}")"
  if [[ "${backend}" == "python" ]]; then
    python3 "${SCRIPT_DIR}/adapters/python_adapter.py" list --family "${family}"
    return 0
  fi
  "${script_path}" list --family "${family}"
}

adapter_run() {
  local backend="$1"
  local family="$2"
  local algorithm="$3"
  local out_path="$4"
  local script_path
  script_path="$(adapter_script "${backend}")"

  if [[ "${backend}" == "python" ]]; then
    python3 "${SCRIPT_DIR}/adapters/python_adapter.py" run --family "${family}" --algorithm "${algorithm}" --out "${out_path}"
    return $?
  fi

  "${script_path}" run --family "${family}" --algorithm "${algorithm}" --out "${out_path}"
}
