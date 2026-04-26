#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
CONFIG_MODES = ROOT_DIR / "config" / "modes.csv"


FAILURE_MAP = {
    "unsupported_algorithm": "unsupported_alg",
    "unsupported_operation": "unsupported_operation",
    "parse_error": "parse_error",
    "interop_failed": "adapter_error",
    "python_oqs_module_missing": "adapter_unavailable",
    "adapter_failed": "adapter_error",
    "benchmark_failed": "adapter_error",
}


@dataclass
class InteropResult:
    status: str
    failure_code: str
    notes: str
    payload: dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run interop matrix, negative tests, and TLS probes")
    parser.add_argument("--command", choices=["matrix", "negative", "tls", "report"], required=True)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--family", choices=["kem", "sig"], default=None)
    parser.add_argument("--algorithm", default=None)
    parser.add_argument("--backends", default="openssl,liboqs,python")
    parser.add_argument("--kem-mode", choices=["cross-backend", "local-only"], default="cross-backend")
    parser.add_argument("--mode", default=None)
    parser.add_argument("--providers", default="openssl,liboqs,python")
    return parser.parse_args()


def parse_csv_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def canonical_failure(code: str, status: str) -> str:
    if status == "pass":
        return ""
    lowered = (code or "").strip().lower()
    if lowered in FAILURE_MAP:
        return FAILURE_MAP[lowered]
    if lowered:
        return lowered
    return "unknown_failure"


def invoke_adapter(backend: str, family: str, algorithm: str, operation: str, payload: dict) -> InteropResult:
    with tempfile.TemporaryDirectory(prefix="interop-") as temp_dir:
        in_path = Path(temp_dir) / "in.json"
        out_path = Path(temp_dir) / "out.json"
        write_json(in_path, payload)

        if backend == "python":
            cmd = [
                "python3",
                str(SCRIPT_DIR / "adapters" / "python_adapter.py"),
                "interop",
                "--family",
                family,
                "--algorithm",
                algorithm,
                "--operation",
                operation,
                "--in",
                str(in_path),
                "--out",
                str(out_path),
            ]
        else:
            cmd = [
                str(SCRIPT_DIR / "adapters" / f"{backend}_adapter.sh"),
                "interop",
                "--family",
                family,
                "--algorithm",
                algorithm,
                "--operation",
                operation,
                "--in",
                str(in_path),
                "--out",
                str(out_path),
            ]

        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
        response = load_json(out_path)
        if not response:
            return InteropResult(
                status="fail",
                failure_code="parse_error",
                notes=f"adapter produced invalid response (rc={proc.returncode})",
                payload={},
            )

        adapter_status = str(response.get("status", "error")).lower()
        if proc.returncode == 0 and adapter_status == "ok":
            return InteropResult(status="pass", failure_code="", notes="ok", payload=response)

        failure = canonical_failure(str(response.get("error_code", "")), "fail")
        notes = str(response.get("error_message") or response.get("error_code") or f"adapter_rc_{proc.returncode}")
        return InteropResult(status="fail", failure_code=failure, notes=notes, payload=response)


def mode_group(mode: str) -> str:
    with CONFIG_MODES.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("mode") == mode:
                return row.get("kex_group", "")
    raise ValueError(f"mode not found: {mode}")


def tls_probe(provider: str, mode: str) -> tuple[str, str, str]:
    set_mode_cmd = [str(SCRIPT_DIR / "set_mode.sh"), mode]
    set_mode_proc = subprocess.run(set_mode_cmd, check=False, capture_output=True, text=True)
    if set_mode_proc.returncode != 0:
        return "fail", "set_mode_failed", "failed to activate mode"

    group = mode_group(mode)
    if provider == "openssl":
        cmd = [
            "docker",
            "exec",
            "tls-client",
            "openssl",
            "s_client",
            "-connect",
            "tls-server:4433",
            "-groups",
            group,
            "-CAfile",
            "/opt/nginx/certs/server.crt",
            "-partial_chain",
            "-brief",
        ]
    elif provider == "liboqs":
        cmd = [
            "docker",
            "exec",
            "tls-client",
            "openssl",
            "s_client",
            "-provider",
            "oqsprovider",
            "-connect",
            "tls-server:4433",
            "-groups",
            group,
            "-CAfile",
            "/opt/nginx/certs/server.crt",
            "-partial_chain",
            "-brief",
        ]
    elif provider == "python":
        cmd = [
            "python3",
            "-c",
            (
                "import ssl, socket;"
                "ctx=ssl.create_default_context(cafile='certs/server.crt');"
                "s=ctx.wrap_socket(socket.socket(), server_hostname='tls-server');"
                "s.connect(('127.0.0.1', 4433));"
                "s.close()"
            ),
        ]
    else:
        return "fail", "unsupported_provider", "provider is not defined"

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode == 0:
        return "pass", "", "handshake_ok"

    stderr = (proc.stderr or "").lower()
    if "alert" in stderr:
        return "fail", "tls_alert", "tls alert received"
    return "fail", "tls_probe_failed", "provider probe failed"


def run_matrix(out_dir: Path, family: str, algorithm: str, backends: list[str], kem_mode: str) -> None:
    rows: list[dict] = []
    failures: list[dict] = []

    for src in backends:
        if family == "kem" and kem_mode == "local-only":
            target_backends = [src]
        else:
            target_backends = backends
        for dst in target_backends:
            case = "cross_sign_verify" if family == "sig" else "cross_encap_decap"
            status = "pass"
            failure_code = ""
            notes = "ok"

            keygen = invoke_adapter(src, family, algorithm, "keygen", {})
            if keygen.status != "pass":
                status = "fail"
                failure_code = keygen.failure_code
                notes = f"{src}:keygen:{keygen.notes}"
            else:
                key_data = keygen.payload.get("data", {})
                if family == "sig":
                    message_b64 = "aW50ZXJvcC1zaWduYXR1cmUtdGVzdA=="
                    sign = invoke_adapter(
                        src,
                        family,
                        algorithm,
                        "sign",
                        {
                            "secret_key_b64": key_data.get("secret_key_b64", ""),
                            "message_b64": message_b64,
                        },
                    )
                    if sign.status != "pass":
                        status = "fail"
                        failure_code = sign.failure_code
                        notes = f"{src}:sign:{sign.notes}"
                    else:
                        verify = invoke_adapter(
                            dst,
                            family,
                            algorithm,
                            "verify",
                            {
                                "public_key_b64": key_data.get("public_key_b64", ""),
                                "message_b64": message_b64,
                                "signature_b64": sign.payload.get("data", {}).get("signature_b64", ""),
                            },
                        )
                        if verify.status != "pass":
                            status = "fail"
                            failure_code = verify.failure_code
                            notes = f"{dst}:verify:{verify.notes}"
                        elif not bool(verify.payload.get("data", {}).get("verified", False)):
                            status = "fail"
                            failure_code = "verify_mismatch"
                            notes = "signature verify returned false"
                else:
                    encap = invoke_adapter(
                        dst,
                        family,
                        algorithm,
                        "encap",
                        {
                            "public_key_b64": key_data.get("public_key_b64", ""),
                        },
                    )
                    if encap.status != "pass":
                        status = "fail"
                        failure_code = encap.failure_code
                        notes = f"{dst}:encap:{encap.notes}"
                    else:
                        decap = invoke_adapter(
                            src,
                            family,
                            algorithm,
                            "decap",
                            {
                                "secret_key_b64": key_data.get("secret_key_b64", ""),
                                "ciphertext_b64": encap.payload.get("data", {}).get("ciphertext_b64", ""),
                            },
                        )
                        if decap.status != "pass":
                            status = "fail"
                            failure_code = decap.failure_code
                            notes = f"{src}:decap:{decap.notes}"
                        elif decap.payload.get("data", {}).get("shared_secret_b64") != encap.payload.get("data", {}).get("shared_secret_b64"):
                            status = "fail"
                            failure_code = "kem_mismatch"
                            notes = "encap/decap shared secret mismatch"

            row = {
                "source_backend": src,
                "target_backend": dst,
                "family": family,
                "algorithm": algorithm,
                "kem_mode": kem_mode if family == "kem" else "",
                "test_case": case,
                "status": status,
                "failure_code": failure_code,
                "notes": notes if family != "kem" or kem_mode != "local-only" else f"{notes}; local_only_mode",
            }
            rows.append(row)
            if status != "pass":
                failures.append(
                    {
                        "suite": "matrix",
                        "family": family,
                        "algorithm": algorithm,
                        "source_backend": src,
                        "target_backend": dst,
                        "provider": "",
                        "mode": "",
                        "test_case": case,
                        "failure_code": canonical_failure(failure_code, status),
                        "notes": notes,
                    }
                )

    write_csv(
        out_dir / "matrix.csv",
        rows,
        ["source_backend", "target_backend", "family", "algorithm", "kem_mode", "test_case", "status", "failure_code", "notes"],
    )
    append_failures(out_dir / "failures.csv", failures)


def run_negative(out_dir: Path, family: str, algorithm: str, backends: list[str]) -> None:
    rows: list[dict] = []
    failures: list[dict] = []

    for backend in backends:
        invalid = invoke_adapter(backend, family, "definitely_not_an_algorithm", "keygen", {})
        invalid_status = "pass" if invalid.status == "fail" else "fail"
        invalid_failure = "" if invalid_status == "pass" else "negative_test_failed"
        invalid_notes = "rejected invalid algorithm" if invalid_status == "pass" else "invalid algorithm unexpectedly succeeded"
        rows.append(
            {
                "backend": backend,
                "family": family,
                "algorithm": algorithm,
                "case": "invalid_algorithm",
                "status": invalid_status,
                "failure_code": invalid_failure,
                "notes": invalid_notes,
            }
        )
        if invalid_status != "pass":
            failures.append(
                {
                    "suite": "negative",
                    "family": family,
                    "algorithm": algorithm,
                    "source_backend": backend,
                    "target_backend": "",
                    "provider": "",
                    "mode": "",
                    "test_case": "invalid_algorithm",
                    "failure_code": invalid_failure,
                    "notes": invalid_notes,
                }
            )

        if family == "sig":
            keygen = invoke_adapter(backend, family, algorithm, "keygen", {})
            if keygen.status == "pass":
                message_b64 = "bmVnYXRpdmUtc2lnLXRlc3Q="
                sign = invoke_adapter(
                    backend,
                    family,
                    algorithm,
                    "sign",
                    {
                        "secret_key_b64": keygen.payload.get("data", {}).get("secret_key_b64", ""),
                        "message_b64": message_b64,
                    },
                )
                if sign.status == "pass":
                    signature = sign.payload.get("data", {}).get("signature_b64", "")
                    tampered = f"{signature[:-1]}A" if signature else ""
                    verify = invoke_adapter(
                        backend,
                        family,
                        algorithm,
                        "verify",
                        {
                            "public_key_b64": keygen.payload.get("data", {}).get("public_key_b64", ""),
                            "message_b64": message_b64,
                            "signature_b64": tampered,
                        },
                    )
                    neg_status = "pass"
                    neg_failure = ""
                    neg_notes = "tampered signature rejected"
                    if verify.status == "pass" and bool(verify.payload.get("data", {}).get("verified", False)):
                        neg_status = "fail"
                        neg_failure = "verify_mismatch"
                        neg_notes = "tampered signature verified"
                    rows.append(
                        {
                            "backend": backend,
                            "family": family,
                            "algorithm": algorithm,
                            "case": "tampered_signature",
                            "status": neg_status,
                            "failure_code": neg_failure,
                            "notes": neg_notes,
                        }
                    )
                    if neg_status != "pass":
                        failures.append(
                            {
                                "suite": "negative",
                                "family": family,
                                "algorithm": algorithm,
                                "source_backend": backend,
                                "target_backend": "",
                                "provider": "",
                                "mode": "",
                                "test_case": "tampered_signature",
                                "failure_code": neg_failure,
                                "notes": neg_notes,
                            }
                        )
        else:
            keygen = invoke_adapter(backend, family, algorithm, "keygen", {})
            if keygen.status == "pass":
                encap = invoke_adapter(
                    backend,
                    family,
                    algorithm,
                    "encap",
                    {"public_key_b64": keygen.payload.get("data", {}).get("public_key_b64", "")},
                )
                if encap.status == "pass":
                    ciphertext = encap.payload.get("data", {}).get("ciphertext_b64", "")
                    tampered = f"{ciphertext[:-1]}A" if ciphertext else ""
                    decap = invoke_adapter(
                        backend,
                        family,
                        algorithm,
                        "decap",
                        {
                            "secret_key_b64": keygen.payload.get("data", {}).get("secret_key_b64", ""),
                            "ciphertext_b64": tampered,
                        },
                    )
                    neg_status = "pass"
                    neg_failure = ""
                    neg_notes = "tampered ciphertext rejected or mismatched"
                    if decap.status == "pass" and decap.payload.get("data", {}).get("shared_secret_b64") == encap.payload.get("data", {}).get("shared_secret_b64"):
                        neg_status = "fail"
                        neg_failure = "kem_mismatch"
                        neg_notes = "tampered ciphertext produced valid shared secret"
                    rows.append(
                        {
                            "backend": backend,
                            "family": family,
                            "algorithm": algorithm,
                            "case": "tampered_ciphertext",
                            "status": neg_status,
                            "failure_code": neg_failure,
                            "notes": neg_notes,
                        }
                    )
                    if neg_status != "pass":
                        failures.append(
                            {
                                "suite": "negative",
                                "family": family,
                                "algorithm": algorithm,
                                "source_backend": backend,
                                "target_backend": "",
                                "provider": "",
                                "mode": "",
                                "test_case": "tampered_ciphertext",
                                "failure_code": neg_failure,
                                "notes": neg_notes,
                            }
                        )

    write_csv(
        out_dir / "negative.csv",
        rows,
        ["backend", "family", "algorithm", "case", "status", "failure_code", "notes"],
    )
    append_failures(out_dir / "failures.csv", failures)


def run_tls(out_dir: Path, mode: str, providers: list[str]) -> None:
    rows: list[dict] = []
    failures: list[dict] = []

    for provider in providers:
        status, failure_code, notes = tls_probe(provider, mode)
        rows.append(
            {
                "provider": provider,
                "mode": mode,
                "status": status,
                "failure_code": failure_code,
                "notes": notes,
            }
        )
        if status != "pass":
            failures.append(
                {
                    "suite": "tls",
                    "family": "",
                    "algorithm": "",
                    "source_backend": "",
                    "target_backend": "",
                    "provider": provider,
                    "mode": mode,
                    "test_case": "tls_probe",
                    "failure_code": canonical_failure(failure_code, status),
                    "notes": notes,
                }
            )

    write_csv(out_dir / "tls.csv", rows, ["provider", "mode", "status", "failure_code", "notes"])
    append_failures(out_dir / "failures.csv", failures)


def append_failures(path: Path, additions: list[dict]) -> None:
    headers = ["suite", "family", "algorithm", "source_backend", "target_backend", "provider", "mode", "test_case", "failure_code", "notes"]
    existing: list[dict] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            existing = list(csv.DictReader(handle))
    all_rows = existing + additions
    write_csv(path, all_rows, headers)


def build_report(run_dir: Path) -> None:
    cmd = [
        "python3",
        str(SCRIPT_DIR / "interop_matrix.py"),
        "--matrix-csv",
        str(run_dir / "matrix.csv"),
        "--negative-csv",
        str(run_dir / "negative.csv"),
        "--tls-csv",
        str(run_dir / "tls.csv"),
        "--failures-csv",
        str(run_dir / "failures.csv"),
        "--summary-csv",
        str(run_dir / "summary.csv"),
        "--dashboard-output",
        str(run_dir / "INTEROP_DASHBOARD.md"),
        "--output",
        str(run_dir / "REPORT.md"),
        "--metadata-json",
        str(run_dir / "run-meta.json"),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    args = parse_args()

    if args.command == "report":
        run_dir = Path(args.run_dir or "").resolve()
        if not run_dir.exists():
            raise SystemExit("run directory does not exist")
        build_report(run_dir)
        return 0

    out_dir = Path(args.out_dir or "").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.command in {"matrix", "negative"}:
        if not args.family or not args.algorithm:
            raise SystemExit("--family and --algorithm are required")
        write_json(
            out_dir / "run-meta.json",
            {
                "run_id": out_dir.name,
                "family": args.family,
                "algorithm": args.algorithm,
                "kem_mode": args.kem_mode if args.family == "kem" else "",
            },
        )

    if args.command == "matrix":
        run_matrix(out_dir, args.family or "", args.algorithm or "", parse_csv_list(args.backends), args.kem_mode)
    elif args.command == "negative":
        run_negative(out_dir, args.family or "", args.algorithm or "", parse_csv_list(args.backends))
    elif args.command == "tls":
        if not args.mode:
            raise SystemExit("--mode is required")
        run_tls(out_dir, args.mode, parse_csv_list(args.providers))

    build_report(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
