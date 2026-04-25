#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import shutil
import statistics
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

PROFILES = ["dc_lan", "cross_region", "mobile_edge", "constrained_cpu", "burst_gateway"]
MODES = ["classical", "kex_pqc", "cert_pqc", "hybrid", "pqc"]


def percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return math.nan
    idx = int(round(q * (len(sorted_vals) - 1)))
    return sorted_vals[idx]


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
        k, v = line.split("=", 1)
        if k in vals:
            vals[k] = float(v)
    return vals


def read_latency(path: Path) -> dict[str, object]:
    rows = list(csv.DictReader(path.open(newline="")))
    total = len(rows)
    ok_rows = [r for r in rows if r.get("success") == "1"]
    failures = [r for r in rows if r.get("success") != "1"]

    tls = sorted(float(r["tls_setup"]) for r in ok_rows)
    total_time = sorted(float(r["total"]) for r in ok_rows)

    err_counter = Counter()
    for r in failures:
        err = (r.get("error") or "unknown").strip() or "unknown"
        key = err.split(":", 1)[0][:80]
        err_counter[key] += 1

    return {
        "samples": total,
        "success": len(ok_rows),
        "success_rate": (len(ok_rows) / total * 100.0) if total else 0.0,
        "errors": sum(err_counter.values()),
        "error_top": err_counter.most_common(3),
        "tls_p50": statistics.median(tls) if tls else math.nan,
        "tls_p95": percentile(tls, 0.95),
        "tls_p99": percentile(tls, 0.99),
        "total_p50": statistics.median(total_time) if total_time else math.nan,
    }


def read_concurrency(path: Path) -> dict[str, float]:
    rows = list(csv.DictReader(path.open(newline="")))
    if not rows:
        return {
            "rounds": 0,
            "ok": 0,
            "fail": 0,
            "success_rate": 0.0,
            "cpu_peak": math.nan,
            "cpu_avg": math.nan,
            "mem_peak": math.nan,
            "mem_avg": math.nan,
        }

    cpu = []
    mem = []
    ok = 0
    fail = 0
    for r in rows:
        try:
            ok += int(r.get("ok", "0"))
        except ValueError:
            pass
        try:
            fail += int(r.get("fail", "0"))
        except ValueError:
            pass

        try:
            cpu.append(float((r.get("cpu_perc") or "").replace("%", "")))
        except ValueError:
            pass
        try:
            mem.append(float((r.get("mem_perc") or "").replace("%", "")))
        except ValueError:
            pass

    total = ok + fail
    return {
        "rounds": len(rows),
        "ok": ok,
        "fail": fail,
        "success_rate": (ok / total * 100.0) if total else 0.0,
        "cpu_peak": max(cpu) if cpu else math.nan,
        "cpu_avg": sum(cpu) / len(cpu) if cpu else math.nan,
        "mem_peak": max(mem) if mem else math.nan,
        "mem_avg": sum(mem) / len(mem) if mem else math.nan,
    }


def pcap_metrics(path: Path) -> dict[str, float]:
    metrics = {"pcap_bytes": float(path.stat().st_size)}
    tshark = shutil.which("tshark")
    if not tshark:
        return metrics

    cmd = [
        tshark,
        "-r",
        str(path),
        "-Y",
        "tls.handshake",
        "-T",
        "fields",
        "-e",
        "tls.handshake.type",
        "-e",
        "tls.handshake.length",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return metrics

    by_type: defaultdict[str, int] = defaultdict(int)
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        htype = parts[0].strip()
        try:
            hlen = int(parts[1].strip())
        except ValueError:
            continue
        by_type[htype] += hlen

    for htype, total in by_type.items():
        metrics[f"hs_type_{htype}_bytes"] = float(total)
    return metrics


def latest(pattern: str, base: Path) -> Path | None:
    matches = sorted(base.glob(pattern))
    return matches[-1] if matches else None


def median_of(values: list[float]) -> float:
    vals = [v for v in values if not math.isnan(v)]
    return statistics.median(vals) if vals else math.nan


def fmt(v: float, n: int = 4) -> str:
    if math.isnan(v):
        return "N/A"
    return f"{v:.{n}f}"


def fmt_pct(v: float) -> str:
    if math.isnan(v):
        return "N/A"
    return f"{v:.2f}%"


def delta(v: float, b: float) -> str:
    if math.isnan(v) or math.isnan(b) or b == 0:
        return "N/A"
    return f"{((v-b)/b)*100:+.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", required=True)
    ap.add_argument("--slo-file", required=True)
    args = ap.parse_args()

    root = Path(args.results_dir)
    root.mkdir(parents=True, exist_ok=True)
    slo = parse_slo(Path(args.slo_file))
    summary_csv = root / "summary.csv"
    heatmap_csv = root / "heatmap-p95.csv"
    summary_md = root / "SUMMARY.md"

    rows: list[dict[str, object]] = []

    for profile in PROFILES:
        profile_root = root / profile / "sessions"
        if not profile_root.exists():
            continue
        session_dirs = sorted([p for p in profile_root.iterdir() if p.is_dir()])
        for mode in MODES:
            latency_sessions = []
            conc_sessions = []
            payload_sessions = []
            err_counter: Counter[str] = Counter()

            for sess in session_dirs:
                lat = latest(f"latency-{mode}-*.csv", sess)
                con = latest(f"concurrency-{mode}-*.csv", sess)
                pcap = latest(f"tls-capture-{mode}-*.pcap", sess)

                if lat:
                    lm = read_latency(lat)
                    latency_sessions.append(lm)
                    for err, c in lm["error_top"]:
                        err_counter[err] += c
                if con:
                    conc_sessions.append(read_concurrency(con))
                if pcap:
                    payload_sessions.append(pcap_metrics(pcap))

            if not latency_sessions and not conc_sessions:
                continue

            row = {
                "profile": profile,
                "mode": mode,
                "sessions": float(max(len(latency_sessions), len(conc_sessions))),
                "latency_success_rate": median_of([float(x["success_rate"]) for x in latency_sessions]) if latency_sessions else math.nan,
                "latency_p50": median_of([float(x["tls_p50"]) for x in latency_sessions]) if latency_sessions else math.nan,
                "latency_p95": median_of([float(x["tls_p95"]) for x in latency_sessions]) if latency_sessions else math.nan,
                "latency_p99": median_of([float(x["tls_p99"]) for x in latency_sessions]) if latency_sessions else math.nan,
                "concurrency_success_rate": median_of([float(x["success_rate"]) for x in conc_sessions]) if conc_sessions else math.nan,
                "cpu_peak": median_of([float(x["cpu_peak"]) for x in conc_sessions]) if conc_sessions else math.nan,
                "cpu_avg": median_of([float(x["cpu_avg"]) for x in conc_sessions]) if conc_sessions else math.nan,
                "mem_peak": median_of([float(x["mem_peak"]) for x in conc_sessions]) if conc_sessions else math.nan,
                "mem_avg": median_of([float(x["mem_avg"]) for x in conc_sessions]) if conc_sessions else math.nan,
                "pcap_bytes": median_of([float(x.get("pcap_bytes", math.nan)) for x in payload_sessions]) if payload_sessions else math.nan,
                "top_error": err_counter.most_common(1)[0][0] if err_counter else "",
            }
            rows.append(row)

    # baseline per profile
    baseline = {}
    for r in rows:
        if r["mode"] == "classical":
            baseline[r["profile"]] = r

    # write summary csv
    fields = [
        "profile", "mode", "sessions", "latency_success_rate", "latency_p50", "latency_p95", "latency_p99",
        "concurrency_success_rate", "cpu_peak", "cpu_avg", "mem_peak", "mem_avg", "pcap_bytes", "top_error",
        "delta_latency_p95_vs_classical", "delta_cpu_peak_vs_classical", "delta_mem_peak_vs_classical",
    ]
    with summary_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            b = baseline.get(r["profile"])
            rp95 = float(r["latency_p95"])
            rcpu = float(r["cpu_peak"])
            rmem = float(r["mem_peak"])
            bp95 = float(b["latency_p95"]) if b else math.nan
            bcpu = float(b["cpu_peak"]) if b else math.nan
            bmem = float(b["mem_peak"]) if b else math.nan
            item = dict(r)
            item["delta_latency_p95_vs_classical"] = delta(rp95, bp95)
            item["delta_cpu_peak_vs_classical"] = delta(rcpu, bcpu)
            item["delta_mem_peak_vs_classical"] = delta(rmem, bmem)
            w.writerow(item)

    # heatmap csv
    with heatmap_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["profile"] + MODES)
        for profile in PROFILES:
            row = [profile]
            for mode in MODES:
                m = next((x for x in rows if x["profile"] == profile and x["mode"] == mode), None)
                row.append(fmt(float(m["latency_p95"]), 6) if m else "N/A")
            w.writerow(row)

    # compatibility table from status
    status_file = root / "compatibility-status.csv"
    compat = defaultdict(lambda: {"pass": 0, "fail": 0, "reasons": Counter()})
    if status_file.exists():
        for r in csv.DictReader(status_file.open(newline="")):
            key = (r["profile"], r["mode"])
            compat[key][r["status"]] += 1
            if r["status"] == "fail" and r.get("reason"):
                compat[key]["reasons"][r["reason"][:80]] += 1

    lines = [
        "# Multi-Profile PQC Report",
        "",
        "## Executive Summary",
        "",
        "| Profile | Mode | Sessions | Handshake success | TLS p95 (s) | CPU peak (%) | Mem peak (%) | Payload pcap bytes |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for profile in PROFILES:
        for mode in MODES:
            m = next((x for x in rows if x["profile"] == profile and x["mode"] == mode), None)
            if not m:
                continue
            lines.append(
                f"| {profile} | {mode} | {fmt(float(m['sessions']),0)} | {fmt_pct(float(m['latency_success_rate']))} | {fmt(float(m['latency_p95']),6)} | {fmt(float(m['cpu_peak']),2)} | {fmt(float(m['mem_peak']),2)} | {fmt(float(m['pcap_bytes']),0)} |"
            )

    lines += [
        "",
        "## Delta vs Classical",
        "",
        "| Profile | Mode | Delta TLS p95 | Delta CPU peak | Delta Mem peak |",
        "|---|---|---:|---:|---:|",
    ]
    for profile in PROFILES:
        b = next((x for x in rows if x["profile"] == profile and x["mode"] == "classical"), None)
        if not b:
            continue
        for mode in ["kex_pqc", "cert_pqc", "hybrid", "pqc"]:
            m = next((x for x in rows if x["profile"] == profile and x["mode"] == mode), None)
            if not m:
                continue
            lines.append(
                "| {profile} | {mode} | {dp95} | {dcpu} | {dmem} |".format(
                    profile=profile,
                    mode=mode,
                    dp95=delta(float(m["latency_p95"]), float(b["latency_p95"])),
                    dcpu=delta(float(m["cpu_peak"]), float(b["cpu_peak"])),
                    dmem=delta(float(m["mem_peak"]), float(b["mem_peak"])),
                )
            )

    lines += [
        "",
        "## Compatibility",
        "",
        "| Profile | Mode | Pass steps | Fail steps | Top failure reason |",
        "|---|---|---:|---:|---|",
    ]
    for profile in PROFILES:
        for mode in MODES:
            c = compat.get((profile, mode), {"pass": 0, "fail": 0, "reasons": Counter()})
            reason = c["reasons"].most_common(1)[0][0] if c["reasons"] else ""
            lines.append(f"| {profile} | {mode} | {c['pass']} | {c['fail']} | {reason} |")

    lines += [
        "",
        "## SLO Targets",
        "",
        f"- Handshake success >= {slo['SLO_HANDSHAKE_SUCCESS_MIN']}%",
        f"- TLS p95 <= {slo['SLO_TLS_P95_MAX']}s",
        f"- Hybrid p95 overhead <= {slo['SLO_HYBRID_P95_OVERHEAD_MAX']}% in dc_lan and cross_region",
        "",
        "## Artifacts",
        "",
        f"- Summary CSV: `{summary_csv}`",
        f"- Heatmap CSV: `{heatmap_csv}`",
        f"- Compatibility status CSV: `{status_file}`",
    ]

    summary_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {summary_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
