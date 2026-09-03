from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import requests


@dataclass(frozen=True)
class FilingSnapshot:
    captured_at_utc: str
    url: str
    sha256: str
    filing_date: str
    report_date: str
    accession: str


def _headers() -> dict[str, str]:
    return {
        "User-Agent": os.environ.get("SEC_USER_AGENT", "Prasanna K prasannak0911@gmail.com academic credit research"),
        "Accept-Encoding": "gzip, deflate",
    }


def _soup(html: str) -> BeautifulSoup:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(html, "lxml")


def fetch_filing_html(filing: dict[str, str], raw_dir: Path) -> tuple[str, FilingSnapshot]:
    response = requests.get(filing["url"], headers=_headers(), timeout=45)
    response.raise_for_status()
    raw = response.content
    raw_dir.mkdir(parents=True, exist_ok=True)
    accession_compact = filing["accession"].replace("-", "")
    name = f"{filing['form']}_{filing['report_date']}_{accession_compact}.html"
    (raw_dir / name).write_bytes(raw)
    snap = FilingSnapshot(
        captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        url=filing["url"],
        sha256=hashlib.sha256(raw).hexdigest(),
        filing_date=filing["filed"],
        report_date=filing["report_date"],
        accession=filing["accession"],
    )
    snapshot_name = f"filing_snapshot_{filing['form'].replace('-', '').lower()}_{filing['report_date']}_{accession_compact}.json"
    (raw_dir / snapshot_name).write_text(json.dumps(snap.__dict__, indent=2), encoding="utf-8")
    return raw.decode(response.encoding or "utf-8", errors="replace"), snap


def _parse_numeric_token(token: str) -> float:
    cleaned = token.replace("$", "").replace(",", "").strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    value = float(cleaned)
    return -value if negative else value


def _number_tokens(cells: list[str]) -> list[float]:
    out: list[float] = []
    for cell in cells:
        cleaned = cell.replace("$", "").replace(",", "").strip()
        if re.fullmatch(r"\(?-?\d+(?:\.\d+)?\)?", cleaned):
            out.append(_parse_numeric_token(cell))
    return out


def _numbers_after_label(text: str, labels: tuple[str, ...]) -> list[float]:
    lower = text.lower()
    positions = [(lower.find(label.lower()), label) for label in labels if lower.find(label.lower()) >= 0]
    if not positions:
        return []
    pos, label = min(positions, key=lambda x: x[0])
    tail = text[pos + len(label):]
    tokens = re.findall(r"\(?-?\$?\s*\d[\d,]*(?:\.\d+)?\)?", tail)
    return [_parse_numeric_token(token) for token in tokens]


def _find_table(soup: BeautifulSoup, required_terms: tuple[str, ...]):
    for table in soup.find_all("table"):
        text = " ".join(table.stripped_strings)
        if all(term.lower() in text.lower() for term in required_terms):
            return table
    raise ValueError(f"Could not find filing table containing {required_terms}")


def _years_before_row(table, target_row, unique: bool) -> list[str]:
    years: list[str] = []
    for tr in table.find_all("tr"):
        if tr is target_row:
            break
        text = " ".join(tr.stripped_strings)
        for year in re.findall(r"\b20\d{2}\b", text):
            if not unique or year not in years:
                years.append(year)
    return years


def _unique_years_in_table(table) -> list[str]:
    years: list[str] = []
    for year in re.findall(r"\b20\d{2}\b", " ".join(table.stripped_strings)):
        if year not in years:
            years.append(year)
    return years


def extract_cash_flow_metric_series_millions(
    html: str,
    labels: tuple[str, ...] = ("Depreciation and amortization", "Depreciation and amortization expense"),
) -> dict[str, float]:
    soup = _soup(html)
    candidate_tables = []
    for table in soup.find_all("table"):
        text = " ".join(table.stripped_strings)
        lower = text.lower()
        if "operating activities" not in lower or "net income" not in lower:
            continue
        if any(label.lower() in lower for label in labels):
            candidate_tables.append(table)
    if not candidate_tables:
        raise ValueError(f"Could not find cash-flow table containing any of {labels}")

    for table in candidate_tables:
        for tr in table.find_all("tr"):
            cells = [" ".join(td.stripped_strings) for td in tr.find_all(["th", "td"])]
            joined = " ".join(cells)
            if not any(label.lower() in joined.lower() for label in labels):
                continue
            values = _number_tokens(cells)
            if len(values) < 2:
                values = _numbers_after_label(joined, labels)
            years = _years_before_row(table, tr, unique=True)
            if len(years) < len(values):
                years = _unique_years_in_table(table)
            if len(values) < 2 or len(years) < len(values):
                continue
            selected_years = years[: len(values)] if len(years) == len(values) else years[-len(values):]
            series = {year: abs(float(value)) for year, value in zip(selected_years, values)}
            if len(series) == len(values):
                return series
    raise ValueError(f"Cash-flow metric row found but period/value mapping failed for {labels}")


def extract_income_statement_metric_series_millions(
    html: str,
    labels: tuple[str, ...] = ("Interest expense, net of capitalized interest",),
    expected_years: tuple[str, ...] | None = None,
) -> dict[str, float]:
    soup = _soup(html)
    candidate_tables = []
    for table in soup.find_all("table"):
        text = " ".join(table.stripped_strings)
        lower = text.lower()
        if "operating income" not in lower or "interest income" not in lower:
            continue
        if any(label.lower() in lower for label in labels):
            candidate_tables.append(table)
    if not candidate_tables:
        raise ValueError(f"Could not find income-statement table containing any of {labels}")

    for table in candidate_tables:
        table_years = _unique_years_in_table(table)
        for tr in table.find_all("tr"):
            cells = [" ".join(td.stripped_strings) for td in tr.find_all(["th", "td"])]
            joined = " ".join(cells)
            if not any(label.lower() in joined.lower() for label in labels):
                continue
            values = _number_tokens(cells)
            if len(values) < 2:
                values = _numbers_after_label(joined, labels)
            if len(values) < 2:
                continue
            if expected_years:
                if len(values) < len(expected_years):
                    continue
                selected_values = values[-len(expected_years):]
                return {year: abs(float(value)) for year, value in zip(expected_years, selected_values)}
            preceding_years = _years_before_row(table, tr, unique=False)
            if len(preceding_years) >= len(values):
                selected_years = preceding_years[-len(values):]
                series: dict[str, float] = {}
                for year, value in zip(selected_years, values):
                    series[year] = abs(float(value))
                if len(series) >= 2:
                    return series
            if len(table_years) >= 2 and len(values) == len(table_years):
                return {year: abs(float(value)) for year, value in zip(table_years, values)}
            if len(table_years) >= 2 and len(values) >= 4:
                return {table_years[0]: abs(float(values[-2])), table_years[1]: abs(float(values[-1]))}
            if len(table_years) >= len(values):
                return {year: abs(float(value)) for year, value in zip(table_years[: len(values)], values)}
    raise ValueError(f"Income-statement metric row found but period/value mapping failed for {labels}")


def extract_debt_stack_millions(html: str) -> dict[str, float]:
    soup = _soup(html)
    table = _find_table(soup, ("Secured Subsidiary Guaranteed", "Total Debt"))
    targets = {
        "secured_subsidiary_guaranteed": "Total Secured Subsidiary Guaranteed",
        "unsecured_subsidiary_guaranteed": "Total Unsecured Subsidiary Guaranteed",
        "unsecured_no_subsidiary_guarantee": "Total Unsecured (No Subsidiary Guarantee)",
        "gross_debt": "Total Debt",
        "net_debt_reported": "Total Debt, net of unamortized debt issuance costs and discounts",
        "current_portion_long_term_debt": "Current portion of long-term debt",
        "long_term_debt": "Long-Term Debt",
    }
    result: dict[str, float] = {}
    for key, label in targets.items():
        matched = None
        for tr in table.find_all("tr"):
            cells = [" ".join(td.stripped_strings) for td in tr.find_all(["th", "td"])]
            if not cells:
                continue
            row_label = cells[0].strip().lower()
            joined = " ".join(cells)
            # "Long-Term Debt" is a suffix of "Current portion of long-term debt".
            # Require the actual row label for this target so the current-debt row cannot
            # silently masquerade as non-current debt.
            if key == "long_term_debt":
                row_matches = row_label.startswith("long-term debt") and "current portion" not in row_label
            else:
                row_matches = label.lower() in joined.lower()
            if row_matches:
                nums = _number_tokens(cells)
                if not nums:
                    nums = _numbers_after_label(joined, (label,))
                if nums:
                    matched = abs(nums[0])
                    break
        if matched is None:
            raise ValueError(f"Debt-table row not found or not numeric: {label}")
        result[key] = matched
    return result


def extract_maturity_schedule_millions(html: str) -> dict[str, float]:
    soup = _soup(html)
    table = _find_table(soup, ("Principal Payments", "Thereafter"))
    schedule: dict[str, float] = {}
    for tr in table.find_all("tr"):
        cells = [" ".join(td.stripped_strings) for td in tr.find_all(["th", "td"])]
        joined = " ".join(cells)
        label_match = re.search(r"(Remainder of \d{4}|20\d{2}|Thereafter|Total)", joined, flags=re.I)
        nums = _number_tokens(cells)
        if not nums and label_match:
            nums = _numbers_after_label(joined, (label_match.group(1),))
        if not label_match or not nums:
            continue
        label = label_match.group(1)
        schedule[label] = abs(nums[-1])
    if "Total" not in schedule or len(schedule) < 5:
        raise ValueError(f"Maturity schedule extraction incomplete: {schedule}")
    return schedule


def _extract_amount_billion(text: str, pattern: str, label: str) -> float:
    m = re.search(pattern, text, flags=re.I | re.S)
    if not m:
        raise ValueError(f"Could not parse {label}")
    return float(m.group(1)) * 1000.0


def extract_covenant_liquidity_context(html: str) -> dict[str, Any]:
    soup = _soup(html)
    text = " ".join(soup.stripped_strings)

    coverage = re.search(r"minimum interest coverage.*?not less than\s*([0-9.]+)\s*(?:to|:)\s*1(?:\.0)?", text, flags=re.I | re.S)
    debt_cap = re.search(r"debt to capital.*?not\s+(?:to\s+)?exceed\s*([0-9.]+)\s*%", text, flags=re.I | re.S)
    if not coverage or not debt_cap:
        raise ValueError("Could not parse key covenant ratios")

    minimum_liquidity = _extract_amount_billion(text, r"minimum liquidity(?: requirement)?(?: of| was)?\s*(?:at least\s*)?\$\s*([0-9.]+)\s*billion", "minimum liquidity")
    revolver = _extract_amount_billion(text, r"(?:we\s+)?had\s*\$\s*([0-9.]+)\s*billion available for borrowings under the Revolving Facility", "revolver availability")
    collateral = _extract_amount_billion(text, r"combined net book value of approximately\s*\$\s*([0-9.]+)\s*billion", "collateral book value")
    ship_collateral = _extract_amount_billion(text, r"including\s*\$\s*([0-9.]+)\s*billion related to ships and certain assets", "ship collateral book value")

    return {
        "minimum_interest_coverage_ratio": float(coverage.group(1)),
        "maximum_debt_to_capital_pct": float(debt_cap.group(1)),
        "minimum_liquidity_millions": minimum_liquidity,
        "undrawn_revolver_millions": revolver,
        "secured_collateral_book_value_millions": collateral,
        "ship_collateral_book_value_millions": ship_collateral,
        "covenant_calculation_warning": "Reported agreement definitions differ from simple public-data proxies; do not claim covenant headroom from proxy ratios.",
    }
