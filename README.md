# TLS + PQC Benchmark Lab

Reproducible Docker lab for benchmarking TLS handshake behavior across classical, hybrid, and post-quantum cryptography (PQC) modes.

It is designed for repeatable comparative runs, profile-based infrastructure emulation, and report generation you can use in migration decisions.

## What This Lab Measures

- Handshake latency (`p50`, `p95`, `p99`)
- Success/failure rate and error categories
- Host pressure (CPU and memory during concurrency tests)
- Handshake payload size from packet capture (`.pcap`)
- Overhead delta versus classical baseline

## Prerequisites

- Docker Desktop with Compose
- Python 3
- Optional: Wireshark for manual packet inspection
- Optional: `tshark` for automatic TLS handshake message sizing in reports

## Quick Start

```bash
./scripts/bootstrap.sh
./scripts/run_profiles.sh 3 50 5 off
```

This boots the lab and runs the full multi-profile matrix with defaults.

## Sequential Run Order (Recommended)

Use this sequence when you want full control and clean, reproducible outputs.

1) Start clean for profile aggregation:

```bash
rm -rf results/profiles
```

2) Bootstrap containers and baseline certs:

```bash
./scripts/bootstrap.sh
```

3) Capture environment metadata (host + Docker + SLO snapshot):

```bash
./scripts/capture_env.sh
```

4) Run the multi-profile benchmark matrix (randomized mode order per profile):

```bash
./scripts/run_profiles.sh 3 50 5 off
```

5) Review generated reports:

```bash
open results/profiles/SUMMARY.md
open results/profiles/ACCEPTANCE.md
```

Optional post-runs:

- TLS resumption A/B comparison:

```bash
./scripts/run_resumption_ab.sh 1 50 5
```

- One-command end-to-end run:

```bash
./scripts/run_all.sh
```

## Architecture Diagram

```mermaid
flowchart LR
  U[User / CI] --> B[bootstrap.sh]
  B --> D[(Docker Compose)]
  D --> C["tls-client container<br/>(OQS OpenSSL + curl)"]
  D --> S["tls-server container<br/>(OQS NGINX)"]

  R[run_profiles.sh] --> P["Apply infra profile<br/>(tc + docker update)"]
  P --> M["Run mode matrix<br/>classical/kex_pqc/cert_pqc/hybrid/pqc"]
  M --> L["Latency<br/>run_latency.sh"]
  M --> H["Capture<br/>capture_handshake.sh"]
  M --> Q["Concurrency<br/>run_concurrency.sh"]
  M --> SP["Crypto speed<br/>run_speed.sh"]

  L --> O[(results/profiles)]
  H --> O
  Q --> O
  SP --> O

  O --> G[generate_profiles_report.py]
  G --> A[check_acceptance.py]
  A --> F[SUMMARY.md + ACCEPTANCE.md + CSVs]
```

## Experiment Matrix

### Infrastructure profiles

- `dc_lan`: `0ms` delay, `0ms` jitter, `0%` loss, `1gbit`
- `cross_region`: `60ms` delay, `10ms` jitter, `0.1%` loss, `100mbit`
- `mobile_edge`: `120ms` delay, `30ms` jitter, `1%` loss, `10mbit`
- `constrained_cpu`: LAN network + constrained CPU/memory limits
- `burst_gateway`: LAN network + high-burst concurrency profile

Profile definitions live in `config/infra_profiles.csv` and are applied using `tc` and `docker update`.

### TLS crypto modes

- `classical`: RSA-2048 + X25519
- `kex_pqc`: RSA-2048 + ML-KEM-768
- `cert_pqc`: ML-DSA-65 + X25519
- `hybrid`: RSA-2048 + X25519MLKEM768
- `pqc`: ML-DSA-65 + ML-KEM-768

## Core Workflows

### Full profile suite

```bash
./scripts/run_profiles.sh 3 50 5 off
```

Arguments: `<sessions> <latency_runs> <warmup> <resumption_mode>`

- `sessions` default: `3`
- `latency_runs` default: `50`
- `warmup` default: `5`
- `resumption_mode`: `off` or `on`

### TLS resumption A/B suite

```bash
./scripts/run_resumption_ab.sh 1 50 5
```

Generates separate OFF/ON suites under `results/resumption/`.

### One-command default workflow

```bash
./scripts/run_all.sh
```

## Output Layout

Primary output root: `results/profiles/`

Key generated files:

- `results/profiles/SUMMARY.md`
- `results/profiles/summary.csv`
- `results/profiles/heatmap-p95.csv`
- `results/profiles/compatibility-status.csv`
- `results/profiles/ACCEPTANCE.md`

What each file means:

- `results/profiles/ACCEPTANCE.md`: final pass/fail gate against SLO thresholds in `config/slo.env`.
- `results/profiles/SUMMARY.md`: human-readable report for decisions (tables + deltas + compatibility).
- `results/profiles/summary.csv`: machine-readable aggregate metrics (best source for custom charts).
- `results/profiles/heatmap-p95.csv`: profile x mode matrix of handshake `p95` values.
- `results/profiles/compatibility-status.csv`: raw pass/fail rows per `session/profile/mode/step` with reason text.

Per profile/session artifacts:

- `results/profiles/<profile>/sessions/<session-id>/latency-*.csv`
- `results/profiles/<profile>/sessions/<session-id>/concurrency-*.csv`
- `results/profiles/<profile>/sessions/<session-id>/tls-capture-*.pcap`

Session-scoped supporting artifacts:

- `results/profiles/_session-speed/<session-id>/speed-*.txt`: raw `openssl speed` throughput output.
- `results/environment/host-metadata-*.json`: host and Docker metadata snapshot for reproducibility.

## Interpretation Model

Use `classical` as baseline for deltas:

- KEX overhead: `kex_pqc - classical`
- Certificate overhead: `cert_pqc - classical`
- Combined PQC overhead: `pqc - classical`
- Migration profile overhead: `hybrid - classical`

Recommended interpretation flow:

1. Read `results/profiles/ACCEPTANCE.md` first.
   - If this fails, treat performance numbers as diagnostic only, not rollout-ready.
2. Read `results/profiles/SUMMARY.md` next.
   - `Executive Summary` = absolute behavior per profile/mode.
   - `Delta vs Classical` = relative overhead/benefit.
3. Use `results/profiles/summary.csv` for deeper analysis and plotting.

Example decision memo (short format):

- Scope: `3` sessions, `5` infra profiles, `5` crypto modes, resumption `off`.
- Gate result: `ACCEPTANCE.md` is `PASS`/`FAIL` (state exact reason if fail).
- Migration call: choose `hybrid` if p95 overhead stays within SLO and compatibility is clean.
- Pilot call: choose `pqc` when compatibility is acceptable and overhead is tolerable for target profiles.
- Rollout note: prioritize profiles where business latency is most sensitive (`dc_lan` vs `cross_region` etc.).

How to reason about outcomes:

- If deltas are small in `cross_region`/`mobile_edge` but visible in `dc_lan`, network latency dominates and crypto overhead is less user-visible.
- If `constrained_cpu` shows rising `p95` or failures, crypto compute cost is the likely bottleneck.
- If `hybrid` stays near `classical` with clean compatibility, it is typically the safest near-term migration profile.
- If `pqc` has larger overhead or compatibility issues, use it as pilot/target-state rather than immediate default.

Packet-level interpretation:

- Open `results/profiles/<profile>/sessions/<session-id>/tls-capture-*.pcap` in Wireshark for manual handshake inspection.
- If `tshark` is installed, report generation includes handshake message-level sizing automatically.

## Acceptance Checks

Automatically evaluated in `results/profiles/ACCEPTANCE.md`:

- shortlisted modes handshake success >= `99.5%`
- `hybrid` p95 overhead <= `15%` in `dc_lan` and `cross_region`
- no unresolved compatibility blockers

SLO thresholds are configured in `config/slo.env`.

## Additional PQC Utilities

### Algorithm playground

```bash
./scripts/playground.sh list --family kem
./scripts/playground.sh list --family sig
./scripts/playground.sh run --backend openssl --family kem --alg mlkem --param 768
./scripts/playground.sh compare --backend-a openssl --backend-b liboqs --family sig --alg mldsa --param 65
./scripts/playground.sh vector --backend openssl --vector-file vectors/kem/core-support.json
```

See `docs/pqc_playground.md`.

### Interoperability harness

```bash
./scripts/interop.sh matrix --family kem --alg mlkem --param 768 --backends openssl,liboqs,python
./scripts/interop.sh negative --family sig --alg mldsa --param 65 --backends openssl,liboqs,python
./scripts/interop.sh report --run-dir results/interop/<timestamp>
```

See `docs/pqc_interop.md`.

## Troubleshooting

If PQC names are unavailable in your container image:

```bash
docker exec tls-client openssl list -groups
docker exec tls-client openssl list -kem-algorithms
docker exec tls-client openssl list -signature-algorithms
```

Capture reproducibility metadata snapshot:

```bash
./scripts/capture_env.sh
```

## License

Licensed under Apache License 2.0. See `LICENSE`.

## Security and Risk Notice

This repository is for benchmarking and research workflows. It is provided on an "AS IS" basis, without warranties or guarantees. You are responsible for validation and safe usage in your own environment.
