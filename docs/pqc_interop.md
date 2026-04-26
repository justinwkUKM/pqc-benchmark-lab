# PQC Interoperability Harness

The interoperability harness runs deep adapter interop cases (not benchmark-only comparisons).

## Commands

```bash
./scripts/interop.sh matrix --family kem --alg mlkem --param 768 --backends openssl,liboqs,python
./scripts/interop.sh matrix --family kem --alg mlkem --param 768 --backends openssl,liboqs,python --kem-mode local-only
./scripts/interop.sh matrix --family sig --alg mldsa --param 65 --backends openssl,liboqs,python
./scripts/interop.sh negative --family sig --alg mldsa --param 65 --backends openssl,liboqs,python
./scripts/interop.sh report --run-dir results/interop/<timestamp>
```

Provider-aware TLS probe:

```bash
./scripts/interop.sh tls --mode hybrid --providers openssl,liboqs,python
```

`tls` now performs provider-specific probe commands instead of reusing a placeholder loop.

For KEM matrix runs:

- `--kem-mode cross-backend` (default): full source->target matrix.
- `--kem-mode local-only`: only same-backend KEM rows (useful when key serialization blocks cross-backend transfer).

## Artifacts

Outputs are written under `results/interop/<timestamp>/`.

- `matrix.csv`: cross-backend interop results (`keygen/sign/verify` or `keygen/encap/decap`).
- `negative.csv`: invalid algorithm + tamper tests.
- `tls.csv`: provider-specific TLS probe outcomes.
- `failures.csv`: normalized failure taxonomy rows.
- `summary.csv`: suite-level pass/fail rollup for dashboards.
- `INTEROP_DASHBOARD.md`: dashboard markdown summary.
- `REPORT.md`: full markdown report generated from CSV artifacts.
- `run-meta.json`: family + algorithm metadata.

Failure codes are normalized (for example: `unsupported_alg`, `parse_error`, `verify_mismatch`, `kem_mismatch`, `tls_alert`).

## Adapter SDK

See `docs/adapter_contract.md` for the adapter CLI/JSON contract used by the interop harness.

## Recommended defaults in this repo

- Use `openssl,liboqs,python` for baseline runs.
- Add new backends by implementing the contract in `docs/adapter_contract.md`.
