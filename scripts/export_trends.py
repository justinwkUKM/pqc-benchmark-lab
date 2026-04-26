#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export run trend CSVs from run index")
    parser.add_argument("--runs-index", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_acceptance(report_path: Path) -> str:
    if not report_path.exists():
        return "UNKNOWN"
    text = report_path.read_text(encoding="utf-8")
    if "Overall: PASS" in text:
        return "PASS"
    if "Overall: FAIL" in text:
        return "FAIL"
    return "UNKNOWN"


def aggregate_compatibility(rows: list[dict[str, str]]) -> dict[tuple[str, str], tuple[int, int, float]]:
    grouped: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = (row.get("profile", ""), row.get("mode", ""))
        grouped.setdefault(key, {"pass": 0, "fail": 0})
        if row.get("status") == "pass":
            grouped[key]["pass"] += 1
        else:
            grouped[key]["fail"] += 1

    out: dict[tuple[str, str], tuple[int, int, float]] = {}
    for key, item in grouped.items():
        total = item["pass"] + item["fail"]
        rate = (item["pass"] / total * 100.0) if total else 0.0
        out[key] = (item["pass"], item["fail"], rate)
    return out


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    index_rows = read_csv(Path(args.runs_index).resolve())
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    latency_rows: list[dict[str, str]] = []
    compatibility_rows: list[dict[str, str]] = []
    overview_rows: list[dict[str, str]] = []

    for idx_row in index_rows:
        run_id = idx_row.get("run_id", "")
        run_root_value = idx_row.get("run_root", "")
        if not run_id or not run_root_value:
            continue

        run_root = Path(run_root_value)
        reports_root = run_root / "reports"
        summary_rows = read_csv(reports_root / "summary.csv")
        compat_raw = read_csv(reports_root / "compatibility-status.csv")
        compat_grouped = aggregate_compatibility(compat_raw)
        acceptance = parse_acceptance(reports_root / "ACCEPTANCE.md")

        finished_utc = idx_row.get("finished_utc", "")
        workload = idx_row.get("workload", "")

        for row in summary_rows:
            latency_rows.append(
                {
                    "run_id": run_id,
                    "finished_utc": finished_utc,
                    "workload": workload,
                    "profile": row.get("profile", ""),
                    "mode": row.get("mode", ""),
                    "latency_p95": row.get("latency_p95", ""),
                    "latency_success_rate": row.get("latency_success_rate", ""),
                    "delta_latency_p95_vs_classical": row.get("delta_latency_p95_vs_classical", ""),
                    "cpu_peak": row.get("cpu_peak", ""),
                    "pcap_bytes": row.get("pcap_bytes", ""),
                }
            )

        failed_steps = 0
        for (profile, mode), (pass_steps, fail_steps, rate) in compat_grouped.items():
            failed_steps += fail_steps
            compatibility_rows.append(
                {
                    "run_id": run_id,
                    "finished_utc": finished_utc,
                    "workload": workload,
                    "profile": profile,
                    "mode": mode,
                    "pass_steps": str(pass_steps),
                    "fail_steps": str(fail_steps),
                    "compatibility_rate": f"{rate:.2f}",
                }
            )

        overview_rows.append(
            {
                "run_id": run_id,
                "finished_utc": finished_utc,
                "workload": workload,
                "sessions": idx_row.get("sessions", ""),
                "latency_runs": idx_row.get("latency_runs", ""),
                "resumption_mode": idx_row.get("resumption_mode", ""),
                "acceptance_overall": acceptance,
                "failed_compat_steps": str(failed_steps),
            }
        )

    write_csv(
        output_dir / "latency_p95_timeseries.csv",
        [
            "run_id",
            "finished_utc",
            "workload",
            "profile",
            "mode",
            "latency_p95",
            "latency_success_rate",
            "delta_latency_p95_vs_classical",
            "cpu_peak",
            "pcap_bytes",
        ],
        latency_rows,
    )
    write_csv(
        output_dir / "compatibility_timeseries.csv",
        [
            "run_id",
            "finished_utc",
            "workload",
            "profile",
            "mode",
            "pass_steps",
            "fail_steps",
            "compatibility_rate",
        ],
        compatibility_rows,
    )
    write_csv(
        output_dir / "run_overview_timeseries.csv",
        [
            "run_id",
            "finished_utc",
            "workload",
            "sessions",
            "latency_runs",
            "resumption_mode",
            "acceptance_overall",
            "failed_compat_steps",
        ],
        overview_rows,
    )

    print(f"Wrote {output_dir / 'latency_p95_timeseries.csv'}")
    print(f"Wrote {output_dir / 'compatibility_timeseries.csv'}")
    print(f"Wrote {output_dir / 'run_overview_timeseries.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
