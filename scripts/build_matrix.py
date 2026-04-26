#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build executable algorithm matrix from capability snapshot")
    parser.add_argument("--capabilities", required=True, help="Path to capabilities.json")
    parser.add_argument("--catalog", default=str(ROOT / "vectors" / "catalog" / "algorithms.json"))
    parser.add_argument("--families", default="kem,sig", help="CSV family filter")
    parser.add_argument("--backends", default="openssl,liboqs,python", help="CSV backend filter")
    parser.add_argument("--min-level", type=int, default=0, help="Minimum security level")
    parser.add_argument("--max-level", type=int, default=10, help="Maximum security level")
    parser.add_argument("--require-all-backends", action="store_true", help="Only include algorithms supported by all selected backends")
    parser.add_argument("--output", required=True, help="Output CSV path")
    return parser.parse_args()


def split_csv(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def load_json(path: str) -> dict:
    return json.loads(Path(path).resolve().read_text(encoding="utf-8"))


def support_map(capabilities: dict, selected_backends: list[str], selected_families: list[str]) -> dict[tuple[str, str], set[str]]:
    support: dict[tuple[str, str], set[str]] = {}
    for backend in capabilities.get("backends", []):
        backend_name = backend.get("backend")
        if backend_name not in selected_backends:
            continue
        families = backend.get("families", {})
        for family in selected_families:
            for algorithm in families.get(family, []):
                key = (family, algorithm.lower())
                support.setdefault(key, set()).add(backend_name)
    return support


def normalize_catalog(catalog: dict) -> dict[tuple[str, str], dict]:
    index: dict[tuple[str, str], dict] = {}
    for item in catalog.get("algorithms", []):
        family = item.get("family", "").strip()
        name = item.get("canonical_name", "").strip().lower()
        if family and name:
            index[(family, name)] = item
    return index


def main() -> int:
    args = parse_args()
    capabilities = load_json(args.capabilities)
    catalog = load_json(args.catalog)

    selected_families = split_csv(args.families)
    selected_backends = split_csv(args.backends)

    support = support_map(capabilities, selected_backends, selected_families)
    catalog_index = normalize_catalog(catalog)

    rows: list[dict[str, str]] = []
    for (family, algorithm), backends in sorted(support.items()):
        metadata = catalog_index.get((family, algorithm))
        if not metadata:
            continue

        level = int(metadata.get("security_level", 0))
        if level < args.min_level or level > args.max_level:
            continue

        if args.require_all_backends and backends != set(selected_backends):
            continue

        for backend in sorted(backends):
            rows.append(
                {
                    "family": family,
                    "algorithm": algorithm,
                    "backend": backend,
                    "security_level": str(level),
                    "maturity": metadata.get("maturity", ""),
                    "key_size_class": metadata.get("key_size_class", ""),
                    "known_caveats": "|".join(metadata.get("known_caveats", [])),
                    "command": f"./scripts/playground.sh run --backend {backend} --family {family} --alg {algorithm}",
                }
            )

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "family",
        "algorithm",
        "backend",
        "security_level",
        "maturity",
        "key_size_class",
        "known_caveats",
        "command",
    ]
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {out_path} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
