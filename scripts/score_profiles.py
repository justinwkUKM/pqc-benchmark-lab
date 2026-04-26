#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent.parent
CRITERIA = [
    "performance",
    "compatibility",
    "resource_cost",
    "handshake_size",
    "security_policy_fit",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score and rank crypto modes by weighted decision criteria")
    parser.add_argument("--summary-csv", required=True, help="Path to summary.csv")
    parser.add_argument("--compat-csv", default=None, help="Path to compatibility-status.csv")
    parser.add_argument("--scoring-config", default=str(ROOT / "config" / "scoring_profiles.yaml"))
    parser.add_argument("--preset", default="balanced", help="Scoring preset key")
    parser.add_argument("--profiles", default="all", help="Profile filter: all or comma-separated list")
    parser.add_argument("--top", type=int, default=3, help="How many top candidates to include")
    parser.add_argument("--output-md", required=True, help="Output markdown decision brief")
    parser.add_argument("--output-csv", default=None, help="Optional detailed score CSV")
    return parser.parse_args()


def parse_float(value: str | None) -> float:
    text = (value or "").strip()
    if not text or text.lower() == "nan" or text == "N/A":
        return math.nan
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return math.nan


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_scoring_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"Failed to parse {path}. Keep scoring_profiles.yaml JSON-compatible (JSON is valid YAML). {exc}"
        )


def selected_profiles(value: str) -> set[str] | None:
    if value.strip().lower() == "all":
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def normalize_inverse(values: dict[str, float]) -> dict[str, float]:
    finite = [v for v in values.values() if not math.isnan(v)]
    if not finite:
        return {k: 0.0 for k in values}
    v_min = min(finite)
    v_max = max(finite)
    if math.isclose(v_min, v_max):
        return {k: 100.0 for k in values}

    out: dict[str, float] = {}
    for key, val in values.items():
        if math.isnan(val):
            out[key] = 0.0
            continue
        out[key] = (v_max - val) / (v_max - v_min) * 100.0
    return out


def normalize_direct(values: dict[str, float]) -> dict[str, float]:
    finite = [v for v in values.values() if not math.isnan(v)]
    if not finite:
        return {k: 0.0 for k in values}
    v_min = min(finite)
    v_max = max(finite)
    if math.isclose(v_min, v_max):
        return {k: 100.0 for k in values}

    out: dict[str, float] = {}
    for key, val in values.items():
        if math.isnan(val):
            out[key] = 0.0
            continue
        out[key] = (val - v_min) / (v_max - v_min) * 100.0
    return out


def compatibility_scores(compat_rows: list[dict[str, str]], modes: list[str], mode_profiles: dict[str, set[str]]) -> dict[str, float]:
    if not compat_rows:
        return {mode: 100.0 for mode in modes}

    totals: dict[str, dict[str, int]] = {mode: {"pass": 0, "total": 0} for mode in modes}
    for row in compat_rows:
        mode = row.get("mode", "")
        profile = row.get("profile", "")
        if mode not in totals or profile not in mode_profiles.get(mode, set()):
            continue
        totals[mode]["total"] += 1
        if row.get("status") == "pass":
            totals[mode]["pass"] += 1

    scores: dict[str, float] = {}
    for mode, data in totals.items():
        if data["total"] == 0:
            scores[mode] = 100.0
        else:
            scores[mode] = data["pass"] / data["total"] * 100.0
    return scores


def policy_fit_scores(modes: list[str], security_levels: dict[str, int], policy_target: int) -> dict[str, float]:
    out: dict[str, float] = {}
    for mode in modes:
        level = int(security_levels.get(mode, 1))
        if level >= policy_target:
            out[mode] = 100.0
            continue
        gap = policy_target - level
        out[mode] = max(0.0, 100.0 - gap * 40.0)
    return out


def median_by_mode(rows: list[dict[str, str]], key: str) -> dict[str, float]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        mode = row.get("mode", "")
        grouped.setdefault(mode, [])
        val = parse_float(row.get(key, ""))
        if not math.isnan(val):
            grouped[mode].append(val)

    out: dict[str, float] = {}
    for mode, vals in grouped.items():
        out[mode] = median(vals) if vals else math.nan
    return out


def build_tradeoff_notes(item: dict[str, float], ranked: list[dict[str, float]]) -> str:
    score_parts = [
        ("performance", item["performance"]),
        ("compatibility", item["compatibility"]),
        ("resource", item["resource_cost"]),
        ("size", item["handshake_size"]),
        ("policy", item["security_policy_fit"]),
    ]
    score_parts.sort(key=lambda x: x[1], reverse=True)
    top = score_parts[0]
    bottom = score_parts[-1]
    winner = ranked[0]
    gap = winner["composite_score"] - item["composite_score"]
    if item["mode"] == winner["mode"]:
        return f"Strongest on {top[0]}; main watch item is {bottom[0]}."
    return f"Trails leader by {gap:.2f} points; strongest on {top[0]}, weakest on {bottom[0]}."


def main() -> int:
    args = parse_args()

    summary_path = Path(args.summary_csv).resolve()
    compat_path = Path(args.compat_csv).resolve() if args.compat_csv else None
    config_path = Path(args.scoring_config).resolve()

    summary_rows = read_csv(summary_path)
    if summary_rows and "mode" not in summary_rows[0]:
        raise SystemExit(f"Unexpected summary schema in {summary_path}; expected mode/profile metrics table.")
    compat_rows = read_csv(compat_path) if compat_path and compat_path.exists() else []
    config = load_scoring_config(config_path)

    preset = (config.get("presets", {}) or {}).get(args.preset)
    if not preset:
        raise SystemExit(f"Unknown scoring preset '{args.preset}'. Available: {', '.join(sorted((config.get('presets', {}) or {}).keys()))}")

    profile_filter = selected_profiles(args.profiles)
    filtered_rows = []
    for row in summary_rows:
        profile = row.get("profile", "")
        if profile_filter is not None and profile not in profile_filter:
            continue
        filtered_rows.append(row)

    if not filtered_rows:
        raise SystemExit("No summary rows matched the selected profile filter.")

    modes = sorted({row.get("mode", "") for row in filtered_rows if row.get("mode", "")})
    mode_profiles: dict[str, set[str]] = {}
    for row in filtered_rows:
        mode = row.get("mode", "")
        mode_profiles.setdefault(mode, set()).add(row.get("profile", ""))

    weights = preset.get("weights", {})
    for criterion in CRITERIA:
        if criterion not in weights:
            raise SystemExit(f"Missing weight '{criterion}' in preset '{args.preset}'")

    perf_raw = median_by_mode(filtered_rows, "latency_p95")
    cpu_raw = median_by_mode(filtered_rows, "cpu_peak")
    pcap_raw = median_by_mode(filtered_rows, "pcap_bytes")

    performance = normalize_inverse(perf_raw)
    resource_cost = normalize_inverse(cpu_raw)
    handshake_size = normalize_inverse(pcap_raw)
    compatibility = compatibility_scores(compat_rows, modes, mode_profiles)

    policy_target = int(preset.get("policy_target_level", 2))
    security_levels = {k: int(v) for k, v in (config.get("security_levels", {}) or {}).items()}
    security_fit = policy_fit_scores(modes, security_levels, policy_target)

    ranked: list[dict[str, float]] = []
    for mode in modes:
        total_weight = sum(float(weights[name]) for name in CRITERIA)
        item = {
            "mode": mode,
            "performance": performance.get(mode, 0.0),
            "compatibility": compatibility.get(mode, 0.0),
            "resource_cost": resource_cost.get(mode, 0.0),
            "handshake_size": handshake_size.get(mode, 0.0),
            "security_policy_fit": security_fit.get(mode, 0.0),
            "latency_p95_median": perf_raw.get(mode, math.nan),
            "cpu_peak_median": cpu_raw.get(mode, math.nan),
            "pcap_bytes_median": pcap_raw.get(mode, math.nan),
            "security_level": float(security_levels.get(mode, 1)),
        }
        weighted = 0.0
        for criterion in CRITERIA:
            weighted += item[criterion] * float(weights[criterion])
        item["composite_score"] = weighted / total_weight if total_weight else 0.0
        ranked.append(item)

    ranked.sort(key=lambda x: x["composite_score"], reverse=True)
    top_n = max(1, args.top)
    top = ranked[:top_n]

    for item in ranked:
        item["tradeoff_note"] = build_tradeoff_notes(item, ranked)

    out_md = Path(args.output_md).resolve()
    out_md.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Decision Brief")
    lines.append("")
    lines.append(f"Preset: `{args.preset}`")
    lines.append(f"Policy target level: `{policy_target}`")
    lines.append(f"Profiles in scope: `{args.profiles}`")
    lines.append("")
    lines.append("## Ranked Options")
    lines.append("")
    lines.append("| Rank | Mode | Composite | Performance | Compatibility | Resource | Handshake Size | Policy Fit |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|")
    for idx, item in enumerate(ranked, start=1):
        lines.append(
            "| {rank} | {mode} | {score:.2f} | {performance:.2f} | {compatibility:.2f} | {resource_cost:.2f} | {handshake_size:.2f} | {security_policy_fit:.2f} |".format(
                rank=idx,
                **item,
                score=item["composite_score"],
            )
        )

    lines.append("")
    lines.append("## Top Candidates")
    lines.append("")
    for idx, item in enumerate(top, start=1):
        lines.append(f"### {idx}. {item['mode']}")
        lines.append("")
        lines.append(
            "- Rationale: composite `{score:.2f}` with median TLS p95 `{p95:.6f}s`, median CPU peak `{cpu:.2f}%`, compatibility `{compat:.2f}%`.".format(
                score=item["composite_score"],
                p95=item["latency_p95_median"],
                cpu=item["cpu_peak_median"],
                compat=item["compatibility"],
            )
        )
        lines.append(f"- Tradeoff notes: {item['tradeoff_note']}")
        lines.append("")

    lines.append("## Preset Weights")
    lines.append("")
    lines.append("| Criterion | Weight |")
    lines.append("|---|---:|")
    for criterion in CRITERIA:
        lines.append(f"| {criterion} | {float(weights[criterion]):.2f} |")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.output_csv:
        out_csv = Path(args.output_csv).resolve()
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "mode",
            "composite_score",
            "performance",
            "compatibility",
            "resource_cost",
            "handshake_size",
            "security_policy_fit",
            "latency_p95_median",
            "cpu_peak_median",
            "pcap_bytes_median",
            "security_level",
            "tradeoff_note",
        ]
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(ranked)

    print(f"Wrote {out_md}")
    if args.output_csv:
        print(f"Wrote {Path(args.output_csv).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
