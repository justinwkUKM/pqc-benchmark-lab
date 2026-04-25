# TLS + PQC Lab

Reproducible Docker lab for comparative analysis of classical, hybrid, and PQC TLS across multiple infrastructure profiles.

## Prerequisites

- Docker Desktop running
- Wireshark installed on host (optional for manual `.pcap` analysis)
- Optional: `tshark` for automatic handshake message sizing in reports

## Phase 0: Freeze Test Conditions

- Docker images are pinned by digest in `docker-compose.yml`.
- SLO thresholds are in `config/slo.env`.
- Host metadata capture script: `scripts/capture_env.sh`.
- Optional digest refresh script: `scripts/pin_images.sh`.

Capture metadata and SLO snapshot:

```bash
./scripts/capture_env.sh
```

## Profiles and Scenarios

### Infra profiles (implemented)

- `dc_lan`: `0ms` delay, `0ms` jitter, `0%` loss, `1gbit`
- `cross_region`: `60ms` delay, `10ms` jitter, `0.1%` loss, `100mbit`
- `mobile_edge`: `120ms` delay, `30ms` jitter, `1%` loss, `10mbit`
- `constrained_cpu`: LAN network + `--cpus 0.5 --memory 512m`
- `burst_gateway`: LAN network + high burst concurrency profile

Definitions are documented in `config/infra_profiles.csv` and applied with `tc` + `docker update`.

### Crypto modes (scenario matrix)

- `classical`: RSA-2048 + X25519
- `kex_pqc`: RSA-2048 + ML-KEM-768
- `cert_pqc`: ML-DSA-65 + X25519
- `hybrid`: RSA-2048 + X25519MLKEM768
- `pqc`: ML-DSA-65 + ML-KEM-768

## Full Multi-Profile Experiment

This implements randomized mode order per profile, 3 sessions by default, and report aggregation by median across sessions.

```bash
./scripts/run_profiles.sh 3 50 5 off
```

Arguments: `<sessions> <latency_runs> <warmup> <resumption_mode>`

- `sessions`: default `3`
- `latency_runs`: default `50`
- `warmup`: default `5`
- `resumption_mode`: `off` or `on`

Workload settings:

- Latency: 50 samples, 5 warmup
- Concurrency: 10 rounds x 100 parallel (except `burst_gateway`: 20 x 200)
- Packet capture: 1+ handshake capture per scenario/profile/session
- Throughput: one `openssl speed` pass per session

## Optional Resumption A/B

```bash
./scripts/run_resumption_ab.sh 1 50 5
```

Generates separate OFF vs ON suites under `results/resumption/`.

## Outputs

Primary output directory:

- `results/profiles/`

Generated artifacts:

- `results/profiles/SUMMARY.md`
- `results/profiles/summary.csv`
- `results/profiles/heatmap-p95.csv`
- `results/profiles/compatibility-status.csv`
- `results/profiles/ACCEPTANCE.md`

Per profile/session artifacts:

- `results/profiles/<profile>/sessions/<session-id>/latency-*.csv`
- `results/profiles/<profile>/sessions/<session-id>/concurrency-*.csv`
- `results/profiles/<profile>/sessions/<session-id>/tls-capture-*.pcap`

## Metrics Implemented

- TLS latency: `p50/p95/p99`
- Success rate and error counts/types
- CPU peak/avg and memory peak/avg
- Payload size: pcap bytes and TLS handshake message bytes when `tshark` is available
- Delta vs baseline (`classical`) per profile
- Decomposition support:
  - KEX effect = `kex_pqc - classical`
  - Cert effect = `cert_pqc - classical`
  - Combined PQC = `pqc - classical`
  - Migration overhead = `hybrid - classical`

## Acceptance Criteria

Evaluated automatically in `results/profiles/ACCEPTANCE.md`:

- shortlisted modes handshake success >= `99.5%`
- `hybrid` p95 overhead <= `15%` in `dc_lan` and `cross_region`
- no unresolved compatibility blockers

## Quick Start

```bash
./scripts/bootstrap.sh
./scripts/run_profiles.sh 3 50 5 off
```

## Additional PQC Utilities

### Algorithm playground

```bash
./scripts/playground.sh list --family kem
./scripts/playground.sh list --family sig
./scripts/playground.sh run --backend openssl --family kem --alg mlkem --param 768
./scripts/playground.sh compare --backend-a openssl --backend-b liboqs --family sig --alg mldsa --param 65
./scripts/playground.sh vector --backend openssl --vector-file vectors/kem/core-support.json
```

See `docs/pqc_playground.md` for complete usage.

### Interoperability harness

```bash
./scripts/interop.sh matrix --family kem --alg mlkem --param 768 --backends openssl,liboqs,python
./scripts/interop.sh negative --family sig --alg mldsa --param 65 --backends openssl,liboqs,python
./scripts/interop.sh report --run-dir results/interop/<timestamp>
```

See `docs/pqc_interop.md` for complete usage.

## Notes

- If PQC names are unavailable in your image build, verify:

```bash
docker exec tls-client openssl list -groups
docker exec tls-client openssl list -kem-algorithms
docker exec tls-client openssl list -signature-algorithms
```

- To rerun the end-to-end default workflow:

```bash
./scripts/run_all.sh
```
