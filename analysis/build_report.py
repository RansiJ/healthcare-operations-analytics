"""Build a static portfolio report from verified, previously completed exports.

No Spark session, source download, pipeline rerun or inference is performed.
"""

import argparse
import base64
import csv
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
import platform
import statistics

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, PercentFormatter

from healthcare_pipeline.sources import DEFAULT_ROOT, PROJECT_ROOT, SOURCES, ContractError, digest_file


IDS = ("OP_18b", "OP_22", "H_COMP_1_A_P")
LABELS = ("ED length of visit", "Left before being seen", "Nurses always communicated well")
COLORS = ("#007e79", "#b26234", "#536c9c")
FILES = ("dim_hospital.csv", "dim_measure.csv", "fact_hospital_measure.csv",
         "hospital_metrics.csv", "peer_benchmarks.csv")
REPO = "https://github.com/RansiJ/healthcare-operations-analytics"


def latest_successful(runs_root):
    candidates = sorted(Path(runs_root).glob("*/SUCCESS.json"))
    return candidates[-1].parent if candidates else None


def validate_sources(report):
    if report["status"] != "passed":
        raise ContractError("Historical evidence is not a passed run")
    observed = {r["dataset_id"]: r["sha256"] for r in report["sources"]}
    if observed != {s.dataset_id: s.sha256 for s in SOURCES}:
        raise ContractError("Report source hashes do not match the three approved sources")


def verified_run(run_dir):
    """Missing exports allow summary-only reporting; corrupted exports never do."""
    run_dir = Path(run_dir).resolve()
    if (run_dir / "FAILED.json").exists():
        raise ContractError("Run contains FAILED.json; do not use it")
    success = json.loads((run_dir / "SUCCESS.json").read_text(encoding="utf-8"))
    report_path = run_dir / "quality_report.json"
    if digest_file(report_path) != success["quality_report_sha256"]:
        raise ContractError("SUCCESS.json quality-report hash mismatch")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report["status"] != "passed" or success["run_id"] != report["run_id"] or report["run_id"] != run_dir.name:
        raise ContractError("Unsuccessful or inconsistent run identity")
    validate_sources(report)
    if set(report["output_sha256"]) != set(FILES):
        raise ContractError("Unexpected analytical export manifest")
    missing = []
    hashes = {}
    for filename in FILES:
        path = run_dir / filename
        if not path.is_file():
            missing.append(filename)
            continue
        actual = digest_file(path)
        if actual != report["output_sha256"][filename]:
            raise ContractError(f"Export hash mismatch: {filename}")
        hashes[filename] = actual
    if missing:
        return report, None, {"mode": "summary_only", "missing_exports": missing,
            "run_id": report["run_id"], "quality_report_sha256": digest_file(report_path),
            "verified_available_export_sha256": hashes}
    # All five files have passed integrity checks before any analytical CSV is read.
    tables = {}
    for filename in FILES:
        with (run_dir / filename).open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if len(rows) != report["rows"][filename.removesuffix(".csv")]:
            raise ContractError(f"Export row-count mismatch: {filename}")
        tables[filename] = rows
    return report, tables, {"mode": "verified_exports", "run_id": report["run_id"],
        "quality_report_sha256": digest_file(report_path),
        "success_sha256": digest_file(run_dir / "SUCCESS.json"),
        "verified_export_sha256": hashes, "approved_source_sha256": {s.dataset_id: s.sha256 for s in SOURCES}}


def distribution(values):
    """Hospital-level descriptive statistics; inclusive (type-7) quartiles."""
    if not values:
        raise ContractError("Cannot invent a distribution without observations")
    q1, median, q3 = statistics.quantiles(values, n=4, method="inclusive") if len(values) > 1 else [values[0]] * 3
    return {"n": len(values), "q1": q1, "median": median, "q3": q3,
            "min": min(values), "max": max(values), "zero_count": sum(v == 0 for v in values)}


def summarize(report, tables):
    summaries = []
    grouped = {}
    for measure, label in zip(IDS, LABELS):
        coverage = next(r for r in report["coverage"] if r["measure_id"] == measure)
        item = {**coverage, "label": label,
                "comparable_pct": 100 * coverage["comparable"] / report["cohort_hospitals"],
                "signal_pct_of_comparable": 100 * coverage["unfavorable_signals"] / coverage["comparable"],
                "eligible_insufficient_peers": coverage["eligible"] - coverage["comparable"],
                "ineligible": report["cohort_hospitals"] - coverage["eligible"],
                "missing_score": report["cohort_hospitals"] - coverage["numeric_scores"],
                "period": "Jan-Dec 2024" if measure == "OP_22" else "Oct 2024-Sep 2025",
                "unit": "minutes" if measure == "OP_18b" else "percent",
                "direction": "higher" if measure == "H_COMP_1_A_P" else "lower"}
        if tables is not None:
            rows = [r for r in tables["peer_benchmarks.csv"] if r["measure_id"] == measure]
            eligible = [r for r in rows if r["comparison_eligible"] == "true"]
            comparable = [r for r in rows if r["comparison_status"] == "comparable"]
            observed = (len(rows), len(eligible), len(comparable), sum(r["unfavorable_signal"] == "true" for r in comparable))
            expected = (coverage["reported_rows"], coverage["eligible"], coverage["comparable"], coverage["unfavorable_signals"])
            if observed != expected:
                raise ContractError(f"Analytical coverage does not reconcile: {measure}")
            if any(r["unfavorable_signal"] != "" for r in rows if r["comparison_status"] != "comparable"):
                raise ContractError("Unqualified hospital has a populated signal")
            periods = {(r["start_date"], r["end_date"]) for r in rows}
            expected_period = ("2024-01-01", "2024-12-31") if measure == "OP_22" else ("2024-10-01", "2025-09-30")
            if periods != {expected_period}:
                raise ContractError("Report would mix measurement periods")
            item["distribution"] = distribution([float(r["score_value"]) for r in eligible])
            item["gap_distribution"] = distribution([float(r["gap_to_peer_median"]) for r in comparable])
            grouped[measure] = {"all": rows, "eligible": eligible, "comparable": comparable}
        summaries.append(item)
    example = None
    if tables is not None:
        common = set.intersection(*[{r["facility_id"] for r in grouped[m]["comparable"]} for m in IDS])
        facility_id = min(common)  # Selection uses identity/comparability, never outcome or rank.
        selected = [next(r for r in grouped[m]["comparable"] if r["facility_id"] == facility_id) for m in IDS]
        keep = ["facility_id", "facility_name", "state", "measure_id", "score_value", "peer_count",
                "peer_q1", "peer_median", "peer_q3", "gap_to_peer_median", "unfavorable_signal", "start_date", "end_date"]
        example = {"selection_rule": "Lowest facility ID comparable on all three measures; independent of scores or flags",
                   "facility_id": facility_id, "facility_name": selected[0]["facility_name"], "state": selected[0]["state"],
                   "measures": [{k: r[k] for k in keep} for r in selected]}
    return {"run_id": report["run_id"], "cohort_hospitals": report["cohort_hospitals"],
            "source_release": report["source_release"], "mode": "verified_exports" if tables is not None else "summary_only",
            "metrics": summaries, "example": example}, grouped


def save_chart(fig, path):
    fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white", metadata={"Software": "Matplotlib 3.10.8"})
    plt.close(fig)


def charts(summary, grouped, output):
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "axes.spines.top": False, "axes.spines.right": False, "axes.labelcolor": "#243943",
        "text.color": "#162b35", "axes.titleweight": "bold", "axes.titlesize": 12,
        "xtick.color": "#4d626c", "ytick.color": "#4d626c", "grid.alpha": .16})
    names = []
    metrics = summary["metrics"]
    fig, ax = plt.subplots(figsize=(12, 3.5), layout="constrained")
    left = [0.] * 3
    fields = [("comparable", "Comparable", "#007e79"),
              ("eligible_insufficient_peers", "Eligible, insufficient peers", "#91b9b4"),
              ("excluded_numeric", "Numeric, excluded by policy", "#c58a55"),
              ("missing_score", "Unavailable score", "#cdd5d8")]
    for field, label, color in fields:
        values = [100 * m[field] / summary["cohort_hospitals"] for m in metrics]
        ax.barh(range(3), values, left=left, color=color, height=.48, label=label)
        left = [a + b for a, b in zip(left, values)]
    for i, m in enumerate(metrics):
        ax.text(2, i, f"{m['comparable']:,} comparable / {m['cohort_hospitals']:,}", va="center", color="white", fontsize=10, weight="bold")
    ax.set_yticks(range(3), [f"{m['measure_id']}\n{m['period']}" for m in metrics]); ax.invert_yaxis()
    ax.set_xlim(0, 100); ax.xaxis.set_major_formatter(PercentFormatter(100)); ax.set_xlabel("Share of the 2,767-hospital cohort, separately for each measure")
    ax.legend(ncols=2, loc="upper center", bbox_to_anchor=(.5, -.27), frameon=False)
    save_chart(fig, output / "coverage.png"); names.append("coverage.png")
    if summary["mode"] == "summary_only":
        return names
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.1), layout="constrained")
    for ax, m, color in zip(axes, metrics, COLORS):
        values = [float(r["score_value"]) for r in grouped[m["measure_id"]]["eligible"]]
        bins = [v - .5 for v in range(25)] if m["measure_id"] == "OP_22" else 26
        ax.hist(values, bins=bins, color=color, edgecolor="white", linewidth=.6)
        ax.axvline(m["distribution"]["median"], color="#172f3b", linestyle="--", linewidth=1.5, label=f"Median {m['distribution']['median']:g}")
        ax.set_title(m["label"], loc="left", pad=12, fontsize=10.5)
        ax.set_xlabel(f"Hospital score ({m['unit']})\n{m['period']}; eligible n={len(values):,}")
        ax.set_ylabel("Hospitals"); ax.grid(axis="y"); ax.legend(frameon=False, fontsize=9)
        if m["measure_id"] == "OP_22":ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    save_chart(fig, output / "distributions.png"); names.append("distributions.png")
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.1), layout="constrained")
    for ax, m, color in zip(axes, metrics, COLORS):
        values = [float(r["gap_to_peer_median"]) for r in grouped[m["measure_id"]]["comparable"]]
        ax.hist(values, bins=27, color=color, edgecolor="white", linewidth=.6)
        ax.axvline(0, color="#172f3b", linestyle="--", linewidth=1.4)
        unit = "minutes" if m["unit"] == "minutes" else "percentage points"
        ax.set_title(m["measure_id"], loc="left", pad=12)
        ax.set_xlabel(f"Gap vs peer median ({'min' if m['unit'] == 'minutes' else 'pp'})\n{m['period']}; comparable n={len(values):,}")
        ax.set_ylabel("Hospitals"); ax.grid(axis="y")
        ax.text(.98, .95, "Lower is favorable" if m["direction"] == "lower" else "Higher is favorable", transform=ax.transAxes, ha="right", va="top", fontsize=9)
    save_chart(fig, output / "peer_gaps.png"); names.append("peer_gaps.png")
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 2.9), layout="constrained")
    for ax, m, row in zip(axes, metrics, summary["example"]["measures"]):
        q1, med, q3, score = [float(row[k]) for k in ["peer_q1", "peer_median", "peer_q3", "score_value"]]
        ax.plot([q1, q3], [0, 0], color="#a4b4bd", linewidth=10, solid_capstyle="round", label="Peer Q1-Q3")
        ax.scatter([med], [0], marker="|", s=320, color="#172f3b", linewidth=2, zorder=3, label="Peer median")
        ax.scatter([score], [.2], s=90, color="#b26234" if row["unfavorable_signal"] == "true" else "#007e79", zorder=4, label="Hospital score")
        ax.annotate(f"{score:g}", (score, .2), xytext=(0, 12), textcoords="offset points", ha="center", weight="bold")
        width = max(q3, score) - min(q1, score)
        pad = max(width * .22, .7 if m["unit"] == "percent" else 3)
        ax.set_xlim(min(q1, score) - pad, max(q3, score) + pad); ax.set_ylim(-.35, .65)
        ax.set_yticks([]); ax.spines["left"].set_visible(False)
        ax.set_title(f"{m['measure_id']} | {row['peer_count']} other peers", loc="left", fontsize=11)
        ax.set_xlabel(f"{m['unit'].capitalize()} | {m['period']}")
    handles = [Line2D([], [], color="#a4b4bd", linewidth=8),
               Line2D([], [], color="#172f3b", marker="|", markersize=14, linestyle="None"),
               Line2D([], [], color="#b26234", marker="o", linestyle="None"),
               Line2D([], [], color="#007e79", marker="o", linestyle="None")]
    fig.legend(handles, ["Peer Q1-Q3", "Peer median", "Hospital: review signal", "Hospital: no quartile signal"], ncols=4, loc="outside lower center", frameon=False, fontsize=9)
    save_chart(fig, output / "hospital_example.png"); names.append("hospital_example.png")
    return names


def number(value):
    return f"{value:,.1f}".removesuffix(".0")


def findings(summary):
    a, b, c = summary["metrics"]
    common = [
        f"Only {a['comparable']:,}, {b['comparable']:,} and {c['comparable']:,} hospitals qualify for peer comparisons on OP_18b, OP_22 and nurse communication respectively. Across the three measures, 197 eligible hospital-measure records lack ten other same-state peers; no national fallback is used.",
        f"Unfavorable review signals occur in {a['unfavorable_signals']:,}/{a['comparable']:,} OP_18b comparisons ({a['signal_pct_of_comparable']:.1f}%), {b['unfavorable_signals']:,}/{b['comparable']:,} OP_22 comparisons ({b['signal_pct_of_comparable']:.1f}%) and {c['unfavorable_signals']:,}/{c['comparable']:,} nurse-communication comparisons ({c['signal_pct_of_comparable']:.1f}%). These relative quartile flags are not estimates of clinical failure or directly comparable prevalence rates; rounded scores and ties affect flag shares.",
    ]
    if summary["mode"] == "summary_only":
        return common
    return [
        f"Among {a['eligible']:,} eligible hospitals, the median published ED visit median is {number(a['distribution']['median'])} minutes (hospital IQR {number(a['distribution']['q1'])}-{number(a['distribution']['q3'])}). This describes hospitals equally, not a pooled patient waiting time.",
        f"The median published left-before-seen percentage is {number(b['distribution']['median'])}% (IQR {number(b['distribution']['q1'])}-{number(b['distribution']['q3'])}%) among {b['eligible']:,} eligible hospitals. {b['distribution']['zero_count']:,} report 0% ({100*b['distribution']['zero_count']/b['eligible']:.1f}%); rounded published zeros should not be interpreted as verified absence of individual events.",
        f"The nurse-communication median is {number(c['distribution']['median'])}% (IQR {number(c['distribution']['q1'])}-{number(c['distribution']['q3'])}%) across {c['eligible']:,} eligible hospitals. Notes and survey-sample rules exclude {c['excluded_numeric']:,} additional numeric scores from comparisons. This measure reflects inpatient experience, a different patient population from ED care.",
        *common,
    ]


def render_html(summary, chart_names, output, report_date):
    def image(name, alt):
        encoded = base64.b64encode((output / "figures" / name).read_bytes()).decode("ascii")
        return f'<img src="data:image/png;base64,{encoded}" alt="{escape(alt)}" loading="eager">'
    metrics = summary["metrics"]
    cards = "".join(f'<article class="kpi"><span class="eyebrow">{escape(m["measure_id"])}</span><strong>{number(m["distribution"]["median"])}<small>{" min" if m["unit"] == "minutes" else "%"}</small></strong><h3>{escape(m["label"])}</h3><p>Median across {m["eligible"]:,} eligible hospitals<br>{m["period"]}</p></article>' for m in metrics) if summary["mode"] != "summary_only" else "".join(f'<article class="kpi"><span class="eyebrow">{m["measure_id"]}</span><strong>{m["eligible_coverage_pct"]:.1f}<small>%</small></strong><h3>Eligible coverage</h3><p>{m["eligible"]:,} of {m["cohort_hospitals"]:,} hospitals<br>{m["period"]}</p></article>' for m in metrics)
    table_rows = "".join(f'<tr><th scope="row">{m["measure_id"]}</th><td>{m["eligible"]:,} ({m["eligible_coverage_pct"]:.1f}%)</td><td>{m["comparable"]:,}</td><td>{m["unfavorable_signals"]:,} / {m["comparable"]:,} ({m["signal_pct_of_comparable"]:.1f}%)</td><td>{m["period"]}</td></tr>' for m in metrics)
    full_sections = ""
    if summary["mode"] == "verified_exports":
        example = summary["example"]
        examples = "".join(f'<tr><th scope="row">{m["measure_id"]}</th><td>{number(float(r["score_value"]))}{" min" if m["unit"] == "minutes" else "%"}</td><td>{number(float(r["peer_median"]))}</td><td>{float(r["gap_to_peer_median"]):+g} {"min" if m["unit"] == "minutes" else "pp"}</td><td>{r["peer_count"]}</td><td>{"Review signal" if r["unfavorable_signal"] == "true" else "No quartile signal"}</td></tr>' for m, r in zip(metrics, example["measures"]))
        full_sections = f'''<section id="distributions"><span class="section-no">03 / DESCRIPTIVE DISTRIBUTIONS</span><h2>The distribution matters as much as the midpoint.</h2><p>Each panel uses eligible hospital-level published scores. Hospitals carry equal weight. Axes, sample sizes and periods are separate; there is no combined hospital-quality score.</p><figure>{image("distributions.png", "Three separate score distributions: ED minutes, left-before-seen percent and inpatient nurse-communication percent.")}<figcaption>Dashed lines mark medians across eligible hospitals. These are cross-sectional distributions, not patient-level estimates or time trends.</figcaption></figure></section>
<section id="peers"><span class="section-no">04 / LOCAL PEER CONTEXT</span><h2>Compare each hospital with other eligible hospitals.</h2><p>Peers share state, hospital type, measure, source release and exact measurement dates. The evaluated hospital is excluded before calculating exact continuous quartiles; at least ten other eligible hospitals are required.</p><figure>{image("peer_gaps.png", "Separate distributions of hospital score minus its own leave-one-out peer median, in minutes or percentage points.")}<figcaption>Zero means the hospital equals its own peer median. The sign's favorable direction differs for nurse communication. A positive or negative median gap alone does not determine the quartile review flag.</figcaption></figure>
<div class="case"><span class="eyebrow">AN ILLUSTRATION, NOT A RANKING</span><h3>{escape(example["facility_name"].title())}</h3><p>{escape(example["state"])} · CMS facility {example["facility_id"]}. Selection rule: {escape(example["selection_rule"])}.</p><figure>{image("hospital_example.png", "Illustrative hospital scores against its own peer interquartile ranges and medians for the three separate measures.")}<figcaption>The gray band is the peer interquartile range, not a confidence interval. Peer membership and periods differ by measure. Orange marks a descriptive quartile review signal.</figcaption></figure><div class="table-wrap"><table><thead><tr><th>Measure</th><th>Hospital</th><th>Peer median</th><th>Gap</th><th>Other peers</th><th>Result</th></tr></thead><tbody>{examples}</tbody></table></div><p class="note">The OP_22 score equals its peer Q3 and therefore does not cross the strict threshold. This example supplies operational context without labeling the hospital's overall clinical quality.</p></div></section>'''
    finding_html = "".join(f'<li>{escape(text)}</li>' for text in findings(summary))
    mode_note = "Verified full exports from an existing successful pipeline run. No pipeline rerun or inferential analysis." if summary["mode"] == "verified_exports" else "Summary-only mode: full exports are unavailable. Only verified historical coverage/flag counts are shown; no distributions or hospital examples are invented."
    report_checks = "For this report, the selected run's SUCCESS.json, quality-report hash, all five export hashes and row counts were verified before analysis. This report build read existing exports; it did not rerun Spark, the pipeline or the original test suite." if summary["mode"] == "verified_exports" else "For this summary-only report, the existing passed quality report and its approved-source hash references were checked. Full-export verification and distribution analysis were unavailable; no hospital values, distributions or new percentile calculations are presented. The pipeline was not rerun."
    css = '''*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f6f3ed;color:#18323e;font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}a{color:#006e6a;text-underline-offset:4px}header,main,footer{max-width:1180px;margin:auto;padding:0 40px}header{padding-top:26px}.masthead{display:flex;justify-content:space-between;gap:20px;border-bottom:1px solid #ccd3cf;padding-bottom:18px;font-size:12px;letter-spacing:.12em;font-weight:700}.masthead a{text-decoration:none}nav{display:flex;gap:22px;flex-wrap:wrap;padding:18px 0;font-size:13px}.hero{padding:48px 0 32px}.eyebrow,.section-no{font-size:11px;letter-spacing:.14em;font-weight:750;color:#537078}.hero h1{font:normal clamp(36px,5.2vw,64px)/1.05 Georgia,serif;letter-spacing:-.03em;max-width:900px;margin:18px 0 24px}.deck{font-size:20px;line-height:1.5;max-width:790px;color:#48616b}.meta{font-size:12px;color:#607078}.status{display:inline-block;border:1px solid #90b6af;border-radius:30px;padding:6px 12px;color:#006e6a;font-size:11px;letter-spacing:.05em;font-weight:700}.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:22px 0 34px}.kpi{background:white;border-top:3px solid #007e79;padding:24px}.kpi:nth-child(2){border-color:#b26234}.kpi:nth-child(3){border-color:#536c9c}.kpi strong{display:block;font-size:46px;line-height:1.3;letter-spacing:-.04em;margin:10px 0}.kpi small{font-size:20px;letter-spacing:0}.kpi h3{font-size:15px;margin:12px 0 5px}.kpi p{font-size:12px;color:#526b75;margin:0}.callout{border-left:3px solid #b26234;background:#eee9de;padding:16px 22px;font-size:14px}section{padding:42px 0;border-top:1px solid #cbd4d0}h2{font:normal 34px/1.2 Georgia,serif;letter-spacing:-.02em;margin:15px 0 18px;max-width:880px}h3{font-size:20px}p{max-width:960px}figure{background:white;margin:24px 0;padding:20px 14px 12px;border:1px solid #e0e5e2}figure img{display:block;width:100%;height:auto}figcaption{font-size:12px;color:#536b74;margin:12px 14px 4px;line-height:1.6}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;text-align:left;font-size:13px}th,td{padding:13px 12px;border-bottom:1px solid #d5ded9;vertical-align:top}thead{background:#e9eee9}tbody th{white-space:nowrap}.sources{display:grid;grid-template-columns:repeat(3,1fr);gap:24px}.sources p{font-size:13px}.sources h3{font-size:16px}.case{background:#eeeee6;padding:26px;margin-top:30px}.case h3{font:normal 29px/1.2 Georgia,serif;margin:12px 0}.note{font-size:12px;color:#5b6c74}.findings li,.limits li{margin:14px 0;padding-left:8px}.decisions{display:grid;grid-template-columns:1fr 1fr;gap:24px}.decisions article{border-top:2px solid #007e79;padding-top:10px}.decisions h3{font-size:17px}code{font-size:12px;overflow-wrap:anywhere}.method{font-size:14px}footer{border-top:1px solid #cbd4d0;padding-top:24px;padding-bottom:40px;font-size:12px;color:#526d78}@media(max-width:680px){header,main,footer{padding-left:20px;padding-right:20px}.masthead{display:block}.masthead span{display:block;margin-top:8px}.hero{padding-top:28px}.deck{font-size:17px}.kpis,.sources,.decisions{grid-template-columns:1fr}.kpi{padding:20px}.kpi strong{font-size:40px}h2{font-size:28px}section{padding:32px 0}.case{padding:16px}figure{padding:8px 2px;overflow-x:auto}figure img{min-width:850px}nav{gap:14px}th,td{padding:10px 8px}}@media print{body{background:white;font-size:11px}header,main,footer{max-width:none;padding-left:0;padding-right:0}nav{display:none}.hero{padding-top:15px}section{padding:20px 0}.kpi{padding:12px}.kpi strong{font-size:30px}h2{font-size:25px}figure,table,.kpis{break-inside:avoid}a{color:inherit}.case{background:#f4f4f0}footer{font-size:10px}}'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="A reproducible, descriptive analysis of CMS hospital operational measures and inpatient experience, with exact leave-one-out peer comparisons."><title>Healthcare Operations &amp; Performance Analytics</title><style>{css}</style></head><body>
<header><div class="masthead"><a href="{REPO}">RANSIJ / DATA ANALYTICS PORTFOLIO</a><span>RESEARCH NOTE 01 · {report_date}</span></div><nav aria-label="Report sections"><a href="#question">Business question</a><a href="#coverage">Coverage</a><a href="#peers">Peer context</a><a href="#findings">Findings</a><a href="#method">Method &amp; limits</a></nav></header>
<main><div class="hero"><span class="status">STATIC ANALYTICAL REPORT · CMS PUBLIC DATA</span><h1>Healthcare Operations<br>&amp; Performance Analytics</h1><p class="deck">Find operational review opportunities while keeping measurement periods, patient populations and data quality in view.</p><p class="meta">2,767 acute care hospitals with emergency services · 50 U.S. states + DC<br>CMS release: {summary['source_release']} · Analysis source run: <code>{summary['run_id']}</code></p></div><div class="kpis">{cards}</div><p class="callout">{escape(mode_note)}<br><strong>Interpretation:</strong> review signals are descriptive, relative to peers and intended for further investigation. They are not clinical diagnoses, causal conclusions or an overall hospital-quality rating.</p>
<section id="question"><span class="section-no">01 / THE BUSINESS QUESTION</span><h2>Where should an operations team look more closely?</h2><p>Which acute care hospitals with emergency services show unfavorable ED operations or inpatient communication signals relative to other eligible hospitals of the same type in the same state? The intended decision is a prioritized operational review using local context, rather than an automatic intervention or a patient-care recommendation.</p><div class="sources"><article><h3><a href="https://data.cms.gov/provider-data/dataset/xubh-q36u">Hospital General Information</a></h3><p>Hospital identity, state, type, ownership and emergency-service availability establish the population. Snapshot attributes are not reconstructed historical attributes.</p></article><article><h3><a href="https://data.cms.gov/provider-data/dataset/yv7e-xc69">Timely and Effective Care</a></h3><p>OP_18b: ED visit median minutes, excluding transfer and psychiatric/mental-health cases. OP_22: published percent leaving before being seen. Lower is favorable for both.</p></article><article><h3><a href="https://data.cms.gov/provider-data/dataset/dgck-syfz">HCAHPS Patient Survey</a></h3><p>H_COMP_1_A_P: percent reporting nurses always communicated well during an inpatient stay. Higher is favorable. It is not an ED satisfaction measure.</p></article></div></section>
<section id="coverage"><span class="section-no">02 / COVERAGE BEFORE COMPARISON</span><h2>A reported number is not always a comparable one.</h2><p>Eligibility applies source notes, valid scores and dates, and at least 100 completed surveys for HCAHPS. All hospitals remain in the coverage denominator. Missing values stay missing; insufficient peer groups receive no comparison signal.</p><figure>{image("coverage.png", "Coverage across all 2,767 hospitals for each measure, separating comparable, insufficient peers, excluded numeric scores and unavailable scores.")}<figcaption>Coverage denominator: 2,767 hospitals per measure. Categories are mutually exclusive. HCAHPS precision and data-collection notes reduce usable coverage even when a numeric score is published.</figcaption></figure><div class="table-wrap"><table><thead><tr><th>Measure</th><th>Eligible / 2,767</th><th>Comparable</th><th>Flagged / comparable</th><th>Measurement period</th></tr></thead><tbody>{table_rows}</tbody></table></div></section>
{full_sections}
<section id="findings"><span class="section-no">05 / FINDINGS &amp; DECISIONS</span><h2>Evidence to guide a review, with room for context.</h2><ol class="findings">{finding_html}</ol><div class="decisions"><article><h3>Review ED flow locally</h3><p>Use eligible OP_18b/OP_22 flags to request more recent arrival, staffing and throughput data. Verify case mix and local processes before considering capacity or workflow changes.</p></article><article><h3>Review communication and evidence gaps</h3><p>For inpatient communication flags, examine local survey comments and communication routines. For excluded or sparse-peer records, improve the evidence base before making a relative-performance claim.</p></article></div></section>
<section id="method"><span class="section-no">06 / METHODOLOGY &amp; LIMITATIONS</span><h2>Traceable from original bytes to a bounded comparison.</h2><p class="method">The original pipeline used PySpark to normalize and validate three fixed CMS sources, build hospital/measure dimensions and a long-form fact model, and preserve missingness and notes. Spark SQL used joins, CTEs and a window count to calculate identity-excluding references with exact continuous percentiles. A flag requires an eligible target, ten other peers, and a strict crossing of Q3 for ED measures or Q1 for HCAHPS. Published percentages are retained on the 0-100 scale; gaps use percentage points.</p><p class="method">Prior Phase 2 evidence records 27 passing tests, 22,557 independently checked percentiles and two equivalent model runs. {report_checks}</p><ul class="limits"><li>OP_22 covers calendar 2024; OP_18b and HCAHPS cover October 2024-September 2025. These are historical, cross-sectional measures, not current operational monitoring.</li><li>ED operations and inpatient experience represent different patient populations. Their co-occurrence does not establish causation.</li><li>State/type matching does not adjust for hospital size, case mix, teaching status, staffing or rurality. Missingness and survey nonresponse can be selective.</li><li>Quartile rules generate relative review flags by design. Ties, rounding and eligibility affect flag shares. Peer IQRs are not confidence intervals.</li><li>Medians across hospitals are not pooled patient medians. Rounded percentages and period survey totals do not supply item-level patient denominators.</li><li>Databricks execution and a Power BI dashboard are postponed. This is a Python/matplotlib static HTML report; no cloud execution, ML or inferential test is claimed.</li></ul></section></main><footer><p>Prepared with Python and matplotlib · Official CMS public data · Generated {report_date}<br><a href="{REPO}">Source repository</a> · <a href="{REPO}/blob/main/docs/executive_summary.md">Executive summary</a> · <a href="{REPO}/blob/main/docs/evidence/analysis_summary.json">Calculated report evidence</a> · <a href="{REPO}/blob/main/docs/quality_checks.md">Pipeline validation</a></p></footer></body></html>'''


def executive(summary):
    items = findings(summary) if summary["mode"] == "summary_only" else [
        f"{m['label']}: hospital median {number(m['distribution']['median'])}{' minutes' if m['unit']=='minutes' else '%'} (IQR {number(m['distribution']['q1'])}-{number(m['distribution']['q3'])}{' minutes' if m['unit']=='minutes' else '%'}); {m['eligible']:,} eligible hospitals. {m['unfavorable_signals']:,} of {m['comparable']:,} comparable hospitals cross the unfavorable peer-quartile threshold ({m['signal_pct_of_comparable']:.1f}%)."
        for m in summary["metrics"]]
    return "\n".join(["# Executive summary", "", "## Healthcare Operations & Performance Analytics", "",
        "**Decision question.** Which hospitals warrant a closer operational or inpatient-communication review relative to eligible same-state peers?", "",
        f"**Evidence.** Three fixed official CMS datasets, release {summary['source_release']}; {summary['cohort_hospitals']:,} acute care hospitals with emergency services in the 50 states and DC. The report uses existing run `{summary['run_id']}`. OP_22 covers 2024; OP_18b and HCAHPS cover October 2024-September 2025. " + ("All five analytical export hashes and the SUCCESS-to-quality-report chain were verified before analysis." if summary["mode"] == "verified_exports" else "Full exports are unavailable; only existing quality-report counts are used."), "",
        "**Descriptive results.**", "", *[f"- {text}" for text in items], "",
        "**Possible decisions.** Use eligible flags to request current workflow, arrival, staffing and survey-comment evidence. Review ED flow and inpatient communication separately. Improve evidence where source notes or sparse peer groups prevent comparison; 197 eligible hospital-measure records lack ten other peers.", "",
        "**Interpretation limits.** Flags are generated by relative quartile rules and are signals to investigate, not clinical-quality diagnoses. Same-state/type peers are not matched on case mix, size, staffing or teaching status. Survey nonresponse, rounding and selection into eligibility can affect results. No causal effect, significance test, treatment recommendation or overall hospital-quality index is estimated. Hospital medians are not pooled patient medians. Databricks and Power BI are postponed.", ""])


def build(run_dir, output, report_date, summary_only=False):
    output = Path(output).resolve()
    if run_dir is not None:
        input_dir = Path(run_dir).resolve()
        if output == input_dir or input_dir in output.parents or output in input_dir.parents:
            raise ContractError("Report output must not modify or overlap the original run tree")
    if run_dir is None or summary_only:
        report = json.loads((PROJECT_ROOT / "docs/evidence/run_summary.json").read_text(encoding="utf-8"))
        validate_sources(report)
        tables = None
        verification = {"mode": "summary_only", "run_id": report["run_id"],
                        "evidence_sha256": digest_file(PROJECT_ROOT / "docs/evidence/run_summary.json"),
                        "reason": "Explicit summary-only mode or no successful export directory available"}
    else:
        report, tables, verification = verified_run(run_dir)
    summary, grouped = summarize(report, tables)
    output.mkdir(parents=True, exist_ok=True)
    names = charts(summary, grouped, output / "figures")
    (output / "index.html").write_text(render_html(summary, names, output, report_date), encoding="utf-8", newline="\n")
    (output / "executive_summary.md").write_text(executive(summary), encoding="utf-8", newline="\n")
    (output / ".nojekyll").write_text("", encoding="utf-8", newline="\n")
    evidence = output / "evidence"
    evidence.mkdir(exist_ok=True)
    (evidence / "analysis_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    verification.update({"report_date": report_date, "python_version": platform.python_version(),
        "matplotlib_version": matplotlib.__version__, "pipeline_reexecuted": False,
        "inferential_tests_executed": False, "builder_sha256": digest_file(Path(__file__)),
        "artifact_sha256": {str(p.relative_to(output)).replace("\\", "/"): digest_file(p)
            for p in [output / "index.html", output / "executive_summary.md", evidence / "analysis_summary.json",
                      *[output / "figures" / n for n in names]]}})
    (evidence / "report_source_verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"mode": summary["mode"], "run_id": summary["run_id"], "charts": names,
        "output": str(output), "medians": [m.get("distribution", {}).get("median") for m in summary["metrics"]]}, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_ROOT / "runs")
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "docs")
    parser.add_argument("--report-date", default=datetime.now(timezone(timedelta(hours=-6))).date().isoformat())
    parser.add_argument("--summary-only", action="store_true", help="Use historical coverage counts only; no invented distributions")
    args = parser.parse_args()
    date.fromisoformat(args.report_date)
    run_dir = args.run_dir or latest_successful(args.runs_root)
    build(run_dir, args.output_dir, args.report_date, args.summary_only)


if __name__ == "__main__":
    main()
