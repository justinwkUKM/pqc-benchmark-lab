#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Python PQ adapter")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list")
    list_cmd.add_argument("--family", choices=["kem", "sig"], required=True)

    run_cmd = sub.add_parser("run")
    run_cmd.add_argument("--family", choices=["kem", "sig"], required=True)
    run_cmd.add_argument("--algorithm", required=True)
    run_cmd.add_argument("--out", required=True)

    return parser.parse_args()


def has_oqs() -> bool:
    try:
        import oqs  # noqa: F401

        return True
    except Exception:
        return False


def list_algorithms(family: str) -> list[str]:
    import oqs

    if family == "kem":
        return sorted(oqs.get_enabled_kem_mechanisms())
    return sorted(oqs.get_enabled_sig_mechanisms())


def run_benchmark(family: str, algorithm: str) -> dict:
    import oqs

    started = time.time_ns()
    if family == "kem":
        with oqs.KeyEncapsulation(algorithm) as kem:
            pub = kem.generate_keypair()
            ct, ss = kem.encap_secret(pub)
            ss2 = kem.decap_secret(ct)
            ok = ss == ss2
            return {
                "operation_results": {
                    "keygen": 1,
                    "encaps": 1,
                    "decaps": 1,
                },
                "artifacts": {
                    "public_key_len": len(pub),
                    "ciphertext_len": len(ct),
                    "shared_secret_len": len(ss),
                },
                "verify_ok": ok,
                "elapsed_ns": time.time_ns() - started,
            }

    with oqs.Signature(algorithm) as sig:
        pub = sig.generate_keypair()
        message = b"pqc-lab-python-adapter"
        signature = sig.sign(message)
        ok = sig.verify(message, signature, pub)
        return {
            "operation_results": {
                "keygen": 1,
                "signs": 1,
                "verify": 1,
            },
            "artifacts": {
                "public_key_len": len(pub),
                "signature_len": len(signature),
                "message_len": len(message),
            },
            "verify_ok": ok,
            "elapsed_ns": time.time_ns() - started,
        }


def write_run(path: Path, family: str, algorithm: str, status: str, reason: str, details: dict) -> None:
    payload = {
        "run_id": f"python-{int(time.time())}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "playground",
        "backend": "python",
        "family": family,
        "algorithm": algorithm,
        "parameter_set": algorithm,
        "operation": "benchmark",
        "status": status,
        "error_code": reason,
        "error_message": "",
        "host": platform.platform(),
        "operation_results": details.get("operation_results", {}),
        "artifacts": details.get("artifacts", {}),
        "verify_ok": details.get("verify_ok"),
        "timing_ns": details.get("elapsed_ns"),
        "raw": details,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    if args.command == "list":
        if not has_oqs():
            return 0
        for item in list_algorithms(args.family):
            print(item)
        return 0

    out_path = Path(args.out).resolve()
    if not has_oqs():
        write_run(
            out_path,
            args.family,
            args.algorithm,
            "unsupported",
            "python_oqs_module_missing",
            {},
        )
        return 2

    try:
        details = run_benchmark(args.family, args.algorithm)
    except Exception as exc:
        write_run(
            out_path,
            args.family,
            args.algorithm,
            "error",
            "benchmark_failed",
            {"exception": str(exc), "python": sys.version, "cwd": os.getcwd()},
        )
        return 1

    write_run(out_path, args.family, args.algorithm, "ok", "", details)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
