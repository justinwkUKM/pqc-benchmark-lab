#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path


def parse_slo(path: Path) -> dict[str, float]:
    vals = {
        "SLO_HANDSHAKE_SUCCESS_MIN": 99.5,
        "SLO_TLS_P95_MAX": 0.050,
        "SLO_HYBRID_P95_OVERHEAD_MAX": 15.0,
    }
    if not path.exists():
        return vals
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        if key in vals:
            vals[key] = float(val)
    return vals


def as_float(v: str) -> float:
    if v is None or v == "" or v == "N/A":
        return math.nan
    if isinstance(v, str) and v.endswith("%"):
        v = v[:-1]
    try:
        return float(v)
    except ValueError:
        return math.nan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--slo-file", required=True)
    args = ap.parse_args()

    root = Path(args.results_dir)
    summary_csv = root / "summary.csv"
    out_file = root / "ACCEPTANCE.md"
    slo = parse_slo(Path(args.slo_file))

    if not summary_csv.exists():
        raise SystemExit(f"Missing summary CSV: {summary_csv}")

    rows = list(csv.DictReader(summary_csv.open(newline="")))

    checks = []

    # 1) all profiles complete with >= success threshold for shortlisted modes
    shortlisted = ["classical", "hybrid", "pqc"]
    pass_all = True
    details = []
    for r in rows:
        if r["mode"] not in shortlisted:
            continue
        hs = as_float(r["latency_success_rate"])
        ok = not math.isnan(hs) and hs >= slo["SLO_HANDSHAKE_SUCCESS_MIN"]
        pass_all = pass_all and ok
        details.append(f"{r['profile']}/{r['mode']}={hs:.2f}%")
    checks.append(("Shortlisted handshake success >= threshold", pass_all, "; ".join(details)))

    # 2) hybrid p95 overhead <= threshold in dc_lan and cross_region
    pass_hybrid = True
    hdetails = []
    by_key = {(r["profile"], r["mode"]): r for r in rows}
    for profile in ["dc_lan", "cross_region"]:
        b = by_key.get((profile, "classical"))
        h = by_key.get((profile, "hybrid"))
        if not b or not h:
            pass_hybrid = False
            hdetails.append(f"{profile}=missing")
            continue
        bp95 = as_float(b["latency_p95"])
        hp95 = as_float(h["latency_p95"])
        if math.isnan(bp95) or math.isnan(hp95) or bp95 == 0:
            pass_hybrid = False
            hdetails.append(f"{profile}=invalid")
            continue
        overhead = ((hp95 - bp95) / bp95) * 100
        ok = overhead <= slo["SLO_HYBRID_P95_OVERHEAD_MAX"]
        pass_hybrid = pass_hybrid and ok
        hdetails.append(f"{profile}={overhead:+.2f}%")
    checks.append(("Hybrid p95 overhead threshold", pass_hybrid, "; ".join(hdetails)))

    # 3) no unresolved compatibility blockers
    compat_file = root / "compatibility-status.csv"
    compatibility_ok = True
    cdetails = []
    if compat_file.exists():
        for r in csv.DictReader(compat_file.open(newline="")):
            if r["status"] == "fail":
                compatibility_ok = False
                cdetails.append(f"{r['profile']}/{r['mode']}/{r['step']}")
        if not cdetails:
            cdetails.append("none")
    else:
        compatibility_ok = False
        cdetails.append("compatibility-status.csv missing")
    checks.append(("No unresolved compatibility blockers", compatibility_ok, "; ".join(cdetails[:20])))

    overall = all(x[1] for x in checks)
    lines = [
        "# Acceptance Check",
        "",
        f"Overall: {'PASS' if overall else 'FAIL'}",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, ok, detail in checks:
        lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |")

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
