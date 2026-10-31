from datetime import date
from decimal import Decimal
import os
import random
import sys
import unittest

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")

from pyspark.sql import SparkSession, functions as F

from healthcare_pipeline.pipeline import execute_sql
from healthcare_pipeline.reference import continuous_percentile, verify_peer_rows
from healthcare_pipeline.sources import ContractError
from healthcare_pipeline.transform import (MEASURES, MEASURE_SCHEMA, hospital_dimension,
    normalize_fact, harmonize, require_unique)


RAW_FIELDS = ["facility_id_raw", "measure_facility_name_raw", "measure_state_raw",
              "start_date_raw", "end_date_raw", "measure_id", "measure_name_raw",
              "score_raw", "sample_raw", "score_note_raw", "sample_note_raw",
              "response_rate_raw", "response_note_raw", "source_dataset_id"]


def raw_row(facility="010001", measure="OP_18b", score="100", sample="100", note="", **changes):
    row = dict(zip(RAW_FIELDS, [facility, "Hospital", "AL", "10/01/2024", "09/30/2025",
        measure, "Metric", score, sample, note, "", None, "", "yv7e-xc69"]))
    if measure == "OP_22":
        row.update(start_date_raw="01/01/2024", end_date_raw="12/31/2024")
    if measure == "H_COMP_1_A_P":
        row.update(source_dataset_id="dgck-syfz", response_rate_raw="17")
    row.update(changes)
    return tuple(row[k] for k in RAW_FIELDS)


class SparkContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spark = (SparkSession.builder.master("local[2]").appName("healthcare-phase2-tests")
            .config("spark.sql.shuffle.partitions", "2").config("spark.ui.enabled", "false").getOrCreate())
        cls.spark.sparkContext.setLogLevel("ERROR")
        cls.measures = cls.spark.createDataFrame(MEASURES, MEASURE_SCHEMA)

    @classmethod
    def tearDownClass(cls):
        cls.spark.stop()

    def normalized(self, rows):
        raw = self.spark.createDataFrame(rows, ", ".join(k + " string" for k in RAW_FIELDS))
        return normalize_fact(raw, self.measures)

    def peer_input(self, values, state="AL", measure="OP_18b", eligible=True, start=date(2024, 10, 1), offset=0):
        return [(date(2026, 8, 13), "dgck-syfz" if measure == "H_COMP_1_A_P" else "yv7e-xc69",
            f"{offset+i:06d}", measure, start, date(2025, 9, 30), state,
            "Acute Care Hospitals", None if v is None else float(v), eligible,
            "higher" if measure == "H_COMP_1_A_P" else "lower",
            "percent" if measure != "OP_18b" else "minutes") for i, v in enumerate(values)]

    def peers(self, rows):
        schema = ("source_release date, source_dataset_id string, facility_id string, measure_id string, "
            "start_date date, end_date date, state string, hospital_type string, score_value double, "
            "comparison_eligible boolean, favorable_direction string, unit string")
        self.spark.createDataFrame(rows, schema).createOrReplaceTempView("hospital_metrics")
        return [r.asDict() for r in execute_sql(self.spark, "peer_benchmarks.sql").collect()]

    def test_missing_values_notes_zero_and_survey_threshold(self):
        rows = [raw_row("010001", score="0"), raw_row("010002", score="Not Available"),
            raw_row("010003", score="Not Applicable"), raw_row("010004", score=""),
            raw_row("010005", note="3"), raw_row("010006", measure="OP_22", score="0", note="2"),
            raw_row("010007", measure="OP_22", score="3", note="2, 7"),
            raw_row("010008", measure="H_COMP_1_A_P", score="76", sample="100"),
            raw_row("010009", measure="H_COMP_1_A_P", score="76", sample="99"),
            raw_row("010010", measure="H_COMP_1_A_P", score="76", response_note_raw="11"),
            raw_row("010011", measure="H_COMP_1_A_P", score="76", sample_note_raw="3"),
            raw_row("010012", measure="H_COMP_1_A_P", score="76", sample="Not Available")]
        got = {r.facility_id: r for r in self.normalized(rows).collect()}
        self.assertEqual(got["010001"].score_value, Decimal(0))
        self.assertTrue(got["010001"].comparison_eligible)
        for facility, status in [("010002", "not_available"), ("010003", "not_applicable"), ("010004", "blank")]:
            self.assertEqual(got[facility].value_status, status)
            self.assertIsNone(got[facility].score_value)
            self.assertFalse(got[facility].comparison_eligible)
        self.assertEqual(got["010005"].score_value, Decimal(100))
        self.assertFalse(got["010005"].comparison_eligible)
        self.assertTrue(got["010006"].comparison_eligible)
        self.assertTrue(got["010006"].sample_based_submission)
        self.assertEqual(got["010007"].score_note_codes, ["2", "7"])
        self.assertFalse(got["010007"].comparison_eligible)
        self.assertTrue(got["010008"].comparison_eligible)
        for facility in ["010009", "010010", "010011", "010012"]:
            self.assertFalse(got[facility].comparison_eligible)
        self.assertEqual(got["010006"].start_date, date(2024, 1, 1))

    def test_unknown_notes_stop(self):
        with self.assertRaisesRegex(ContractError, "Unknown footnote"):
            self.normalized([raw_row(note="999")])

    def test_bad_dates_stop(self):
        with self.assertRaisesRegex(ContractError, "Invalid measurement date"):
            self.normalized([raw_row(start_date_raw="02/30/2024")])

    def test_different_period_stops(self):
        with self.assertRaisesRegex(ContractError, "Unexpected measurement period"):
            self.normalized([raw_row(start_date_raw="01/01/2024")])

    def test_unknown_measure_source_mapping_stops(self):
        with self.assertRaisesRegex(ContractError, "Unexpected measure/source"):
            self.normalized([raw_row(source_dataset_id="dgck-syfz")])

    def test_bad_numeric_and_count_stop(self):
        for changes in [{"score": "NaN"}, {"score": "garbage"}, {"sample": "1.5"}, {"sample": "-1"}]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ContractError, "Malformed numeric"):
                self.normalized([raw_row(**changes)])

    def test_range_checks_stop(self):
        for row in [raw_row(score="-1"), raw_row(measure="OP_22", score="101"),
                    raw_row(measure="H_COMP_1_A_P", score="76", response_rate_raw="101")]:
            with self.subTest(row=row), self.assertRaisesRegex(ContractError, "Out-of-range"):
                self.normalized([row])

    def test_duplicate_fact_key_stops(self):
        with self.assertRaisesRegex(ContractError, "Duplicate fact key"):
            self.normalized([raw_row(), raw_row(score="101")])

    def test_facility_zero_is_not_repaired(self):
        with self.assertRaisesRegex(ContractError, "Invalid measure ID"):
            self.normalized([raw_row(facility="10001")])

    def test_population_and_duplicate_hospitals(self):
        schema = "`Facility ID` string, `Facility Name` string, State string, `Hospital Type` string, `Hospital Ownership` string, `Emergency Services` string"
        rows = [("010001", " A ", " al ", "Acute Care Hospitals", "Private", "Yes"),
                ("010002", "B", "AL", "Critical Access Hospitals", "Private", "Yes"),
                ("010003", "C", "PR", "Acute Care Hospitals", "Private", "Yes"),
                ("010004", "D", "AL", "Acute Care Hospitals", "Private", "No"),
                ("010005", "E", "DC", "Acute Care Hospitals", "Private", "Yes")]
        result = hospital_dimension(self.spark.createDataFrame(rows, schema)).collect()
        self.assertEqual({r.facility_id for r in result if r.in_cohort}, {"010001", "010005"})
        self.assertEqual(next(r for r in result if r.facility_id == "010001").facility_name_raw, " A ")
        with self.assertRaisesRegex(ContractError, "Duplicate hospital key"):
            hospital_dimension(self.spark.createDataFrame(rows + [rows[0]], schema))

    def test_exact_continuous_interpolation_differs_from_discrete(self):
        got = self.spark.sql("SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY v) AS q FROM VALUES (0), (10) t(v)").first().q
        self.assertEqual(got, 2.5)
        self.assertEqual(got, continuous_percentile([0, 10], .25))

    def test_harmonization_selects_only_approved_measures(self):
        common = ["Facility ID", "Facility Name", "State", "Start Date", "End Date"]
        t_names = common + ["Measure ID", "Measure Name", "Score", "Sample", "Footnote"]
        h_names = common + ["HCAHPS Measure ID", "HCAHPS Question", "HCAHPS Answer Percent",
            "Number of Completed Surveys", "HCAHPS Answer Percent Footnote",
            "Number of Completed Surveys Footnote", "Survey Response Rate Percent", "Survey Response Rate Percent Footnote"]
        base = ["010001", "Hospital", "AL", "10/01/2024", "09/30/2025"]
        timely = self.spark.createDataFrame([base + [m, "Label", "3", "100", ""] for m in ["OP_18b", "OP_22", "EDV"]], t_names)
        survey = self.spark.createDataFrame([base + [m, "Label", "76", "100", "", "", "17", ""] for m in ["H_COMP_1_A_P", "H_COMP_2_A_P"]], h_names)
        result = harmonize(timely, survey).collect()
        self.assertEqual({r.measure_id for r in result}, {"OP_18b", "OP_22", "H_COMP_1_A_P"})
        self.assertTrue(all(r.facility_id_raw == "010001" for r in result))

    def test_self_exclusion_10_peers_and_strict_ties(self):
        result = self.peers(self.peer_input([0] * 10 + [1000]))
        oracle = verify_peer_rows(result)
        self.assertEqual(oracle["comparable_rows_verified"], 11)
        high = next(r for r in result if r["score_value"] == 1000)
        self.assertEqual(high["peer_count"], 10)
        self.assertEqual(high["peer_median"], 0)
        self.assertTrue(high["unfavorable_signal"])
        for row in result:
            if row["score_value"] == 0:
                self.assertEqual(row["peer_count"], 10)  # retain other zero-valued hospitals
                self.assertFalse(row["unfavorable_signal"])  # strict > Q3, not >=

    def test_nine_other_peers_and_ineligible_never_signal(self):
        rows = self.peer_input(range(10)) + self.peer_input([999], eligible=False, offset=100)
        result = self.peers(rows)
        verify_peer_rows(result)
        for row in result:
            self.assertIsNone(row["unfavorable_signal"])
            self.assertIsNone(row["peer_median"])
        invalid = next(r for r in result if not r["comparison_eligible"])
        self.assertEqual(invalid["peer_count"], 0)
        self.assertEqual(invalid["comparison_status"], "ineligible")

    def test_ineligible_with_large_valid_group_never_signal(self):
        rows = self.peer_input(range(12)) + self.peer_input([10000], eligible=False, offset=100)
        result = self.peers(rows)
        verify_peer_rows(result)
        invalid = next(r for r in result if not r["comparison_eligible"])
        self.assertIsNone(invalid["unfavorable_signal"])
        self.assertIsNone(invalid["peer_q3"])

    def test_peer_partition_prevents_period_measure_state_type_leakage(self):
        rows = self.peer_input([10] * 11)
        rows += self.peer_input([9999] * 11, state="NY", offset=100)
        rows += self.peer_input([9999] * 11, start=date(2024, 1, 1), offset=200)
        rows += self.peer_input([99] * 11, measure="H_COMP_1_A_P", offset=300)
        rows += [tuple(list(r[:7]) + ["Critical Access Hospitals"] + list(r[8:])) for r in self.peer_input([9999] * 11, offset=400)]
        result = self.peers(rows)
        verify_peer_rows(result)
        target = next(r for r in result if r["facility_id"] == "000000")
        self.assertEqual(target["peer_count"], 10)
        self.assertEqual(target["peer_median"], 10)

    def test_higher_direction_and_ties(self):
        rows = self.peer_input([10] + [80] * 10, measure="H_COMP_1_A_P")
        result = self.peers(rows)
        verify_peer_rows(result)
        self.assertTrue(next(r for r in result if r["score_value"] == 10)["unfavorable_signal"])
        self.assertFalse(next(r for r in result if r["score_value"] == 80)["unfavorable_signal"])

    def test_randomized_decimal_scores_match_independent_quantiles(self):
        rng = random.Random(741)
        rows = []
        for group, n in enumerate([1, 2, 10, 11, 12, 19, 24]):
            values = [rng.randrange(0, 3000) / 10 for _ in range(n)]
            rows += self.peer_input(values, state=f"G{group}", offset=100*group)
        result = self.peers(rows)
        report = verify_peer_rows(result)
        self.assertEqual(report["rows_verified"], sum([1, 2, 10, 11, 12, 19, 24]))

    def test_oracle_detects_corrupted_sql_output(self):
        result = self.peers(self.peer_input(range(11)))
        result[0]["peer_count"] += 1
        with self.assertRaisesRegex(ContractError, "peer count mismatch"):
            verify_peer_rows(result)


class QuantileOracleTests(unittest.TestCase):
    def test_known_interpolations_and_repeated_values(self):
        self.assertIsNone(continuous_percentile([], .25))
        self.assertEqual(continuous_percentile([7], .75), 7)
        self.assertEqual(continuous_percentile([0, 10], .25), 2.5)
        self.assertEqual(continuous_percentile([0, 10], .75), 7.5)
        self.assertEqual(continuous_percentile([0, 10, 20, 30], .25), 7.5)
        self.assertEqual(continuous_percentile([0, 0, 10, 10], .5), 5)


if __name__ == "__main__":
    unittest.main()
