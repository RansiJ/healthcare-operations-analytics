# Healthcare Operations & Performance Analytics: scope

Status: Phase 1 complete; proposed design awaiting user review. No authorization to start Phase 2 is inferred from this document.

Inspection and download date: **2026-10-31, America/Costa_Rica**. Source release dates and measurement periods are separate from this date.

## 1. Authorization and environment

The user's request authorizes only discovery, source inspection and minimum scope design. The supplied `Codex_Brief_Healthcare_Analytics.md` is project reference material; its descriptions of later phases are future requirements, not authorization to execute them. Only these two design documents have been created.

The working directory is `C:/Users/ramse/OneDrive/Documentos/proyectos/github-portfolio`. It is a workspace containing independent projects, not itself a Git repository. No applicable `AGENTS.md` was found in the workspace or its ancestors. No healthcare project or healthcare source files were found in the initial file inventory.

The root README and `service-operations-analytics-pipeline/README.md` were read. The existing NYC 311 project already demonstrates Python, DuckDB, SQL, reproducible extraction and a published aggregate dashboard. This project will instead emphasize substantive PySpark transformations, Spark SQL, hospital measure comparability and a report actually created in Power BI Desktop. Existing projects remain untouched.

## 2. Business question and intended decision

**Which acute care hospitals with emergency services show an unfavorable operational or inpatient experience signal relative to other hospitals of the same type in the same state, for the same measure and measurement period?**

Audience: an operations analyst preparing a shortlist for hospital management review. The output supports investigation of workflow, capacity and communication; it does not diagnose causes, assess clinical quality, recommend patient treatment or rank hospitals overall.

One cross-sectional release, three analytical sources, three KPI. No trend analysis, patient-level records, composite score, predictive model or external enrichment.

## 3. Job alignment checked

The original [Vereda Labs Data Analyst - Intermediate / Senior posting](https://jobs.ashbyhq.com/veredalabs/b331cf48-636e-4270-8145-3b8aa15e8462) was found and reviewed through its publicly indexed content on the inspection date. Direct page extraction returned a JavaScript shell. The posting describes recruiting for clients in Costa Rica and Mexico; it is not necessarily an internal Vereda role. Its continued acceptance of applications was not tested.

The relevant requirements are multi-source preparation, data quality, SQL and BI reporting, analytical/statistical work and communication. Python and Databricks are preferred; healthcare operations is a plus. Planned evidence: three-source joins and cleaning in PySpark, readable Spark SQL with CTE and window functions for peer comparisons, a real Power BI report, and a short executive interpretation in English. These are portfolio demonstrations, not claims of prior professional healthcare experience.

## 4. Sources actually inspected

CMS dataset pages returned JavaScript shells. Official metastore and datastore APIs were accessible. Two API rows and schema were inspected per source; subsequently **all three complete CSV bodies were downloaded into memory and scanned**. No CSV was saved in this repository or retained as a raw snapshot. Bytes and SHA-256 hashes are recorded in [data_dictionary.md](data_dictionary.md).

Metadata from both the metastore and the [CMS catalog](https://data.cms.gov/provider-data/data.json) agreed on `modified=2026-07-22` and `released=2026-08-13` for all three sources. These are the versions actually served at inspection; an October release is not assumed. `issued` denotes initial catalog publication, not this snapshot's version.

| Source | Official page | Complete CSV rows | Columns | Role |
|---|---|---:|---:|---|
| Hospital General Information | [xubh-q36u](https://data.cms.gov/provider-data/dataset/xubh-q36u) | 5,419 | 38 | Hospital attributes and cohort |
| Timely and Effective Care - Hospital | [yv7e-xc69](https://data.cms.gov/provider-data/dataset/yv7e-xc69) | 138,084 | 16 | Two emergency department indicators |
| Patient survey (HCAHPS) - Hospital | [dgck-syfz](https://data.cms.gov/provider-data/dataset/dgck-syfz) | 325,720 | 22 | One inpatient experience indicator |

The CMS Hospital Data Dictionary **July 2026** and current Footnote Crosswalk were also consulted as reference documentation, not additional analytical sources. The topics page and measurement-period page could not be read directly without JavaScript; actual row dates, the PDF and crosswalk resolve the design requirements.

### Inspection results, not business findings

Hospital General Information has 5,419 distinct facility IDs across 5,419 rows. Each candidate metric has one row per facility/measure/period in this snapshot, with no duplicate composite keys. All facilities in the three selected measures exist in the hospital source; zero orphan measure rows were observed. These checks do not certify uniqueness for unselected measures.

| Measure | All-source rows | Numeric scores | Missing scores | Observed numeric range | Observed period, inclusive |
|---|---:|---:|---:|---|---|
| `OP_18b` | 4,658 | 4,081 | 577 | 42-413 minutes | 2024-10-01 to 2025-09-30 |
| `OP_22` | 4,658 | 3,821 | 837 | 0-23 percent | 2024-01-01 to 2024-12-31 |
| `H_COMP_1_A_P` | 4,790 | 3,949 | 841 | 52-100 percent | 2024-10-01 to 2025-09-30 |

Every missing score in these three selected measures was the literal `Not Available`. Numeric does not automatically mean eligible for comparison: partial-period and survey-quality notes matter. Observed ranges are audit results, not future validation limits.

## 5. Three KPI and temporal decision

1. **Emergency department length of visit (`OP_18b`)**: published hospital median minutes from arrival to departure for discharged ED patients, excluding psychiatric/mental health and transferred patients. Lower values are favorable. This is total visit duration, not time until first clinical contact.
2. **Left before being seen (`OP_22`)**: published percentage of ED patients who left before being seen. Lower values are favorable. Use the reported percentage without reconstructing a numerator from its rounded value.
3. **Nurse communication, always (`H_COMP_1_A_P`)**: published percentage reporting that nurses always communicated well during an inpatient stay. Higher values are favorable. This is not an ED satisfaction measure.

Keep all three, with **separate, visible measurement periods**. OP_22 cannot be described as contemporaneous with the other two and will not enter a same-period association analysis. A hospital-level side-by-side view may show all three only with period labels. There is no synthetic common reporting year and no combined signal requiring all three to be present.

## 6. Cohort and comparability

Proposed minimum cohort: `Hospital Type = Acute Care Hospitals`, `Emergency Services = Yes`, in the 50 U.S. states and Washington, D.C. Territories and all other hospital types are excluded. Result in the inspected snapshot: **2,767 hospitals**.

The national input is small enough for this bounded project; choosing one state is unnecessary and would reduce peer coverage. The default comparison is within state. Ownership remains a descriptive filter, not a mandatory peer partition. No beds, staffing, teaching status, rurality or patient-acuity adjustment is available in the selected design. Same-state/type peers are approximate operational comparators, not matched hospitals.

Comparison eligibility:

- Valid published numeric score, valid row dates and the exact selected measurement period.
- `OP_18b`: no measure footnote. `OP_22`: blank footnote or code `2` (sample-based submission); code `2` remains visibly flagged. All other codes are excluded from the primary peer calculation pending a documented rule.
- HCAHPS: at least 100 completed surveys and blank answer-percent, completed-survey and response-rate footnotes. The 100-survey rule is a conservative **project policy**, not CMS suppression of all scores below 100. Public numeric values excluded from comparisons remain visible as limited-data records.
- No imputation and no requirement that a hospital have all three measures. Excluded/missing rows remain available for coverage reporting.

| Measure | Cohort rows | Numeric scores | Eligible after proposed notes/sample rules | Eligible / 2,767 | Eligible hospitals with >=10 other eligible same-state peers |
|---|---:|---:|---:|---:|---:|
| `OP_18b` | 2,767 | 2,662 | 2,632 | 95.12% | 2,567 |
| `OP_22` | 2,767 | 2,588 | 2,588 | 93.53% | 2,522 |
| `H_COMP_1_A_P` | 2,767 | 2,677 | 2,496 | 90.21% | 2,430 |

The 30 additional numeric OP_18b exclusions have partial-period note `3`. For HCAHPS, 181 numeric cohort scores fail the proposed notes/sample rules. Eligible same-period OP_18b/HCAHPS pairs: 2,447; eligible all-three intersection: 2,374. Neither intersection replaces the per-measure denominator.

For every KPI, AK, DC, DE, HI, MT, ND, RI, VT and WY lack enough eligible hospitals to give each target 10 other same-state peers under this rule. Keep their values and coverage, but label the comparison `insufficient peers`. Do not silently substitute a national benchmark.

### Benchmark and review signal

For each target hospital, form peers from other eligible hospitals with the same state, hospital type, measure and exact start/end dates. Exclude the target. Require **at least 10 other hospitals**. This is a project stability rule, not a CMS standard or guarantee of statistical precision.

Use the unweighted median of peer hospital scores and continuous 25th/75th percentiles. Report peer count and the gap: target minus peer median, in minutes or percentage points. A descriptive review signal is above peer Q3 for OP_18b/OP_22 or below peer Q1 for HCAHPS, with strict inequalities. Ties alone do not trigger a signal. Label it as a relative signal, without clinical thresholds or a significance claim.

The median of hospital medians is a benchmark of hospitals, not a pooled patient median. Do not average hospital medians or weight published percentages by `Sample` to fabricate patient-level rates. Coverage, peer count and exclusion counts are supporting context, not additional business KPI.

User filters must not silently change benchmark membership. In the minimum BI design, state/type/period define the fixed benchmark; ownership and hospital selection filter the displayed results. Recomputed ownership-specific benchmarks are outside the initial scope.

## 7. Proposed model and quality contract

Design only; no tables or transformations have been implemented.

- `dim_hospital`: one row per `(source_release, facility_id)`, preserving ID as text. Attributes are from the source snapshot, not reconstructed historical attributes.
- `dim_measure`: one row per selected `measure_id`, with definition, unit, direction and source mapping.
- `fact_hospital_measure`: one row per `(source_release, source_dataset_id, facility_id, measure_id, start_date, end_date)`, retaining raw and parsed score/sample/notes and eligibility status.
- Join facts many-to-one to the hospital snapshot using `(source_release, facility_id)`. Union the selected long-form measures after explicit schema mapping. Never join entire multi-measure files on hospital ID alone. A future wide export must first assert one row per hospital for each selected metric/period and use explicit metric-specific date columns.

Phase 2 acceptance checks: fixed bytes/hashes; required columns; text IDs without lost zeros; hospital uniqueness; selected fact-key uniqueness; valid dates and exact periods; OP_18b >=0 minutes; percentage scores in [0,100]; nonnegative integral counts; response rate in [0,100]; preserved notes; exclusion counts by reason; many-to-one join cardinality; orphans; per-measure and per-state coverage; unchanged eligible-hospital denominators through export. Conflicting duplicates or unknown footnote semantics must stop publication rather than select an arbitrary row.

## 8. Later analysis and deliverables, subject to review

Phase 2 will implement substantive PySpark parsing, note handling, controlled source integration and quality checks in Databricks Free Edition. Spark SQL files will use CTE for eligible cohorts, joins for hospital/measure integration and window functions for peer counts and distributions. Full files can be downloaded outside Databricks and uploaded manually if outbound access is restricted. No execution in Databricks has occurred.

Phase 3 will export the small analytical model for one actual Power BI Desktop report: hospital detail, per-KPI peer gaps and coverage, with clearly labeled periods. The report must be created and saved in Desktop before any `.pbix` completion claim. Power BI has not been operated in this phase.

One modest statistical question is reserved for later: whether OP_18b and nurse-communication scores are associated across eligible hospitals in their shared period. Start with descriptive plots and Spearman correlation, hospital-level bootstrap uncertainty and a prespecified within-state sensitivity review; document complete-case selection, ecological bias and the lack of patient-level risk adjustment. Do not treat survey totals as item-level binomial denominators, infer that ED duration caused inpatient responses, or calculate a patient-level significance test from these aggregates. Skip inferential claims if assumptions or subgroup coverage are inadequate. No statistical results have been computed.

Phase 4 will add an English README and one-page executive summary with calculated findings, verified report screenshots and reproduction steps. No dbt, Snowflake, paid services, Docker, orchestration, ML or additional BI tool is proposed.

Minimal staged structure (only the first two files exist now):

```text
healthcare-operations-analytics/
  docs/scope.md                   # Phase 1
  docs/data_dictionary.md         # Phase 1
  README.md                      # Later: reproduction and results
  notebooks/                     # Later: audit/transform; analysis if justified
  sql/                           # Later: measure model and peer comparisons
  tests/                         # Later: meaningful data-contract checks
  dashboard/                     # Later: Power BI specification and real artifacts
  docs/quality_checks.md          # Later: executed checks and exclusions
  docs/executive_summary.md       # Later: calculated executive findings
  requirements.txt               # Later: actual dependencies
  .gitignore                     # Later: raw data, local outputs and credentials
```

## 9. Review checkpoint, risks and blockers

No source-access, candidate-measure or join-key blocker remains for this descriptive design. The period mismatch is resolved by separate-period reporting, not by pretending temporal alignment. The unresolved precision of the generic `Sample` field for patient-level reconstruction is avoided by retaining it as a reported count and never reconstructing pooled outcomes.

The **user's review is the required next checkpoint**. Accept or revise the three-KPI/separate-period design, the cohort and peer/notes policies before starting Phase 2. If a single common measurement period for all three KPI becomes mandatory, this snapshot cannot satisfy it; archive selection or dropping OP_22 would require a scope revision.

After review, Phase 2 must first persist the inspected source versions outside Git and validate the hashes below. If the resource URLs disappear or the bytes differ, stop and review a replacement version instead of silently refreshing. The in-memory audit is evidence of inspection, not a durable local source archive.

Main limitations: older measurement periods despite a 2026 release; snapshot attributes may differ from attributes during measurement; approximate peer matching; voluntary/incomplete submissions and selective missingness; survey nonresponse and low sample precision; rounded hospital aggregates; partial-period notes despite apparently identical row dates; and different clinical populations across ED and inpatient experience measures.

Stop here. Pipeline, notebooks, SQL implementation, dependencies, dashboard, DAX and business findings are not part of this phase.
