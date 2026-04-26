#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

FAILURES=0
WARNINGS=0

check_cmd() {
  local cmd="$1"
  local label="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ok] ${label}: $(command -v "${cmd}")"
  else
    echo "[fail] ${label}: missing command '${cmd}'"
    FAILURES=$((FAILURES + 1))
  fi
}

check_optional_cmd() {
  local cmd="$1"
  local label="$2"
  if command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ok] ${label}: $(command -v "${cmd}")"
  else
    echo "[warn] ${label}: command '${cmd}' not found (optional)"
    WARNINGS=$((WARNINGS + 1))
  fi
}

check_file() {
  local file_path="$1"
  if [[ -f "${file_path}" ]]; then
    echo "[ok] file present: ${file_path}"
  else
    echo "[fail] missing file: ${file_path}"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "== PQC Lab Doctor =="
echo "root: ${ROOT_DIR}"

check_cmd docker "Docker"
check_cmd python3 "Python 3"
check_cmd openssl "OpenSSL"
check_optional_cmd tshark "tshark"

if docker compose version >/dev/null 2>&1; then
  echo "[ok] Docker Compose plugin available"
elif command -v docker-compose >/dev/null 2>&1; then
  echo "[ok] docker-compose binary available"
else
  echo "[fail] Docker Compose not available"
  FAILURES=$((FAILURES + 1))
fi

if docker info >/dev/null 2>&1; then
  echo "[ok] Docker daemon reachable"
else
  echo "[fail] Docker daemon is not reachable; start Docker Desktop"
  FAILURES=$((FAILURES + 1))
fi

check_file "${ROOT_DIR}/docker-compose.yml"
check_file "${ROOT_DIR}/config/modes.csv"
check_file "${ROOT_DIR}/config/infra_profiles.csv"
check_file "${ROOT_DIR}/config/workloads.csv"
check_file "${ROOT_DIR}/config/suites.csv"
check_file "${ROOT_DIR}/config/scoring_profiles.yaml"

if python3 "${ROOT_DIR}/scripts/validate_config.py" >/dev/null 2>&1; then
  echo "[ok] configuration validation passed"
else
  echo "[fail] configuration validation failed (run python3 scripts/validate_config.py)"
  FAILURES=$((FAILURES + 1))
fi

if grep -q "@sha256:" "${ROOT_DIR}/docker-compose.yml"; then
  echo "[ok] docker image digests appear pinned"
else
  echo "[warn] docker images are not pinned by digest"
  WARNINGS=$((WARNINGS + 1))
fi

if [[ -f "${ROOT_DIR}/results/runs/index.csv" ]]; then
  echo "[ok] run index present"
else
  echo "[warn] run index missing; it will be generated after first run"
  WARNINGS=$((WARNINGS + 1))
fi

echo
echo "Doctor summary: failures=${FAILURES}, warnings=${WARNINGS}"

if [[ "${FAILURES}" -gt 0 ]]; then
  exit 1
fi

exit 0
