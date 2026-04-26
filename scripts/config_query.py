#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
INFRA_CSV = ROOT / "config" / "infra_profiles.csv"
MODES_CSV = ROOT / "config" / "modes.csv"
WORKLOADS_CSV = ROOT / "config" / "workloads.csv"
SUITES_CSV = ROOT / "config" / "suites.csv"


def as_bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def split_pipe(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split("|") if part.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def find_row(path: Path, key: str, name: str) -> dict[str, str]:
    for row in read_csv(path):
        if row.get(key) == name:
            return row
    raise SystemExit(f"Unknown {key}: {name}")


def cmd_profiles(_: argparse.Namespace) -> int:
    for row in read_csv(INFRA_CSV):
        if as_bool(row.get("enabled", "true")):
            print(row["profile"])
    return 0


def cmd_modes(_: argparse.Namespace) -> int:
    for row in read_csv(MODES_CSV):
        if as_bool(row.get("enabled", "true")):
            print(row["mode"])
    return 0


def cmd_workloads(_: argparse.Namespace) -> int:
    for row in read_csv(WORKLOADS_CSV):
        if as_bool(row.get("enabled", "true")):
            print(row["workload"])
    return 0


def cmd_suites(_: argparse.Namespace) -> int:
    for row in read_csv(SUITES_CSV):
        if as_bool(row.get("enabled", "true")):
            print(row["suite"])
    return 0


def cmd_profile_parallel(args: argparse.Namespace) -> int:
    profile = find_row(INFRA_CSV, "profile", args.profile)
    parallel = profile.get("parallel", "100")
    rounds = profile.get("rounds", "10")
    print(f"{parallel} {rounds}")
    return 0


def cmd_profile_limits(args: argparse.Namespace) -> int:
    profile = find_row(INFRA_CSV, "profile", args.profile)
    print(
        " ".join(
            [
                profile.get("delay_ms", "0"),
                profile.get("jitter_ms", "0"),
                profile.get("loss_pct", "0"),
                profile.get("bandwidth", "1gbit"),
                profile.get("cpus", "none"),
                profile.get("memory", "none"),
            ]
        )
    )
    return 0


def cmd_workload_get(args: argparse.Namespace) -> int:
    row = find_row(WORKLOADS_CSV, "workload", args.name)
    print(json.dumps(row))
    return 0


def cmd_suite_get(args: argparse.Namespace) -> int:
    row = find_row(SUITES_CSV, "suite", args.name)
    if not as_bool(row.get("enabled", "true")):
        raise SystemExit(f"Suite is disabled: {args.name}")
    print(json.dumps(row))
    return 0


def cmd_expand(args: argparse.Namespace) -> int:
    field = args.field
    value = args.value
    if value == "all":
        if field == "profiles":
            return cmd_profiles(args)
        if field == "modes":
            return cmd_modes(args)
    for item in split_pipe(value):
        print(item)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query lab configuration CSV files")
    sub = parser.add_subparsers(dest="command", required=True)

    p_profiles = sub.add_parser("profiles", help="List enabled infra profiles")
    p_profiles.set_defaults(handler=cmd_profiles)

    p_modes = sub.add_parser("modes", help="List enabled crypto modes")
    p_modes.set_defaults(handler=cmd_modes)

    p_workloads = sub.add_parser("workloads", help="List enabled workload presets")
    p_workloads.set_defaults(handler=cmd_workloads)

    p_suites = sub.add_parser("suites", help="List enabled suite presets")
    p_suites.set_defaults(handler=cmd_suites)

    p_parallel = sub.add_parser("profile-parallel", help="Get profile concurrency settings")
    p_parallel.add_argument("--profile", required=True)
    p_parallel.set_defaults(handler=cmd_profile_parallel)

    p_limits = sub.add_parser("profile-limits", help="Get profile network/server limits")
    p_limits.add_argument("--profile", required=True)
    p_limits.set_defaults(handler=cmd_profile_limits)

    p_workload_get = sub.add_parser("workload-get", help="Get workload row as JSON")
    p_workload_get.add_argument("--name", required=True)
    p_workload_get.set_defaults(handler=cmd_workload_get)

    p_suite_get = sub.add_parser("suite-get", help="Get suite row as JSON")
    p_suite_get.add_argument("--name", required=True)
    p_suite_get.set_defaults(handler=cmd_suite_get)

    p_expand = sub.add_parser("expand", help="Expand 'all' or pipe-separated profile/mode list")
    p_expand.add_argument("--field", required=True, choices=["profiles", "modes"])
    p_expand.add_argument("--value", required=True)
    p_expand.set_defaults(handler=cmd_expand)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
