import numpy as np

from credit_underwriting.facts import annual_duration_points, latest_instant_point
from credit_underwriting.filing import (
    extract_cash_flow_metric_series_millions,
    extract_covenant_liquidity_context,
    extract_debt_stack_millions,
    extract_maturity_schedule_millions,
)
from credit_underwriting.underwriting import debt_capacity_grid, recovery_waterfall, scenario_analysis


def _fact(values):
    return {"units": {"USD": values}}


def test_equivalent_taxonomy_selection_prefers_current_concept():
    companyfacts = {
        "facts": {
            "us-gaap": {
                "Revenues": _fact([
                    {"val": 100.0, "start": "2017-12-01", "end": "2018-11-30", "filed": "2019-01-01", "accn": "old", "form": "10-K", "fy": 2018, "fp": "FY"}
                ]),
                "RevenueFromContractWithCustomerExcludingAssessedTax": _fact([
                    {"val": 300.0, "start": "2024-12-01", "end": "2025-11-30", "filed": "2026-01-01", "accn": "new", "form": "10-K", "fy": 2025, "fp": "FY"}
                ]),
                "LongTermDebtCurrent": _fact([
                    {"val": 10.0, "end": "2022-11-30", "filed": "2023-01-01", "accn": "old-debt", "form": "10-K", "fy": 2022, "fp": "FY"}
                ]),
                "LongTermDebtAndFinanceLeaseObligationsCurrent": _fact([
                    {"val": 20.0, "end": "2026-05-31", "filed": "2026-06-26", "accn": "new-debt", "form": "10-Q", "fy": 2026, "fp": "Q2"}
                ]),
            }
        }
    }
    revenue = annual_duration_points(companyfacts, "revenue")
    assert len(revenue) == 1
    assert revenue[0].tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert revenue[0].end == "2025-11-30"
    debt = latest_instant_point(companyfacts, "debt_current")
    assert debt.tag == "LongTermDebtAndFinanceLeaseObligationsCurrent"
    assert debt.end == "2026-05-31"


def test_scenario_severity_is_monotonic():
    ttm = {
        "revenue": 30000.0,
        "ebitda_margin": 0.20,
        "fcf_margin": 0.08,
        "interest_expense": 1200.0,
    }
    debt = {"gross_debt": 25000.0}
    df = scenario_analysis(ttm, debt).set_index("scenario")
    assert df.loc["base", "revenue"] > df.loc["downside", "revenue"] > df.loc["severe", "revenue"]
    assert df.loc["base", "ebitda_proxy"] > df.loc["downside", "ebitda_proxy"] > df.loc["severe", "ebitda_proxy"]
    assert df.loc["base", "gross_leverage"] < df.loc["downside", "gross_leverage"] < df.loc["severe", "gross_leverage"]
    assert df.loc["base", "ebitda_interest_coverage_proxy"] > df.loc["downside", "ebitda_interest_coverage_proxy"] > df.loc["severe", "ebitda_interest_coverage_proxy"]


def test_recovery_is_bounded_and_monotonic_in_value():
    ttm = {"revenue": 30000.0, "ebitda_margin": 0.20, "fcf_margin": 0.08, "interest_expense": 1200.0}
    debt = {
        "gross_debt": 25000.0,
        "secured_subsidiary_guaranteed": 3000.0,
        "unsecured_subsidiary_guaranteed": 19000.0,
        "unsecured_no_subsidiary_guarantee": 3000.0,
    }
    scenarios = scenario_analysis(ttm, debt)
    rec = recovery_waterfall(scenarios, debt, cash=1500.0)
    cols = ["secured_recovery_pct", "unsecured_guaranteed_recovery_pct", "unsecured_no_guarantee_recovery_pct"]
    for col in cols:
        assert ((rec[col] >= 0) & (rec[col] <= 1)).all()
        for _, part in rec.groupby("scenario"):
            ordered = part.sort_values("ev_ebitda_multiple")[col].to_numpy()
            assert np.all(np.diff(ordered) >= -1e-12)
    assert (rec["secured_recovery_pct"] >= rec["unsecured_guaranteed_recovery_pct"]).all()
    assert (rec["unsecured_guaranteed_recovery_pct"] >= rec["unsecured_no_guarantee_recovery_pct"]).all()


def test_debt_capacity_has_correct_directions():
    df = debt_capacity_grid(5000.0, 1000.0, 25000.0)
    lev = df[df["constraint"] == "gross_leverage"].sort_values("threshold")
    cov = df[df["constraint"] == "ebitda_interest_coverage"].sort_values("threshold")
    assert np.all(np.diff(lev["debt_capacity"]) > 0)
    assert np.all(np.diff(cov["debt_capacity"]) < 0)


def test_cash_flow_metric_series_maps_visible_period_columns():
    annual_html = """
    <html><body><table>
      <tr><td>CARNIVAL CORPORATION LTD.</td></tr>
      <tr><td>CONSOLIDATED STATEMENTS OF CASH FLOWS</td></tr>
      <tr><td>Years Ended November 30</td><td>2025</td><td>2024</td><td>2023</td></tr>
      <tr><td>OPERATING ACTIVITIES</td></tr>
      <tr><td>Net income (loss)</td><td>2,760</td><td>1,916</td><td>(74)</td></tr>
      <tr><td>Depreciation and amortization</td><td>2,790</td><td>2,557</td><td>2,370</td></tr>
    </table></body></html>
    """
    quarterly_html = """
    <html><body><table>
      <tr><td>CONSOLIDATED STATEMENTS OF CASH FLOWS</td></tr>
      <tr><td>Six Months Ended May 31</td><td>2026</td><td>2025</td></tr>
      <tr><td>OPERATING ACTIVITIES</td></tr>
      <tr><td>Net income</td><td>801</td><td>494</td></tr>
      <tr><td>Depreciation and amortization</td><td>1,419</td><td>1,346</td></tr>
    </table></body></html>
    """
    annual = extract_cash_flow_metric_series_millions(annual_html)
    ytd = extract_cash_flow_metric_series_millions(quarterly_html)
    assert annual == {"2025": 2790.0, "2024": 2557.0, "2023": 2370.0}
    assert ytd == {"2026": 1419.0, "2025": 1346.0}


def test_filing_extractors_on_minimal_sec_like_html():
    html = """
    <html><body>
    <table>
      <tr><td>Secured Subsidiary Guaranteed</td></tr>
      <tr><td>Total Secured Subsidiary Guaranteed</td><td>3,098</td><td>3,098</td></tr>
      <tr><td>Total Unsecured Subsidiary Guaranteed</td><td>19,674</td><td>21,411</td></tr>
      <tr><td>Total Unsecured (No Subsidiary Guarantee)</td><td>2,799</td><td>2,874</td></tr>
      <tr><td>Total Debt</td><td>25,570</td><td>27,383</td></tr>
      <tr><td>Total Debt, net of unamortized debt issuance costs and discounts</td><td>24,889</td><td>26,640</td></tr>
      <tr><td>Less: Current portion of long-term debt</td><td>(1,471)</td><td>(2,603)</td></tr>
      <tr><td>Long-Term Debt</td><td>23,418</td><td>24,037</td></tr>
    </table>
    <table>
      <tr><td>Year</td><td>Principal Payments</td></tr>
      <tr><td>Remainder of 2026</td><td>745</td></tr>
      <tr><td>2027</td><td>2,523</td></tr>
      <tr><td>2028</td><td>3,967</td></tr>
      <tr><td>2029</td><td>4,144</td></tr>
      <tr><td>2030</td><td>2,895</td></tr>
      <tr><td>Thereafter</td><td>11,295</td></tr>
      <tr><td>Total</td><td>25,570</td></tr>
    </table>
    <p>we had $4.5 billion available for borrowings under the Revolving Facility</p>
    <p>combined net book value of approximately $22.4 billion, including $20.6 billion related to ships and certain assets</p>
    <p>Maintain minimum interest coverage (adjusted EBITDA to consolidated net interest charges, as defined in the agreements) at a ratio of not less than 3.0 to 1.0</p>
    <p>Limit our debt to capital (as defined in the agreements) percentage to a percentage not to exceed 65%</p>
    <p>Maintain minimum liquidity of $1.5 billion</p>
    </body></html>
    """
    debt = extract_debt_stack_millions(html)
    assert debt["gross_debt"] == 25570.0
    assert debt["secured_subsidiary_guaranteed"] == 3098.0
    maturity = extract_maturity_schedule_millions(html)
    assert maturity["2027"] == 2523.0 and maturity["Total"] == 25570.0
    context = extract_covenant_liquidity_context(html)
    assert context["minimum_interest_coverage_ratio"] == 3.0
    assert context["maximum_debt_to_capital_pct"] == 65.0
    assert context["minimum_liquidity_millions"] == 1500.0
    assert context["undrawn_revolver_millions"] == 4500.0
    assert context["secured_collateral_book_value_millions"] == 22400.0
