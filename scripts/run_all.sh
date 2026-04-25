#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/bootstrap.sh"
"${SCRIPT_DIR}/run_profiles.sh" 3 50 5 off

echo "All scenarios completed. Results are in ../results/profiles"
