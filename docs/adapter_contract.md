# Adapter Contract (Interop SDK)

This document defines the adapter SDK for interoperability runs.

## Purpose

Adapters expose a stable CLI contract so the harness can execute:

- cross-backend `keygen/sign/verify` for signatures,
- cross-backend `encap/decap` for KEM,
- negative tests,
- capability discovery.

## Required executable naming

Adapter scripts live in `scripts/adapters/` and follow:

- `scripts/adapters/<backend>_adapter.sh` for shell adapters
- `scripts/adapters/python_adapter.py` for Python adapter

The harness resolves backends by this naming convention.

## Required commands

Every adapter must implement:

1. `list --family kem|sig`
2. `run --family kem|sig --algorithm <name> --out <json-path>`
3. `interop --family kem|sig --algorithm <name> --operation <name> --in <json-path> --out <json-path>`

`run` remains benchmark-oriented; `interop` is operation-oriented.

## Interop operations

`--operation` accepts:

- `capabilities`
- `keygen`
- `sign` (sig only)
- `verify` (sig only)
- `encap` (kem only)
- `decap` (kem only)

## Input payload (`--in`)

JSON object. Required fields by operation:

- `capabilities`: no required fields
- `keygen`: no required fields
- `sign`: `secret_key_b64`, `message_b64`
- `verify`: `public_key_b64`, `message_b64`, `signature_b64`
- `encap`: `public_key_b64`
- `decap`: `secret_key_b64`, `ciphertext_b64`

All binary values are base64 strings.

## Output payload (`--out`)

Adapters must always write JSON with this envelope:

```json
{
  "backend": "python",
  "family": "sig",
  "algorithm": "mldsa65",
  "operation": "verify",
  "status": "ok",
  "error_code": "",
  "error_message": "",
  "data": {}
}
```

### `status`

- `ok`: operation completed
- `unsupported`: backend cannot satisfy operation/algorithm
- `error`: operation attempted but failed

### `data` by operation

- `capabilities`: `supported_algorithm` (bool), `supported_operations` (string array)
- `keygen`: `public_key_b64`, `secret_key_b64`
- `sign`: `signature_b64`
- `verify`: `verified` (bool)
- `encap`: `ciphertext_b64`, `shared_secret_b64`
- `decap`: `shared_secret_b64`

## Exit codes

- `0` for `status=ok`
- `2` for `status=unsupported`
- `1` for `status=error`

Harness logic is response-driven (JSON), but exit codes are used as a quick signal.

## Failure taxonomy expectations

Adapters should use stable `error_code` values where possible:

- `unsupported_algorithm`
- `unsupported_operation`
- `parse_error`
- `interop_failed`
- `benchmark_failed`

Harness normalizes these into `results/interop/<run>/failures.csv`.

## Validation checklist for new adapters

1. `list` returns newline-delimited algorithms for both families.
2. `run` writes benchmark JSON at requested output path.
3. `interop capabilities` returns operation map for algorithm.
4. `interop keygen/sign/verify` works for one signature algorithm.
5. `interop keygen/encap/decap` works for one KEM algorithm.
6. Invalid inputs return `status=error` with `parse_error` or equivalent.
