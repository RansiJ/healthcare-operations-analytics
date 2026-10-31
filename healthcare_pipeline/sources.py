"""Pinned inputs, streaming SHA-256 verification and external-only raw storage."""

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE = "2026-08-13"
DEFAULT_ROOT = Path.home() / ".local/share/healthcare-operations-analytics"


@dataclass(frozen=True)
class Source:
    dataset_id: str
    filename: str
    resource: str
    sha256: str
    size: int
    rows: int
    columns: int

    @property
    def url(self):
        return ("https://data.cms.gov/provider-data/sites/default/files/resources/"
                f"{self.resource}/{self.filename}")


SOURCES = (
    Source("xubh-q36u", "Hospital_General_Information.csv",
           "893c372430d9d71a1c52737d01239d47_1785189955",
           "f874f09fef895a1ccf5bb7392dcbb2be05c9860339261b093fe00f0c1b013480",
           1450767, 5419, 38),
    Source("yv7e-xc69", "Timely_and_Effective_Care-Hospital.csv",
           "0437b5494ac61507ad90f2af6b8085a7_1785189967",
           "1e5a1ca803c2b09468fe3ae3fe60fef3e910f5f5300630a24791c88a1abff516",
           34150899, 138084, 16),
    Source("dgck-syfz", "HCAHPS-Hospital.csv",
           "78a50346fbe828ea0ce2837847af6a7c_1785189950",
           "b70e598f29552df302e30ed649d178abd1b3d3c868ae97cf8e55453dd33898fc",
           105461119, 325720, 22),
)


class ContractError(ValueError):
    """A source or analytic contract failed; publication must stop."""


def external_path(path):
    """Resolve symlinks; refuse project storage and any ancestor Git worktree."""
    path = Path(path).expanduser().resolve()
    if path == PROJECT_ROOT or PROJECT_ROOT in path.parents:
        raise ContractError("Raw data and run outputs must be outside the project")
    if any((p / ".git").exists() for p in (path, *path.parents)):
        raise ContractError("Storage must be outside every Git working tree")
    return path


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path, source):
    path = Path(path)
    actual = digest_file(path)
    if actual != source.sha256 or path.stat().st_size != source.size:
        raise ContractError(
            f"HASH/SIZE MISMATCH {source.dataset_id}: expected {source.sha256} "
            f"({source.size} bytes); observed {actual} ({path.stat().st_size} bytes). "
            "Stop; do not replace the approved version."
        )
    return actual


def verify_sources(raw_dir):
    """Verify all three byte streams BEFORE Spark reads any source."""
    raw_dir = external_path(raw_dir)
    records = []
    for source in SOURCES:
        path = raw_dir / source.filename
        # Also check the resolved file: reject a symlink into a Git repository.
        external_path(path)
        digest = verify_file(path, source)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            header = next(csv.reader(stream))
        if len(header) != source.columns or len(set(header)) != len(header):
            raise ContractError(f"Unexpected header: {source.dataset_id}")
        receipt_path = raw_dir / (source.filename + ".download.json")
        receipt = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
        records.append({
            "dataset_id": source.dataset_id, "filename": source.filename,
            "url": source.url, "sha256": digest, "bytes": source.size,
            "source_release": RELEASE, "source_modified": "2026-07-22",
            "verified_at_utc": datetime.now(timezone.utc).isoformat(),
            "downloaded_at_utc": receipt.get("downloaded_at_utc"),
            "download_date_note": receipt.get("download_date_note", "No original download receipt supplied"),
        })
    return records


def download_sources(raw_dir):
    """Never overwrite originals. A mismatched .part stays quarantined for review."""
    raw_dir = external_path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        path = raw_dir / source.filename
        if path.exists():
            verify_file(path, source)
            continue
        part = path.with_suffix(path.suffix + ".part")
        # Exclusive creation prevents silently overwriting a previous failed download.
        with part.open("xb") as dest, urllib.request.urlopen(source.url, timeout=90) as response:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                dest.write(block)
        verify_file(part, source)
        part.rename(path)
        receipt = {"downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
                   "url": source.url, "sha256": source.sha256,
                   "download_date_note": "Recorded immediately after completed download"}
        (raw_dir / (source.filename + ".download.json")).write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return verify_sources(raw_dir)

