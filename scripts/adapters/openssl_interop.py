#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import shlex
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OpenSSL/liboqs interop adapter runner")
    parser.add_argument("--backend", choices=["openssl", "liboqs"], required=True)
    parser.add_argument("--family", choices=["kem", "sig"], required=True)
    parser.add_argument("--algorithm", required=True)
    parser.add_argument("--operation", choices=["capabilities", "keygen", "sign", "verify", "encap", "decap"], required=True)
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def emit(path: Path, backend: str, family: str, algorithm: str, operation: str, status: str, error_code: str, error_message: str, data: dict) -> None:
    payload = {
        "backend": backend,
        "family": family,
        "algorithm": algorithm,
        "operation": operation,
        "status": status,
        "error_code": error_code,
        "error_message": error_message,
        "data": data,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def provider_flags(backend: str) -> list[str]:
    if backend == "liboqs":
        return ["-provider", "oqsprovider", "-provider", "default"]
    return []


def docker_exec(args: list[str], input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    command = ["docker", "exec", "-i", "tls-client", *args]
    return subprocess.run(command, input=input_bytes, check=False, capture_output=True)


def sh(command: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return docker_exec(["sh", "-lc", command], input_bytes=input_bytes)


def mktemp_dir() -> str:
    proc = sh("mktemp -d /tmp/interop.XXXXXX")
    if proc.returncode != 0:
        raise RuntimeError("failed to allocate temp directory in tls-client container")
    return proc.stdout.decode("utf-8", errors="replace").strip()


def rmrf(path: str) -> None:
    sh(f"rm -rf {shlex.quote(path)}")


def write_remote(path: str, data: bytes) -> None:
    proc = sh(f"cat > {shlex.quote(path)}", input_bytes=data)
    if proc.returncode != 0:
        raise RuntimeError("failed writing remote file")


def read_remote(path: str) -> bytes:
    proc = sh(f"base64 < {shlex.quote(path)}")
    if proc.returncode != 0:
        raise RuntimeError("failed reading remote file")
    b64 = b"".join(proc.stdout.splitlines())
    return base64.b64decode(b64)


def openssl_cmd(flags: list[str], *parts: str) -> list[str]:
    return ["openssl", *parts[:1], *flags, *parts[1:]]


def list_algorithms(family: str, backend: str) -> set[str]:
    if family == "kem":
        cmd = openssl_cmd(provider_flags(backend), "list", "-kem-algorithms")
    else:
        cmd = openssl_cmd(provider_flags(backend), "list", "-signature-algorithms")
    proc = docker_exec(cmd)
    if proc.returncode != 0:
        return set()
    algorithms: set[str] = set()
    for raw in proc.stdout.decode("utf-8", errors="replace").splitlines():
        line = raw.strip().replace("{", " ").replace("}", " ")
        if not line:
            continue
        name = line.split()[0].strip()
        if name:
            algorithms.add(name)
    return algorithms


def run_op(backend: str, family: str, algorithm: str, operation: str, payload: dict) -> tuple[str, str, str, dict]:
    supported = algorithm in list_algorithms(family, backend)
    if operation == "capabilities":
        operations = ["keygen"]
        if family == "sig":
            operations.extend(["sign", "verify"])
        else:
            operations.extend(["encap", "decap"])
        return "ok", "", "", {"supported_algorithm": supported, "supported_operations": operations if supported else []}

    if not supported:
        return "unsupported", "unsupported_algorithm", "algorithm is not available in this provider", {}

    if family == "sig" and operation in {"encap", "decap"}:
        return "unsupported", "unsupported_operation", "operation not valid for sig family", {}
    if family == "kem" and operation in {"sign", "verify"}:
        return "unsupported", "unsupported_operation", "operation not valid for kem family", {}

    flags = provider_flags(backend)
    work = mktemp_dir()
    try:
        sk = f"{work}/sk.bin"
        pk = f"{work}/pk.bin"
        msg = f"{work}/msg.bin"
        sig = f"{work}/sig.bin"
        ct = f"{work}/ct.bin"
        ss = f"{work}/ss.bin"

        if operation == "keygen":
            gen_cmd = openssl_cmd(flags, "genpkey", "-algorithm", algorithm, "-out", sk)
            gen = docker_exec(gen_cmd)
            if gen.returncode != 0:
                stderr = gen.stderr.decode("utf-8", errors="replace")
                if "No encoders were found" in stderr:
                    return "unsupported", "unsupported_operation", "provider does not support serializing this key type", {}
                return "error", "interop_failed", "key generation failed", {}
            pub_cmd = openssl_cmd(flags, "pkey", "-in", sk, "-pubout", "-out", pk)
            pub = docker_exec(pub_cmd)
            if pub.returncode != 0:
                return "error", "interop_failed", "public key export failed", {}
            return "ok", "", "", {
                "public_key_b64": base64.b64encode(read_remote(pk)).decode("ascii"),
                "secret_key_b64": base64.b64encode(read_remote(sk)).decode("ascii"),
            }

        if operation == "sign":
            write_remote(sk, base64.b64decode(str(payload["secret_key_b64"]).encode("ascii"), validate=True))
            write_remote(msg, base64.b64decode(str(payload["message_b64"]).encode("ascii"), validate=True))
            sign_cmd = openssl_cmd(flags, "pkeyutl", "-sign", "-inkey", sk, "-rawin", "-in", msg, "-out", sig)
            signed = docker_exec(sign_cmd)
            if signed.returncode != 0:
                stderr = signed.stderr.decode("utf-8", errors="replace").strip()
                return "error", "parse_error", f"sign operation failed: {stderr}"[:240], {}
            return "ok", "", "", {"signature_b64": base64.b64encode(read_remote(sig)).decode("ascii")}

        if operation == "verify":
            write_remote(pk, base64.b64decode(str(payload["public_key_b64"]).encode("ascii"), validate=True))
            write_remote(msg, base64.b64decode(str(payload["message_b64"]).encode("ascii"), validate=True))
            write_remote(sig, base64.b64decode(str(payload["signature_b64"]).encode("ascii"), validate=True))
            verify_cmd = openssl_cmd(
                flags,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                pk,
                "-sigfile",
                sig,
                "-rawin",
                "-in",
                msg,
            )
            verified = docker_exec(verify_cmd)
            if verified.returncode == 0:
                return "ok", "", "", {"verified": True}
            stderr = verified.stderr.decode("utf-8", errors="replace").lower()
            if "signature verification failure" in stderr:
                return "ok", "", "", {"verified": False}
            return "error", "parse_error", "verify operation failed", {}

        if operation == "encap":
            write_remote(pk, base64.b64decode(str(payload["public_key_b64"]).encode("ascii"), validate=True))
            encap_cmd = openssl_cmd(flags, "pkeyutl", "-encap", "-pubin", "-inkey", pk, "-out", ct, "-secret", ss)
            encapped = docker_exec(encap_cmd)
            if encapped.returncode != 0:
                stderr = encapped.stderr.decode("utf-8", errors="replace")
                if "Unknown option" in stderr or "not supported" in stderr:
                    return "unsupported", "unsupported_operation", "provider does not support pkeyutl encapsulation", {}
                return "error", "parse_error", "encapsulation failed", {}
            return "ok", "", "", {
                "ciphertext_b64": base64.b64encode(read_remote(ct)).decode("ascii"),
                "shared_secret_b64": base64.b64encode(read_remote(ss)).decode("ascii"),
            }

        if operation == "decap":
            write_remote(sk, base64.b64decode(str(payload["secret_key_b64"]).encode("ascii"), validate=True))
            write_remote(ct, base64.b64decode(str(payload["ciphertext_b64"]).encode("ascii"), validate=True))
            decap_cmd = openssl_cmd(flags, "pkeyutl", "-decap", "-inkey", sk, "-in", ct, "-secret", ss)
            decapped = docker_exec(decap_cmd)
            if decapped.returncode != 0:
                stderr = decapped.stderr.decode("utf-8", errors="replace")
                if "Unknown option" in stderr or "not supported" in stderr:
                    return "unsupported", "unsupported_operation", "provider does not support pkeyutl decapsulation", {}
                return "error", "parse_error", "decapsulation failed", {}
            return "ok", "", "", {"shared_secret_b64": base64.b64encode(read_remote(ss)).decode("ascii")}

        return "unsupported", "unsupported_operation", "operation not implemented", {}
    except KeyError as exc:
        return "error", "parse_error", f"missing field: {exc}", {}
    except Exception as exc:
        return "error", "interop_failed", str(exc), {}
    finally:
        rmrf(work)


def main() -> int:
    args = parse_args()
    out_path = Path(args.out).resolve()
    in_payload = {}
    try:
        in_payload = json.loads(Path(args.in_path).read_text(encoding="utf-8"))
    except Exception:
        in_payload = {}

    status, code, message, data = run_op(args.backend, args.family, args.algorithm, args.operation, in_payload)
    emit(out_path, args.backend, args.family, args.algorithm, args.operation, status, code, message, data)
    if status == "ok":
        return 0
    if status == "unsupported":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
