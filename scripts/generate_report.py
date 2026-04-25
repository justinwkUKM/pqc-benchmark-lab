#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from pathlib import Path
from statistics import median


SCENARIOS = [
    ("classical", "RSA-2048", "X25519"),
    ("kex_pqc", "RSA-2048", "ML-KEM-768"),
    ("cert_pqc", "ML-DSA-65", "X25519"),
    ("hybrid", "RSA-2048", "X25519MLKEM768"),
    ("pqc", "ML-DSA-65", "ML-KEM-768"),
    ("hybrid_pqc_cert", "ML-DSA-65", "X25519MLKEM768"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate comparative markdown report from results CSV files")
    parser.add_argument(
        "--results-dir",
        default=str((Path(__file__).resolve().parent.parent / "results")),
        help="Directory containing latency/concurrency outputs",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output markdown path (default: <results-dir>/REPORT.md)",
    )
    return parser.parse_args()


def latest_file(results_dir: Path, pattern: str) -> Path | None:
    matches = sorted(results_dir.glob(pattern))
    if not matches:
        return None
    return matches[-1]


def parse_float(text: str) -> float | None:
    value = (text or "").strip().replace("%", "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return math.nan
    idx = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


def read_latency(path: Path) -> dict[str, float] | None:
    if path is None or not path.exists():
        return None

    tls_vals: list[float] = []
    total_vals: list[float] = []

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tls = parse_float(row.get("tls_setup", ""))
            total = parse_float(row.get("total", ""))
            if tls is not None:
                tls_vals.append(tls)
            if total is not None:
                total_vals.append(total)

    if not tls_vals:
        return None

    tls_vals.sort()
    total_vals.sort()
    return {
        "samples": float(len(tls_vals)),
        "tls_p50": median(tls_vals),
        "tls_p95": percentile(tls_vals, 0.95),
        "tls_p99": percentile(tls_vals, 0.99),
        "total_p50": median(total_vals) if total_vals else math.nan,
    }


def read_concurrency(path: Path) -> dict[str, float] | None:
    if path is None or not path.exists():
        return None

    cpu_vals: list[float] = []
    mem_vals: list[float] = []
    rounds = 0

    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rounds += 1
            cpu = parse_float(row.get("cpu_perc", ""))
            mem = parse_float(row.get("mem_perc", ""))
            if cpu is not None:
                cpu_vals.append(cpu)
            if mem is not None:
                mem_vals.append(mem)

    if rounds == 0:
        return None

    return {
        "rounds": float(rounds),
        "cpu_peak": max(cpu_vals) if cpu_vals else math.nan,
        "cpu_avg": (sum(cpu_vals) / len(cpu_vals)) if cpu_vals else math.nan,
        "mem_peak": max(mem_vals) if mem_vals else math.nan,
        "mem_avg": (sum(mem_vals) / len(mem_vals)) if mem_vals else math.nan,
    }


def fmt_num(value: float | None, digits: int = 4, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "N/A"
    return f"{value:.{digits}f}{suffix}"


def fmt_delta(value: float | None, baseline: float | None, digits: int = 2, suffix: str = "%") -> str:
    if value is None or baseline is None:
        return "N/A"
    if any(isinstance(v, float) and math.isnan(v) for v in (value, baseline)):
        return "N/A"
    if baseline == 0:
        return "N/A"
    delta = ((value - baseline) / baseline) * 100
    return f"{delta:+.{digits}f}{suffix}"


def main() -> int:
    args = parse_args()
    results_dir = Path(args.results_dir).resolve()
    output = Path(args.output).resolve() if args.output else (results_dir / "REPORT.md")
    output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for mode, cert, kex in SCENARIOS:
        latency_path = latest_file(results_dir, f"latency-{mode}-*.csv")
        conc_path = latest_file(results_dir, f"concurrency-{mode}-*.csv")
        pcap_path = latest_file(results_dir, f"tls-capture-{mode}-*.pcap")

        latency = read_latency(latency_path) if latency_path else None
        conc = read_concurrency(conc_path) if conc_path else None

        rows.append(
            {
                "mode": mode,
                "cert": cert,
                "kex": kex,
                "latency_path": latency_path,
                "concurrency_path": conc_path,
                "pcap_path": pcap_path,
                "latency": latency,
                "concurrency": conc,
            }
        )

    baseline_row = next((r for r in rows if r["mode"] == "classical"), None)
    baseline_latency = baseline_row["latency"] if baseline_row else None
    baseline_conc = baseline_row["concurrency"] if baseline_row else None

    baseline_tls_p50 = baseline_latency.get("tls_p50") if baseline_latency else None
    baseline_tls_p95 = baseline_latency.get("tls_p95") if baseline_latency else None
    baseline_cpu_peak = baseline_conc.get("cpu_peak") if baseline_conc else None
    baseline_mem_peak = baseline_conc.get("mem_peak") if baseline_conc else None

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    speed_file = latest_file(results_dir, "speed-*.txt")

    lines: list[str] = []
    lines.append("# TLS PQC Comparative Report")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append("")
    lines.append("## Scenario Summary")
    lines.append("")
    lines.append("| Scenario | Cert | KEX group | TLS p50 (s) | TLS p95 (s) | TLS p99 (s) | CPU peak (%) | Mem peak (%) | Samples | Rounds |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")

    for row in rows:
        latency = row["latency"] or {}
        conc = row["concurrency"] or {}
        lines.append(
            "| {mode} | {cert} | {kex} | {tls_p50} | {tls_p95} | {tls_p99} | {cpu_peak} | {mem_peak} | {samples} | {rounds} |".format(
                mode=row["mode"],
                cert=row["cert"],
                kex=row["kex"],
                tls_p50=fmt_num(latency.get("tls_p50") if latency else None, 6),
                tls_p95=fmt_num(latency.get("tls_p95") if latency else None, 6),
                tls_p99=fmt_num(latency.get("tls_p99") if latency else None, 6),
                cpu_peak=fmt_num(conc.get("cpu_peak") if conc else None, 2),
                mem_peak=fmt_num(conc.get("mem_peak") if conc else None, 2),
                samples=fmt_num(latency.get("samples") if latency else None, 0),
                rounds=fmt_num(conc.get("rounds") if conc else None, 0),
            )
        )

    lines.append("")
    lines.append("## Delta vs Baseline (classical)")
    lines.append("")
    lines.append("| Scenario | Delta TLS p50 | Delta TLS p95 | Delta CPU peak | Delta Mem peak |")
    lines.append("|---|---:|---:|---:|---:|")

    for row in rows:
        if row["mode"] == "classical":
            continue
        latency = row["latency"] or {}
        conc = row["concurrency"] or {}
        lines.append(
            "| {mode} | {d_tls_p50} | {d_tls_p95} | {d_cpu} | {d_mem} |".format(
                mode=row["mode"],
                d_tls_p50=fmt_delta(latency.get("tls_p50") if latency else None, baseline_tls_p50),
                d_tls_p95=fmt_delta(latency.get("tls_p95") if latency else None, baseline_tls_p95),
                d_cpu=fmt_delta(conc.get("cpu_peak") if conc else None, baseline_cpu_peak),
                d_mem=fmt_delta(conc.get("mem_peak") if conc else None, baseline_mem_peak),
            )
        )

    lines.append("")
    lines.append("## Artifact Mapping")
    lines.append("")
    lines.append("| Scenario | Latency CSV | Concurrency CSV | Packet Capture |")
    lines.append("|---|---|---|---|")

    for row in rows:
        latency_path = row["latency_path"]
        conc_path = row["concurrency_path"]
        pcap_path = row["pcap_path"]

        def rel_or_na(p: Path | None) -> str:
            return str(p.relative_to(results_dir)) if p else "N/A"

        lines.append(
            f"| {row['mode']} | {rel_or_na(latency_path)} | {rel_or_na(conc_path)} | {rel_or_na(pcap_path)} |"
        )

    lines.append("")
    lines.append("## Speed Benchmark Artifact")
    lines.append("")
    lines.append(f"- {str(speed_file.relative_to(results_dir)) if speed_file else 'N/A'}")
    lines.append("")
    lines.append("## Interpretation Prompts")
    lines.append("")
    lines.append("- KEX overhead: compare `kex_pqc` vs `classical`.")
    lines.append("- Certificate overhead: compare `cert_pqc` vs `classical`.")
    lines.append("- Combined PQC overhead: compare `pqc` vs `classical`.")
    lines.append("- Migration profile: compare `hybrid` vs `classical`.")

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
