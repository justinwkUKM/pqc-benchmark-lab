from __future__ import annotations

from conftest import load_script_module


parse_speed = load_script_module("parse_speed")


def test_parse_metrics_skips_zero_and_other_algorithms() -> None:
    text = "\n".join(
        [
            "+R1:100:mlkem768:2.0",
            "+R2:200:mlkem768:0",
            "+R3:999:other:1.0",
            "noise",
        ]
    )

    metrics = parse_speed.parse_metrics(text, "mlkem768")
    assert metrics == {"op_1": 50.0}


def test_canonical_hash_is_order_independent() -> None:
    payload_a = {"a": 1, "b": {"x": 2, "y": 3}}
    payload_b = {"b": {"y": 3, "x": 2}, "a": 1}

    assert parse_speed.canonical_hash(payload_a) == parse_speed.canonical_hash(payload_b)
