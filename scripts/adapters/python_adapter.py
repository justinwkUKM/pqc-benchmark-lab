#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
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

    interop_cmd = sub.add_parser("interop")
    interop_cmd.add_argument("--family", choices=["kem", "sig"], required=True)
    interop_cmd.add_argument("--algorithm", required=True)
    interop_cmd.add_argument("--operation", choices=["capabilities", "keygen", "sign", "verify", "encap", "decap"], required=True)
    interop_cmd.add_argument("--in", dest="in_path", required=True)
    interop_cmd.add_argument("--out", required=True)

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


def b64_encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64_decode(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"), validate=True)


def write_interop(path: Path, family: str, algorithm: str, operation: str, status: str, reason: str, message: str, data: dict) -> None:
    payload = {
        "backend": "python",
        "family": family,
        "algorithm": algorithm,
        "operation": operation,
        "status": status,
        "error_code": reason,
        "error_message": message,
        "data": data,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def interop_capabilities(family: str, algorithm: str) -> dict:
    if not has_oqs():
        return {
            "supported_algorithm": False,
            "supported_operations": [],
            "reason": "python_oqs_module_missing",
        }
    supported = algorithm in set(list_algorithms(family))
    operations = ["keygen"]
    if family == "sig":
        operations.extend(["sign", "verify"])
    else:
        operations.extend(["encap", "decap"])
    return {
        "supported_algorithm": supported,
        "supported_operations": operations if supported else [],
    }


def run_interop(family: str, algorithm: str, operation: str, input_payload: dict) -> tuple[str, str, str, dict]:
    import oqs

    if operation == "capabilities":
        return "ok", "", "", interop_capabilities(family, algorithm)

    if not has_oqs():
        return "unsupported", "python_oqs_module_missing", "python-oqs module is unavailable", {}

    capabilities = interop_capabilities(family, algorithm)
    if not capabilities.get("supported_algorithm"):
        return "unsupported", "unsupported_algorithm", "algorithm is not enabled in python-oqs", {}

    try:
        if operation == "keygen":
            if family == "sig":
                with oqs.Signature(algorithm) as sig:
                    public_key = sig.generate_keypair()
                    secret_key = sig.export_secret_key()
            else:
                with oqs.KeyEncapsulation(algorithm) as kem:
                    public_key = kem.generate_keypair()
                    secret_key = kem.export_secret_key()
            return "ok", "", "", {
                "public_key_b64": b64_encode(public_key),
                "secret_key_b64": b64_encode(secret_key),
            }

        if family == "sig" and operation == "sign":
            secret_key = b64_decode(str(input_payload["secret_key_b64"]))
            message = b64_decode(str(input_payload["message_b64"]))
            with oqs.Signature(algorithm, secret_key=secret_key) as sig:
                signature = sig.sign(message)
            return "ok", "", "", {"signature_b64": b64_encode(signature)}

        if family == "sig" and operation == "verify":
            public_key = b64_decode(str(input_payload["public_key_b64"]))
            message = b64_decode(str(input_payload["message_b64"]))
            signature = b64_decode(str(input_payload["signature_b64"]))
            with oqs.Signature(algorithm) as sig:
                verified = bool(sig.verify(message, signature, public_key))
            return "ok", "", "", {"verified": verified}

        if family == "kem" and operation == "encap":
            public_key = b64_decode(str(input_payload["public_key_b64"]))
            with oqs.KeyEncapsulation(algorithm) as kem:
                ciphertext, shared_secret = kem.encap_secret(public_key)
            return "ok", "", "", {
                "ciphertext_b64": b64_encode(ciphertext),
                "shared_secret_b64": b64_encode(shared_secret),
            }

        if family == "kem" and operation == "decap":
            secret_key = b64_decode(str(input_payload["secret_key_b64"]))
            ciphertext = b64_decode(str(input_payload["ciphertext_b64"]))
            with oqs.KeyEncapsulation(algorithm, secret_key=secret_key) as kem:
                shared_secret = kem.decap_secret(ciphertext)
            return "ok", "", "", {"shared_secret_b64": b64_encode(shared_secret)}

        return "unsupported", "unsupported_operation", "operation is not supported for this family", {}
    except KeyError as exc:
        return "error", "parse_error", f"missing field: {exc}", {}
    except Exception as exc:
        return "error", "interop_failed", str(exc), {}


def main() -> int:
    args = parse_args()

    if args.command == "list":
        if not has_oqs():
            return 0
        for item in list_algorithms(args.family):
            print(item)
        return 0

    out_path = Path(args.out).resolve()

    if args.command == "interop":
        input_payload: dict = {}
        try:
            input_payload = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
        except Exception:
            input_payload = {}

        status, reason, message, data = run_interop(args.family, args.algorithm, args.operation, input_payload)
        write_interop(out_path, args.family, args.algorithm, args.operation, status, reason, message, data)
        if status == "ok":
            return 0
        if status == "unsupported":
            return 2
        return 1

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
