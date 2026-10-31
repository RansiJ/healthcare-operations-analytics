"""All row transformations use native PySpark expressions, never Python UDFs."""

from datetime import date
import csv
from pathlib import Path

from pyspark.sql import functions as F, types as T

from .sources import RELEASE, SOURCES, ContractError


STATES = "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
# Only the meanings actually inspected in the Phase 1 crosswalk are accepted.
KNOWN_NOTES = ["1", "2", "3", "4", "5", "6", "7", "10", "11", "12", "13", "19", "24", "28", "29"]
MEASURES = [
    ("OP_18b", "yv7e-xc69", "ED length of visit", "minutes", "lower",
     "Discharged ED patients; excludes transfers and psychiatric/mental health cases",
     date(2024, 10, 1), date(2025, 9, 30)),
    ("OP_22", "yv7e-xc69", "Left before being seen", "percent", "lower",
     "ED patients; not an inpatient experience measure", date(2024, 1, 1), date(2024, 12, 31)),
    ("H_COMP_1_A_P", "dgck-syfz", "Nurses always communicated well", "percent", "higher",
     "Inpatient survey respondents; not ED satisfaction", date(2024, 10, 1), date(2025, 9, 30)),
]
MEASURE_SCHEMA = "measure_id string, source_dataset_id string, measure_label string, unit string, favorable_direction string, patient_population string, expected_start_date date, expected_end_date date"
FACT_KEY = ["source_release", "source_dataset_id", "facility_id", "measure_id", "start_date", "end_date"]


def require_empty(frame, condition, message):
    example = [r.asDict(recursive=True) for r in frame.filter(condition).limit(3).collect()]
    if example:
        raise ContractError(f"{message}: {example}")


def require_unique(frame, keys, message):
    require_empty(frame.groupBy(*keys).count(), F.col("count") != 1, message)


def read_source(spark, path, expected_rows):
    """Explicit all-string schema keeps zeros and missing-value tokens intact."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        header = next(csv.reader(stream))
    schema = T.StructType([T.StructField(name, T.StringType(), True) for name in header])
    frame = (spark.read.schema(schema).option("header", True)
             .option("enforceSchema", False).option("mode", "FAILFAST")
             .option("multiLine", True).option("escape", '"')
             .option("nullValue", "__CMS_NULL_SENTINEL__").option("emptyValue", "")
             .option("ignoreLeadingWhiteSpace", False).option("ignoreTrailingWhiteSpace", False)
             .csv(str(path).replace("\\", "/")))
    count = frame.count()
    if count != expected_rows:
        raise ContractError(f"CSV row count {path}: expected {expected_rows}, observed {count}")
    return frame


def hospital_dimension(raw):
    names = {"Facility ID": "facility_id", "Facility Name": "facility_name",
             "State": "state", "Hospital Type": "hospital_type",
             "Hospital Ownership": "hospital_ownership", "Emergency Services": "emergency_services"}
    frame = raw.select(*[F.col(a).alias(b + "_raw") for a, b in names.items()])
    for name in names.values():
        frame = frame.withColumn(name, F.trim(F.col(name + "_raw")))
    frame = frame.withColumn("state", F.upper("state"))
    frame = frame.withColumn("source_release", F.lit(RELEASE).cast("date"))
    frame = frame.withColumn("in_cohort", F.coalesce(
        (F.col("hospital_type") == "Acute Care Hospitals") &
        (F.col("emergency_services") == "Yes") & F.col("state").isin(STATES), F.lit(False)))
    require_empty(frame, F.col("facility_id").isNull() | ~F.col("facility_id").rlike(r"^[0-9A-Z]{6}$"), "Invalid hospital ID")
    require_unique(frame, ["source_release", "facility_id"], "Duplicate hospital key")
    return frame


def harmonize(timely, survey):
    common = {"Facility ID": "facility_id_raw", "Facility Name": "measure_facility_name_raw",
              "State": "measure_state_raw", "Start Date": "start_date_raw", "End Date": "end_date_raw"}
    t = timely.filter(F.col("Measure ID").isin("OP_18b", "OP_22")).select(
        *[F.col(a).alias(b) for a, b in common.items()],
        F.col("Measure ID").alias("measure_id"), F.col("Measure Name").alias("measure_name_raw"),
        F.col("Score").alias("score_raw"), F.col("Sample").alias("sample_raw"),
        F.col("Footnote").alias("score_note_raw"),
        F.lit(None).cast("string").alias("sample_note_raw"),
        F.lit(None).cast("string").alias("response_rate_raw"),
        F.lit(None).cast("string").alias("response_note_raw"),
        F.lit("yv7e-xc69").alias("source_dataset_id"))
    h = survey.filter(F.col("HCAHPS Measure ID") == "H_COMP_1_A_P").select(
        *[F.col(a).alias(b) for a, b in common.items()],
        F.col("HCAHPS Measure ID").alias("measure_id"), F.col("HCAHPS Question").alias("measure_name_raw"),
        F.col("HCAHPS Answer Percent").alias("score_raw"), F.col("Number of Completed Surveys").alias("sample_raw"),
        F.col("HCAHPS Answer Percent Footnote").alias("score_note_raw"),
        F.col("Number of Completed Surveys Footnote").alias("sample_note_raw"),
        F.col("Survey Response Rate Percent").alias("response_rate_raw"),
        F.col("Survey Response Rate Percent Footnote").alias("response_note_raw"),
        F.lit("dgck-syfz").alias("source_dataset_id"))
    return t.unionByName(h)


def parse_number(frame, raw, value, status, integral=False):
    text = F.trim(F.col(raw))
    pattern = r"^\+?[0-9]+$" if integral else r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$"
    dtype = "bigint" if integral else "decimal(18,6)"
    frame = frame.withColumn(value, F.when(text.rlike(pattern), F.expr(f"try_cast(trim({raw}) AS {dtype})")))
    return frame.withColumn(status,
        F.when(text.isNull() | (text == ""), "blank")
         .when(text == "Not Available", "not_available")
         .when(text == "Not Applicable", "not_applicable")
         .when(F.col(value).isNotNull(), "numeric").otherwise("parse_error"))


def parse_notes(frame, raw, codes):
    return frame.withColumn(codes, F.expr(
        f"filter(transform(split(coalesce({raw}, ''), ','), x -> trim(x)), x -> x <> '')"))


def normalize_fact(raw, dim_measure):
    frame = (raw.withColumn("facility_id", F.trim("facility_id_raw"))
             .withColumn("source_release", F.lit(RELEASE).cast("date")))
    for raw_name, value, status, integral in [
        ("score_raw", "score_value", "value_status", False),
        ("sample_raw", "reported_sample_count", "sample_status", True),
        ("response_rate_raw", "response_rate_percent", "response_status", False),
    ]:
        frame = parse_number(frame, raw_name, value, status, integral)
    for name in ("score", "sample", "response"):
        frame = parse_notes(frame, name + "_note_raw", name + "_note_codes")
    frame = frame.withColumn("unknown_notes", F.array_except(
        F.array_union(F.array_union("score_note_codes", "sample_note_codes"), "response_note_codes"),
        F.array(*[F.lit(x) for x in KNOWN_NOTES])))
    require_empty(frame, F.size("unknown_notes") > 0, "Unknown footnote; review semantics before processing")
    require_empty(frame, F.col("facility_id").isNull() | ~F.col("facility_id").rlike(r"^[0-9A-Z]{6}$"), "Invalid measure ID")
    for name in ("start_date", "end_date"):
        frame = frame.withColumn(name, F.to_date(F.try_to_timestamp(F.col(name + "_raw"), F.lit("MM/dd/yyyy"))))
        require_empty(frame, F.col(name).isNull() | (F.date_format(name, "MM/dd/yyyy") != F.trim(F.col(name + "_raw"))), "Invalid measurement date")
    require_empty(frame.join(dim_measure.select("measure_id", "source_dataset_id"),
                             ["measure_id", "source_dataset_id"], "left_anti"),
                  F.lit(True), "Unexpected measure/source mapping")
    frame = frame.join(dim_measure, ["measure_id", "source_dataset_id"], "inner")
    require_empty(frame, (F.col("start_date") != F.col("expected_start_date")) |
                  (F.col("end_date") != F.col("expected_end_date")) |
                  (F.col("start_date") > F.col("end_date")), "Unexpected measurement period")
    require_empty(frame, (F.col("score_value") < 0) |
                  ((F.col("unit") == "percent") & (F.col("score_value") > 100)) |
                  (F.col("response_rate_percent") < 0) | (F.col("response_rate_percent") > 100), "Out-of-range value")
    require_empty(frame, (F.col("value_status") == "parse_error") |
                  (F.col("sample_status") == "parse_error") |
                  (F.col("response_status") == "parse_error"), "Malformed numeric token")
    allowed_score_notes = ((F.size("score_note_codes") == 0) |
        ((F.col("measure_id") == "OP_22") &
         (F.size(F.array_except("score_note_codes", F.array(F.lit("2")))) == 0)))
    is_hcahps = F.col("measure_id") == "H_COMP_1_A_P"
    frame = frame.withColumn("exclusion_reasons", F.filter(F.array(
        F.when(F.col("value_status") != "numeric", F.concat(F.lit("score_"), F.col("value_status"))),
        F.when(~allowed_score_notes, F.lit("score_footnote")),
        F.when(is_hcahps & (F.col("reported_sample_count").isNull() | (F.col("reported_sample_count") < 100)), F.lit("surveys_below_100_or_missing")),
        F.when(is_hcahps & (F.size("sample_note_codes") > 0), F.lit("survey_count_footnote")),
        F.when(is_hcahps & (F.size("response_note_codes") > 0), F.lit("response_rate_footnote")),
    ), lambda x: x.isNotNull()))
    frame = (frame.withColumn("comparison_eligible", F.size("exclusion_reasons") == 0)
             .withColumn("sample_based_submission", F.array_contains("score_note_codes", "2")))
    require_unique(frame, FACT_KEY, "Duplicate fact key")
    return frame.drop("unknown_notes", "expected_start_date", "expected_end_date")


def build_model(spark, raw_dir, provenance):
    raw = [read_source(spark, Path(raw_dir) / s.filename, s.rows) for s in SOURCES]
    hospitals = hospital_dimension(raw[0])
    measures = spark.createDataFrame(MEASURES, MEASURE_SCHEMA)
    facts = normalize_fact(harmonize(raw[1], raw[2]), measures)
    require_empty(facts.join(hospitals.select("source_release", "facility_id"),
                            ["source_release", "facility_id"], "left_anti"), F.lit(True), "Orphan hospital measure")
    provenance_schema = "source_dataset_id string, source_sha256 string, verified_at_utc string, downloaded_at_utc string"
    prov = spark.createDataFrame([(r["dataset_id"], r["sha256"], r["verified_at_utc"], r["downloaded_at_utc"]) for r in provenance], provenance_schema)
    facts = facts.join(prov, "source_dataset_id", "inner")
    hospitals = hospitals.withColumn("source_dataset_id", F.lit(SOURCES[0].dataset_id)).join(prov, "source_dataset_id", "inner")
    return {"dim_hospital": hospitals, "dim_measure": measures, "fact_hospital_measure": facts}

