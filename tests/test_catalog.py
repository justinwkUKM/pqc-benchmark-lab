from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from conftest import load_script_module


if not (Path(__file__).resolve().parent.parent / "scripts" / "catalog.py").exists():
    pytest.skip("scripts/catalog.py not present", allow_module_level=True)


catalog = load_script_module("catalog")


def test_lines_removes_blanks_and_whitespace() -> None:
    assert catalog.lines("\n alpha \n\n beta\n") == ["alpha", "beta"]


def test_parse_backends_uses_defaults() -> None:
    assert catalog.parse_backends(None) == ["openssl", "liboqs", "python"]


def test_backend_snapshot_raises_for_unknown_backend() -> None:
    with pytest.raises(SystemExit, match="Unsupported backend"):
        catalog.backend_snapshot("unknown")


def test_cmd_list_outputs_backend_prefixed_family(capsys, monkeypatch) -> None:
    monkeypatch.setattr(
        catalog,
        "backend_snapshot",
        lambda _: {"backend": "python", "families": {"kem": ["mlkem768"], "sig": []}},
    )
    args = argparse.Namespace(backends="python", family="kem")

    assert catalog.cmd_list(args) == 0
    assert capsys.readouterr().out.strip() == "python:mlkem768"
