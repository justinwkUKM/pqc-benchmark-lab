#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate markdown interop report")
    parser.add_argument("--matrix-csv", required=True)
    parser.add_argument("--negative-csv", default=None)
    parser.add_argument("--output", required=True)
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
    metadata = {}
    if args.metadata_json:
        metadata = json.loads(Path(args.metadata_json).read_text(encoding="utf-8"))

    output_lines = ["# PQC Interoperability Report", ""]
    if metadata:
        output_lines.append(f"- Run ID: {metadata.get('run_id', 'N/A')}")
        output_lines.append(f"- Family: {metadata.get('family', 'N/A')}")
        output_lines.append(f"- Algorithm: {metadata.get('algorithm', 'N/A')}")
        output_lines.append("")

    output_lines.append("## Compatibility Matrix")
    output_lines.append("")
    output_lines.append("| Source Backend | Target Backend | Status | Notes |")
    output_lines.append("|---|---|---|---|")
    for row in rows:
        output_lines.append(
            f"| {row.get('source_backend', '')} | {row.get('target_backend', '')} | {row.get('status', '')} | {row.get('notes', '')} |"
        )

    output_lines.append("")
    output_lines.append("## Negative Tests")
    output_lines.append("")
    output_lines.append("| Backend | Case | Status | Notes |")
    output_lines.append("|---|---|---|---|")
    for row in neg_rows:
        output_lines.append(
            f"| {row.get('backend', '')} | {row.get('case', '')} | {row.get('status', '')} | {row.get('notes', '')} |"
        )

    out = Path(args.output).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
