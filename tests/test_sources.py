import dataclasses
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from healthcare_pipeline.sources import (SOURCES, PROJECT_ROOT, ContractError,
                                         external_path, verify_file, verify_sources)


class SourceTests(unittest.TestCase):
    def test_exactly_three_pinned_sources(self):
        self.assertEqual([s.dataset_id for s in SOURCES], ["xubh-q36u", "yv7e-xc69", "dgck-syfz"])

    def test_checksum_and_size(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fixture.csv"
            path.write_bytes(b"original\r\n")
            source = dataclasses.replace(SOURCES[0], sha256=hashlib.sha256(path.read_bytes()).hexdigest(), size=10)
            verify_file(path, source)
            path.write_bytes(b"tampered\r\n")
            with self.assertRaisesRegex(ContractError, "MISMATCH"):
                verify_file(path, source)

    def test_wrong_size_also_fails(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "fixture"
            path.write_bytes(b"x")
            source = dataclasses.replace(SOURCES[0], sha256=hashlib.sha256(b"x").hexdigest(), size=2)
            with self.assertRaises(ContractError):
                verify_file(path, source)

    def test_project_raw_storage_refused(self):
        with self.assertRaises(ContractError):
            external_path(PROJECT_ROOT / "data")

    def test_git_ancestor_storage_refused(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / ".git").mkdir()
            with self.assertRaises(ContractError):
                external_path(Path(root) / "raw")

    def test_first_bad_source_stops_verification(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / SOURCES[0].filename).write_bytes(b"changed")
            with patch("healthcare_pipeline.sources.verify_file", wraps=verify_file) as check:
                with self.assertRaises(ContractError):
                    verify_sources(root)
                self.assertEqual(check.call_count, 1)

    def test_hash_mismatch_stops_run_before_spark_or_output(self):
        from healthcare_pipeline.pipeline import run
        with tempfile.TemporaryDirectory() as root:
            raw = Path(root) / "raw"
            raw.mkdir()
            (raw / SOURCES[0].filename).write_bytes(b"changed")
            output = Path(root) / "runs"
            with self.assertRaisesRegex(ContractError, "MISMATCH"):
                run(object(), raw, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
