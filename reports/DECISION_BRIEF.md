# Decision Brief

Preset: `balanced`
Policy target level: `2`
Profiles in scope: `all`

## Ranked Options

| Rank | Mode | Composite | Performance | Compatibility | Resource | Handshake Size | Policy Fit |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | hybrid | 98.27 | 93.82 | 100.00 | 100.00 | 100.00 | 100.00 |
| 2 | classical | 92.00 | 100.00 | 100.00 | 100.00 | 100.00 | 60.00 |
| 3 | pqc | 72.00 | 0.00 | 100.00 | 100.00 | 100.00 | 100.00 |

## Top Candidates

### 1. hybrid

- Rationale: composite `98.27` with median TLS p95 `0.023941s`, median CPU peak `2.00%`, compatibility `100.00%`.
- Tradeoff notes: Strongest on compatibility; main watch item is performance.

### 2. classical

- Rationale: composite `92.00` with median TLS p95 `0.023061s`, median CPU peak `2.00%`, compatibility `100.00%`.
- Tradeoff notes: Trails leader by 6.27 points; strongest on performance, weakest on policy.

### 3. pqc

- Rationale: composite `72.00` with median TLS p95 `0.037292s`, median CPU peak `2.00%`, compatibility `100.00%`.
- Tradeoff notes: Trails leader by 26.27 points; strongest on compatibility, weakest on performance.

## Preset Weights

| Criterion | Weight |
|---|---:|
| performance | 0.28 |
| compatibility | 0.24 |
| resource_cost | 0.18 |
| handshake_size | 0.10 |
| security_policy_fit | 0.20 |
