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
        "SLO_P95_DELTA_REGRESSION_MAX": 15.0,
        "SLO_COMPATIBILITY_DROP_MAX": 1.0,
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


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


def aggregate_compatibility(rows: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    totals: dict[tuple[str, str], dict[str, int]] = {}
    for row in rows:
        key = (row.get("profile", ""), row.get("mode", ""))
        if key not in totals:
            totals[key] = {"pass": 0, "total": 0}
        totals[key]["total"] += 1
        if row.get("status") == "pass":
            totals[key]["pass"] += 1

    out: dict[tuple[str, str], float] = {}
    for key, item in totals.items():
        if item["total"] == 0:
            out[key] = math.nan
        else:
            out[key] = item["pass"] / item["total"] * 100.0
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--report-dir", default=None)
    ap.add_argument("--slo-file", required=True)
    ap.add_argument("--baseline-summary-csv", default=None)
    ap.add_argument("--baseline-compat-csv", default=None)
    args = ap.parse_args()

    root = Path(args.results_dir)
    report_dir = Path(args.report_dir).resolve() if args.report_dir else (root / "reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    summary_csv = report_dir / "summary.csv"
    out_file = report_dir / "ACCEPTANCE.md"
    slo = parse_slo(Path(args.slo_file))

    if not summary_csv.exists():
        raise SystemExit(f"Missing summary CSV: {summary_csv}")

    rows = load_csv_rows(summary_csv)

    checks: list[tuple[str, bool | None, str]] = []

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
    checked_profiles = 0
    by_key = {(r["profile"], r["mode"]): r for r in rows}
    for profile in ["dc_lan", "cross_region"]:
        b = by_key.get((profile, "classical"))
        h = by_key.get((profile, "hybrid"))
        if not b or not h:
            hdetails.append(f"{profile}=not_in_scope")
            continue
        checked_profiles += 1
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
    if checked_profiles == 0:
        pass_hybrid = True
    checks.append(("Hybrid p95 overhead threshold", pass_hybrid, "; ".join(hdetails)))

    # 3) no unresolved compatibility blockers
    compat_file = report_dir / "compatibility-status.csv"
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

    baseline_summary = Path(args.baseline_summary_csv).resolve() if args.baseline_summary_csv else None
    if baseline_summary and baseline_summary.exists():
        baseline_rows = load_csv_rows(baseline_summary)
        baseline_map = {(r.get("profile", ""), r.get("mode", "")): as_float(r.get("latency_p95", "")) for r in baseline_rows}
        p95_regression_limit = slo["SLO_P95_DELTA_REGRESSION_MAX"]
        regressions: list[str] = []
        p95_ok = True
        for row in rows:
            key = (row.get("profile", ""), row.get("mode", ""))
            current = as_float(row.get("latency_p95", ""))
            base = baseline_map.get(key, math.nan)
            if math.isnan(current) or math.isnan(base) or base <= 0:
                continue
            delta_pct = ((current - base) / base) * 100.0
            if delta_pct > p95_regression_limit:
                p95_ok = False
                regressions.append(f"{key[0]}/{key[1]}={delta_pct:+.2f}%")
        checks.append(
            (
                f"Regression guard: p95 delta <= {p95_regression_limit:.2f}%",
                p95_ok,
                "; ".join(regressions[:20]) if regressions else "none",
            )
        )
    else:
        checks.append(("Regression guard: p95 delta", None, "baseline summary not provided"))

    baseline_compat = Path(args.baseline_compat_csv).resolve() if args.baseline_compat_csv else None
    if baseline_compat and baseline_compat.exists() and compat_file.exists():
        baseline_rates = aggregate_compatibility(load_csv_rows(baseline_compat))
        current_rates = aggregate_compatibility(load_csv_rows(compat_file))
        drop_limit = slo["SLO_COMPATIBILITY_DROP_MAX"]
        drops: list[str] = []
        compat_drop_ok = True
        for key, base_rate in baseline_rates.items():
            curr_rate = current_rates.get(key, math.nan)
            if math.isnan(base_rate) or math.isnan(curr_rate):
                continue
            drop = base_rate - curr_rate
            if drop > drop_limit:
                compat_drop_ok = False
                drops.append(f"{key[0]}/{key[1]}={drop:+.2f}pp")
        checks.append(
            (
                f"Regression guard: compatibility drop <= {drop_limit:.2f}pp",
                compat_drop_ok,
                "; ".join(drops[:20]) if drops else "none",
            )
        )
    else:
        checks.append(("Regression guard: compatibility drop", None, "baseline compatibility not provided"))

    evaluated = [x[1] for x in checks if x[1] is not None]
    overall = all(evaluated) if evaluated else False
    lines = [
        "# Acceptance Check",
        "",
        f"Overall: {'PASS' if overall else 'FAIL'}",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
    ]
    for name, ok, detail in checks:
        if ok is None:
            result = "SKIP"
        else:
            result = "PASS" if ok else "FAIL"
        lines.append(f"| {name} | {result} | {detail} |")

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
