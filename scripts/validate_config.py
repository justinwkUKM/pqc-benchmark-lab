#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def require_columns(path: Path, rows: list[dict[str, str]], required: list[str]) -> list[str]:
    errors: list[str] = []
    if not rows:
        return [f"{path}: file is empty"]
    cols = set(rows[0].keys())
    for key in required:
        if key not in cols:
            errors.append(f"{path}: missing required column '{key}'")
    return errors


def is_positive_int(text: str) -> bool:
    try:
        return int(text) > 0
    except Exception:
        return False


def validate_modes(path: Path) -> list[str]:
    rows = read_csv(path)
    errors = require_columns(
        path,
        rows,
        ["mode", "cert_algorithm", "kex_group", "resumption_supported", "tls_version", "enabled"],
    )
    seen = set()
    for idx, row in enumerate(rows, start=2):
        mode = (row.get("mode") or "").strip()
        if not mode:
            errors.append(f"{path}:{idx}: mode cannot be empty")
        if mode in seen:
            errors.append(f"{path}:{idx}: duplicate mode '{mode}'")
        seen.add(mode)
    return errors


def validate_workloads(path: Path) -> list[str]:
    rows = read_csv(path)
    errors = require_columns(
        path,
        rows,
        [
            "workload",
            "latency_runs",
            "warmup",
            "resumption_mode",
            "parallel",
            "rounds",
            "http_version",
            "keepalive_mix",
            "mtls_mode",
            "load_pattern",
            "mode_order_strategy",
            "enabled",
        ],
    )
    seen = set()
    for idx, row in enumerate(rows, start=2):
        name = (row.get("workload") or "").strip()
        if not name:
            errors.append(f"{path}:{idx}: workload cannot be empty")
        if name in seen:
            errors.append(f"{path}:{idx}: duplicate workload '{name}'")
        seen.add(name)

        if not is_positive_int(row.get("latency_runs", "")):
            errors.append(f"{path}:{idx}: latency_runs must be > 0")
        if not is_positive_int(row.get("parallel", "")):
            errors.append(f"{path}:{idx}: parallel must be > 0")
        if not is_positive_int(row.get("rounds", "")):
            errors.append(f"{path}:{idx}: rounds must be > 0")
        try:
            warmup = int(row.get("warmup", ""))
            if warmup < 0:
                raise ValueError
        except Exception:
            errors.append(f"{path}:{idx}: warmup must be >= 0")

        resumption = (row.get("resumption_mode") or "").strip().lower()
        if resumption not in {"on", "off"}:
            errors.append(f"{path}:{idx}: resumption_mode must be on/off")

        http_version = (row.get("http_version") or "").strip().lower()
        if http_version not in {"http1.1", "http2"}:
            errors.append(f"{path}:{idx}: http_version must be http1.1/http2")

        keepalive = (row.get("keepalive_mix") or "").strip().lower()
        if keepalive not in {"close", "keepalive", "mix30", "mix50", "mix70"}:
            errors.append(f"{path}:{idx}: keepalive_mix must be close/keepalive/mix30/mix50/mix70")

        mtls = (row.get("mtls_mode") or "").strip().lower()
        if mtls not in {"on", "off"}:
            errors.append(f"{path}:{idx}: mtls_mode must be on/off")

        pattern = (row.get("load_pattern") or "").strip().lower()
        if pattern not in {"steady", "burst", "ramp"}:
            errors.append(f"{path}:{idx}: load_pattern must be steady/burst/ramp")

        strategy = (row.get("mode_order_strategy") or "").strip().lower()
        if strategy not in {"fixed", "seeded_random"}:
            errors.append(f"{path}:{idx}: mode_order_strategy must be fixed/seeded_random")
    return errors


def validate_suites(path: Path) -> list[str]:
    rows = read_csv(path)
    errors = require_columns(
        path,
        rows,
        ["suite", "workload", "sessions", "profiles", "modes", "seed_strategy", "enabled"],
    )
    seen = set()
    for idx, row in enumerate(rows, start=2):
        name = (row.get("suite") or "").strip()
        if not name:
            errors.append(f"{path}:{idx}: suite cannot be empty")
        if name in seen:
            errors.append(f"{path}:{idx}: duplicate suite '{name}'")
        seen.add(name)
        if not is_positive_int(row.get("sessions", "")):
            errors.append(f"{path}:{idx}: sessions must be > 0")
        strategy = (row.get("seed_strategy") or "").strip().lower()
        if strategy not in {"fixed", "seeded"}:
            errors.append(f"{path}:{idx}: seed_strategy must be fixed/seeded")
    return errors


def validate_profiles(path: Path) -> list[str]:
    rows = read_csv(path)
    errors = require_columns(
        path,
        rows,
        ["profile", "delay_ms", "jitter_ms", "loss_pct", "bandwidth", "cpus", "memory", "parallel", "rounds"],
    )
    seen = set()
    for idx, row in enumerate(rows, start=2):
        profile = (row.get("profile") or "").strip()
        if not profile:
            errors.append(f"{path}:{idx}: profile cannot be empty")
        if profile in seen:
            errors.append(f"{path}:{idx}: duplicate profile '{profile}'")
        seen.add(profile)

        if not is_positive_int(row.get("parallel", "")):
            errors.append(f"{path}:{idx}: parallel must be > 0")
        if not is_positive_int(row.get("rounds", "")):
            errors.append(f"{path}:{idx}: rounds must be > 0")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(validate_modes(ROOT / "config" / "modes.csv"))
    errors.extend(validate_workloads(ROOT / "config" / "workloads.csv"))
    errors.extend(validate_profiles(ROOT / "config" / "infra_profiles.csv"))
    errors.extend(validate_suites(ROOT / "config" / "suites.csv"))

    if errors:
        print("Configuration validation failed:")
        for item in errors:
            print(f"- {item}")
        return 1

    print("Configuration validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
