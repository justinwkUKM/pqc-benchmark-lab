#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/common.sh"

MODE="${1:-classical}"
OUT_PCAP="${RESULTS_DIR}/tls-capture-${MODE}-$(timestamp).pcap"
NETWORK_NAME="tls-pq-lab_pq-net"
RESUMPTION_MODE="${RESUMPTION_MODE:-off}"

CURL_FLAGS=(--http1.1 --cacert /opt/nginx/certs/server.crt)
if [[ "${RESUMPTION_MODE}" == "off" ]]; then
  CURL_FLAGS+=(--no-keepalive -H "Connection: close")
fi

set_mode "${MODE}"

if docker ps -a --format '{{.Names}}' | grep -q '^sniffer$'; then
  docker rm -f sniffer >/dev/null
fi

echo "Starting tcpdump capture on ${NETWORK_NAME}..."
docker run -d --name sniffer --network "${NETWORK_NAME}" nicolaka/netshoot \
  tcpdump -i any port 4433 -w /tmp/tls-capture.pcap >/dev/null

sleep 1
docker exec tls-client curl -s "${CURL_FLAGS[@]}" https://tls-server:4433 >/dev/null

docker stop sniffer >/dev/null
docker cp sniffer:/tmp/tls-capture.pcap "${OUT_PCAP}"
docker rm sniffer >/dev/null

echo "Saved: ${OUT_PCAP}"
echo "Open in Wireshark and filter: tls.handshake.type == 2"
