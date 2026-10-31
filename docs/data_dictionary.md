# Source and metric dictionary

Status: inspected Phase 1 contract; no ingestion or transformation implementation. Inspection/download date: **2026-10-31, America/Costa_Rica**. See [scope.md](scope.md) for the cohort, peer rules and review checkpoint.

## 1. Source version register

All three analytical datasets reported `modified=2026-07-22` and `released=2026-08-13`. Source API schemas describe every field as text. CSV headers use display names and are mapped explicitly below; dates and numbers must not be inferred automatically.

The following are the **actual complete CSV downloads**, inspected in memory without saving raw files in the workspace. Hashes cover the original response-body bytes before decoding; row counts exclude headers. A second read returned the same hashes and row counts. Phase 2 must persist and verify these bytes before processing.

| Dataset ID | Rows | Columns | Bytes | SHA-256 |
|---|---:|---:|---:|---|
| `xubh-q36u` | 5,419 | 38 | 1,450,767 | `f874f09fef895a1ccf5bb7392dcbb2be05c9860339261b093fe00f0c1b013480` |
| `yv7e-xc69` | 138,084 | 16 | 34,150,899 | `1e5a1ca803c2b09468fe3ae3fe60fef3e910f5f5300630a24791c88a1abff516` |
| `dgck-syfz` | 325,720 | 22 | 105,461,119 | `b70e598f29552df302e30ed649d178abd1b3d3c868ae97cf8e55453dd33898fc` |

Exact resources:

- Hospital General Information: [dataset](https://data.cms.gov/provider-data/dataset/xubh-q36u), [CSV](https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1785189955/Hospital_General_Information.csv). HTTP Last-Modified: `Mon, 27 Jul 2026 22:11:00 GMT`. Datastore resource ID: `90fa4cdf-f49d-556d-8790-d32fbbec40c6`.
- Timely and Effective Care - Hospital: [dataset](https://data.cms.gov/provider-data/dataset/yv7e-xc69), [CSV](https://data.cms.gov/provider-data/sites/default/files/resources/0437b5494ac61507ad90f2af6b8085a7_1785189967/Timely_and_Effective_Care-Hospital.csv). HTTP Last-Modified: `Mon, 27 Jul 2026 22:11:10 GMT`. Datastore resource ID: `c99ae75e-0a7d-5db4-99ed-3ba2b7324baf`.
- Patient survey (HCAHPS) - Hospital: [dataset](https://data.cms.gov/provider-data/dataset/dgck-syfz), [CSV](https://data.cms.gov/provider-data/sites/default/files/resources/78a50346fbe828ea0ce2837847af6a7c_1785189950/HCAHPS-Hospital.csv). HTTP Last-Modified: `Mon, 27 Jul 2026 22:10:53 GMT`. Datastore resource ID: `b42ae2a7-5512-5cb4-b429-d3eaaab212d7`.

No ETag was returned for these downloads. HTTP modification time, catalog modification date, release date and measurement dates have different meanings. Resource paths and hashes identify this inspected version; permanent availability of the paths is not guaranteed.

Official reference material:

- [CMS Hospital Data Dictionary, July 2026](https://data.cms.gov/provider-data/sites/default/files/data_dictionaries/hospital/HOSPITAL_Data_Dictionary.pdf): 100 pages; hospital ID and source field types, HCAHPS table pp. 32-33, Timely and Effective Care pp. 77-78, measure descriptions p. 93. PDF names use hyphens (`OP-18b`, `OP-22`); actual CSV IDs use underscores. Select the actual CSV IDs.
- [CMS Footnote Crosswalk](https://data.cms.gov/provider-data/dataset/y9us-9xdf), [exact CSV](https://data.cms.gov/provider-data/sites/default/files/resources/f29bb7c812e242f6edfef0a4b7d0eaca_1760630713/Footnote_Crosswalk.csv): reference lookup only, modified 2025-09-18, released 2026-08-13; downloaded 3,456 bytes, SHA-256 `5214e1468fb04c5cdeac8920f2c446cccaa65e2f6f929424cd228042a52d963e`.
- [CMS HCAHPS explanation](https://data.cms.gov/provider-data/topics/hospitals/hcahps), [about hospital data and footnotes](https://data.cms.gov/provider-data/topics/hospitals/about-data). Publicly indexed official text was consulted; direct topic-page extraction requires JavaScript.

These references do not expand the scope beyond three analytical datasets.

## 2. Keys, grain and common fields

Raw values are strings. Proposed normalized names describe the future model; they do not indicate implemented columns.

| CSV header | API field / normalized name | Proposed type | Meaning and handling |
|---|---|---|---|
| `Facility ID` | `facility_id` | string | CMS facility identifier, e.g. `010001`; preserve all six characters and leading zeros. Never cast to integer or repair by assuming a lost zero. Reject/inspect blank or malformed IDs; do not join by name/address. |
| `Facility Name` | `facility_name` | string | Display label; hospital source is authoritative for this snapshot. Preserve measure-file name discrepancies for audit. |
| `State` | `state` | string | Two-character code. Minimum geography is 50 states plus DC; exclude territories explicitly. |
| `Hospital Type` | `hospital_type` | string | Hospital-source category; primary cohort is exactly `Acute Care Hospitals`. |
| `Hospital Ownership` | `hospital_ownership` | string | Hospital-source descriptive category; not a causal control. |
| `Emergency Services` | `emergency_services` | string | Hospital-source Yes/No flag; primary cohort requires `Yes`. |
| `Start Date` | `start_date` | date + raw string | Measurement start, parse strictly as `MM/dd/yyyy`, normalize to ISO date. Not download date. |
| `End Date` | `end_date` | date + raw string | Measurement end, inclusive; require start <= end. A partial-period footnote overrides any inference of complete coverage. |
| Not a source column | `source_dataset_id` | string | Catalog ID from the fixed source manifest. |
| Not a source column | `source_release` | date | Catalog `released`, 2026-08-13 in this design; use with dataset and hash for provenance. |
| Not a source column | `download_date`, `source_sha256` | date, string | Actual future persisted download date and validated content hash; do not copy the Phase 1 date onto a later download. |

Hospital grain: one facility per source snapshot; observed 5,419 unique IDs. Fact grain: one facility/measure/start/end/source snapshot. All selected measure composite keys were unique. Hospital-to-fact is one-to-many; fact-to-hospital must be many-to-one. Never combine state/national result tables with these hospital rows. No state or national analytical datasets are included.

Address, ZIP, county and telephone columns exist but are unnecessary for the minimum analysis. Overall hospital ratings and measure-group counts exist but are excluded from the KPI model. If ZIP is ever retained, keep it as text as well.

## 3. Timely and Effective Care fields

| CSV header | API field / proposed name | Proposed representation | Meaning |
|---|---|---|---|
| `Condition` | `_condition` / `condition` | string | API name differs from the CSV header; selected rows are Emergency Department. |
| `Measure ID` | `measure_id` | string | Select exactly `OP_18b` and `OP_22`; preserve case. |
| `Measure Name` | `measure_name` | string | Source wording retained for audit and definition validation. |
| `Score` | `score` / `score_raw`, `score_value` | string + nullable decimal | Published value; unit comes from the measure dictionary, not the column name. The full file also contains categorical scores (e.g. EDV `very high`), so generic numeric casting of all rows is invalid. |
| `Sample` | `sample` / `sample_raw`, `reported_sample_count` | string + nullable nonnegative integer | Published measure-related case/sample count. Keep the generic source meaning; no assumption that it is total ED volume or a common denominator across measures. |
| `Footnote` | `footnote` / `footnote_raw`, `footnote_codes` | string + list of strings | May contain multiple comma-separated codes. Parse after CSV decoding; never split the file itself on commas. |

### OP_18b: emergency department length of visit

- Measure and unit verified in the downloaded CSV: hospital median **minutes**, lower favorable. Population: discharged ED patients, excluding transfer and psychiatric/mental-health cases. The CMS phrase "Average (median)" means median here.
- Period observed for all 4,658 rows: **2024-10-01 through 2025-09-30**.
- 4,081 numeric scores; 577 `Not Available`; observed range 42-413. All-source footnote values: blank, `1`, `1, 3`, `3`, `3, 7`, `5`, `12`, `19`.
- Example actually observed: facility `010001`, score `212`, sample `396`, blank footnote. It is a source example, not an operational finding.
- Proposed valid numeric domain: >=0 minutes. Preserve a legitimate zero if ever supplied; do not infer zero from missingness. Blank notes are required for primary comparison; code `3` means the apparent annual dates do not establish a full measurement interval.
- Do not interpret as door-to-provider time, include admitted patients indiscriminately, or calculate a pooled patient median from hospital medians.

### OP_22: left before being seen

- Published **percentage**, 0-100 scale, lower favorable. CMS dictionary identifies patients leaving ED before being seen; source CSV label is `Left before being seen`.
- Period observed for all 4,658 rows: **2024-01-01 through 2024-12-31**. This differs from OP_18b within the same CSV.
- 3,821 numeric scores; 837 `Not Available`; observed range 0-23. All-source footnote values: blank, `1`, `2`, `2, 7`, `5`, `12`, `19`.
- Example actually observed: facility `010001`, score `3`, sample `62163`, blank footnote. `3` means 3%, not a count and not 0.03 in the source representation. A Power BI percent format must either divide by 100 explicitly or retain 0-100 with a percent suffix, consistently.
- Zero is an observed valid percentage. Code `2` identifies a sample-based submission and can be retained with a flag; code `2, 7` fails eligibility because of `7`.
- The design consumes the published score. Exact patient inclusion and denominator reconstruction would require the applicable OQR specification; this project does not derive event counts from rounded percentages or combine hospital percentages into a patient-level rate.

## 4. HCAHPS fields and selected measure

| CSV header | API field / proposed name | Proposed representation | Meaning |
|---|---|---|---|
| `HCAHPS Measure ID` | `hcahps_measure_id` / `measure_id` | string | Filter `H_COMP_1_A_P` before harmonizing with the other fact source. |
| `HCAHPS Question` | `hcahps_question` | string | Wording for the reported measure. |
| `HCAHPS Answer Description` | `hcahps_answer_description` | string | Selected category: nurses always communicated well. |
| `HCAHPS Answer Percent` | `hcahps_answer_percent` / `score_raw`, `score_value` | string + nullable decimal | Published 0-100 percentage. Do not substitute star rating or linear mean. |
| `HCAHPS Answer Percent Footnote` | `hcahps_answer_percent_footnote` | raw string + code list | Primary quality/precision notes for this score. |
| `Number of Completed Surveys` | `number_of_completed_surveys` | raw string + nullable integer | Hospital survey total for the period; not necessarily the number answering this specific item/composite. |
| `Number of Completed Surveys Footnote` | `number_of_completed_surveys_footnote` | raw string + code list | Preserve separately even if identical to score notes in this snapshot. |
| `Survey Response Rate Percent` | `survey_response_rate_percent` | raw string + nullable decimal | Published hospital response rate on 0-100 scale; retain for nonresponse context, not a fourth KPI. |
| `Survey Response Rate Percent Footnote` | `survey_response_rate_percent_footnote` | raw string + code list | Preserve response-rate qualifications. |
| `Patient Survey Star Rating`, its footnote | `patient_survey_star_rating`, `patient_survey_star_rating_footnote` | raw strings if retained | Not used for this KPI. Example selected rows contain `Not Applicable`. |
| `HCAHPS Linear Mean Value` | `hcahps_linear_mean_value` | raw string if retained | Different representation; excluded from the selected score. Example selected rows contain `Not Applicable`. |

### H_COMP_1_A_P: nurses always communicated well

- Verified answer: patients reporting that nurses **always** communicated well during a recent inpatient stay; **percent**, higher favorable. Use the CMS-published score as provided, without inventing a raw respondent numerator or attempting new case-mix adjustments.
- Period observed for all 4,790 rows: **2024-10-01 through 2025-09-30**.
- 3,949 numeric scores; 841 `Not Available`; observed range 52-100. Non-numeric completed-survey totals for these rows were `Not Available` (841).
- Observed answer-percent note values: blank, `1`, `3`, `3, 10`, `5`, `5, 24`, `6`, `6, 11`, `6, 29`, `10`, `10, 11`, `11`, `19`. Star-rating notes were blank across the selected rows.
- Example actually observed: facility `010001`, answer `76`, completed surveys `1392`, response rate `17`, blank score/sample/response notes. This is 76%, not 76 points on a star scale.
- Primary peer eligibility requires a numeric score, numeric survey total >=100 and blank score, survey-total and response-rate notes. CMS can publish scores below 100 surveys; the project retains these values as limited-data records while excluding them from the primary benchmark. This project is not calculating CMS star ratings.
- The inpatient population cannot be assumed to be the same patients as the ED indicators, even when their date intervals match. Nonresponse, differences in case mix and survey administration remain limitations.

## 5. Missingness, notes and status rules

Preserve source strings before parsing. Trim only for interpretation; do not replace `Not Available`, `Not Applicable`, blanks, malformed numeric values, suppressed results or insufficient sample sizes with zero. A numeric score with a cautionary note remains stored numerically, but its comparison eligibility may be false.

Proposed fields: `value_status` (numeric, not_available, not_applicable, blank or parse_error), `comparison_eligible` and an explicit `exclusion_reason`. Keep sample/response statuses separately: a missing sample is not a zero sample. Do not discard a hospital row merely because a KPI is unavailable.

Relevant current crosswalk meanings, paraphrased:

| Code | Meaning | Minimum handling |
|---|---|---|
| `1` | Too few cases/patients to report | Retain status; exclude primary comparison |
| `2` | Submitted from a sample of cases/patients | Allow for OP_22 with visible sample flag |
| `3` | Shorter measurement period than required | Exclude primary comparison despite row dates |
| `4` | CMS suppressed one or more quarters | Exclude primary comparison |
| `5` | Results unavailable for this period | Missing/unavailable; exclude |
| `6` | Fewer than 100 completed CAHPS surveys | Retain numeric value if published; exclude primary benchmark |
| `7` | No cases met measure criteria | Retain status; exclude |
| `10` | Very few eligible CAHPS patients, fewer than 50 completed surveys | Retain limited-data value; exclude |
| `11` | Data collection discrepancies | Exclude primary benchmark |
| `12` | Measure not applicable to this hospital/period | Not applicable; exclude |
| `13` | Result cannot be calculated | Retain status; exclude |
| `19` | Public data restricted to IQR/OQR participants | Retain availability qualification; exclude primary benchmark |
| `24` | VHA results combined with administrative parent | Do not infer independent hospital results; outside cohort |
| `28` | Approved extraordinary-circumstances exception may affect results | Exclude primary benchmark |
| `29` | Partial-period data under approved exception | Exclude primary benchmark |

Codes `4`, `13`, `28` are documented defensively from the current crosswalk; they were not observed in the three selected measures. An unknown code or an unrecognized token must trigger review. A multi-code value fails eligibility if any code is disqualifying. The 2026 snapshot contains numeric cautioned results; dropping all notes and retaining only numbers is demonstrably unsafe.

## 6. Read-only inspection method and reproducibility

No dependencies were installed. Inspection used Python standard-library `urllib.request`, `csv`, `io`, `json`, `hashlib`, `collections` and `concurrent.futures` in temporary shell invocations; no script, notebook, table, SQL file or export was created. CSV decoding used `utf-8-sig` and the CSV parser, preserving IDs as strings.

Actual API requests executed for each dataset ID:

```text
GET https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{id}
GET https://data.cms.gov/provider-data/api/1/datastore/query/{id}/0?limit=2
GET https://data.cms.gov/provider-data/data.json
GET each exact CSV URL listed in section 1
GET the exact Footnote_Crosswalk.csv URL listed in section 1
```

The following is the actual CSV audit invocation executed in PowerShell for the policy-count check. It is included as inspection evidence, not a pipeline implementation. It makes read-only HTTP requests and prints counts; no files are written. It requires memory for the full CSV. Rerunning is a future explicit verification step; Phase 1 has already stopped at review.

```powershell
@'
import urllib.request, csv, io, hashlib, collections, json
base='https://data.cms.gov/provider-data/sites/default/files/resources/'
files={
'xubh-q36u':'893c372430d9d71a1c52737d01239d47_1785189955/Hospital_General_Information.csv',
'yv7e-xc69':'0437b5494ac61507ad90f2af6b8085a7_1785189967/Timely_and_Effective_Care-Hospital.csv',
'dgck-syfz':'78a50346fbe828ea0ce2837847af6a7c_1785189950/HCAHPS-Hospital.csv'}
selected={}
for source,path in files.items():
 b=urllib.request.urlopen(base+path,timeout=60).read()
 rows=list(csv.DictReader(io.TextIOWrapper(io.BytesIO(b),encoding='utf-8-sig',newline='')))
 selected[source]=[r for r in rows if source=='xubh-q36u' or r.get('Measure ID',r.get('HCAHPS Measure ID')) in ('OP_18b','OP_22','H_COMP_1_A_P')]
 print(source,len(b),hashlib.sha256(b).hexdigest(),len(rows))
 del rows,b
states=set('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC'.split())
h={r['Facility ID']:r for r in selected['xubh-q36u'] if r['Hospital Type']=='Acute Care Hospitals' and r['Emergency Services']=='Yes' and r['State'] in states}
valid={}
for measure,source,field,foot in [('OP_18b','yv7e-xc69','Score','Footnote'),('OP_22','yv7e-xc69','Score','Footnote'),('H_COMP_1_A_P','dgck-syfz','HCAHPS Answer Percent','HCAHPS Answer Percent Footnote')]:
 rr=[r for r in selected[source] if r.get('Measure ID',r.get('HCAHPS Measure ID'))==measure and r['Facility ID'] in h]
 numeric=[r for r in rr if r[field].replace('.','',1).isdigit()]
 eligible=[r for r in numeric if r[foot].strip() in ('','2') and (measure!='H_COMP_1_A_P' or (r['Number of Completed Surveys'].isdigit() and int(r['Number of Completed Surveys'])>=100 and r['Number of Completed Surveys Footnote'].strip()==''))]
 valid[measure]={r['Facility ID'] for r in eligible}
 counts=collections.Counter(h[r['Facility ID']]['State'] for r in eligible)
 print(json.dumps({'measure':measure,'cohort':len(rr),'numeric':len(numeric),'eligible':len(eligible),'eligible_coverage_pct':round(100*len(eligible)/len(h),2),'numeric_excluded_by_notes_or_n':len(numeric)-len(eligible),'eligible_with_at_least_10_other_state_peers':sum(n for n in counts.values() if n>=11),'states_without_10_other_peers':{s:n for s,n in sorted(counts.items()) if n<11},'cohort_numeric_note_counts':dict(collections.Counter(r[foot] for r in numeric))}))
print('same_period_complete_pairs',len(valid['OP_18b']&valid['H_COMP_1_A_P']))
print('all_three_eligible',len(set.intersection(*valid.values())))
'@ | python -
```

This inspection snippet accepts blank or `2` in its common note predicate. There are **no numeric cohort OP_18b or HCAHPS rows with code `2`** in this snapshot, so the documented measure-specific stricter policy yields identical counts. HCAHPS score, survey-total and response-rate note values were also checked to be identical for these selected rows; the production contract nevertheless checks them independently. The snippet's numeric detector is sufficient for the observed nonnegative decimal strings, not the future production parsing contract. It does not validate every unrelated measure or implement a durable ingestion process.

Phase 2 must turn the proposed contracts into actual checks and retain executed evidence, reject reasons and immutable raw source files outside Git. Databricks processing, SQL models, statistical tests, exports and Power BI execution have not been performed.
