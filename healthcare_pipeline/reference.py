"""Independent, bounded audit oracle; never used to calculate the Spark outputs.

Uses rational interpolation on sorted hospital observations, not Spark functions.
"""

from collections import defaultdict
from fractions import Fraction
import math

from .sources import ContractError


def continuous_percentile(values, probability):
    """Type-7 continuous quantile: h=(n-1)*p, interpolate adjacent order stats."""
    values = sorted(Fraction(str(x)) for x in values)
    if not values:
        return None
    h = (len(values) - 1) * Fraction(str(probability))
    lo = h.numerator // h.denominator
    hi = min(lo + 1, len(values) - 1)
    return float(values[lo] + (h - lo) * (values[hi] - values[lo]))


def verify_peer_rows(rows):
    """Check ALL rows against a separate identity-aware Python implementation."""
    groups = defaultdict(list)
    fields = ("source_release", "source_dataset_id", "state", "hospital_type",
              "measure_id", "start_date", "end_date")
    for row in rows:
        if row["comparison_eligible"]:
            groups[tuple(row[k] for k in fields)].append(row)
    comparable = 0
    for row in rows:
        others = [p for p in groups[tuple(row[k] for k in fields)]
                  if p["facility_id"] != row["facility_id"]] if row["comparison_eligible"] else []
        expected_count = len(others)
        if row["peer_count"] != expected_count:
            raise ContractError(f"Independent peer count mismatch: {row['facility_id']}")
        status = ("ineligible" if not row["comparison_eligible"] else
                  "comparable" if expected_count >= 10 else "insufficient_peers")
        if row["comparison_status"] != status:
            raise ContractError("Independent comparison status mismatch")
        if status != "comparable":
            for field in ("peer_q1", "peer_median", "peer_q3", "gap_to_peer_median", "unfavorable_signal"):
                if row[field] is not None:
                    raise ContractError(f"Unqualified comparison populated {field}")
            continue
        comparable += 1
        values = [p["score_value"] for p in others]
        expected = [continuous_percentile(values, p) for p in (0.25, 0.5, 0.75)]
        for field, value in zip(("peer_q1", "peer_median", "peer_q3"), expected):
            if row[field] is None or not math.isclose(float(row[field]), value, rel_tol=0, abs_tol=1e-9):
                raise ContractError(f"Independent continuous percentile mismatch: {field}")
        score = float(row["score_value"])
        expected_signal = score > expected[2] if row["favorable_direction"] == "lower" else score < expected[0]
        if row["unfavorable_signal"] != expected_signal:
            raise ContractError("Independent strict-threshold signal mismatch")
        if not math.isclose(float(row["gap_to_peer_median"]), score - expected[1], rel_tol=0, abs_tol=1e-9):
            raise ContractError("Independent median gap mismatch")
    return {"rows_verified": len(rows), "comparable_rows_verified": comparable,
            "percentile_values_verified": comparable * 3, "tolerance": 1e-9,
            "algorithm": "independent rational type-7 interpolation; identity-based self-exclusion"}

