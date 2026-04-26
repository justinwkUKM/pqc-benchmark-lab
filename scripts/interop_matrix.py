#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate markdown interop report")
    parser.add_argument("--matrix-csv", required=True)
    parser.add_argument("--negative-csv", default=None)
    parser.add_argument("--tls-csv", default=None)
    parser.add_argument("--failures-csv", default=None)
    parser.add_argument("--summary-csv", default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dashboard-output", default=None)
    parser.add_argument("--metadata-json", default=None)
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parse_args()
    matrix_path = Path(args.matrix_csv).resolve()
    rows = read_csv(matrix_path)
    neg_rows = read_csv(Path(args.negative_csv).resolve()) if args.negative_csv else []
    tls_rows = read_csv(Path(args.tls_csv).resolve()) if args.tls_csv else []
    failure_rows = read_csv(Path(args.failures_csv).resolve()) if args.failures_csv else []
    metadata = {}
    if args.metadata_json:
        meta_path = Path(args.metadata_json)
        if meta_path.exists():
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))

    matrix_total = len(rows)
    matrix_pass = sum(1 for row in rows if row.get("status") == "pass")
    matrix_fail = matrix_total - matrix_pass
    neg_total = len(neg_rows)
    neg_pass = sum(1 for row in neg_rows if row.get("status") == "pass")
    neg_fail = neg_total - neg_pass
    tls_total = len(tls_rows)
    tls_pass = sum(1 for row in tls_rows if row.get("status") == "pass")
    tls_fail = tls_total - tls_pass

    failure_counter = Counter(row.get("failure_code", "") for row in failure_rows if row.get("failure_code"))

    summary_rows = [
        {"suite": "matrix", "total": matrix_total, "passed": matrix_pass, "failed": matrix_fail, "pass_rate": f"{(matrix_pass / matrix_total * 100):.2f}" if matrix_total else "100.00"},
        {"suite": "negative", "total": neg_total, "passed": neg_pass, "failed": neg_fail, "pass_rate": f"{(neg_pass / neg_total * 100):.2f}" if neg_total else "100.00"},
        {"suite": "tls", "total": tls_total, "passed": tls_pass, "failed": tls_fail, "pass_rate": f"{(tls_pass / tls_total * 100):.2f}" if tls_total else "100.00"},
    ]

    if args.summary_csv:
        summary_path = Path(args.summary_csv).resolve()
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["suite", "total", "passed", "failed", "pass_rate"])
            writer.writeheader()
            for row in summary_rows:
                writer.writerow(row)

    output_lines = ["# PQC Interoperability Report", ""]
    if metadata:
        output_lines.append(f"- Run ID: {metadata.get('run_id', 'N/A')}")
        output_lines.append(f"- Family: {metadata.get('family', 'N/A')}")
        output_lines.append(f"- Algorithm: {metadata.get('algorithm', 'N/A')}")
        output_lines.append("")

    output_lines.append("## Compatibility Matrix")
    output_lines.append("")
    output_lines.append("| Source Backend | Target Backend | Family | Algorithm | KEM Mode | Test Case | Status | Failure Code | Notes |")
    output_lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in rows:
        output_lines.append(
            f"| {row.get('source_backend', '')} | {row.get('target_backend', '')} | {row.get('family', '')} | {row.get('algorithm', '')} | {row.get('kem_mode', '')} | {row.get('test_case', '')} | {row.get('status', '')} | {row.get('failure_code', '')} | {row.get('notes', '')} |"
        )

    output_lines.append("")
    output_lines.append("## Negative Tests")
    output_lines.append("")
    output_lines.append("| Backend | Family | Algorithm | Case | Status | Failure Code | Notes |")
    output_lines.append("|---|---|---|---|---|---|---|")
    for row in neg_rows:
        output_lines.append(
            f"| {row.get('backend', '')} | {row.get('family', '')} | {row.get('algorithm', '')} | {row.get('case', '')} | {row.get('status', '')} | {row.get('failure_code', '')} | {row.get('notes', '')} |"
        )

    output_lines.append("")
    output_lines.append("## TLS Provider Probes")
    output_lines.append("")
    output_lines.append("| Provider | Mode | Status | Failure Code | Notes |")
    output_lines.append("|---|---|---|---|---|")
    for row in tls_rows:
        output_lines.append(
            f"| {row.get('provider', '')} | {row.get('mode', '')} | {row.get('status', '')} | {row.get('failure_code', '')} | {row.get('notes', '')} |"
        )

    output_lines.append("")
    output_lines.append("## Failure Taxonomy")
    output_lines.append("")
    output_lines.append("| Failure Code | Count |")
    output_lines.append("|---|---|")
    for code, count in sorted(failure_counter.items()):
        output_lines.append(f"| {code} | {count} |")

    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(output_lines) + "\n", encoding="utf-8")

    if args.dashboard_output:
        dashboard_lines = ["# Interop Dashboard", ""]
        if metadata:
            dashboard_lines.append(f"- Run ID: {metadata.get('run_id', 'N/A')}")
            dashboard_lines.append(f"- Family: {metadata.get('family', 'N/A')}")
            dashboard_lines.append(f"- Algorithm: {metadata.get('algorithm', 'N/A')}")
            if metadata.get("kem_mode"):
                dashboard_lines.append(f"- KEM Mode: {metadata.get('kem_mode')}")
            dashboard_lines.append("")

        has_kem_mode = any((row.get("kem_mode") or "").strip() for row in rows)
        if has_kem_mode:
            dashboard_lines.append("## KEM Mode Legend")
            dashboard_lines.append("")
            dashboard_lines.append("- `cross-backend`: full source->target matrix; off-diagonal rows measure real cross-provider key transfer interop.")
            dashboard_lines.append("- `local-only`: diagonal-only (`source_backend == target_backend`) checks; use this when provider key serialization blocks cross-backend transfer.")
            dashboard_lines.append("- Pass rates are only comparable across runs that use the same KEM mode.")
            dashboard_lines.append("")

        dashboard_lines.append("## Summary")
        dashboard_lines.append("")
        dashboard_lines.append("| Suite | Total | Passed | Failed | Pass Rate (%) |")
        dashboard_lines.append("|---|---:|---:|---:|---:|")
        for row in summary_rows:
            dashboard_lines.append(
                f"| {row['suite']} | {row['total']} | {row['passed']} | {row['failed']} | {row['pass_rate']} |"
            )

        dashboard_lines.append("")
        dashboard_lines.append("## Top Failure Codes")
        dashboard_lines.append("")
        dashboard_lines.append("| Failure Code | Count |")
        dashboard_lines.append("|---|---:|")
        for code, count in sorted(failure_counter.items(), key=lambda item: (-item[1], item[0])):
            dashboard_lines.append(f"| {code} | {count} |")

        dashboard_path = Path(args.dashboard_output).resolve()
        dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        dashboard_path.write_text("\n".join(dashboard_lines) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
