from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

import numpy as np
import pandas as pd


DURATION_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
    "operating_income": ("OperatingIncomeLoss",),
    "depreciation_amortization": ("DepreciationDepletionAndAmortization",),
    "interest_expense": ("InterestExpenseNonOperating", "InterestExpense"),
    "cash_from_operations": ("NetCashProvidedByUsedInOperatingActivities",),
    "capital_expenditures": ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"),
}

INSTANT_TAGS: dict[str, tuple[str, ...]] = {
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "debt_current": (
        "LongTermDebtCurrent",
        "LongTermDebtAndFinanceLeaseObligationsCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
    ),
    "debt_noncurrent": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtAndCapitalLeaseObligationsNoncurrent",
    ),
}

DurationOverrides = dict[str, dict[str, dict[str, Any]]]


@dataclass(frozen=True)
class FactPoint:
    metric: str
    tag: str
    unit: str
    value: float
    start: str | None
    end: str
    filed: str
    accession: str
    form: str
    fiscal_year: int | None
    fiscal_period: str | None

    def source_row(self, scale: float = 1e6) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "source_type": "sec_companyfacts",
            "xbrl_tag": self.tag,
            "unit": self.unit,
            "value_raw": self.value,
            "value_usd_millions": self.value / scale,
            "start": self.start,
            "end": self.end,
            "filed": self.filed,
            "accession": self.accession,
            "form": self.form,
            "fy": self.fiscal_year,
            "fp": self.fiscal_period,
        }


def _facts(companyfacts: dict[str, Any]) -> dict[str, Any]:
    facts = companyfacts.get("facts", {}).get("us-gaap", {})
    if not facts:
        raise ValueError("SEC companyfacts has no us-gaap facts")
    return facts


def _entries_for_tag(companyfacts: dict[str, Any], tag: str, unit: str = "USD") -> list[dict[str, Any]]:
    fact = _facts(companyfacts).get(tag)
    if not fact:
        return []
    return list(fact.get("units", {}).get(unit, []))


def _best_available_tag(
    companyfacts: dict[str, Any],
    candidates: Iterable[str],
    unit: str = "USD",
    allowed_forms: tuple[str, ...] | None = None,
) -> str:
    """Choose the candidate concept with the freshest usable SEC observation.

    Issuers often migrate between equivalent US-GAAP concepts over time. Tuple order is
    therefore not a validity rule: an old concept can exist historically while a later
    equivalent contains the current filing. Freshest period end is primary; usable row
    count is a deterministic tiebreaker.
    """
    scored: list[tuple[str, int, str]] = []
    candidate_tuple = tuple(candidates)
    for tag in candidate_tuple:
        entries = [
            e
            for e in _entries_for_tag(companyfacts, tag, unit)
            if e.get("end") and (allowed_forms is None or e.get("form") in allowed_forms)
        ]
        if entries:
            scored.append((max(str(e["end"]) for e in entries), len(entries), tag))
    if not scored:
        raise ValueError(f"None of the candidate SEC tags are available: {candidate_tuple}")
    return max(scored)[2]


def _duration_days(entry: dict[str, Any]) -> int | None:
    if not entry.get("start") or not entry.get("end"):
        return None
    return (date.fromisoformat(entry["end"]) - date.fromisoformat(entry["start"])).days


def _dedupe_latest_filed(entries: list[dict[str, Any]], key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    chosen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for e in entries:
        key = tuple(e.get(k) for k in key_fields)
        old = chosen.get(key)
        if old is None or (e.get("filed") or "") > (old.get("filed") or ""):
            chosen[key] = e
    return list(chosen.values())


def annual_duration_points(companyfacts: dict[str, Any], metric: str) -> list[FactPoint]:
    tag = _best_available_tag(companyfacts, DURATION_TAGS[metric], allowed_forms=("10-K",))
    entries = []
    for e in _entries_for_tag(companyfacts, tag):
        days = _duration_days(e)
        if e.get("form") == "10-K" and e.get("fp") == "FY" and days is not None and 300 <= days <= 430:
            entries.append(e)
    entries = _dedupe_latest_filed(entries, ("end",))
    entries.sort(key=lambda e: e["end"])
    return [
        FactPoint(metric, tag, "USD", float(e["val"]), e.get("start"), e["end"], e["filed"], e["accn"], e["form"], e.get("fy"), e.get("fp"))
        for e in entries
    ]


def duration_point_ending(
    companyfacts: dict[str, Any],
    metric: str,
    end: str,
    forms: tuple[str, ...],
    min_days: int,
    max_days: int,
) -> FactPoint:
    # For an exact target period, search all economically equivalent concepts rather than
    # assuming the globally freshest concept necessarily contains the comparative row.
    matches: list[tuple[str, dict[str, Any]]] = []
    for tag in DURATION_TAGS[metric]:
        for e in _entries_for_tag(companyfacts, tag):
            days = _duration_days(e)
            if e.get("end") == end and e.get("form") in forms and days is not None and min_days <= days <= max_days:
                matches.append((tag, e))
    if not matches:
        raise ValueError(f"No {metric} duration fact ending {end} with {min_days}-{max_days} days")
    tag, e = max(matches, key=lambda item: (item[1].get("filed") or "", item[0]))
    return FactPoint(metric, tag, "USD", float(e["val"]), e.get("start"), e["end"], e["filed"], e["accn"], e["form"], e.get("fy"), e.get("fp"))


def latest_instant_point(companyfacts: dict[str, Any], metric: str, allowed_forms: tuple[str, ...] = ("10-Q", "10-K")) -> FactPoint:
    tag = _best_available_tag(companyfacts, INSTANT_TAGS[metric], allowed_forms=allowed_forms)
    candidates = [e for e in _entries_for_tag(companyfacts, tag) if e.get("form") in allowed_forms and e.get("end")]
    if not candidates:
        raise ValueError(f"No instant SEC fact available for {metric}")
    e = max(candidates, key=lambda x: (x["end"], x.get("filed") or ""))
    return FactPoint(metric, tag, "USD", float(e["val"]), None, e["end"], e["filed"], e["accn"], e["form"], e.get("fy"), e.get("fp"))


def _override(overrides: DurationOverrides | None, metric: str, end: str) -> dict[str, Any] | None:
    return (overrides or {}).get(metric, {}).get(end)


def _source_from_override(record: dict[str, Any], metric: str, end: str) -> dict[str, Any]:
    if "value_usd_millions" not in record:
        raise ValueError(f"Duration override for {metric} {end} lacks value_usd_millions")
    source = dict(record.get("source_row", {}))
    source.setdefault("metric", metric)
    source.setdefault("source_type", "sec_filing_table")
    source.setdefault("unit", "USD")
    source.setdefault("value_usd_millions", float(record["value_usd_millions"]))
    source.setdefault("value_raw", float(record["value_usd_millions"]) * 1e6)
    source.setdefault("end", end)
    return source


def build_annual_history(
    companyfacts: dict[str, Any],
    years: int = 3,
    duration_overrides: DurationOverrides | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    point_maps: dict[str, dict[str, FactPoint]] = {}
    available_ends: dict[str, set[str]] = {}

    for metric in DURATION_TAGS:
        points: list[FactPoint] = []
        try:
            points = annual_duration_points(companyfacts, metric)
        except ValueError:
            if not (duration_overrides or {}).get(metric):
                raise
        point_maps[metric] = {p.end: p for p in points}
        override_ends = set((duration_overrides or {}).get(metric, {}).keys())
        available_ends[metric] = set(point_maps[metric]) | override_ends

    common_ends: set[str] | None = None
    for ends in available_ends.values():
        common_ends = set(ends) if common_ends is None else common_ends & ends
    if not common_ends or len(common_ends) < years:
        detail = {k: sorted(v)[-5:] for k, v in available_ends.items()}
        raise ValueError(f"Fewer than {years} common annual periods across required metrics: {detail}")
    selected_ends = sorted(common_ends)[-years:]

    rows: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    for end in selected_ends:
        row: dict[str, Any] = {"period_end": end}
        for metric in DURATION_TAGS:
            override_record = _override(duration_overrides, metric, end)
            if override_record is not None:
                row[metric] = float(override_record["value_usd_millions"])
                sources.append(_source_from_override(override_record, metric, end))
            else:
                p = point_maps[metric].get(end)
                if p is None:
                    raise ValueError(f"Missing annual {metric} evidence for {end}")
                row[metric] = p.value / 1e6
                sources.append(p.source_row())
        row["ebitda_proxy"] = row["operating_income"] + row["depreciation_amortization"]
        row["free_cash_flow"] = row["cash_from_operations"] - row["capital_expenditures"]
        row["ebitda_margin"] = row["ebitda_proxy"] / row["revenue"]
        row["fcf_margin"] = row["free_cash_flow"] / row["revenue"]
        row["ebitda_interest_coverage"] = row["ebitda_proxy"] / row["interest_expense"] if row["interest_expense"] > 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(sources)


def _duration_value_and_source(
    companyfacts: dict[str, Any],
    metric: str,
    end: str,
    forms: tuple[str, ...],
    min_days: int,
    max_days: int,
    duration_overrides: DurationOverrides | None,
) -> tuple[float, dict[str, Any]]:
    record = _override(duration_overrides, metric, end)
    if record is not None:
        return float(record["value_usd_millions"]), _source_from_override(record, metric, end)
    point = duration_point_ending(companyfacts, metric, end, forms, min_days, max_days)
    return point.value / 1e6, point.source_row()


def build_ttm_metrics(
    companyfacts: dict[str, Any],
    latest_10q_report_date: str,
    latest_10k_report_date: str,
    duration_overrides: DurationOverrides | None = None,
) -> tuple[dict[str, float], pd.DataFrame]:
    """Bridge latest FY to TTM: latest FY + current YTD - prior-year comparable YTD."""
    q_end = date.fromisoformat(latest_10q_report_date)
    prior_q_end = q_end.replace(year=q_end.year - 1).isoformat()
    sources: list[dict[str, Any]] = []
    ttm: dict[str, float] = {}
    for metric in DURATION_TAGS:
        fy_value, fy_source = _duration_value_and_source(companyfacts, metric, latest_10k_report_date, ("10-K",), 300, 430, duration_overrides)
        current_value, current_source = _duration_value_and_source(companyfacts, metric, latest_10q_report_date, ("10-Q",), 150, 220, duration_overrides)
        prior_value, prior_source = _duration_value_and_source(companyfacts, metric, prior_q_end, ("10-Q", "10-K"), 150, 220, duration_overrides)
        ttm[metric] = fy_value + current_value - prior_value
        for source, role in ((fy_source, "latest_fy"), (current_source, "current_ytd"), (prior_source, "prior_ytd")):
            row = dict(source)
            row["ttm_bridge_role"] = role
            sources.append(row)

    ttm["ebitda_proxy"] = ttm["operating_income"] + ttm["depreciation_amortization"]
    ttm["free_cash_flow"] = ttm["cash_from_operations"] - ttm["capital_expenditures"]
    ttm["ebitda_margin"] = ttm["ebitda_proxy"] / ttm["revenue"]
    ttm["fcf_margin"] = ttm["free_cash_flow"] / ttm["revenue"]
    ttm["ebitda_interest_coverage"] = ttm["ebitda_proxy"] / ttm["interest_expense"] if ttm["interest_expense"] > 0 else np.nan
    return ttm, pd.DataFrame(sources)


def current_balance_sheet(companyfacts: dict[str, Any]) -> tuple[dict[str, float], pd.DataFrame]:
    points = {metric: latest_instant_point(companyfacts, metric) for metric in INSTANT_TAGS}
    ends = {p.end for p in points.values()}
    if len(ends) != 1:
        raise ValueError(f"Current balance-sheet metrics do not share one period end: {ends}")
    values = {metric: p.value / 1e6 for metric, p in points.items()}
    values["gross_debt"] = values["debt_current"] + values["debt_noncurrent"]
    values["net_debt"] = values["gross_debt"] - values["cash"]
    values["period_end"] = next(iter(ends))
    return values, pd.DataFrame([p.source_row() for p in points.values()])
