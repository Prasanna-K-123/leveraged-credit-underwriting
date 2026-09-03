from credit_underwriting.filing import extract_income_statement_metric_series_millions


def test_interest_expense_series_annual_statement():
    html = """
    <html><body><table>
      <tr><td>CONSOLIDATED STATEMENTS OF INCOME</td></tr>
      <tr><td>Years Ended November 30</td><td>2025</td><td>2024</td><td>2023</td></tr>
      <tr><td>Operating Income</td><td>4,483</td><td>3,574</td><td>1,956</td></tr>
      <tr><td>Interest income</td><td>51</td><td>93</td><td>233</td></tr>
      <tr><td>Interest expense, net of capitalized interest</td><td>(1,349)</td><td>(1,755)</td><td>(2,066)</td></tr>
    </table></body></html>
    """
    assert extract_income_statement_metric_series_millions(html) == {
        "2025": 1349.0,
        "2024": 1755.0,
        "2023": 2066.0,
    }


def test_interest_expense_series_quarterly_prefers_ytd_columns():
    html = """
    <html><body><table>
      <tr><td>CONSOLIDATED STATEMENTS OF INCOME</td></tr>
      <tr><td>Three Months Ended May 31</td><td>2026</td><td>2025</td><td>Six Months Ended May 31</td><td>2026</td><td>2025</td></tr>
      <tr><td>Operating Income</td><td>900</td><td>800</td><td>1,500</td><td>1,300</td></tr>
      <tr><td>Interest income</td><td>10</td><td>12</td><td>24</td><td>18</td></tr>
      <tr><td>Interest expense, net of capitalized interest</td><td>(285)</td><td>(341)</td><td>(577)</td><td>(718)</td></tr>
    </table></body></html>
    """
    assert extract_income_statement_metric_series_millions(html) == {
        "2026": 577.0,
        "2025": 718.0,
    }
