# Phase 2 executed quality checks

Work date: **2026-10-31, America/Costa_Rica**. Phase 1 was approved by the user, with Phase 2 explicitly authorized. This document reports actual local execution; it does not claim execution in Databricks or completion of Phase 3.

**Portfolio update:** the user later authorized a static descriptive report using existing exports, and postponed Databricks and Power BI. See [the report validation](report_validation.md) for that separate work. The Phase 2 execution results below remain historical evidence; the pipeline and original Spark suite were not rerun for the portfolio report.

## Evidence and runtime

- [Actual first-run quality report](evidence/run_summary.json): source/code/output hashes, row counts, overall and state coverage, exclusions and the independent peer-reference verification.
- [Repeat-run verification](evidence/repeat_run_verification.json): exact business-field equality across all five tables in two complete runs.
- [Source-to-model verification](evidence/source_model_verification.json): independent CSV/Decimal/date/note checks for all 14,106 selected source observations.
- [Final unit-suite result](evidence/tests_summary.json): 27 tests, exit code 0, all successful, with test-source hashes and the actual log checksum.
- Python 3.11.16; PySpark 4.0.1; Py4J 0.10.9.9; Microsoft OpenJDK 17.0.21; local Spark `local[2]` on Windows. Only PySpark and its JVM bridge were installed as Python project dependencies. Test assertions use standard-library unittest and Fraction.

The initial Python 3.12.10 attempt failed because workers exited unexpectedly, reproducible even with a one-row DataFrame. Apache's [SPARK-53759](https://issues.apache.org/jira/si/jira.issueviews%3Aissue-html/SPARK-53759/SPARK-53759.html) documents this Windows/Python 3.12+ issue in Spark 4.0.1. The final validation uses an isolated Python 3.11 environment. No system-wide Python or Java configuration was changed.

Java was downloaded from Microsoft's official OpenJDK distribution as a portable ZIP outside the project. Its SHA-256 was checked against Microsoft's published checksum: `49154292866386b2f4f09a3ecf3be07ab80a419149c84ec1d4419b9eec9e4b64`. Missing native Hadoop/`winutils.exe` warnings did not prevent the verified CSV-read/driver-export path. Spark's Python socket ResourceWarnings appeared during the unittest run; they did not change assertions or analytical results.

## Raw-source integrity

All originals are retained outside the portfolio directory at:

```text
C:/Users/ramse/.local/share/healthcare-operations-analytics/raw/2026-08-13/
```

The three downloaded SHA-256 hashes and byte lengths match the approved Phase 1 versions exactly. No alternate release was substituted. All sources are verified before Spark reads them and again after the run. The full files contain 5,419 / 138,084 / 325,720 rows and 38 / 16 / 22 columns respectively.

Original bootstrap downloads were made on client work date 2026-10-31; their precise original UTC timestamps were not recorded. The adjacent download receipts say so explicitly. Verification times are independently recorded in the quality report. Future downloads through the CLI write an exact completion timestamp; no guessed timestamp has been substituted for this run.

The source registry embeds the approved hashes. A mismatch fails before any Spark model or output directory is created. External-path validation prevents placing raw inputs or run outputs under this project or another Git worktree. No original CSV is tracked in the project.

## Model, selection and joins

| Output table | Actual rows | Grain |
|---|---:|---|
| `dim_hospital` | 5,419 | Source release / facility |
| `dim_measure` | 3 | Selected measure |
| `fact_hospital_measure` | 14,106 | Release / dataset / facility / measure / start / end |
| `hospital_metrics` | 8,301 | Selected measure rows in the approved population |
| `peer_benchmarks` | 8,301 | Same grain, with per-target peer references |

The population contains **2,767** acute care hospitals with emergency services in the 50 states plus DC. The fact table retains **5,805** selected metric records outside this cohort. The other **128,768** Timely and Effective Care rows and **320,930** HCAHPS rows contain unselected measures; they are intentionally not modeled. No selected hospital/measure record is dropped merely because its score is missing or its comparison eligibility is false.

Executed validations found zero duplicate hospital keys, duplicate selected fact keys, orphan selected hospitals, cohort state disagreements, or source hospital-name mismatches. Many-to-one hospital joins preserved expected cardinality; peer SQL and CSV serialization preserved all 8,301 cohort rows. No malformed selected numeric token, invalid date, unexpected period, out-of-range selected value or unknown footnote passed the gates.

A separate standard-library scan of the original CSVs also checked all 14,106 selected observations against the Spark fact export: raw/text facility IDs, original scores and sample fields, Decimal numeric scores, integer counts, note arrays, exact dates and independently applied eligibility rules all agreed. This check did not add a fourth analytical source.

The type/quality contracts stop the run on invalid data; legitimate missingness and known cautionary notes are retained as values/statuses/reasons. Row-count checks apply to all source rows; measure-specific type/range/notes checks apply to the three selected indicators, not unrelated measures in the large source files.

## Eligibility and peer availability reconciled with Phase 1

| Measure | Numeric scores | Eligible targets | Eligible coverage / 2,767 | Comparable targets with >=10 other peers | Numeric values excluded by notes/sample rules |
|---|---:|---:|---:|---:|---:|
| `OP_18b` | 2,662 | 2,632 | 95.12% | 2,567 | 30 |
| `OP_22` | 2,588 | 2,588 | 93.53% | 2,522 | 0 |
| `H_COMP_1_A_P` | 2,677 | 2,496 | 90.21% | 2,430 | 181 |

All counts match the approved inspection. Each indicator has 2,767 cohort rows, including unavailable scores. There are 105 / 179 / 90 unavailable cohort scores respectively. In total there are **585 ineligible** cohort records and **197 eligible records with insufficient peers**. Those 782 records receive null benchmarks, gaps and signals; they are not false negatives or zeros.

The quality report preserves state-specific coverage (153 state/measure combinations). AK, DC, DE, HI, MT, ND, RI, VT and WY have insufficient same-state peer groups under the approved rule for these measures. There is no national fallback.

Reason counts can overlap: a missing score can have a source footnote, and HCAHPS may have the same caution on score, survey total and response rate. The report lists every applicable reason; summing reason counts is not a rejected-record denominator.

## Exact leave-one-out references

`sql/peer_benchmarks.sql` uses native [Spark SQL `percentile_cont`](https://spark.apache.org/docs/4.0.1/sql-ref-functions-builtin.html), with no approximate percentile function. For sorted values, the continuous percentile interpolates at zero-based position `(n-1)*p`.

The target is excluded by facility identity **before** percentile aggregation, and only eligible same-state/type/measure/source/period peers enter the distribution. Other hospitals with the same score are retained. A window count records the eligible group size. Percentiles are exposed only when the target is eligible and has at least ten other peers.

The separate `reference.py` verifier uses Python Fraction interpolation over independently selected peer lists. It checked every one of the **8,301** SQL result rows, including:

- identity-based peer counts and qualification status;
- all three continuous percentile values for **7,519 comparable rows**, totaling **22,557** percentile checks;
- strict unfavorable-signal thresholds and target-minus-peer-median gaps;
- null references, gaps and signals for every unqualified target.

All checks passed. Float comparison tolerance is `1e-9` to account for the SQL function's double representation; this is not an approximate-quantile accuracy setting.

As a SQL-output validation count, the pipeline produced 659 OP_18b, 493 OP_22 and 541 HCAHPS unfavorable flags. These are per-measure review flags for their own periods and populations, not a combined hospital-quality result, final business interpretation or inferential finding.

## Executed unit suite

The final full suite executed **27 tests in 261.711 seconds**, returned native process exit code **0**, and reported **OK**, with no failed assertions or test errors. The earlier 24-test suite also passed; three additional source/mapping/selection checks were then included in this final full execution. The initial Python 3.12 worker failure is documented above and is not counted as a successful validation.

The suite covers checksum/size failures and early stopping; external/Git storage refusal; population rules and leading zeros; all three measure selections; missing versus zero values; multiple notes; partial periods; survey totals at 99 versus 100; independent survey/response notes; unknown source mappings and notes; invalid dates, counts, ranges and duplicate keys; self-exclusion, ties, both favorable directions, nine versus ten additional peers, isolated state/type/measure/period partitions, and randomized decimal inputs.

The independent oracle is also deliberately fed a corrupted SQL result in one test and correctly rejects it. `uv pip check` verified the two installed dependencies are compatible. The downloader's existing-file route reverified the three retained originals without overwriting them.

## Repeated run and export integrity

Two complete runs passed all processing and validation gates:

```text
20261031T100551Z_e122eb7a
20261031T100805Z_d4fac535
```

Both successful run directories are retained at `C:/Users/ramse/.local/share/healthcare-operations-analytics/runs/`. Their source and implementation hashes agree. The comparison verified both success-marker report hashes and every recorded output-file hash, then compared all five CSV tables field by field in their deterministic key order. Every business field agreed exactly. Only `verified_at_utc` and `downloaded_at_utc` were excluded from the cross-run field comparison as provenance timestamps. Their complete file hashes remain recorded separately; no claim of identical timestamp-bearing files is made.

Executed commands from the project root, with the isolated runtime configured as in README:

```powershell
& $env:PYSPARK_PYTHON -m unittest discover -s tests -v
& $env:PYSPARK_PYTHON -m healthcare_pipeline run
& $env:PYSPARK_PYTHON -m healthcare_pipeline run
```

The source-to-model and repeat checks were also actually executed in temporary Python shell invocations using only csv, json, hashlib, Decimal and datetime. The JSON evidence records their method, observed run IDs and canonical business-field hashes. Raw files and full run outputs remain external; only these small quality summaries are copied into the repository.

Each run writes new external files without overwriting a previous run. `schemas.json` preserves types; note/reason arrays are JSON cells, missing scalar values empty CSV cells, and booleans lowercase. Every file is read back to check row counts and eligibility denominators. Original-file hashes are checked again before `SUCCESS.json` is written. A failed run has `FAILED.json` and must not be consumed.

## Remaining limitations and stop point

Databricks Free Edition account execution remains unverified and is postponed by the user. The [reproduction guide](reproducibility.md) preserves local execution instructions. No account or cloud resource was configured for the static report.

The exports intentionally stay bounded to 20,000 rows per table. They are CSV model artifacts, not persistent Delta tables or a cloud ingestion service. The independent verifier is also designed for this small hospital snapshot. More scale would require a separate design decision, not silent changes to this implementation.

Hospital attributes are snapshot attributes; peer matching does not adjust for acuity, size, teaching status, rurality or staffing. OP_22 uses 2024, while OP_18b and inpatient HCAHPS use October 2024-September 2025. Hospital medians and percentages are not patient-level pooled estimates. These limitations carry forward unchanged.

Phase 2 stops with the validated analytical model and its evidence. No dashboard, final statistical analysis, ML model, Snowflake/dbt integration, or Phase 3 work has been undertaken.
