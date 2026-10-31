# Static report: executed analysis and validation

Work date: **2026-10-31, America/Costa_Rica**. The user authorized a static portfolio report from existing results and postponed Databricks and Power BI. The pipeline and original Spark suite were not rerun.

## Inputs verified before analysis

The most recent successful existing run was `20261031T100805Z_d4fac535`, completed `2026-10-31T10:09:37.591238+00:00`. The original run remains external to Git and was read only.

The report builder verified:

1. A consistent run ID and passed status, with no FAILED marker.
2. The quality-report SHA-256 referenced by SUCCESS.json: `d2bac8c5b85b90d5af41a9900892d3dab6c92244e726c728546f9059623fd782`.
3. The three approved source hashes in that report.
4. All five analytical CSV hashes before reading any CSV observations.
5. Each export's row count and the three measures' eligibility, comparability and flag counts against the quality report.
6. Exact measurement periods and null signals for unqualified targets.

The complete input-to-artifact manifest is [report_source_verification.json](evidence/report_source_verification.json). It records the actual run, five input hashes, builder hash, runtime and generated artifact hashes. The original files' hashes still agreed after report preparation.

## Analyses actually executed

The full exports were available. Standard-library CSV/statistics processing calculated:

- Hospital-level score distributions among eligible hospitals, including inclusive/type-7 quartiles, medians, range and published-zero counts.
- Coverage categories, with 2,767 hospitals as each measure's denominator.
- Existing leave-one-out peer-gap distributions among comparable hospitals.
- Per-measure review-flag counts and shares, using comparable hospitals as the denominator.
- One illustrative hospital: the lowest facility ID comparable on all three measures, selected independently of scores and flags.
- A five-hospital OP_18b review shortlist, copied from the existing flagged comparisons and ordered by the largest stored difference from each hospital's own peer median.

The resulting medians are **170 minutes**, **2%** and **78%**; hospital IQRs are **140-204 minutes**, **1-3%** and **75-81%** respectively. These summarize hospitals equally. They are not pooled patient estimates or a common-period composite.

Facility `010001`, Southeast Health Medical Center (AL), is the deterministic example. Its three score/peer-median pairs are 212/153 minutes, 3/2 percent and 76/78 percent, with 70, 67 and 50 other peers respectively. Its OP_18b score crosses peer Q3; OP_22 equals Q3 and does not cross it; HCAHPS does not cross peer Q1. No overall hospital-quality judgment is derived.

All computed values are retained in [analysis_summary.json](evidence/analysis_summary.json). Four actual matplotlib figures show coverage, scores, peer gaps and the hospital illustration. The HTML embeds these images, so downloading a single file is sufficient for offline viewing.

No regression, correlation coefficient, hypothesis test, confidence interval, causal effect, current-capacity estimate or clinical-quality index was calculated. Business actions are prudent requests for local evidence, not claims that a particular intervention will improve an outcome.

### Shortlist selection

The final review added one table using **OP_18b only**, for **2024-10-01 to 2025-09-30**. Its pool is the 659 existing eligible, comparable OP_18b flags in the verified export. Every candidate has at least ten other eligible same-state peers and exceeds its own peer Q3 under the unchanged pipeline rule.

Select the five largest positive values of the existing `gap_to_peer_median` field, with facility ID ascending as the tie-breaker. Copy the hospital name/state, score, peer median, gap and peer count directly from the export. No new benchmark, eligibility rule or combined score is calculated. The table shows large gaps worth checking in current local operations; it is not a clinical-quality ranking or a causal explanation. Size, case mix and staffing remain unadjusted.

The five selected facility IDs are `050327`, `450289`, `450213`, `190005` and `140119`. Their full source values, dates, selection rule and pool count are preserved under `review_candidates` in [analysis_summary.json](evidence/analysis_summary.json).

## Report-specific checks executed

- **11 unittest checks passed**, native exit code 0. The original eight report tests cover quartiles/zeros, no observations, the success/hash chain, latest-run selection, corrupted CSV/report rejection, missing-export fallback and source scope. Three shortlist tests check the five-row limit and stable tie-breaker, qualified OP_18b flags only, and verbatim source values. Summary-only mode omits both hospital examples and shortlist values. See [actual test output](evidence/report_tests.json).
- **9 descriptive quartile values** were cross-checked independently with the existing Fraction-based interpolation implementation, separate from statistics.quantiles.
- A second report-only build in a temporary external directory produced **identical hashes for all generated HTML, executive-summary, statistics and PNG artifacts**, using the same date and pinned environment. This was not a second pipeline execution.
- A summary-only build was actually exercised in a temporary directory: it generated only coverage from the passed historical evidence, with no score distributions or hospital example.
- `uv pip check` passed for the 12 pinned report-environment packages.
- All original pipeline module, SQL and original test hashes still matched their Phase 2 evidence. Those source files were not modified.

The compact QA record is [report_validation.json](evidence/report_validation.json). Temporary QA outputs were outside Git; no original source or run output was overwritten.

## Visual and HTML review

The four matplotlib PNGs were visually inspected; overlapping long axis labels were shortened, and the hospital plot legend distinguishes flagged and unflagged points. Units, measurement periods and sample sizes are visible.

The HTML was rendered in headless Chrome at a **1440-pixel desktop viewport** and an emulated **430-pixel mobile viewport**. The hero, peer comparison, findings/limitations and mobile coverage sections were inspected. All four embedded images loaded. Document width did not exceed the viewport; charts and tables have their own horizontal scrolling on small screens. Tables have headers and figures have explanatory alternative text/captions.

The report is static HTML/CSS with embedded PNGs. It has no application framework, JavaScript chart runtime, server or external font dependency. GitHub Pages serves the committed `docs/` directory.

## Final editorial and publication review

The README, report and executive summary were edited for clearer English and a more direct explanation of the analysis. Broken question-mark separators in the README were replaced with ordinary punctuation; real questions and the CMS API query parameter were retained. The README was also rendered through GitHub's GFM API to check its headings, three tables, links and code blocks.

The new candidate table was rendered and inspected in Chrome at 1440px and 430px. Its five rows and six columns were checked against the source export. All four images loaded, internal section links resolved, and there was no page-level horizontal overflow. On small screens the table scrolls within its own container.

The final review also compared the earlier and current statistics and hospital illustration, and the SHA-256 hashes of all four PNGs. All were unchanged. Original pipeline, SQL, original test files and dependencies were preserved. Only the report was regenerated; Spark and the hospital pipeline were not rerun.

GitHub Pages is configured for branch `main`, path `/docs`, with `docs/.nojekyll` present. The published URL is [the report root](https://ransij.github.io/healthcare-operations-analytics/), which serves `docs/index.html`. Deployment is verified by comparing the HTTP response bytes with the committed HTML, rather than assuming a configured site has deployed. The publication check is completed after pushing the final review.

## Reproduction and remaining work

Use the [report-only reproduction guide](reproducibility.md). The environment is separate from the original Spark environment; matplotlib is the only directly selected report library, with its dependencies pinned in requirements-report.txt. Git attributes preserve evidence bytes and consistent source line endings.

Databricks account execution and a Power BI dashboard remain postponed. Full analytical CSVs and original CMS files remain outside Git. A reader can view the report and small aggregate evidence immediately; reproducing every distribution requires a successful full model export from the pinned sources. If those exports are unavailable, the builder deliberately limits itself to documented evidence counts.

This version stops at the static descriptive portfolio deliverable and GitHub publication.
