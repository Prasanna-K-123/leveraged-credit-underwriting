from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from credit_underwriting.underwriting import (
    current_credit_metrics,
    debt_capacity_grid,
    maturity_coverage,
    recovery_waterfall,
    scenario_analysis,
)

EXPECTED_CURRENT = {
    "gross_debt": 25570.0,
    "cash": 2243.0,
    "net_debt": 23327.0,
    "ttm_revenue": 27311.0,
    "ttm_ebitda_proxy": 7327.0,
    "ttm_free_cash_flow": 3200.0,
    "ttm_interest_expense": 1208.0,
    "gross_leverage": 3.4898321277466904,
    "net_leverage": 3.1837041080933535,
    "ebitda_interest_coverage_proxy": 6.065397350993377,
    "fcf_to_gross_debt": 0.12514665623777865,
    "cash_plus_undrawn_revolver": 6743.0,
    "secured_debt": 3098.0,
    "secured_collateral_book_value": 22400.0,
    "collateral_book_value_to_secured_debt": 7.23047127178825,
    "proxy_vs_minimum_coverage_multiple": 2.0217991169977925,
}


def _assert_close(actual: float, expected: float, label: str) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=1e-9, abs_tol=1e-9):
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def _single_row(path: Path) -> dict:
    frame = pd.read_csv(path)
    if len(frame) != 1:
        raise AssertionError(f"expected one row in {path}, got {len(frame)}")
    return frame.iloc[0].to_dict()


def _assert_frame_close(actual: pd.DataFrame, expected_path: Path, label: str) -> None:
    expected = pd.read_csv(expected_path)
    if list(actual.columns) != list(expected.columns):
        raise AssertionError(f"{label}: column mismatch")
    if len(actual) != len(expected):
        raise AssertionError(f"{label}: row-count mismatch: expected {len(expected)}, got {len(actual)}")
    for column in expected.columns:
        left = actual[column].reset_index(drop=True)
        right = expected[column].reset_index(drop=True)
        if pd.api.types.is_numeric_dtype(right):
            if not np.allclose(
                pd.to_numeric(left, errors="coerce").to_numpy(dtype=float),
                pd.to_numeric(right, errors="coerce").to_numpy(dtype=float),
                rtol=1e-9,
                atol=1e-9,
                equal_nan=True,
            ):
                raise AssertionError(f"{label}: numeric mismatch in {column}")
        elif left.astype(str).tolist() != right.astype(str).tolist():
            raise AssertionError(f"{label}: value mismatch in {column}")


def _verify_derived_metrics(ttm: dict, annual: pd.DataFrame) -> None:
    rows = [("TTM", ttm)] + [(str(row["period_end"]), row.to_dict()) for _, row in annual.iterrows()]
    for label, row in rows:
        _assert_close(row["ebitda_proxy"], row["operating_income"] + row["depreciation_amortization"], f"{label} EBITDA proxy")
        _assert_close(row["free_cash_flow"], row["cash_from_operations"] - row["capital_expenditures"], f"{label} FCF proxy")
        _assert_close(row["ebitda_margin"], row["ebitda_proxy"] / row["revenue"], f"{label} EBITDA margin")
        _assert_close(row["fcf_margin"], row["free_cash_flow"] / row["revenue"], f"{label} FCF margin")
        _assert_close(row["ebitda_interest_coverage"], row["ebitda_proxy"] / row["interest_expense"], f"{label} coverage proxy")


def main() -> None:
    root = Path(__file__).resolve().parent
    ref = root / "reference"
    output = root / "results" / "reference_reproduction"
    output.mkdir(parents=True, exist_ok=True)

    ttm = _single_row(ref / "ttm_metrics.csv")
    balance = _single_row(ref / "balance_sheet_snapshot.csv")
    debt_stack = _single_row(ref / "debt_stack.csv")
    context = _single_row(ref / "covenant_liquidity_context.csv")
    annual = pd.read_csv(ref / "annual_history.csv")
    maturity_frame = pd.read_csv(ref / "maturity_schedule.csv")
    maturities = {str(row.maturity_bucket): float(row.principal_millions) for row in maturity_frame.itertuples()}

    _verify_derived_metrics(ttm, annual)

    current = current_credit_metrics(ttm, balance, debt_stack, context)
    if set(current) != set(EXPECTED_CURRENT):
        raise AssertionError("current-credit metric key set changed")
    for key, expected in EXPECTED_CURRENT.items():
        _assert_close(current[key], expected, f"current.{key}")

    scenarios = scenario_analysis(ttm, debt_stack)
    capacity = debt_capacity_grid(ttm["ebitda_proxy"], ttm["interest_expense"], debt_stack["gross_debt"])
    recovery = recovery_waterfall(scenarios, debt_stack, balance["cash"])
    maturity = maturity_coverage(maturities, current["cash_plus_undrawn_revolver"])

    _assert_frame_close(scenarios, ref / "scenario_analysis.csv", "scenario_analysis")
    _assert_frame_close(capacity, ref / "debt_capacity_sensitivity.csv", "debt_capacity_sensitivity")
    _assert_frame_close(recovery, ref / "recovery_waterfall_sensitivity.csv", "recovery_waterfall_sensitivity")
    _assert_frame_close(maturity, ref / "maturity_liquidity_coverage.csv", "maturity_liquidity_coverage")

    carrying_value = float(balance["debt_current"]) + float(balance["debt_noncurrent"])
    debt_note_carrying = float(debt_stack["current_portion_long_term_debt"]) + float(debt_stack["long_term_debt"])
    capital_stack = sum(float(debt_stack[k]) for k in (
        "secured_subsidiary_guaranteed",
        "unsecured_subsidiary_guaranteed",
        "unsecured_no_subsidiary_guarantee",
    ))
    _assert_close(carrying_value, 24889.0, "carrying-value debt")
    _assert_close(carrying_value - float(debt_stack["net_debt_reported"]), 0.0, "balance/debt-note carrying-value gap")
    _assert_close(debt_note_carrying - float(debt_stack["net_debt_reported"]), 0.0, "current/non-current debt-note gap")
    _assert_close(float(maturities["Total"]) - float(debt_stack["gross_debt"]), 0.0, "maturity/gross-principal gap")
    _assert_close(capital_stack - float(debt_stack["gross_debt"]), 1.0, "capital-stack rounding gap")

    sources = pd.read_csv(ref / "source_register.csv")
    observed_accessions = set(sources["accession"].dropna().astype(str))
    required_accessions = {"0000815097-26-000007", "0000815097-26-000096"}
    if not required_accessions.issubset(observed_accessions):
        raise AssertionError("source register lost one or both pinned SEC accessions")

    result = {
        "issuer": "Carnival Corporation Ltd.",
        "reference_capture_utc": "2026-09-02T11:08:55Z",
        "10k_accession": "0000815097-26-000007",
        "10q_accession": "0000815097-26-000096",
        "ttm_revenue_millions": float(ttm["revenue"]),
        "ttm_ebitda_proxy_millions": float(ttm["ebitda_proxy"]),
        "ttm_free_cash_flow_proxy_millions": float(ttm["free_cash_flow"]),
        "ttm_interest_expense_millions": float(ttm["interest_expense"]),
        "carrying_value_debt_millions": carrying_value,
        "gross_principal_debt_millions": float(debt_stack["gross_debt"]),
        "status": "PASS",
    }
    (output / "reference_verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
