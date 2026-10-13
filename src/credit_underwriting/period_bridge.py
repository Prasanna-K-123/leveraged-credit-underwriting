"""Strict calendar-fiscal TTM bridge using exact contexts and an explicit cutoff.

The original Q2-only functions remain unchanged. This API supports fixed
month-end fiscal calendars; it does not certify heuristic table parsing or
an actual Q1/Q3 live issuer refresh.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
import math
from numbers import Real
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from .facts import DURATION_TAGS, DurationOverrides


def _iso(value: str, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be YYYY-MM-DD") from error
    if result.isoformat() != value:
        raise ValueError(f"{field} must be YYYY-MM-DD")
    return result


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite numeric data")
    return float(value)


def _month_end(value: date) -> bool:
    return value.day == calendar.monthrange(value.year, value.month)[1]


def shift_month_end(value: date, months: int) -> date:
    if not isinstance(value, date) or not _month_end(value) or isinstance(months, bool) or not isinstance(months, int):
        raise ValueError("A month-end date and integer month shift are required")
    year, month_zero = divmod(value.year * 12 + value.month - 1 + months, 12)
    return date(year, month_zero + 1, calendar.monthrange(year, month_zero + 1)[1])


@dataclass(frozen=True)
class Period:
    start: str
    end: str


@dataclass(frozen=True)
class PeriodPlan:
    fiscal_quarter: int
    annual: Period
    current_ytd: Period
    prior_ytd: Period


def calendar_period_plan(quarterly_report_date: str, annual_report_date: str) -> PeriodPlan:
    q_end = _iso(quarterly_report_date, "quarterly_report_date")
    fy_end = _iso(annual_report_date, "annual_report_date")
    if not _month_end(q_end) or not _month_end(fy_end):
        raise ValueError("Only fixed month-end fiscal calendars are supported; 52/53-week calendars are refused")
    months = (q_end.year - fy_end.year) * 12 + q_end.month - fy_end.month
    if months not in (3, 6, 9) or shift_month_end(fy_end, months) != q_end:
        raise ValueError("Quarter must be exactly3/6/9 fiscal months after the latest annual end")
    annual_start = shift_month_end(fy_end, -12) + timedelta(days=1)
    current_start = fy_end + timedelta(days=1)
    prior_end = shift_month_end(q_end, -12)
    return PeriodPlan(months // 3, Period(annual_start.isoformat(), fy_end.isoformat()),
                      Period(current_start.isoformat(), q_end.isoformat()),
                      Period(annual_start.isoformat(), prior_end.isoformat()))


def _available_metadata(row: dict, period: Period, forms: tuple[str, ...], cutoff: date) -> dict | None:
    if not isinstance(row, dict) or row.get("start") != period.start or row.get("end") != period.end or row.get("form") not in forms:
        return None
    filed = _iso(row.get("filed"), "filed")
    if filed > cutoff:
        return None
    if filed < _iso(period.end, "period end"):
        raise ValueError("A source cannot be filed before its period ends")
    accession = row.get("accn") or row.get("accession")
    if not isinstance(accession, str) or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession):
        raise ValueError("A well-formed SEC accession is required")
    return {"filed": filed.isoformat(), "accession": accession}


def _exact_fact(companyfacts: dict, metric: str, period: Period,
                forms: tuple[str, ...], cutoff: date) -> tuple[float, dict]:
    namespaces = companyfacts.get("facts", {})
    if not isinstance(namespaces, dict):
        raise ValueError("Invalid fact namespace mapping")
    facts = namespaces.get("us-gaap", {})
    if not isinstance(facts, dict):
        raise ValueError("Invalid us-gaap fact mapping")
    candidates = []
    for tag in DURATION_TAGS[metric]:
        fact = facts.get(tag, {})
        if not isinstance(fact, dict) or not isinstance(fact.get("units", {}), dict):
            raise ValueError("Invalid fact or unit mapping")
        entries = fact.get("units", {}).get("USD", [])
        if not isinstance(entries, list):
            raise ValueError("USD facts must be a list")
        for row in entries:
            metadata = _available_metadata(row, period, forms, cutoff)
            if metadata is None:
                continue
            value = _finite(row.get("val"), "USD fact value")
            source = {"metric": metric, "source_type": "sec_companyfacts", "xbrl_tag": tag,
                      "unit": "USD", "value_raw": value, "value_usd_millions": value / 1e6,
                      "start": period.start, "end": period.end, "form": row["form"],
                      "fy": row.get("fy"), "fp": row.get("fp"), **metadata}
            candidates.append((value / 1e6, source))
    if not candidates:
        raise ValueError(f"Missing exact USD context for {metric}: {period.start}..{period.end}, cutoff {cutoff}")
    latest = max(source["filed"] for _, source in candidates)
    current = [(value, source) for value, source in candidates if source["filed"] == latest]
    if len({source["value_raw"] for _, source in current}) != 1:
        raise ValueError(f"Conflicting latest exact-context values for {metric}")
    rank = {tag: index for index, tag in enumerate(DURATION_TAGS[metric])}
    return min(current, key=lambda item: (rank[item[1]["xbrl_tag"]], item[1]["accession"]))


def _table_override(record: dict, metric: str, period: Period,
                    forms: tuple[str, ...], cutoff: date) -> tuple[float, dict]:
    if not isinstance(record, dict) or not isinstance(record.get("source_row"), dict):
        raise ValueError("Table override needs an explicit source row")
    row = dict(record["source_row"])
    metadata = _available_metadata(row, period, forms, cutoff)
    if metadata is None:
        raise ValueError("Table override does not have the exact available period/form")
    if row.get("metric") != metric or row.get("source_type") != "sec_filing_table" or row.get("unit") != "USD":
        raise ValueError("Table override metric/type/unit mismatch")
    value = _finite(record.get("value_usd_millions"), "override value_usd_millions")
    source_millions = _finite(row.get("value_usd_millions"), "source value_usd_millions")
    raw = _finite(row.get("value_raw"), "source value_raw")
    if value != source_millions or not math.isclose(raw, value * 1e6, abs_tol=0, rel_tol=1e-12):
        raise ValueError("Override raw/USD-million values disagree")
    digest = row.get("source_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ValueError("Table override requires a64-hex source digest")
    url = row.get("source_url")
    if not isinstance(url, str):
        raise ValueError("Table override requires a SEC Archives URL")
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.netloc not in ("www.sec.gov", "sec.gov")
            or not parsed.path.startswith("/Archives/edgar/data/")
            or metadata["accession"].replace("-", "") not in parsed.path.split("/")):
        raise ValueError("Table override URL/accession is not a SEC Archives identity")
    row.update(metadata, start=period.start, end=period.end)
    return value, row


def build_ttm_metrics_period_aware(companyfacts: dict, latest_10q_report_date: str,
                                  latest_10k_report_date: str, *, filing_cutoff: str,
                                  duration_overrides: DurationOverrides | None = None) -> tuple[dict, pd.DataFrame]:
    """Return a complete exact-context FY + currentYTD - priorYTD bridge.

    The supplied bundle and explicit cutoff define available evidence. This
    does not assume that filing fp/fy identifies the economic comparison
    period, that missing facts can be imputed, or that legacy table overrides
    with no start date identify a YTD interval.
    """
    if not isinstance(companyfacts, dict):
        raise ValueError("companyfacts must be a mapping")
    if duration_overrides is not None and not isinstance(duration_overrides, dict):
        raise ValueError("duration_overrides must be a mapping")
    plan = calendar_period_plan(latest_10q_report_date, latest_10k_report_date)
    cutoff = _iso(filing_cutoff, "filing_cutoff")
    if cutoff < _iso(plan.current_ytd.end, "quarter end"):
        raise ValueError("Filing cutoff precedes the current period end")
    values = {}
    sources = []
    for metric in DURATION_TAGS:
        overrides = (duration_overrides or {}).get(metric, {})
        if not isinstance(overrides, dict):
            raise ValueError("Each metric override must be a mapping by period end")
        selected = []
        for role, period, forms in (("latest_fy", plan.annual, ("10-K",)),
                                    ("current_ytd", plan.current_ytd, ("10-Q",)),
                                    ("prior_ytd", plan.prior_ytd, ("10-Q", "10-K"))):
            override = overrides.get(period.end)
            if override is None:
                value, source = _exact_fact(companyfacts, metric, period, forms, cutoff)
            else:
                value, source = _table_override(override, metric, period, forms, cutoff)
            selected.append(value)
            source = dict(source, ttm_bridge_role=role, fiscal_quarter=plan.fiscal_quarter,
                          filing_cutoff=filing_cutoff,
                          duration_days_inclusive=(_iso(period.end, "end") - _iso(period.start, "start")).days + 1)
            sources.append(source)
        values[metric] = selected[0] + selected[1] - selected[2]
    if not all(math.isfinite(value) for value in values.values()) or values["revenue"] <= 0:
        raise ValueError("TTM metrics must be finite and revenue positive for ratios")
    values["ebitda_proxy"] = values["operating_income"] + values["depreciation_amortization"]
    values["free_cash_flow"] = values["cash_from_operations"] - values["capital_expenditures"]
    values["ebitda_margin"] = values["ebitda_proxy"] / values["revenue"]
    values["fcf_margin"] = values["free_cash_flow"] / values["revenue"]
    values["ebitda_interest_coverage"] = (values["ebitda_proxy"] / values["interest_expense"]
                                           if values["interest_expense"] > 0 else math.nan)
    if values["interest_expense"] > 0 and not math.isfinite(values["ebitda_interest_coverage"]):
        raise ValueError("Positive-interest coverage is not finite")
    if not all(math.isfinite(value) for key, value in values.items() if key != "ebitda_interest_coverage"):
        raise ValueError("Derived metrics are not finite")
    return values, pd.DataFrame(sources)
