#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two playground JSON outputs")
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pct_delta(a: float, b: float) -> float | None:
    if a == 0:
        return None
    return ((b - a) / a) * 100.0


def main() -> int:
    args = parse_args()
    left = load(args.left)
    right = load(args.right)

    lm = left.get("metrics_ops_per_sec", {})
    rm = right.get("metrics_ops_per_sec", {})
    keys = sorted(set(lm.keys()) | set(rm.keys()))

    comparisons = []
    for key in keys:
        lv = lm.get(key)
        rv = rm.get(key)
        if lv is None or rv is None:
            comparisons.append({"metric": key, "left": lv, "right": rv, "delta_percent": None})
            continue
        comparisons.append({"metric": key, "left": lv, "right": rv, "delta_percent": pct_delta(float(lv), float(rv))})

    status = "ok"
    if left.get("status") != "ok" or right.get("status") != "ok":
        status = "error"

    payload = {
        "left_backend": left.get("backend"),
        "right_backend": right.get("backend"),
        "family": left.get("family"),
        "algorithm": left.get("algorithm"),
        "left_status": left.get("status"),
        "right_status": right.get("status"),
        "status": status,
        "metrics": comparisons,
    }

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
