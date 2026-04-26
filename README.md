# TLS + PQC Benchmark Lab

This repository is a reproducible benchmarking lab for evaluating TLS migration options across:

- classical cryptography,
- hybrid classical+PQC,
- pure post-quantum cryptography (PQC).

It helps engineering teams answer practical rollout questions with repeatable data instead of one-off spot checks.

## Why this repository matters

Organizations need to prepare for post-quantum cryptography, but migration decisions are constrained by latency, compatibility, and infrastructure cost.

This lab is important because it lets you:

- quantify handshake overhead by mode,
- separate KEX overhead from certificate-signature overhead,
- test behavior under multiple realistic network/host profiles,
- apply acceptance gates before recommending rollout.

## What this repository can do

### 1) Infrastructure profile emulation

Runs the same crypto matrix across these profiles:

- `dc_lan`: near-zero latency datacenter path
- `cross_region`: 60ms/10ms jitter/0.1% loss/100mbit
- `mobile_edge`: 120ms/30ms jitter/1% loss/10mbit
- `constrained_cpu`: LAN network with server CPU+memory caps
- `burst_gateway`: LAN network with high burst concurrency

Profiles are defined in `config/infra_profiles.csv` and applied via `tc` + `docker update`.

### 2) TLS crypto scenario matrix

Supported benchmark modes:

- `classical`: RSA-2048 + X25519
- `kex_pqc`: RSA-2048 + ML-KEM-768
- `cert_pqc`: ML-DSA-65 + X25519
- `hybrid`: RSA-2048 + X25519MLKEM768
- `pqc`: ML-DSA-65 + ML-KEM-768

### 3) Measurement workflows

- Latency sampling (`p50`, `p95`, `p99`)
- Concurrency pressure (`ok/fail` by round, CPU/memory snapshots)
- TLS packet capture (`.pcap` artifacts)
- Raw crypto throughput (`openssl speed`)

### 4) Run isolation and traceability

Each `run_profiles.sh` execution generates a unique run ID and stores all artifacts in one folder:

- `results/runs/<run-id>/...`

No cross-run mixing occurs in report generation.

### 5) Reporting and gates

Per run, the lab generates:

- `reports/SUMMARY.md`
- `reports/summary.csv`
- `reports/heatmap-p95.csv`
- `reports/compatibility-status.csv`
- `reports/ACCEPTANCE.md`

Acceptance checks are driven by thresholds in `config/slo.env`.

### 6) Optional A/B session resumption analysis

`run_resumption_ab.sh` runs OFF/ON resumption suites as separate run IDs for direct comparison.

## Prerequisites

- Docker Desktop with Compose
- Python 3
- Optional: Wireshark
- Optional: `tshark` (for message-level handshake sizing in report generation)

## Quick start

```bash
./scripts/bootstrap.sh
./scripts/run_profiles.sh 3 50 5 off
```

Open the latest run reports:

```bash
RUN_ID="$(cat results/latest-run.txt)"
open "results/runs/${RUN_ID}/reports/SUMMARY.md"
open "results/runs/${RUN_ID}/reports/ACCEPTANCE.md"
```

## How to use each major capability

### Full profile matrix (recommended default)

```bash
./scripts/run_profiles.sh 3 50 5 off
```

Arguments: `<sessions> <latency_runs> <warmup> <resumption_mode>`

- `sessions`: independent repeats for median aggregation (default `3`)
- `latency_runs`: handshake samples per mode/profile/session (default `50`)
- `warmup`: warmup handshakes before sampling (default `5`)
- `resumption_mode`: `off` or `on`

### Assign a custom run ID

```bash
RUN_ID="release-candidate-01" ./scripts/run_profiles.sh 3 50 5 off
```

### Run resumption OFF/ON A/B

```bash
./scripts/run_resumption_ab.sh 1 50 5
```

### Single command workflow

```bash
./scripts/run_all.sh
```

### Capture environment metadata only

```bash
./scripts/capture_env.sh
```

### Refresh pinned image digests

```bash
./scripts/pin_images.sh
```

### Cleanup old run folders (retention)

Dry run:

```bash
./scripts/cleanup_runs.sh 10 0 true
```

Delete:

```bash
./scripts/cleanup_runs.sh 10 0 false
```

## Output layout (per run)

`results/runs/<run-id>/`

- `meta/`
  - `manifest.json` (run parameters + timing + git commit)
  - `host-metadata.json` (host and docker metadata)
  - `slo-snapshot.env` (SLO snapshot used during run)
- `profiles/<profile>/sessions/<session-id>/`
  - `latency-*.csv`
  - `concurrency-*.csv`
  - `tls-capture-*.pcap`
  - per-step logs
- `speed/<session-id>/speed-*.txt`
- `reports/`
  - `SUMMARY.md`
  - `summary.csv`
  - `heatmap-p95.csv`
  - `compatibility-status.csv`
  - `ACCEPTANCE.md`

Global helpers:

- `results/latest-run.txt`
- `results/runs/index.csv`

## How to interpret the results

Use this order every time:

1. `ACCEPTANCE.md`
   - Go/no-go gate.
   - If FAIL, treat performance data as diagnostic only.

2. `SUMMARY.md`
   - `Executive Summary` = absolute behavior per profile/mode.
   - `Delta vs Classical` = migration overhead relative to baseline.
   - `Compatibility` = operational risk visibility.

3. `summary.csv` and `heatmap-p95.csv`
   - Use for custom charts, dashboards, and release decision docs.

Interpretation decomposition:

- KEX effect = `kex_pqc - classical`
- Certificate effect = `cert_pqc - classical`
- Combined PQC effect = `pqc - classical`
- Migration overhead = `hybrid - classical`

Decision heuristics:

- If `dc_lan` deltas are visible but `cross_region`/`mobile_edge` are small, network latency dominates user-visible impact.
- If `constrained_cpu` regresses sharply, crypto compute is likely your bottleneck.
- If `hybrid` stays close to baseline with clean compatibility, it is usually the safest near-term rollout path.
- If `pqc` is secure-forward but less compatible, use as pilot/target-state before default rollout.

Packet-level interpretation:

- Inspect `tls-capture-*.pcap` in Wireshark for handshake structure and size.
- If `tshark` is present, report generation includes handshake message-level sizing automatically.

## Reproducibility checklist

- Keep images pinned by digest in `docker-compose.yml`.
- Keep SLOs explicit in `config/slo.env`.
- Use run-scoped output folders (`results/runs/<run-id>`).
- Use at least 3 sessions for stable medians.

## Extra tools in this repository

- PQC algorithm playground: `scripts/playground.sh`
- Interop harness: `scripts/interop.sh`

See:

- `docs/pqc_playground.md`
- `docs/pqc_interop.md`

## Troubleshooting

If algorithm names differ in your image build:

```bash
docker exec tls-client openssl list -groups
docker exec tls-client openssl list -kem-algorithms
docker exec tls-client openssl list -signature-algorithms
```

## License

Apache-2.0. See `LICENSE`.

## Security and risk notice

This project is for benchmarking and research workflows. Validate all conclusions in your own production-like environment before rollout decisions.
