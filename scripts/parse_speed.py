#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse OpenSSL speed -mr output")
    parser.add_argument("--backend", required=True)
    parser.add_argument("--family", choices=["kem", "sig"], required=True)
    parser.add_argument("--algorithm", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--raw-file", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


R_LINE = re.compile(r"^\+R\d+:(\d+):([^:]+):([0-9.]+)$")


def parse_metrics(text: str, algorithm: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for line in text.splitlines():
        match = R_LINE.match(line.strip())
        if not match:
            continue
        count, op_alg, seconds = match.groups()
        if op_alg != algorithm:
            continue
        seconds_v = float(seconds)
        if seconds_v == 0:
            continue
        metrics[f"op_{len(metrics)+1}"] = float(count) / seconds_v
    return metrics


def canonical_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    args = parse_args()
    raw_text = Path(args.raw_file).read_text(encoding="utf-8", errors="replace")
    metrics = parse_metrics(raw_text, args.algorithm)

    payload = {
        "run_id": f"{args.backend}-{int(time.time())}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "playground",
        "backend": args.backend,
        "family": args.family,
        "algorithm": args.algorithm,
        "parameter_set": args.algorithm,
        "operation": "speed",
        "status": args.status,
        "error_code": args.reason,
        "error_message": "",
        "host": platform.platform(),
        "metrics_ops_per_sec": metrics,
        "raw_output": raw_text,
    }
    payload["artifact_hash_sha256"] = canonical_hash(
        {
            "backend": payload["backend"],
            "family": payload["family"],
            "algorithm": payload["algorithm"],
            "status": payload["status"],
            "metrics_ops_per_sec": payload["metrics_ops_per_sec"],
        }
    )

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
