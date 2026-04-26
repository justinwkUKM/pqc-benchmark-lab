from __future__ import annotations

import argparse
import csv

import pytest

from conftest import load_script_module


config_query = load_script_module("config_query")


def test_as_bool_parses_common_values() -> None:
    assert config_query.as_bool("yes") is True
    assert config_query.as_bool("OFF") is False
    assert config_query.as_bool("unexpected", default=False) is False


def test_split_pipe_ignores_empty_segments() -> None:
    assert config_query.split_pipe("a| b || c ") == ["a", "b", "c"]


def test_find_row_returns_matching_entry(tmp_path) -> None:
    csv_path = tmp_path / "rows.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["profile", "delay_ms"])
        writer.writeheader()
        writer.writerow({"profile": "dc_lan", "delay_ms": "0"})
        writer.writerow({"profile": "cross_region", "delay_ms": "60"})

    row = config_query.find_row(csv_path, "profile", "cross_region")
    assert row["delay_ms"] == "60"


def test_find_row_raises_for_unknown_key(tmp_path) -> None:
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("profile\nalpha\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Unknown profile: beta"):
        config_query.find_row(csv_path, "profile", "beta")


def test_cmd_expand_all_modes_prints_enabled_modes(capsys, monkeypatch) -> None:
    monkeypatch.setattr(config_query, "read_csv", lambda _: [{"mode": "classical", "enabled": "true"}])
    args = argparse.Namespace(field="modes", value="all")

    assert config_query.cmd_expand(args) == 0
    assert capsys.readouterr().out.strip() == "classical"
