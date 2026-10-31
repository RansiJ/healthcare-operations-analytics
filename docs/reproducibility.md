# Reproduction guide

The portfolio report is built from a previously completed run. It does not launch the hospital pipeline. This guide keeps report reproduction separate from an optional future full-model reproduction.

## Report-only build

Use Python 3.11 and `requirements-report.txt` in an isolated environment outside Git. Matplotlib creates the figures; standard-library csv, statistics and hashlib provide analysis and integrity checks. The pinned file includes matplotlib's transitive dependencies to preserve the tested rendering environment.

```powershell
uv venv "$env:LOCALAPPDATA\healthcare-report-venv" --python 3.11
uv pip install --python "$env:LOCALAPPDATA\healthcare-report-venv\Scripts\python.exe" --link-mode copy -r requirements-report.txt
$reportPython = "$env:LOCALAPPDATA\healthcare-report-venv\Scripts\python.exe"
& $reportPython -m analysis.build_report --run-dir 'C:\path\to\successful-run' --report-date 2026-10-31
& $reportPython -m unittest discover -s tests -p test_report.py -v
```

Run from the repository root. `uv` is optional; a standard Python venv plus pip can install the same requirements. `--link-mode copy` avoids Windows cloud-filesystem hardlink incompatibilities encountered during setup; it does not affect analytical results.

Default input discovery is `~/.local/share/healthcare-operations-analytics/runs/`, using the most recent timestamp-named directory with SUCCESS.json. The builder fails on a corrupted manifest or present-but-mismatched export. It checks all five CSVs before any CSV analysis. Output defaults to `docs/`; it cannot overlap the selected run tree.

The source run for the published report is `20261031T100805Z_d4fac535`, completed at `2026-10-31T10:09:37.591238+00:00`. Its quality-report hash is recorded in [report_source_verification.json](evidence/report_source_verification.json), along with the five checked export hashes. Original files are read only. The HTML embeds its PNG figures and needs no web server, application framework or external chart library.

The report regenerates four matplotlib PNGs, `docs/index.html`, `docs/executive_summary.md`, `docs/evidence/analysis_summary.json`, and the report source/artifact manifest. Use the same `--report-date` and pinned environment for repeatable content. Do not overwrite the original model outputs.

If complete exports are absent, the builder falls back to the existing passed quality report. This limited mode shows only documented coverage/flag counts. It does not reconstruct distributions or individual hospital values. Use `--summary-only --output-dir <another-directory>` to inspect that mode without replacing the full published report. The run/evidence ID and limited mode are visible in generated content.

## Optional future full-model reproduction

These are preserved pipeline instructions, **not commands executed for the static portfolio report**. Keep the environment separate from report rendering. Use Python 3.11 on Windows and Java 17+, because the pinned Spark 4.0.1 has a documented Windows/Python 3.12 worker issue.

```powershell
uv venv "$env:LOCALAPPDATA\healthcare-analytics-venv" --python 3.11
uv pip install --python "$env:LOCALAPPDATA\healthcare-analytics-venv\Scripts\python.exe" -r requirements.txt
$env:JAVA_HOME = 'C:\path\to\jdk-17'
$env:PYSPARK_PYTHON = "$env:LOCALAPPDATA\healthcare-analytics-venv\Scripts\python.exe"
$env:SPARK_LOCAL_IP = '127.0.0.1'
& $env:PYSPARK_PYTHON -m healthcare_pipeline download
& $env:PYSPARK_PYTHON -m healthcare_pipeline verify
& $env:PYSPARK_PYTHON -m unittest discover -s tests -p test_sources.py -v
& $env:PYSPARK_PYTHON -m unittest discover -s tests -p test_spark_contracts.py -v
& $env:PYSPARK_PYTHON -m healthcare_pipeline run
```

The two original test files contain the 27 tests executed in Phase 2. Report tests require the separate report environment. Selecting filenames above keeps the original Spark test path independent of matplotlib.

Original sources default to `~/.local/share/healthcare-operations-analytics/raw/2026-08-13/`; fresh runs go to the sibling `runs/` tree. Override with `--raw-dir` and `--output-root`. Both trees must be external to Git, distinct from one another, and outside this project. Never commit raw or full analytical CSVs.

The downloader requests only pinned resource URLs and checks their approved original-byte SHA-256 hashes. It never substitutes a newer release or overwrites retained originals. If the approved resource disappears or the bytes change, stop and review the source version. The code has no supported silent-refresh path.

Each run creates five bounded CSV tables, schemas, a quality report and a success marker. Consumers must verify SUCCESS.json and its referenced quality-report hash, then verify every output hash. A failed run is not usable. The original [data dictionary](data_dictionary.md), [scope](scope.md) and [executed Phase 2 checks](quality_checks.md) document types, dates, note policy, exact self-exclusion and the 20,000-row/table export bound.

Databricks and Power BI are postponed for this portfolio version. No account, cloud resource or dashboard setup is required here.
