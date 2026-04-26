#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKENDS = ["openssl", "liboqs", "python"]


def run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def lines(text: str) -> list[str]:
    out = []
    for item in text.splitlines():
        item = item.strip()
        if item:
            out.append(item)
    return out


def openssl_algorithms(family: str, provider: str | None = None) -> list[str]:
    if family == "kem":
        cmd = ["docker", "exec", "tls-client", "openssl", "list", "-kem-algorithms"]
    else:
        cmd = ["docker", "exec", "tls-client", "openssl", "list", "-signature-algorithms"]
    code, out, _ = run(cmd)
    if code != 0:
        return []

    values = []
    for raw in lines(out):
        parts = raw.replace("{", "").replace("}", "").split()
        if not parts:
            continue
        name = parts[0]
        if provider:
            if f"@ {provider}" not in raw:
                continue
        values.append(name)
    return sorted(set(values))


def openssl_tls_groups() -> list[str]:
    code, out, _ = run(["docker", "exec", "tls-client", "openssl", "list", "-groups"])
    if code != 0:
        return []
    vals = []
    for raw in lines(out):
        vals.append(raw.split()[0])
    return sorted(set(vals))


def openssl_tls_sigalgs() -> list[str]:
    code, out, _ = run(["docker", "exec", "tls-client", "openssl", "list", "-signature-algorithms"])
    if code != 0:
        return []
    vals = []
    for raw in lines(out):
        vals.append(raw.replace("{", "").replace("}", "").split()[0])
    return sorted(set(vals))


def openssl_ciphersuites() -> list[str]:
    code, out, _ = run(["docker", "exec", "tls-client", "openssl", "ciphers", "-s", "-tls1_3"])
    if code != 0:
        return []
    return sorted(set(out.split(":")))


def python_family_list(family: str) -> list[str]:
    cmd = [
        "python3",
        str(ROOT / "scripts" / "adapters" / "python_adapter.py"),
        "list",
        "--family",
        family,
    ]
    code, out, _ = run(cmd)
    if code != 0:
        return []
    return sorted(set(lines(out)))


def backend_snapshot(name: str) -> dict:
    snapshot = {
        "backend": name,
        "version": {},
        "families": {"kem": [], "sig": []},
        "tls": {"groups": [], "signature_algorithms": [], "ciphersuites_tls13": []},
    }

    if name == "openssl":
        snapshot["families"]["kem"] = openssl_algorithms("kem")
        snapshot["families"]["sig"] = openssl_algorithms("sig")
        snapshot["tls"]["groups"] = openssl_tls_groups()
        snapshot["tls"]["signature_algorithms"] = openssl_tls_sigalgs()
        snapshot["tls"]["ciphersuites_tls13"] = openssl_ciphersuites()
        _, out, _ = run(["docker", "exec", "tls-client", "openssl", "version", "-a"])
        snapshot["version"]["openssl"] = out
    elif name == "liboqs":
        snapshot["families"]["kem"] = openssl_algorithms("kem", provider="oqsprovider")
        snapshot["families"]["sig"] = openssl_algorithms("sig", provider="oqsprovider")
        snapshot["tls"]["groups"] = openssl_tls_groups()
        snapshot["tls"]["signature_algorithms"] = openssl_tls_sigalgs()
        snapshot["tls"]["ciphersuites_tls13"] = openssl_ciphersuites()
        _, out, _ = run(["docker", "exec", "tls-client", "openssl", "list", "-providers", "-verbose"])
        snapshot["version"]["providers"] = out
    elif name == "python":
        snapshot["families"]["kem"] = python_family_list("kem")
        snapshot["families"]["sig"] = python_family_list("sig")
        _, out, _ = run(["python3", "--version"])
        snapshot["version"]["python"] = out
    else:
        raise SystemExit(f"Unsupported backend: {name}")

    return snapshot


def parse_backends(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_BACKENDS)
    return [part.strip() for part in value.split(",") if part.strip()]


def cmd_list(args: argparse.Namespace) -> int:
    backends = parse_backends(args.backends)
    snapshots = [backend_snapshot(item) for item in backends]
    if args.family:
        for snap in snapshots:
            for item in snap["families"].get(args.family, []):
                print(f"{snap['backend']}:{item}")
        return 0

    print(json.dumps(snapshots, indent=2))
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    backends = parse_backends(args.backends)
    out_dir = Path(args.out).resolve() if args.out else (ROOT / "results" / "catalog" / time.strftime("%Y%m%d-%H%M%S"))
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backends": [backend_snapshot(item) for item in backends],
    }
    out_file = out_dir / "capabilities.json"
    out_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(out_file)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Catalog backend algorithm capabilities")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List capabilities")
    p_list.add_argument("--backends", default=None, help="CSV list of backends")
    p_list.add_argument("--family", choices=["kem", "sig"], default=None)
    p_list.set_defaults(handler=cmd_list)

    p_snapshot = sub.add_parser("snapshot", help="Save capability snapshot")
    p_snapshot.add_argument("--backends", default=None, help="CSV list of backends")
    p_snapshot.add_argument("--out", default=None, help="Output directory")
    p_snapshot.set_defaults(handler=cmd_snapshot)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
