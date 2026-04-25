# PQC Algorithm Playground

The playground utility benchmarks and compares supported PQC algorithms across adapters.

## Implemented adapters

- `openssl`: OpenSSL CLI in `tls-client` container.
- `liboqs`: OpenSSL with explicit `-provider oqsprovider` in `tls-client` container.
- `python`: local Python adapter using `python-oqs` if available.

## Commands

```bash
./scripts/playground.sh list --family kem
./scripts/playground.sh list --backend liboqs --family sig

./scripts/playground.sh run --backend openssl --family kem --alg mlkem --param 768
./scripts/playground.sh run --backend liboqs --family sig --alg falcon512

./scripts/playground.sh compare --backend-a openssl --backend-b liboqs --family sig --alg mldsa --param 65

./scripts/playground.sh vector --backend openssl --vector-file vectors/kem/core-support.json
```

## Artifacts

Outputs are written under `results/playground/<timestamp>/`.

- `case-*.json`: per backend benchmark JSON.
- `compare-*.json`: backend-to-backend comparison JSON.
- `vector-report.json`: vector validation report.
- `run-meta.json`: run metadata.

## Scope of v1 vectors

`vector` currently validates deterministic support expectations (`supported` true/false) per backend and algorithm.
