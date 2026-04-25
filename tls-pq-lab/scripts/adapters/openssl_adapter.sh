#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common.sh"

usage() {
  cat <<'EOF'
Usage:
  openssl_adapter.sh list --family kem|sig
  openssl_adapter.sh run --family kem|sig --algorithm <name> --out <json-path>
EOF
}

list_family() {
  local family="$1"
  ensure_up >/dev/null
  if [[ "${family}" == "kem" ]]; then
    docker exec tls-client openssl list -kem-algorithms | tr -d '{}' | awk '{print $1}' | sort -u
    return 0
  fi
  docker exec tls-client openssl list -signature-algorithms | tr -d '{}' | awk '{print $1}' | sort -u
}

emit_run_json() {
  local out_path="$1"
  local backend="$2"
  local family="$3"
  local algorithm="$4"
  local status="$5"
  local reason="$6"
  local raw_file="$7"
  local parser_script
  parser_script="${SCRIPT_DIR}/../parse_speed.py"
  python3 "${parser_script}" \
    --backend "${backend}" \
    --family "${family}" \
    --algorithm "${algorithm}" \
    --status "${status}" \
    --reason "${reason}" \
    --raw-file "${raw_file}" \
    --output "${out_path}"
}

run_speed() {
  local family="$1"
  local algorithm="$2"
  local out_path="$3"
  local raw_file
  raw_file="$(mktemp)"
  ensure_up >/dev/null

  if [[ "${family}" == "kem" ]]; then
    if docker exec tls-client openssl speed -seconds 1 -mr -kem-algorithms "${algorithm}" >"${raw_file}" 2>&1; then
      emit_run_json "${out_path}" "openssl" "${family}" "${algorithm}" "ok" "" "${raw_file}"
    else
      emit_run_json "${out_path}" "openssl" "${family}" "${algorithm}" "error" "benchmark_failed" "${raw_file}"
      return 1
    fi
    return 0
  fi

  if docker exec tls-client openssl speed -seconds 1 -mr -signature-algorithms "${algorithm}" >"${raw_file}" 2>&1; then
    emit_run_json "${out_path}" "openssl" "${family}" "${algorithm}" "ok" "" "${raw_file}"
  else
    emit_run_json "${out_path}" "openssl" "${family}" "${algorithm}" "error" "benchmark_failed" "${raw_file}"
    return 1
  fi
}

COMMAND="${1:-}"
shift || true

FAMILY=""
ALGORITHM=""
OUT_PATH=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --family)
      FAMILY="$2"
      shift 2
      ;;
    --algorithm)
      ALGORITHM="$2"
      shift 2
      ;;
    --out)
      OUT_PATH="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

case "${COMMAND}" in
  list)
    [[ -n "${FAMILY}" ]] || { usage; exit 1; }
    list_family "${FAMILY}"
    ;;
  run)
    [[ -n "${FAMILY}" && -n "${ALGORITHM}" && -n "${OUT_PATH}" ]] || { usage; exit 1; }
    run_speed "${FAMILY}" "${ALGORITHM}" "${OUT_PATH}"
    ;;
  *)
    usage
    exit 1
    ;;
esac
