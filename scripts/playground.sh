#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/pqc_common.sh"
source "${SCRIPT_DIR}/interop_adapters.sh"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/playground.sh list [--backend <name>] [--family kem|sig]
  ./scripts/playground.sh run --backend <name> --family kem|sig --alg <name> [--param <set>] [--out <dir>]
  ./scripts/playground.sh vector --backend <name> --vector-file <path> [--out <dir>]
  ./scripts/playground.sh compare --backend-a <name> --backend-b <name> --family kem|sig --alg <name> [--param <set>] [--out <dir>]
EOF
}

emit_meta() {
  local output_dir="$1"
  local payload="$2"
  python3 - "${output_dir}/run-meta.json" "${payload}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(sys.argv[2])
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

run_one() {
  local backend="$1"
  local family="$2"
  local algorithm="$3"
  local output_dir="$4"
  local case_file="${output_dir}/case-${backend}-${family}-${algorithm}.json"

  if ! check_backend_available "${backend}" && [[ "${backend}" != "python" ]]; then
    echo "backend not available: ${backend}" >&2
    return 1
  fi

  if ! adapter_run "${backend}" "${family}" "${algorithm}" "${case_file}"; then
    if [[ ! -f "${case_file}" ]]; then
      python3 - "${case_file}" "${backend}" "${family}" "${algorithm}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "tool": "playground",
    "backend": sys.argv[2],
    "family": sys.argv[3],
    "algorithm": sys.argv[4],
    "status": "error",
    "error_code": "adapter_failed",
    "metrics_ops_per_sec": {},
}
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
    fi
  fi
  printf '%s\n' "${case_file}"
}

COMMAND="${1:-}"
if [[ -z "${COMMAND}" ]]; then
  usage
  exit 1
fi
shift || true

BACKEND=""
BACKEND_A=""
BACKEND_B=""
FAMILY=""
ALG=""
PARAM=""
OUT_DIR=""
VECTOR_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --backend-a)
      BACKEND_A="$2"
      shift 2
      ;;
    --backend-b)
      BACKEND_B="$2"
      shift 2
      ;;
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
    --out)
      OUT_DIR="$2"
      shift 2
      ;;
    --vector-file)
      VECTOR_FILE="$2"
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
    if [[ -z "${FAMILY}" ]]; then
      FAMILY="kem"
    fi
    if [[ -n "${BACKEND}" ]]; then
      adapter_list "${BACKEND}" "${FAMILY}"
      exit 0
    fi

    for candidate in openssl liboqs python; do
      echo "[${candidate}]"
      adapter_list "${candidate}" "${FAMILY}" || true
      echo
    done
    ;;

  run)
    [[ -n "${BACKEND}" && -n "${FAMILY}" && -n "${ALG}" ]] || { usage; exit 1; }
    CANONICAL_ALG="$(canonical_algorithm "${FAMILY}" "${ALG}" "${PARAM}")"
    if [[ -z "${OUT_DIR}" ]]; then
      OUT_DIR="$(ensure_results_dir "playground")"
    else
      mkdir -p "${OUT_DIR}"
    fi

    CASE_FILE="$(run_one "${BACKEND}" "${FAMILY}" "${CANONICAL_ALG}" "${OUT_DIR}")"
    META_PAYLOAD="{\"command\":\"run\",\"backend\":\"${BACKEND}\",\"family\":\"${FAMILY}\",\"algorithm\":\"${CANONICAL_ALG}\",\"case_file\":\"${CASE_FILE}\"}"
    emit_meta "${OUT_DIR}" "${META_PAYLOAD}"
    echo "Wrote: ${CASE_FILE}"
    ;;

  vector)
    [[ -n "${BACKEND}" && -n "${VECTOR_FILE}" ]] || { usage; exit 1; }
    if [[ -z "${OUT_DIR}" ]]; then
      OUT_DIR="$(ensure_results_dir "playground")"
    else
      mkdir -p "${OUT_DIR}"
    fi

    python3 - "${VECTOR_FILE}" "${BACKEND}" "${SCRIPT_DIR}" "${OUT_DIR}" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

vector_file = Path(sys.argv[1]).resolve()
backend = sys.argv[2]
script_dir = Path(sys.argv[3]).resolve()
out_dir = Path(sys.argv[4]).resolve()
cases = json.loads(vector_file.read_text(encoding="utf-8")).get("cases", [])
results = []

for case in cases:
    family = case["family"]
    algorithm = case["algorithm"]
    expected_supported = bool(case.get("expected_supported", True))
    proc = subprocess.run(
        [str(script_dir / "playground.sh"), "list", "--backend", backend, "--family", family],
        check=False,
        capture_output=True,
        text=True,
    )
    supported = algorithm in proc.stdout.splitlines()
    status = "pass" if supported == expected_supported else "fail"
    results.append({
        "id": case.get("id", f"{family}-{algorithm}"),
        "family": family,
        "algorithm": algorithm,
        "expected_supported": expected_supported,
        "supported": supported,
        "status": status,
    })

report = {
    "backend": backend,
    "vector_file": str(vector_file),
    "status": "pass" if all(r["status"] == "pass" for r in results) else "fail",
    "cases": results,
}

(out_dir / "vector-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(out_dir / "vector-report.json")
if report["status"] != "pass":
    raise SystemExit(1)
PY
    ;;

  compare)
    [[ -n "${BACKEND_A}" && -n "${BACKEND_B}" && -n "${FAMILY}" && -n "${ALG}" ]] || { usage; exit 1; }
    CANONICAL_ALG="$(canonical_algorithm "${FAMILY}" "${ALG}" "${PARAM}")"
    if [[ -z "${OUT_DIR}" ]]; then
      OUT_DIR="$(ensure_results_dir "playground")"
    else
      mkdir -p "${OUT_DIR}"
    fi

    LEFT_FILE="$(run_one "${BACKEND_A}" "${FAMILY}" "${CANONICAL_ALG}" "${OUT_DIR}")"
    RIGHT_FILE="$(run_one "${BACKEND_B}" "${FAMILY}" "${CANONICAL_ALG}" "${OUT_DIR}")"
    python3 "${SCRIPT_DIR}/playground_compare.py" --left "${LEFT_FILE}" --right "${RIGHT_FILE}" --output "${OUT_DIR}/compare-${BACKEND_A}-vs-${BACKEND_B}-${FAMILY}-${CANONICAL_ALG}.json"
    echo "Wrote: ${OUT_DIR}/compare-${BACKEND_A}-vs-${BACKEND_B}-${FAMILY}-${CANONICAL_ALG}.json"
    ;;

  *)
    usage
    exit 1
    ;;
esac
