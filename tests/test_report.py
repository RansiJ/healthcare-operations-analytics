"""Report-only checks; these never start Spark or rerun the hospital pipeline."""

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from analysis.build_report import (FILES, distribution, latest_successful,
    summarize, validate_sources, verified_run)
from healthcare_pipeline.sources import SOURCES, ContractError


class ReportTests(unittest.TestCase):
    def fixture(self, root):
        path = Path(root) / "20261031T100805Z_fixture"
        path.mkdir()
        for filename in FILES:
            (path / filename).write_bytes(b"column\n")
        report = {"run_id": path.name, "status": "passed",
            "sources": [{"dataset_id": s.dataset_id, "sha256": s.sha256} for s in SOURCES],
            "output_sha256": {f: hashlib.sha256((path / f).read_bytes()).hexdigest() for f in FILES},
            "rows": {f.removesuffix('.csv'): 0 for f in FILES}}
        (path / "quality_report.json").write_text(json.dumps(report))
        success = {"run_id": path.name,
            "quality_report_sha256": hashlib.sha256((path / "quality_report.json").read_bytes()).hexdigest()}
        (path / "SUCCESS.json").write_text(json.dumps(success))
        return path

    def test_exact_inclusive_quartiles_and_zero(self):
        got = distribution([0., 10.])
        self.assertEqual((got['q1'], got['median'], got['q3']), (2.5, 5., 7.5))
        self.assertEqual(got['zero_count'], 1)
        self.assertEqual(distribution([7.])['median'], 7.)

    def test_missing_observations_do_not_create_a_distribution(self):
        with self.assertRaises(ContractError):distribution([])

    def test_full_chain_and_latest_selection(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            report, tables, verification = verified_run(path)
            self.assertEqual(latest_successful(root), path)
            self.assertEqual(verification['mode'], 'verified_exports')
            self.assertEqual(len(verification['verified_export_sha256']), 5)

    def test_tampered_csv_stops_without_summary_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            (path / 'peer_benchmarks.csv').write_bytes(b'tampered\n')
            with self.assertRaisesRegex(ContractError, 'Export hash mismatch'):verified_run(path)

    def test_tampered_quality_report_stops(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            (path / 'quality_report.json').write_text('{}')
            with self.assertRaisesRegex(ContractError, 'quality-report hash mismatch'):verified_run(path)

    def test_missing_export_returns_only_verified_summary(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.fixture(root)
            (path / 'peer_benchmarks.csv').unlink()
            report, tables, verification = verified_run(path)
            self.assertIsNone(tables)
            self.assertEqual(verification['mode'], 'summary_only')
            self.assertEqual(verification['missing_exports'], ['peer_benchmarks.csv'])

    def test_no_fourth_or_different_source(self):
        with self.assertRaises(ContractError):validate_sources({'status':'passed','sources':[]})

    def test_summary_mode_has_no_invented_distributions_or_hospitals(self):
        root = Path(__file__).resolve().parents[1]
        report = json.loads((root/'docs/evidence/run_summary.json').read_text())
        summary, grouped = summarize(report, None)
        self.assertEqual(summary['mode'], 'summary_only')
        self.assertEqual(grouped, {})
        self.assertIsNone(summary['example'])
        self.assertTrue(all('distribution' not in m for m in summary['metrics']))


if __name__ == '__main__':
    unittest.main()
