#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

KEEP_LAST="${1:-10}"
MAX_AGE_DAYS="${2:-0}"
DRY_RUN="${3:-true}"

RUNS_DIR="${RESULTS_DIR}/runs"

if [[ ! -d "${RUNS_DIR}" ]]; then
  echo "No runs directory found: ${RUNS_DIR}"
  exit 0
fi

mapfile -t runs < <(ls -1dt "${RUNS_DIR}"/* 2>/dev/null || true)

if [[ "${#runs[@]}" -eq 0 ]]; then
  echo "No run folders found under ${RUNS_DIR}"
  exit 0
fi

to_delete=()

for i in "${!runs[@]}"; do
  if (( i >= KEEP_LAST )); then
    to_delete+=("${runs[$i]}")
  fi
done

if [[ "${MAX_AGE_DAYS}" != "0" ]]; then
  cutoff="$(date -v-"${MAX_AGE_DAYS}"d +%s)"
  for run_dir in "${runs[@]}"; do
    mtime="$(stat -f %m "${run_dir}")"
    if (( mtime < cutoff )); then
      found=false
      for x in "${to_delete[@]:-}"; do
        if [[ "${x}" == "${run_dir}" ]]; then
          found=true
          break
        fi
      done
      if [[ "${found}" == false ]]; then
        to_delete+=("${run_dir}")
      fi
    fi
  done
fi

if [[ "${#to_delete[@]}" -eq 0 ]]; then
  echo "No runs selected for deletion."
  exit 0
fi

echo "Selected runs for deletion (${#to_delete[@]}):"
for d in "${to_delete[@]}"; do
  echo "- ${d}"
done

if [[ "${DRY_RUN}" == "true" ]]; then
  echo "Dry run only. Pass third arg 'false' to delete."
  exit 0
fi

for d in "${to_delete[@]}"; do
  rm -rf "${d}"
done

echo "Deleted ${#to_delete[@]} run folder(s)."
