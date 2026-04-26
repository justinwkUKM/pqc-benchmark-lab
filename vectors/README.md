# PQC Playground Vector Files

This directory stores deterministic capability vectors for the `playground.sh vector` command.

Vector files are JSON with this structure:

```json
{
  "name": "kem-core-support",
  "cases": [
    {
      "id": "mlkem768-supported",
      "family": "kem",
      "algorithm": "mlkem768",
      "expected_supported": true
    }
  ]
}
```

Notes:

- These vectors validate deterministic backend support status (available/unavailable), not fixed cryptographic output bytes.
- Support vectors are stable across reruns and intended for CI gating.
- If backend capabilities change, update vectors and document why in commit history.

Algorithm metadata catalog:

- `vectors/catalog/algorithms.json` defines canonical names, aliases, security level, maturity, and caveats.
- `scripts/build_matrix.py` uses this catalog with capability snapshots to build executable run matrices.
