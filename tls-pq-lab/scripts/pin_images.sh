#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

SERVER_TAG="${1:-openquantumsafe/nginx:latest}"
CLIENT_TAG="${2:-openquantumsafe/curl:latest}"
OUT_FILE="${LAB_ROOT}/.env.images"

docker pull "${SERVER_TAG}" >/dev/null
docker pull "${CLIENT_TAG}" >/dev/null

server_digest="$(docker image inspect "${SERVER_TAG}" --format '{{index .RepoDigests 0}}')"
client_digest="$(docker image inspect "${CLIENT_TAG}" --format '{{index .RepoDigests 0}}')"

cat >"${OUT_FILE}" <<EOF
TLS_SERVER_IMAGE=${server_digest}
TLS_CLIENT_IMAGE=${client_digest}
EOF

echo "Saved pinned image env file: ${OUT_FILE}"
echo "Use with: docker compose --env-file .env.images up -d"
