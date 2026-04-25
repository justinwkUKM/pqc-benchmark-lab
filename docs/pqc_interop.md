# PQC Interoperability Harness

The interoperability harness runs backend matrix comparisons and negative checks.

## Commands

```bash
./scripts/interop.sh matrix --family kem --alg mlkem --param 768 --backends openssl,liboqs,python
./scripts/interop.sh negative --family sig --alg mldsa --param 65 --backends openssl,liboqs,python
./scripts/interop.sh report --run-dir results/interop/<timestamp>
```

Optional TLS profile probe:

```bash
./scripts/interop.sh tls --mode hybrid --providers openssl,liboqs,python
```

## Artifacts

Outputs are written under `results/interop/<timestamp>/`.

- `matrix.csv`: source/target backend compatibility table.
- `negative.csv`: invalid algorithm rejection + sanity check results.
- `REPORT.md`: markdown summary generated from CSV artifacts.
- `run-meta.json`: family + algorithm metadata.
- `cases/*`: comparison and raw case JSON files.

## Recommended defaults in this repo

- Use `openssl,liboqs,python` in v1.
- Treat Go/Rust/BoringSSL/WolfSSL as phase-2 adapters.
