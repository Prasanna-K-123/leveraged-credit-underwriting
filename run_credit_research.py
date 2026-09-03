from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd

from credit_underwriting.facts import build_annual_history, build_ttm_metrics, current_balance_sheet
from credit_underwriting.filing import (
    extract_cash_flow_metric_series_millions,
    extract_covenant_liquidity_context,
    extract_debt_stack_millions,
    extract_income_statement_metric_series_millions,
    extract_maturity_schedule_millions,
    fetch_filing_html,
)
from credit_underwriting.reporting import build_credit_memo, plot_recovery_heatmap, plot_scenario_leverage
from credit_underwriting.sec_data import fetch_sec_bundle, latest_filing
from credit_underwriting.underwriting import (
    current_credit_metrics,
    debt_capacity_grid,
    maturity_coverage,
    recovery_waterfall,
    scenario_analysis,
)

CIK = "0000815097"
TICKER = "CCL"


def _same_fiscal_day(report_date: str, year: int) -> str:
    d = date.fromisoformat(report_date)
    return d.replace(year=year).isoformat()


def _filing_table_override(metric: str, end: str, value_millions: float, filing: dict[str, str], snapshot, label: str) -> dict:
    return {
        "value_usd_millions": float(value_millions),
        "source_row": {
            "metric": metric,
            "source_type": "sec_filing_table",
            "xbrl_tag": None,
            "filing_table_label": label,
            "unit": "USD",
            "value_raw": float(value_millions) * 1e6,
            "value_usd_millions": float(value_millions),
            "start": None,
            "end": end,
            "filed": filing["filed"],
            "accession": filing["accession"],
            "form": filing["form"],
            "fy": int(end[:4]),
            "fp": "FY" if filing["form"] == "10-K" else "YTD",
            "source_url": filing["url"],
            "source_sha256": snapshot.sha256,
            "captured_at_utc": snapshot.captured_at_utc,
        },
    }


def _add_series_overrides(duration_overrides: dict, metric: str, values_by_year: dict[str, float], report_date: str, filing: dict[str, str], snapshot, label: str) -> None:
    duration_overrides.setdefault(metric, {})
    for year, value in values_by_year.items():
        end = _same_fiscal_day(report_date, int(year))
        duration_overrides[metric][end] = _filing_table_override(metric, end, value, filing, snapshot, label)


def main() -> None:
    root = Path(__file__).resolve().parent
    raw_dir = root / "data" / "raw"
    results = root / "results"
    reports = root / "reports"
    figures = reports / "figures"
    for p in (raw_dir, results, reports, figures):
        p.mkdir(parents=True, exist_ok=True)

    companyfacts, submissions, source_snapshot = fetch_sec_bundle(CIK, raw_dir)
    company_name = companyfacts.get("entityName", submissions.get("name", "Carnival"))
    latest_10k = latest_filing(submissions, "10-K")
    latest_10q = latest_filing(submissions, "10-Q")

    annual_html, annual_filing_snapshot = fetch_filing_html(latest_10k, raw_dir)
    quarterly_html, quarterly_filing_snapshot = fetch_filing_html(latest_10q, raw_dir)

    annual_da = extract_cash_flow_metric_series_millions(annual_html)
    ytd_da = extract_cash_flow_metric_series_millions(quarterly_html)
    annual_year = int(latest_10k["report_date"][:4])
    quarterly_year = int(latest_10q["report_date"][:4])
    annual_interest = extract_income_statement_metric_series_millions(
        annual_html,
        expected_years=(str(annual_year), str(annual_year - 1), str(annual_year - 2)),
    )
    ytd_interest = extract_income_statement_metric_series_millions(
        quarterly_html,
        expected_years=(str(quarterly_year), str(quarterly_year - 1)),
    )

    duration_overrides: dict = {}
    _add_series_overrides(duration_overrides, "depreciation_amortization", annual_da, latest_10k["report_date"], latest_10k, annual_filing_snapshot, "Depreciation and amortization")
    _add_series_overrides(duration_overrides, "depreciation_amortization", ytd_da, latest_10q["report_date"], latest_10q, quarterly_filing_snapshot, "Depreciation and amortization")
    _add_series_overrides(duration_overrides, "interest_expense", annual_interest, latest_10k["report_date"], latest_10k, annual_filing_snapshot, "Interest expense, net of capitalized interest")
    _add_series_overrides(duration_overrides, "interest_expense", ytd_interest, latest_10q["report_date"], latest_10q, quarterly_filing_snapshot, "Interest expense, net of capitalized interest")

    annual, annual_sources = build_annual_history(companyfacts, years=3, duration_overrides=duration_overrides)
    ttm, ttm_sources = build_ttm_metrics(companyfacts, latest_10q["report_date"], latest_10k["report_date"], duration_overrides=duration_overrides)
    balance, balance_sources = current_balance_sheet(companyfacts)

    debt_stack = extract_debt_stack_millions(quarterly_html)
    maturities = extract_maturity_schedule_millions(quarterly_html)
    context = extract_covenant_liquidity_context(quarterly_html)

    current = current_credit_metrics(ttm, balance, debt_stack, context)
    scenarios = scenario_analysis(ttm, debt_stack)
    capacity = debt_capacity_grid(ttm["ebitda_proxy"], ttm["interest_expense"], debt_stack["gross_debt"])
    recovery = recovery_waterfall(scenarios, debt_stack, balance["cash"])
    maturity = maturity_coverage(maturities, current["cash_plus_undrawn_revolver"])

    balance_debt_carrying_value = balance["debt_current"] + balance["debt_noncurrent"]
    debt_carrying_value_gap = balance_debt_carrying_value - debt_stack["net_debt_reported"]
    debt_note_current_noncurrent_gap = debt_stack["current_portion_long_term_debt"] + debt_stack["long_term_debt"] - debt_stack["net_debt_reported"]
    maturity_total_gap = maturities["Total"] - debt_stack["gross_debt"]
    capital_stack_gap = debt_stack["secured_subsidiary_guaranteed"] + debt_stack["unsecured_subsidiary_guaranteed"] + debt_stack["unsecured_no_subsidiary_guarantee"] - debt_stack["gross_debt"]

    source_register = pd.concat([
        annual_sources.assign(evidence_set="annual_history"),
        ttm_sources.assign(evidence_set="ttm_bridge"),
        balance_sources.assign(evidence_set="balance_sheet"),
    ], ignore_index=True)
    source_register.to_csv(results / "source_register.csv", index=False)
    annual.to_csv(results / "annual_history.csv", index=False)
    pd.DataFrame([ttm]).to_csv(results / "ttm_metrics.csv", index=False)
    pd.DataFrame([balance]).to_csv(results / "balance_sheet_snapshot.csv", index=False)
    pd.DataFrame([debt_stack]).to_csv(results / "debt_stack.csv", index=False)
    pd.DataFrame([context]).to_csv(results / "covenant_liquidity_context.csv", index=False)
    pd.DataFrame([{"maturity_bucket": k, "principal_millions": v} for k, v in maturities.items()]).to_csv(results / "maturity_schedule.csv", index=False)
    scenarios.to_csv(results / "scenario_analysis.csv", index=False)
    capacity.to_csv(results / "debt_capacity_sensitivity.csv", index=False)
    recovery.to_csv(results / "recovery_waterfall_sensitivity.csv", index=False)
    maturity.to_csv(results / "maturity_liquidity_coverage.csv", index=False)

    filing_extract = {
        "latest_10k": latest_10k,
        "latest_10q": latest_10q,
        "annual_filing_snapshot": annual_filing_snapshot.__dict__,
        "quarterly_filing_snapshot": quarterly_filing_snapshot.__dict__,
        "depreciation_amortization_annual_millions": annual_da,
        "depreciation_amortization_ytd_millions": ytd_da,
        "interest_expense_annual_millions": annual_interest,
        "interest_expense_ytd_millions": ytd_interest,
        "debt_stack_millions": debt_stack,
        "maturity_schedule_millions": maturities,
        "covenant_liquidity_context": context,
    }
    (results / "filing_extractions.json").write_text(json.dumps(filing_extract, indent=2), encoding="utf-8")

    summary = {
        "project": "FLAGSHIP-CREDIT-001",
        "issuer": company_name,
        "ticker": TICKER,
        "cik": CIK,
        "source_snapshot": source_snapshot.__dict__,
        "latest_10k": latest_10k,
        "latest_10q": latest_10q,
        "annual_filing_snapshot": annual_filing_snapshot.__dict__,
        "quarterly_filing_snapshot": quarterly_filing_snapshot.__dict__,
        "latest_balance_sheet_period": balance["period_end"],
        "ttm": ttm,
        "current_credit_metrics": current,
        "reconciliations": {
            "balance_sheet_debt_carrying_value_millions": balance_debt_carrying_value,
            "filing_net_debt_carrying_value_millions": debt_stack["net_debt_reported"],
            "carrying_value_gap_millions": debt_carrying_value_gap,
            "debt_note_current_plus_noncurrent_gap_millions": debt_note_current_noncurrent_gap,
            "maturity_total_minus_gross_debt_millions": maturity_total_gap,
            "capital_stack_sum_minus_gross_debt_millions": capital_stack_gap,
        },
        "evidence_boundary": [
            "TTM values are mechanical SEC-fact/filing-table bridges, not company guidance.",
            "D&A and recent interest expense are read from visible primary SEC statements where companyfacts is missing or stale; accession and file hashes are retained.",
            "EBITDA proxy is operating income plus D&A, not company-defined adjusted EBITDA.",
            "Covenant coverage shown in the filing is not recomputed from the simple public-data EBITDA proxy.",
            "Forward scenarios are illustrative stresses, not forecasts.",
            "Recovery waterfall is a simplified debt-only sensitivity, not a legal recovery estimate.",
        ],
    }
    (results / "research_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    memo = build_credit_memo(company_name, TICKER, source_snapshot.__dict__, latest_10q, current, ttm, debt_stack, context, maturities, scenarios, recovery)
    (reports / "credit_underwriting_memo.md").write_text(memo, encoding="utf-8")
    plot_scenario_leverage(scenarios, figures / "scenario_leverage.png")
    plot_recovery_heatmap(recovery, figures / "unsecured_guaranteed_recovery.png")

    if abs(debt_carrying_value_gap) > 2.0:
        raise RuntimeError(f"Debt carrying-value reconciliation failed: {debt_carrying_value_gap:.2f}m")
    if abs(debt_note_current_noncurrent_gap) > 2.0:
        raise RuntimeError(f"Debt note current/non-current reconciliation failed: {debt_note_current_noncurrent_gap:.2f}m")
    if abs(maturity_total_gap) > 2.0:
        raise RuntimeError(f"Maturity total does not reconcile to gross debt: {maturity_total_gap:.2f}m")
    if abs(capital_stack_gap) > 2.0:
        raise RuntimeError(f"Capital-stack debt buckets do not reconcile to gross debt: {capital_stack_gap:.2f}m")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
