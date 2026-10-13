"""Execute the registered synthetic context matrix without replacing issuer evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
import pandas as pd
from credit_underwriting.period_bridge import build_ttm_metrics_period_aware
from research_period_bridge.fixtures import calendar_cases, ANNUAL_MILLIONS


def legacy_blob_hashes():
    path = ROOT / "research_period_bridge/HISTORICAL_GIT_BLOBS.json"
    expected = json.loads(path.read_text())
    actual = {}
    for rel, blob in expected.items():
        content = (ROOT / rel).read_bytes()
        actual[rel] = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if actual[rel] != blob:
            raise ValueError(f"Legacy source/reference blob changed: {rel}")
    return actual


def compare(actual, expected, path="summary"):
    if type(actual) is not type(expected):
        raise ValueError(f"Reference type changed at {path}")
    if isinstance(actual, float):
        if not math.isfinite(actual) or not math.isfinite(expected) or not math.isclose(actual, expected, abs_tol=1e-10, rel_tol=1e-10):
            raise ValueError(f"Reference float mismatch at {path}")
    elif isinstance(actual, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"Reference schema mismatch at {path}")
        for key in actual: compare(actual[key], expected[key], path + "." + key)
    elif isinstance(actual, list):
        if len(actual) != len(expected): raise ValueError(f"Reference length mismatch at {path}")
        for i, (a, b) in enumerate(zip(actual, expected)): compare(a, b, path + f"[{i}]")
    elif actual != expected: raise ValueError(f"Reference identity mismatch at {path}")


def matrix():
    rows, source_frames = [], []
    for year, month, quarter, data in calendar_cases():
        bundle, q_end, annual_end, cutoff, plan, multiplier = data
        metrics, sources = build_ttm_metrics_period_aware(bundle, q_end, annual_end, filing_cutoff=cutoff)
        expected = {metric: value * multiplier for metric, value in ANNUAL_MILLIONS.items()}
        expected.update(ebitda_proxy=200 * multiplier, free_cash_flow=100 * multiplier,
                        ebitda_margin=.2, fcf_margin=.1, ebitda_interest_coverage=8.0)
        if set(metrics) != set(expected): raise ValueError("Unexpected metric schema")
        for metric, value in expected.items():
            if not math.isclose(metrics[metric], value, abs_tol=1e-10, rel_tol=1e-10):
                raise ValueError(f"Matrix result failed for {year}/{month}/Q{quarter}/{metric}")
        if len(sources) != 18 or set(sources.fiscal_quarter) != {quarter}:
            raise ValueError("Wrong source count or fiscal quarter")
        for role, period in (("latest_fy", plan.annual), ("current_ytd", plan.current_ytd), ("prior_ytd", plan.prior_ytd)):
            selected = sources[sources.ttm_bridge_role == role]
            if (len(selected) != 6 or set(selected.start) != {period.start}
                    or set(selected.end) != {period.end} or any(selected.filed > cutoff)):
                raise ValueError("Source duration or cutoff contract failed")
        case_id = f"FY{year}-M{month:02d}-Q{quarter}"
        rows.append({"case_id": case_id, "annual_report_end": annual_end,
                     "quarter_report_end": q_end, "fiscal_quarter": quarter, "filing_cutoff": cutoff,
                     "annual_start": plan.annual.start, "current_ytd_start": plan.current_ytd.start,
                     "prior_ytd_start": plan.prior_ytd.start, "prior_ytd_end": plan.prior_ytd.end,
                     "expected_ttm_multiplier": multiplier, "metrics_usd_millions_and_ratios": metrics,
                     "verified_source_rows": 18, "status": "PASS"})
        source_frames.append(sources.assign(case_id=case_id, synthetic_fixture=True))
    if len(rows) != 144: raise ValueError("Registered matrix case count changed")
    return {"schema_version": 1, "classification": "SYNTHETIC_FIXED_CALENDAR_CONTEXT_FIXTURES_NOT_ISSUER_RESEARCH",
            "protocol": "docs/EXPLICIT_PERIOD_BRIDGE_PROTOCOL.md", "case_count": len(rows),
            "source_row_count": sum(len(frame) for frame in source_frames),
            "historical_source_and_reference_blobs": legacy_blob_hashes(), "cases": rows,
            "scope": "Exact-context Q1/Q2/Q3 API, fixed month-end fiscal calendars, explicit as-of filing cutoff. No empirical SEC Q1/Q3 refresh, complete table-parser verification, recommendation or external validation."}, pd.concat(source_frames, ignore_index=True)


def run(output: Path):
    output = output.resolve()
    if output.exists() or output == ROOT or ROOT in output.parents:
        raise ValueError("Output must be a new nonexistent directory outside the repository")
    before = legacy_blob_hashes()
    summary, sources = matrix()
    reference = ROOT / "research_period_bridge/reference_summary.json"
    if reference.exists(): compare(summary, json.loads(reference.read_text()))
    if legacy_blob_hashes() != before: raise ValueError("Historical files mutated")
    output.mkdir(parents=True, exist_ok=False)
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    sources.to_csv(output / "synthetic_source_contexts.csv", index=False)
    if legacy_blob_hashes() != before: raise ValueError("Historical files mutated")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print("PERIOD_BRIDGE_RESULT_JSON=" + json.dumps(run(parser.parse_args().output), allow_nan=False))
