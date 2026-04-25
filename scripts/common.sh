#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LAB_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${LAB_ROOT}/docker-compose.yml"
RESULTS_DIR="${RESULTS_DIR:-${LAB_ROOT}/results}"
SLO_FILE="${SLO_FILE:-${LAB_ROOT}/config/slo.env}"

mkdir -p "${RESULTS_DIR}" "${LAB_ROOT}/certs"

compose_bin() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    echo "Docker Compose is not available. Install Docker Desktop or docker-compose." >&2
    exit 1
  fi
}

dc() {
  local bin
  bin="$(compose_bin)"
  if [[ "${bin}" == "docker compose" ]]; then
    docker compose -f "${COMPOSE_FILE}" "$@"
  else
    docker-compose -f "${COMPOSE_FILE}" "$@"
  fi
}

ensure_up() {
  dc up -d
  if ! docker ps --format '{{.Names}}' | grep -q '^tls-server$'; then
    echo "tls-server container is not running" >&2
    exit 1
  fi
  if ! docker ps --format '{{.Names}}' | grep -q '^tls-client$'; then
    echo "tls-client container is not running" >&2
    exit 1
  fi
}

reload_server() {
  docker exec tls-server nginx -t >/dev/null
  docker exec tls-server nginx -s reload >/dev/null
}

mode_group() {
  case "$1" in
    classical) echo "X25519" ;;
    kex_pqc) echo "mlkem768" ;;
    cert_pqc) echo "X25519" ;;
    pqc) echo "mlkem768" ;;
    hybrid) echo "X25519MLKEM768" ;;
    hybrid_pqc_cert) echo "X25519MLKEM768" ;;
    *)
      echo "unknown mode: $1" >&2
      return 1
      ;;
  esac
}

generate_cert() {
  local mode="$1"
  case "${mode}" in
    classical|kex_pqc|hybrid)
      docker exec tls-client openssl req -x509 -newkey rsa:2048 -nodes \
        -keyout /opt/nginx/certs/server.key \
        -out /opt/nginx/certs/server.crt \
        -days 365 -subj "/CN=tls-server" >/dev/null 2>&1
      ;;
    cert_pqc|pqc|hybrid_pqc_cert)
      docker exec tls-client openssl req -x509 -newkey mldsa65 -nodes \
        -keyout /opt/nginx/certs/server.key \
        -out /opt/nginx/certs/server.crt \
        -days 365 -subj "/CN=tls-server" >/dev/null 2>&1
      ;;
    *)
      echo "unknown mode: ${mode}" >&2
      return 1
      ;;
  esac
}

probe_connection() {
  local group
  group="$(mode_group "$1")"
  docker exec tls-client openssl s_client -connect tls-server:4433 -groups "${group}" -CAfile /opt/nginx/certs/server.crt -partial_chain -brief </dev/null
}

set_mode() {
  local mode="$1"
  ensure_up
  generate_cert "${mode}"
  reload_server
  probe_connection "${mode}" >/dev/null
}

timestamp() {
  date +%Y%m%d-%H%M%S
}

load_slo() {
  if [[ -f "${SLO_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${SLO_FILE}"
  fi
  SLO_HANDSHAKE_SUCCESS_MIN="${SLO_HANDSHAKE_SUCCESS_MIN:-99.5}"
  SLO_TLS_P95_MAX="${SLO_TLS_P95_MAX:-0.050}"
  SLO_HYBRID_P95_OVERHEAD_MAX="${SLO_HYBRID_P95_OVERHEAD_MAX:-15.0}"
}

_tc_exec() {
  local cmd="$1"
  docker run --rm --network container:tls-client --cap-add NET_ADMIN nicolaka/netshoot \
    sh -lc "${cmd}"
}

reset_network_profile() {
  _tc_exec "tc qdisc del dev eth0 root >/dev/null 2>&1 || true" >/dev/null
}

apply_network_profile() {
  local delay_ms="$1"
  local jitter_ms="$2"
  local loss_pct="$3"
  local bandwidth="$4"
  local root="root"
  local netem_args=""

  reset_network_profile

  if [[ "${bandwidth}" != "none" ]]; then
    _tc_exec "tc qdisc add dev eth0 root handle 1: tbf rate ${bandwidth} burst 64kbit latency 500ms"
    root="parent 1:1"
  fi

  if [[ "${delay_ms}" != "0" || "${jitter_ms}" != "0" || "${loss_pct}" != "0" ]]; then
    if [[ "${delay_ms}" != "0" ]]; then
      netem_args+=" delay ${delay_ms}ms"
      if [[ "${jitter_ms}" != "0" ]]; then
        netem_args+=" ${jitter_ms}ms distribution normal"
      fi
    fi
    if [[ "${loss_pct}" != "0" ]]; then
      netem_args+=" loss ${loss_pct}%"
    fi
    _tc_exec "tc qdisc add dev eth0 ${root} handle 10: netem${netem_args}"
  fi
}

reset_server_limits() {
  docker update --cpus 0 --memory 0 tls-server >/dev/null 2>&1 || true
}

apply_server_limits() {
  local cpus="$1"
  local memory="$2"
  if [[ "${cpus}" == "none" ]]; then
    reset_server_limits
    return
  fi
  docker update --cpus "${cpus}" --memory "${memory}" tls-server >/dev/null
}

apply_infra_profile() {
  local profile="$1"
  case "${profile}" in
    dc_lan)
      apply_server_limits none none
      apply_network_profile 0 0 0 1gbit
      ;;
    cross_region)
      apply_server_limits none none
      apply_network_profile 60 10 0.1 100mbit
      ;;
    mobile_edge)
      apply_server_limits none none
      apply_network_profile 120 30 1 10mbit
      ;;
    constrained_cpu)
      apply_server_limits 0.5 512m
      apply_network_profile 0 0 0 1gbit
      ;;
    burst_gateway)
      apply_server_limits none none
      apply_network_profile 0 0 0 1gbit
      ;;
    *)
      echo "Unknown infra profile: ${profile}" >&2
      return 1
      ;;
  esac
}
