"""Registered deterministic synthetic fixtures; no retrieved issuer data."""
from datetime import date, timedelta
import calendar

from credit_underwriting.facts import DURATION_TAGS
from credit_underwriting.period_bridge import Period, PeriodPlan

ANNUAL_MILLIONS = dict(revenue=1000, operating_income=150, depreciation_amortization=50,
                       interest_expense=25, cash_from_operations=160, capital_expenditures=60)
YTD = {1: (.30, .20), 2: (.70, .50), 3: (.95, .90)}
QUARTER_END_MONTHS = {
    1: (4, 7, 10), 2: (5, 8, 11), 3: (6, 9, 12), 4: (7, 10, 1),
    5: (8, 11, 2), 6: (9, 12, 3), 7: (10, 1, 4), 8: (11, 2, 5),
    9: (12, 3, 6), 10: (1, 4, 7), 11: (2, 5, 8), 12: (3, 6, 9),
}


def _end(year, month):
    return date(year, month, calendar.monthrange(year, month)[1])


def fixture(year=2025, fiscal_month=11, quarter=2):
    # Expected dates use an explicit fiscal-month lookup, independent of the production planner.
    annual_end = _end(year, fiscal_month)
    quarter_month = QUARTER_END_MONTHS[fiscal_month][quarter - 1]
    quarter_year = year + int(quarter_month < fiscal_month)
    q_end = _end(quarter_year, quarter_month)
    prior_annual_end = _end(year - 1, fiscal_month)
    annual_start = (prior_annual_end + timedelta(days=1)).isoformat()
    plan = PeriodPlan(quarter, Period(annual_start, annual_end.isoformat()),
                      Period((annual_end + timedelta(days=1)).isoformat(), q_end.isoformat()),
                      Period(annual_start, _end(quarter_year - 1, quarter_month).isoformat()))
    current_factor, prior_factor = YTD[quarter]
    cutoff = (q_end + timedelta(days=35)).isoformat()
    current_filed = (q_end + timedelta(days=30)).isoformat()
    annual_filed = (annual_end + timedelta(days=60)).isoformat()
    facts = {}
    for metric, annual in ANNUAL_MILLIONS.items():
        tag = DURATION_TAGS[metric][0]
        entries = []
        for period, factor, form, filed in ((plan.annual, 1, "10-K", annual_filed),
                                           (plan.current_ytd, current_factor, "10-Q", current_filed),
                                           (plan.prior_ytd, prior_factor, "10-Q", current_filed)):
            # Synthetic accession syntax, not a claimed or retrieved SEC filing.
            entries.append(dict(start=period.start, end=period.end, val=round(annual * factor * 1e6),
                                form=form, filed=filed, accn="0000000000-26-000001", fy=2099, fp="Q2"))
        # Unrelated single-quarter duration, and unavailable future restatement.
        if quarter != 1:
            previous_month = QUARTER_END_MONTHS[fiscal_month][quarter - 2]
            previous_year = year + int(previous_month < fiscal_month)
            distractor = dict(entries[1]);distractor.update(start=(_end(previous_year, previous_month) + timedelta(days=1)).isoformat(), val=999999999999)
            entries.append(distractor)
        future = dict(entries[1]);future.update(filed=(q_end + timedelta(days=90)).isoformat(), val=999999999999)
        entries.append(future)
        facts[tag] = {"units": {"USD": entries}}
    return ({"entityName": "SYNTHETIC_PROTOCOL_FIXTURE_NOT_AN_ISSUER", "facts": {"us-gaap": facts}},
            q_end.isoformat(), annual_end.isoformat(), cutoff, plan, 1 + current_factor - prior_factor)


def calendar_cases():
    for year in range(2023, 2027):
        for fiscal_month in range(1, 13):
            for quarter in (1, 2, 3):
                yield year, fiscal_month, quarter, fixture(year, fiscal_month, quarter)
