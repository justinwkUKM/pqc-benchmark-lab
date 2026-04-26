from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pytest

from conftest import load_script_module


if not (Path(__file__).resolve().parent.parent / "scripts" / "build_matrix.py").exists():
    pytest.skip("scripts/build_matrix.py not present", allow_module_level=True)


build_matrix = load_script_module("build_matrix")


def test_split_csv_trims_values() -> None:
    assert build_matrix.split_csv("kem, sig ,, ") == ["kem", "sig"]


def test_support_map_filters_backends_and_families() -> None:
    capabilities = {
        "backends": [
            {"backend": "openssl", "families": {"kem": ["mlkem768"], "sig": ["mldsa65"]}},
            {"backend": "python", "families": {"kem": ["mlkem768"]}},
        ]
    }

    support = build_matrix.support_map(capabilities, ["openssl"], ["kem"])
    assert support == {("kem", "mlkem768"): {"openssl"}}


def test_main_writes_filtered_rows(tmp_path, monkeypatch) -> None:
    capabilities_path = tmp_path / "capabilities.json"
    catalog_path = tmp_path / "catalog.json"
    output_path = tmp_path / "matrix.csv"

    capabilities_path.write_text(
        json.dumps(
            {
                "backends": [
                    {"backend": "openssl", "families": {"kem": ["mlkem768"]}},
                    {"backend": "python", "families": {"kem": ["mlkem768"]}},
                ]
            }
        ),
        encoding="utf-8",
    )
    catalog_path.write_text(
        json.dumps(
            {
                "algorithms": [
                    {
                        "family": "kem",
                        "canonical_name": "mlkem768",
                        "security_level": 3,
                        "maturity": "stable",
                        "key_size_class": "medium",
                        "known_caveats": ["example"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        build_matrix,
        "parse_args",
        lambda: argparse.Namespace(
            capabilities=str(capabilities_path),
            catalog=str(catalog_path),
            families="kem",
            backends="openssl,python",
            min_level=1,
            max_level=5,
            require_all_backends=False,
            output=str(output_path),
        ),
    )

    assert build_matrix.main() == 0
    with output_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 2
    assert {row["backend"] for row in rows} == {"openssl", "python"}
    assert all(row["algorithm"] == "mlkem768" for row in rows)
