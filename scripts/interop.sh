#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pqc_common.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/interop.sh matrix --family kem|sig --alg <name> [--param <set>] --backends <csv> [--kem-mode cross-backend|local-only] [--out <dir>]
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
PROVIDERS="${PQC_BACKENDS_DEFAULT}"
KEM_MODE="cross-backend"
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
    --kem-mode)
      KEM_MODE="$2"
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
    python3 "${SCRIPT_DIR}/interop_runner.py" --command matrix --out-dir "${OUT_DIR}" --family "${FAMILY}" --algorithm "${CANONICAL_ALG}" --backends "${BACKENDS}" --kem-mode "${KEM_MODE}"
    ;;
  negative)
    [[ -n "${FAMILY}" && -n "${ALG}" ]] || { usage; exit 1; }
    CANONICAL_ALG="$(canonical_algorithm "${FAMILY}" "${ALG}" "${PARAM}")"
    python3 "${SCRIPT_DIR}/interop_runner.py" --command negative --out-dir "${OUT_DIR}" --family "${FAMILY}" --algorithm "${CANONICAL_ALG}" --backends "${BACKENDS}"
    ;;
  tls)
    [[ -n "${MODE}" ]] || { usage; exit 1; }
    python3 "${SCRIPT_DIR}/interop_runner.py" --command tls --out-dir "${OUT_DIR}" --mode "${MODE}" --providers "${PROVIDERS}"
    ;;
  report)
    [[ -n "${RUN_DIR}" ]] || { usage; exit 1; }
    python3 "${SCRIPT_DIR}/interop_runner.py" --command report --run-dir "${RUN_DIR}"
    ;;
  *)
    usage
    exit 1
    ;;
esac

echo "Interop artifacts written under: ${OUT_DIR:-${RUN_DIR}}"
