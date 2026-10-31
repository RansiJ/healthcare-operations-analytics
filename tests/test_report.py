"""Report-only checks; these never start Spark or rerun the hospital pipeline."""

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from analysis.build_report import (FILES, distribution, latest_successful,
    review_candidates, summarize, validate_sources, verified_run)
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
        self.assertIsNone(summary['review_candidates'])
        self.assertTrue(all('distribution' not in m for m in summary['metrics']))

    def candidate(self, facility, gap, **changes):
        row = {'facility_id': facility, 'facility_name': 'Hospital '+facility, 'state': 'AL',
               'measure_id': 'OP_18b', 'score_value': str(100+gap), 'peer_median': '100',
               'gap_to_peer_median': str(gap), 'peer_count': '10', 'peer_q3': '105',
               'start_date': '2024-10-01', 'end_date': '2025-09-30',
               'comparison_eligible': 'true', 'comparison_status': 'comparable',
               'unfavorable_signal': 'true'}
        return {**row, **changes}

    def test_shortlist_largest_stored_gaps_limit_and_stable_ties(self):
        rows = [self.candidate(f'{i:06d}', gap) for i, gap in enumerate([50, 100, 100, 80, 70, 60, 40], 1)]
        result = review_candidates(list(reversed(rows)))
        self.assertEqual(result['flagged_pool_count'], 7)
        self.assertEqual([r['facility_id'] for r in result['hospitals']],
                         ['000002', '000003', '000004', '000005', '000006'])

    def test_shortlist_uses_one_measure_and_qualified_existing_flags(self):
        rows = [self.candidate('000001', 20),
                self.candidate('000002', 999, comparison_eligible='false'),
                self.candidate('000003', 999, comparison_status='insufficient_peers'),
                self.candidate('000004', 999, unfavorable_signal='false'),
                self.candidate('000005', 999, peer_count='9'),
                self.candidate('000006', 999, measure_id='OP_22'),
                self.candidate('000007', -20)]
        self.assertEqual([r['facility_id'] for r in review_candidates(rows)['hospitals']], ['000001'])

    def test_shortlist_copies_source_values_and_identifiers(self):
        original = self.candidate('050327', 228, score_value='413.000000',
                                  peer_median='185.0', gap_to_peer_median='228.0', peer_count='195')
        result = review_candidates([original])['hospitals'][0]
        for name, value in result.items():
            self.assertEqual(value, original[name])


if __name__ == '__main__':
    unittest.main()
