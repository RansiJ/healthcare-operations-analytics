"""Verified sources -> PySpark model -> Spark SQL -> validated bounded exports."""

from collections import Counter
from datetime import datetime, timezone
import csv
import json
from pathlib import Path
import platform
import uuid

from pyspark.sql import functions as F

from .reference import verify_peer_rows
from .sources import PROJECT_ROOT, ContractError, digest_file, external_path, verify_sources
from .transform import FACT_KEY, build_model, require_empty, require_unique


def execute_sql(spark, filename):
    return spark.sql((PROJECT_ROOT / "sql" / filename).read_text(encoding="utf-8"))


def json_value(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def export_rows(frame, path, keys):
    """Small, bounded driver export; avoids Hadoop native Windows write dependencies.

    Spark performs all transformations and ordering. Arrays become JSON cells.
    Missing scalar values become empty CSV cells, never zeros.
    """
    rows = frame.orderBy(*keys).limit(20001).collect()
    if len(rows) > 20000:
        raise ContractError("Export exceeds this project's 20,000-row/table bound")
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(frame.columns)
        writer.writerows([[json_value(v) for v in row] for row in rows])
    return [r.asDict(recursive=True) for r in rows]


def run(spark, raw_dir, output_root):
    """Use an existing Databricks Spark session or a local one; no SparkContext/RDD API.

    Each run has a fresh directory. Only a validated run gets SUCCESS.json.
    """
    provenance = verify_sources(raw_dir)  # Must happen before every Spark read.
    output_root = external_path(output_root)
    raw_dir = external_path(raw_dir)
    if output_root == raw_dir or raw_dir in output_root.parents or output_root in raw_dir.parents:
        raise ContractError("Raw input and derived output trees must be separate")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        print("Building verified PySpark model", flush=True)
        model = build_model(spark, raw_dir, provenance)
        for name, frame in model.items():
            frame.createOrReplaceTempView(name)
        metrics = execute_sql(spark, "hospital_metrics.sql")
        metrics.createOrReplaceTempView("hospital_metrics")
        require_unique(metrics, FACT_KEY, "Join multiplied hospital/measure rows")
        require_empty(metrics, F.col("source_state_mismatch"), "Hospital state disagreement")
        peers = execute_sql(spark, "peer_benchmarks.sql")
        require_unique(peers, FACT_KEY, "Peer join multiplied rows")
        model["hospital_metrics"] = metrics
        model["peer_benchmarks"] = peers
        print("Exporting bounded analytical tables", flush=True)
        exported = {}
        schema = {}
        for name, frame in model.items():
            keys = (["measure_id"] if name == "dim_measure" else
                    ["facility_id"] if name == "dim_hospital" else FACT_KEY)
            exported[name] = export_rows(frame, run_dir / (name + ".csv"), keys)
            schema[name] = json.loads(frame.schema.json())
        hospitals = exported["dim_hospital"]
        facts = exported["fact_hospital_measure"]
        metric_rows = exported["hospital_metrics"]
        peer_rows = exported["peer_benchmarks"]
        cohort_ids = {r["facility_id"] for r in hospitals if r["in_cohort"]}
        expected_cohort_facts = sum(r["facility_id"] in cohort_ids for r in facts)
        if len(metric_rows) != expected_cohort_facts or len(peer_rows) != len(metric_rows):
            raise ContractError("Join/export cardinality mismatch")
        print("Verifying every peer reference independently", flush=True)
        oracle = verify_peer_rows(peer_rows)
        coverage = []
        for measure in ("OP_18b", "OP_22", "H_COMP_1_A_P"):
            rows = [r for r in peer_rows if r["measure_id"] == measure]
            eligible = sum(r["comparison_eligible"] for r in rows)
            coverage.append({"measure_id": measure, "cohort_hospitals": len(cohort_ids),
                "reported_rows": len(rows), "numeric_scores": sum(r["value_status"] == "numeric" for r in rows),
                "eligible": eligible, "eligible_coverage_pct": round(100 * eligible / len(cohort_ids), 2),
                "comparable": sum(r["comparison_status"] == "comparable" for r in rows),
                "unfavorable_signals": sum(r["unfavorable_signal"] is True for r in rows),
                "excluded_numeric": sum(r["value_status"] == "numeric" and not r["comparison_eligible"] for r in rows),
                "exclusion_reasons": dict(Counter(x for r in rows for x in r["exclusion_reasons"]))})
        # Guard against silent denominator drift relative to the approved fixed bytes.
        observed = [(r["numeric_scores"], r["eligible"], r["comparable"]) for r in coverage]
        if len(cohort_ids) != 2767 or observed != [(2662, 2632, 2567), (2588, 2588, 2522), (2677, 2496, 2430)]:
            raise ContractError(f"Phase 1 reconciliation failed: cohort={len(cohort_ids)}, counts={observed}")
        state_coverage = []
        for measure in ("OP_18b", "OP_22", "H_COMP_1_A_P"):
            for state in sorted({r["state"] for r in metric_rows}):
                rows = [r for r in peer_rows if r["measure_id"] == measure and r["state"] == state]
                state_coverage.append({"measure_id": measure, "state": state,
                    "cohort_hospitals": sum(r["in_cohort"] and r["state"] == state for r in hospitals),
                    "reported_rows": len(rows), "eligible": sum(r["comparison_eligible"] for r in rows),
                    "comparable": sum(r["comparison_status"] == "comparable" for r in rows)})
        # Read files back: verify row counts and eligible denominators survived serialization.
        output_hashes = {}
        for name, rows in exported.items():
            path = run_dir / (name + ".csv")
            with path.open(encoding="utf-8", newline="") as stream:
                back = list(csv.DictReader(stream))
            if len(back) != len(rows):
                raise ContractError("CSV round-trip row count mismatch")
            if rows and "comparison_eligible" in rows[0]:
                if sum(r["comparison_eligible"] == "true" for r in back) != sum(r["comparison_eligible"] for r in rows):
                    raise ContractError("CSV round-trip eligibility mismatch")
            output_hashes[name + ".csv"] = digest_file(path)
        # Verify input integrity again after lazy Spark reads; raw files must remain unchanged.
        verify_sources(raw_dir)
        code_paths = sorted((PROJECT_ROOT / "healthcare_pipeline").glob("*.py")) + sorted((PROJECT_ROOT / "sql").glob("*.sql"))
        report = {"phase": 2, "status": "passed", "run_id": run_id,
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(), "spark_version": spark.version,
            "source_release": "2026-08-13", "sources": provenance,
            "code_sha256": {str(p.relative_to(PROJECT_ROOT)).replace("\\", "/"): digest_file(p) for p in code_paths},
            "output_sha256": output_hashes, "rows": {k: len(v) for k, v in exported.items()},
            "cohort_hospitals": len(cohort_ids), "coverage": coverage,
            "state_coverage": state_coverage, "independent_peer_verification": oracle,
            "source_name_mismatches": sum(r["source_name_mismatch"] for r in metric_rows),
            "selected_measures_only": True, "join_cardinality_and_export_roundtrip": "passed",
            "malformed_types_dates_ranges_unknown_notes_duplicate_keys_orphans": "none",
            "unselected_timely_rows_not_modeled": 138084 - 9316,
            "unselected_hcahps_rows_not_modeled": 325720 - 4790,
            "selected_facts_outside_cohort": len(facts) - len(metric_rows),
            "limitations": ["Executed locally; not executed in a Databricks account",
                            "Three different patient/measure definitions; OP_22 has a different period",
                            "Signals are descriptive review flags, not clinical or causal findings"]}
        (run_dir / "schemas.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        (run_dir / "quality_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        (run_dir / "SUCCESS.json").write_text(json.dumps({"run_id": run_id, "quality_report_sha256": digest_file(run_dir / "quality_report.json")}, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"run_dir": str(run_dir), "rows": report["rows"], "coverage": coverage, "oracle": oracle}, indent=2), flush=True)
        return report, run_dir
    except Exception as exc:
        (run_dir / "FAILED.json").write_text(json.dumps({"error_type": type(exc).__name__, "message": str(exc)}, indent=2) + "\n", encoding="utf-8")
        raise

