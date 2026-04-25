# TLS PQC Comparative Report Template

## Environment

- Date:
- Host:
- Docker version:
- Server image:
- Client image:

## Scenario Summary

| Scenario | Cert | KEX group | TLS p50 (s) | TLS p95 (s) | CPU peak | Mem peak | Notes |
|---|---|---|---:|---:|---:|---:|---|
| classical | RSA-2048 | X25519 |  |  |  |  | baseline |
| kex_pqc | RSA-2048 | ML-KEM-768 |  |  |  |  | isolates KEX |
| cert_pqc | ML-DSA-65 | X25519 |  |  |  |  | isolates cert |
| hybrid | RSA-2048 | X25519MLKEM768 |  |  |  |  | migration profile |
| pqc | ML-DSA-65 | ML-KEM-768 |  |  |  |  | full PQC |

## Delta vs Baseline

| Scenario | Delta TLS p50 | Delta TLS p95 | Delta CPU peak | Delta Mem peak |
|---|---:|---:|---:|---:|
| kex_pqc |  |  |  |  |
| cert_pqc |  |  |  |  |
| hybrid |  |  |  |  |
| pqc |  |  |  |  |

## Packet Capture Notes

- Wireshark filter: `tls.handshake.type == 2`
- Compare ServerHello and Certificate message sizes between `classical`, `hybrid`, and `pqc`.

## Interpretation

- KEX-driven effect:
- Certificate-driven effect:
- Combined PQC effect:
- Recommended deployment profile:
