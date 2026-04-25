#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pqc_common.sh"
source "${SCRIPT_DIR}/interop_adapters.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/interop.sh matrix --family kem|sig --alg <name> [--param <set>] --backends <csv> [--out <dir>]
  ./scripts/interop.sh negative --family kem|sig --alg <name> [--param <set>] --backends <csv> [--out <dir>]
  ./scripts/interop.sh tls --mode <mode> --providers <csv> [--out <dir>]
  ./scripts/interop.sh report --run-dir <results/interop/...>
EOF
}

COMMAND="${1:-}"
if [[ -z "${COMMAND}" ]]; then
  usage
  exit 1
fi
shift || true

FAMILY=""
ALG=""
PARAM=""
BACKENDS="${PQC_BACKENDS_DEFAULT}"
OUT_DIR=""
MODE=""
PROVIDERS=""
RUN_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --family)
      FAMILY="$2"
      shift 2
      ;;
    --alg)
      ALG="$2"
      shift 2
      ;;
    --param)
      PARAM="$2"
      shift 2
      ;;
    --backends)
      BACKENDS="$2"
      shift 2
      ;;
    --out)
      OUT_DIR="$2"
      shift 2
      ;;
    --mode)
      MODE="$2"
      shift 2
      ;;
    --providers)
      PROVIDERS="$2"
      shift 2
      ;;
    --run-dir)
      RUN_DIR="$2"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${OUT_DIR}" && "${COMMAND}" != "report" ]]; then
  OUT_DIR="$(ensure_results_dir "interop")"
elif [[ -n "${OUT_DIR}" ]]; then
  mkdir -p "${OUT_DIR}"
fi

case "${COMMAND}" in
  matrix)
    [[ -n "${FAMILY}" && -n "${ALG}" ]] || { usage; exit 1; }
    CANONICAL_ALG="$(canonical_algorithm "${FAMILY}" "${ALG}" "${PARAM}")"
    split_csv "${BACKENDS}"
    backend_list=("${SPLIT_CSV_RESULT[@]}")
    MATRIX_CSV="${OUT_DIR}/matrix.csv"
    printf 'source_backend,target_backend,status,notes\n' >"${MATRIX_CSV}"

    for src in "${backend_list[@]}"; do
      for dst in "${backend_list[@]}"; do
        COMPARE_DIR="${OUT_DIR}/cases/${src}-to-${dst}"
        mkdir -p "${COMPARE_DIR}"
        if "${SCRIPT_DIR}/playground.sh" compare --backend-a "${src}" --backend-b "${dst}" --family "${FAMILY}" --alg "${CANONICAL_ALG}" --out "${COMPARE_DIR}" >/dev/null 2>&1; then
          printf '%s,%s,pass,comparison_ok\n' "${src}" "${dst}" >>"${MATRIX_CSV}"
        else
          printf '%s,%s,fail,comparison_failed\n' "${src}" "${dst}" >>"${MATRIX_CSV}"
        fi
      done
    done

    META_JSON="${OUT_DIR}/run-meta.json"
    python3 - "${META_JSON}" "${FAMILY}" "${CANONICAL_ALG}" <<'PY'
import json
import sys
from pathlib import Path

payload = {
    "run_id": Path(sys.argv[1]).parent.name,
    "family": sys.argv[2],
    "algorithm": sys.argv[3],
}
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

    python3 "${SCRIPT_DIR}/interop_matrix.py" --matrix-csv "${MATRIX_CSV}" --output "${OUT_DIR}/REPORT.md" --metadata-json "${META_JSON}"
    echo "Wrote: ${OUT_DIR}/REPORT.md"
    ;;

  negative)
    [[ -n "${FAMILY}" && -n "${ALG}" ]] || { usage; exit 1; }
    CANONICAL_ALG="$(canonical_algorithm "${FAMILY}" "${ALG}" "${PARAM}")"
    split_csv "${BACKENDS}"
    backend_list=("${SPLIT_CSV_RESULT[@]}")
    NEG_CSV="${OUT_DIR}/negative.csv"
    printf 'backend,case,status,notes\n' >"${NEG_CSV}"
    for backend in "${backend_list[@]}"; do
      BAD_FILE="${OUT_DIR}/cases/negative-${backend}.json"
      if adapter_run "${backend}" "${FAMILY}" "definitely_not_an_algorithm" "${BAD_FILE}" >/dev/null 2>&1; then
        printf '%s,invalid_algorithm,fail,unexpected_success\n' "${backend}" >>"${NEG_CSV}"
      else
        printf '%s,invalid_algorithm,pass,rejected_invalid_algorithm\n' "${backend}" >>"${NEG_CSV}"
      fi

      GOOD_FILE="${OUT_DIR}/cases/sanity-${backend}.json"
      if adapter_run "${backend}" "${FAMILY}" "${CANONICAL_ALG}" "${GOOD_FILE}" >/dev/null 2>&1; then
        printf '%s,sanity_valid_algorithm,pass,accepted_valid_algorithm\n' "${backend}" >>"${NEG_CSV}"
      else
        printf '%s,sanity_valid_algorithm,fail,rejected_valid_algorithm\n' "${backend}" >>"${NEG_CSV}"
      fi
    done
    echo "Wrote: ${NEG_CSV}"
    ;;

  tls)
    [[ -n "${MODE}" ]] || { usage; exit 1; }
    if [[ -z "${PROVIDERS}" ]]; then
      PROVIDERS="${PQC_BACKENDS_DEFAULT}"
    fi
    split_csv "${PROVIDERS}"
    provider_list=("${SPLIT_CSV_RESULT[@]}")
    TLS_CSV="${OUT_DIR}/tls.csv"
    printf 'provider,mode,status,notes\n' >"${TLS_CSV}"
    for provider in "${provider_list[@]}"; do
      if "${SCRIPT_DIR}/set_mode.sh" "${MODE}" >/dev/null 2>&1; then
        if probe_connection "${MODE}" >/dev/null 2>&1; then
          printf '%s,%s,pass,handshake_ok\n' "${provider}" "${MODE}" >>"${TLS_CSV}"
        else
          printf '%s,%s,fail,probe_failed\n' "${provider}" "${MODE}" >>"${TLS_CSV}"
        fi
      else
        printf '%s,%s,fail,set_mode_failed\n' "${provider}" "${MODE}" >>"${TLS_CSV}"
      fi
    done
    echo "Wrote: ${TLS_CSV}"
    ;;

  report)
    [[ -n "${RUN_DIR}" ]] || { usage; exit 1; }
    python3 "${SCRIPT_DIR}/interop_matrix.py" \
      --matrix-csv "${RUN_DIR}/matrix.csv" \
      --negative-csv "${RUN_DIR}/negative.csv" \
      --output "${RUN_DIR}/REPORT.md" \
      --metadata-json "${RUN_DIR}/run-meta.json"
    echo "Wrote: ${RUN_DIR}/REPORT.md"
    ;;

  *)
    usage
    exit 1
    ;;
esac
