"""Q2-only bridge preconditions; no SEC requests or historical research reruns."""
import pytest

from credit_underwriting.facts import build_ttm_metrics, require_supported_q2_ttm_bridge


@pytest.mark.parametrize(("quarter", "fiscal_year_end"), [
    ("2026-05-31", "2025-11-30"),  # accepted Carnival Q2 reference
    ("2027-05-31", "2026-11-30"),  # same fiscal month in next annual cycle
])
def test_supported_q2_window(quarter, fiscal_year_end):
    require_supported_q2_ttm_bridge(quarter, fiscal_year_end)


@pytest.mark.parametrize(("quarter", "fiscal_year_end"), [
    ("2026-02-28", "2025-11-30"),  # Q1
    ("2026-08-31", "2025-11-30"),  # Q3
    ("2026-11-30", "2025-11-30"),  # after FY, not Q2
    ("2025-08-31", "2025-11-30"),  # stale report
    ("2027-05-31", "2025-11-30"),  # stale annual context
])
def test_unsupported_quarters_refused_before_fact_lookup(quarter, fiscal_year_end):
    with pytest.raises(ValueError, match="Q2-like"):
        require_supported_q2_ttm_bridge(quarter, fiscal_year_end)
    with pytest.raises(ValueError, match="Q2-like"):
        build_ttm_metrics({}, quarter, fiscal_year_end)


def test_invalid_date_rejected():
    with pytest.raises(ValueError):
        require_supported_q2_ttm_bridge("not-a-date", "2025-11-30")
