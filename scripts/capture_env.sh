#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

OUT_DIR="${RESULTS_DIR}/meta"
OUT_FILE="${OUT_DIR}/host-metadata.json"
mkdir -p "${OUT_DIR}"

load_slo

python3 - "$OUT_FILE" <<'PY'
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


out_file = sys.argv[1]
data = {
    "captured_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "host": {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "mac_model": run(["sysctl", "-n", "hw.model"]),
        "cpu_cores_logical": run(["sysctl", "-n", "hw.logicalcpu"]),
        "cpu_cores_physical": run(["sysctl", "-n", "hw.physicalcpu"]),
        "memory_bytes": run(["sysctl", "-n", "hw.memsize"]),
        "macos_version": run(["sw_vers", "-productVersion"]),
    },
    "docker": {
        "docker_version": run(["docker", "version", "--format", "{{json .}}"]),
        "docker_info": run(["docker", "info", "--format", "{{json .}}"]),
    },
}

with open(out_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY

echo "Saved: ${OUT_FILE}"
echo "SLO file: ${SLO_FILE}"
echo "- handshake success min: ${SLO_HANDSHAKE_SUCCESS_MIN}%"
echo "- tls p95 max: ${SLO_TLS_P95_MAX}s"
echo "- hybrid p95 overhead max: ${SLO_HYBRID_P95_OVERHEAD_MAX}%"
