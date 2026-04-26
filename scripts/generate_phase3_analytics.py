#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import shutil
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path


HANDSHAKE_TYPE_NAMES = {
    "1": "client_hello",
    "2": "server_hello",
    "4": "new_session_ticket",
    "8": "encrypted_extensions",
    "11": "certificate",
    "13": "certificate_request",
    "15": "certificate_verify",
    "20": "finished",
    "24": "key_update",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Phase 3 analytics outputs")
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--report-dir", required=True)
    return parser.parse_args()


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return math.nan
    idx = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def confidence_interval_95(vals: list[float]) -> tuple[float, float]:
    if not vals:
        return (math.nan, math.nan)
    m = statistics.mean(vals)
    if len(vals) < 2:
        return (m, m)
    stdev = statistics.stdev(vals)
    margin = 1.96 * (stdev / math.sqrt(len(vals)))
    return (m - margin, m + margin)


def outlier_count_iqr(vals: list[float]) -> int:
    if len(vals) < 4:
        return 0
    sorted_vals = sorted(vals)
    q1 = percentile(sorted_vals, 0.25)
    q3 = percentile(sorted_vals, 0.75)
    iqr = q3 - q1
    low = q1 - 1.5 * iqr
    high = q3 + 1.5 * iqr
    return sum(1 for v in sorted_vals if v < low or v > high)


def iter_latency_files(results_dir: Path):
    for path in results_dir.glob("profiles/*/sessions/*/latency-*.csv"):
        mode = path.stem.split("latency-", 1)[-1].split("-")[0]
        profile = path.parts[-4]
        session = path.parts[-2]
        yield profile, session, mode, path


def build_statistical_summary(results_dir: Path, report_dir: Path) -> None:
    grouped: dict[tuple[str, str], dict[str, list[float] | int]] = {}

    for profile, _session, mode, path in iter_latency_files(results_dir):
        key = (profile, mode)
        data = grouped.setdefault(
            key,
            {
                "tls_vals": [],
                "total_samples": 0,
                "success_samples": 0,
            },
        )

        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                data["total_samples"] += 1
                if row.get("success") != "1":
                    continue
                data["success_samples"] += 1
                try:
                    data["tls_vals"].append(float(row["tls_setup"]))
                except Exception:
                    continue

    out_file = report_dir / "statistical-summary.csv"
    fields = [
        "profile",
        "mode",
        "samples",
        "success_rate",
        "mean",
        "stddev",
        "variance",
        "p50",
        "p95",
        "p99",
        "ci95_low",
        "ci95_high",
        "outlier_count",
        "outlier_rate",
    ]

    with out_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()

        for (profile, mode), data in sorted(grouped.items()):
            vals = sorted(data["tls_vals"])
            samples = int(data["total_samples"])
            success = int(data["success_samples"])
            success_rate = (success / samples * 100.0) if samples else math.nan

            if vals:
                mean = statistics.mean(vals)
                stddev = statistics.stdev(vals) if len(vals) > 1 else 0.0
                variance = statistics.variance(vals) if len(vals) > 1 else 0.0
                p50 = statistics.median(vals)
                p95 = percentile(vals, 0.95)
                p99 = percentile(vals, 0.99)
                ci_low, ci_high = confidence_interval_95(vals)
                outliers = outlier_count_iqr(vals)
                outlier_rate = (outliers / len(vals) * 100.0) if vals else 0.0
            else:
                mean = stddev = variance = p50 = p95 = p99 = ci_low = ci_high = math.nan
                outliers = 0
                outlier_rate = math.nan

            writer.writerow(
                {
                    "profile": profile,
                    "mode": mode,
                    "samples": samples,
                    "success_rate": f"{success_rate:.2f}" if not math.isnan(success_rate) else "N/A",
                    "mean": f"{mean:.6f}" if not math.isnan(mean) else "N/A",
                    "stddev": f"{stddev:.6f}" if not math.isnan(stddev) else "N/A",
                    "variance": f"{variance:.8f}" if not math.isnan(variance) else "N/A",
                    "p50": f"{p50:.6f}" if not math.isnan(p50) else "N/A",
                    "p95": f"{p95:.6f}" if not math.isnan(p95) else "N/A",
                    "p99": f"{p99:.6f}" if not math.isnan(p99) else "N/A",
                    "ci95_low": f"{ci_low:.6f}" if not math.isnan(ci_low) else "N/A",
                    "ci95_high": f"{ci_high:.6f}" if not math.isnan(ci_high) else "N/A",
                    "outlier_count": outliers,
                    "outlier_rate": f"{outlier_rate:.2f}" if not math.isnan(outlier_rate) else "N/A",
                }
            )


def parse_tshark_handshake(path: Path) -> list[tuple[str, int]]:
    tshark = shutil.which("tshark")
    if not tshark:
        return []

    cmd = [
        tshark,
        "-r",
        str(path),
        "-Y",
        "tls.handshake",
        "-T",
        "fields",
        "-e",
        "tls.handshake.type",
        "-e",
        "tls.handshake.length",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return []

    pairs: list[tuple[str, int]] = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        type_raw, len_raw = line.split("\t", 1)
        types = [t.strip() for t in type_raw.split(",") if t.strip()]
        lens = [l.strip() for l in len_raw.split(",") if l.strip()]
        for idx, htype in enumerate(types):
            if idx >= len(lens):
                continue
            try:
                hlen = int(lens[idx])
            except Exception:
                continue
            pairs.append((htype, hlen))
    return pairs


def build_handshake_breakdown(results_dir: Path, report_dir: Path) -> None:
    rows: list[dict[str, str]] = []
    grouped: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(lambda: {"bytes": 0, "messages": 0})

    for pcap in sorted(results_dir.glob("profiles/*/sessions/*/tls-capture-*.pcap")):
        profile = pcap.parts[-4]
        session = pcap.parts[-2]
        mode = pcap.stem.split("tls-capture-", 1)[-1].split("-")[0]
        for htype, hlen in parse_tshark_handshake(pcap):
            name = HANDSHAKE_TYPE_NAMES.get(htype, f"type_{htype}")
            key = (profile, session, mode, name)
            grouped[key]["bytes"] += hlen
            grouped[key]["messages"] += 1

    for (profile, session, mode, handshake_type), data in sorted(grouped.items()):
        rows.append(
            {
                "profile": profile,
                "session": session,
                "mode": mode,
                "handshake_type": handshake_type,
                "messages": str(data["messages"]),
                "total_bytes": str(data["bytes"]),
            }
        )

    out_file = report_dir / "handshake-size-breakdown.csv"
    with out_file.open("w", newline="", encoding="utf-8") as handle:
        fields = ["profile", "session", "mode", "handshake_type", "messages", "total_bytes"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        if not rows:
            writer.writerow(
                {
                    "profile": "N/A",
                    "session": "N/A",
                    "mode": "N/A",
                    "handshake_type": "tshark_unavailable_or_no_data",
                    "messages": "0",
                    "total_bytes": "0",
                }
            )
        else:
            writer.writerows(rows)


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    report_dir = Path(args.report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    build_statistical_summary(results_dir, report_dir)
    build_handshake_breakdown(results_dir, report_dir)
    print(f"Wrote {report_dir / 'statistical-summary.csv'}")
    print(f"Wrote {report_dir / 'handshake-size-breakdown.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
