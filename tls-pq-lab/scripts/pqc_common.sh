#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

PQC_BACKENDS_DEFAULT="openssl,liboqs,python"

canonical_algorithm() {
  local family="$1"
  local alg="$2"
  local param="${3:-}"
  local normalized

  normalized="$(printf '%s' "${alg}" | tr '[:upper:]' '[:lower:]' | tr -d ' -_')"

  if [[ "${family}" == "kem" ]]; then
    case "${normalized}" in
      mlkem|kyber)
        case "${param}" in
          512|768|1024) echo "mlkem${param}" ;;
          *) echo "mlkem768" ;;
        esac
        ;;
      mlkem512|mlkem768|mlkem1024)
        echo "${normalized}"
        ;;
      *)
        echo "${normalized}"
        ;;
    esac
    return 0
  fi

  case "${normalized}" in
    mldsa|dilithium)
      case "${param}" in
        44|65|87) echo "mldsa${param}" ;;
        *) echo "mldsa65" ;;
      esac
      ;;
    mldsa44|mldsa65|mldsa87|falcon512|falcon1024|sphincssha2128fsimple|sphincs)
      if [[ "${normalized}" == "sphincs" ]]; then
        echo "sphincssha2128fsimple"
      else
        echo "${normalized}"
      fi
      ;;
    *)
      echo "${normalized}"
      ;;
  esac
}

split_csv() {
  local input="$1"
  local -n out_ref=$2
  local item
  IFS=',' read -r -a out_ref <<<"${input}"
  for item in "${!out_ref[@]}"; do
    out_ref["${item}"]="$(printf '%s' "${out_ref["${item}"]}" | xargs)"
  done
}

ensure_results_dir() {
  local bucket="$1"
  local dir="${RESULTS_DIR}/${bucket}/$(timestamp)"
  mkdir -p "${dir}"
  printf '%s\n' "${dir}"
}

adapter_script() {
  local backend="$1"
  printf '%s\n' "${SCRIPT_DIR}/adapters/${backend}_adapter.sh"
}

check_backend_available() {
  local backend="$1"
  local script_path
  script_path="$(adapter_script "${backend}")"
  [[ -x "${script_path}" ]]
}

json_escape() {
  python3 - "$1" <<'PY'
import json
import sys
print(json.dumps(sys.argv[1]))
PY
}
