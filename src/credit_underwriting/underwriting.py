from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Scenario:
    name: str
    revenue_multiplier: float
    ebitda_margin_delta: float
    fcf_margin_delta: float
    interest_cost_multiplier: float


SCENARIOS = (
    Scenario("base", 1.03, 0.000, 0.000, 1.00),
    Scenario("downside", 0.90, -0.030, -0.050, 1.10),
    Scenario("severe", 0.80, -0.060, -0.100, 1.25),
)


def current_credit_metrics(ttm: dict[str, float], balance: dict[str, float], debt_stack: dict[str, float], context: dict[str, float]) -> dict[str, float]:
    gross_debt = float(debt_stack["gross_debt"])
    cash = float(balance["cash"])
    net_debt = gross_debt - cash
    ebitda = float(ttm["ebitda_proxy"])
    interest = float(ttm["interest_expense"])
    fcf = float(ttm["free_cash_flow"])
    secured = float(debt_stack["secured_subsidiary_guaranteed"])
    collateral = float(context["secured_collateral_book_value_millions"])
    revolver = float(context["undrawn_revolver_millions"])

    return {
        "gross_debt": gross_debt,
        "cash": cash,
        "net_debt": net_debt,
        "ttm_revenue": float(ttm["revenue"]),
        "ttm_ebitda_proxy": ebitda,
        "ttm_free_cash_flow": fcf,
        "ttm_interest_expense": interest,
        "gross_leverage": gross_debt / ebitda,
        "net_leverage": net_debt / ebitda,
        "ebitda_interest_coverage_proxy": ebitda / interest,
        "fcf_to_gross_debt": fcf / gross_debt,
        "cash_plus_undrawn_revolver": cash + revolver,
        "secured_debt": secured,
        "secured_collateral_book_value": collateral,
        "collateral_book_value_to_secured_debt": collateral / secured if secured > 0 else np.nan,
        "proxy_vs_minimum_coverage_multiple": (ebitda / interest) / float(context["minimum_interest_coverage_ratio"]),
    }


def scenario_analysis(ttm: dict[str, float], debt_stack: dict[str, float]) -> pd.DataFrame:
    """Explicit illustrative downside assumptions; these are not management guidance."""
    revenue0 = float(ttm["revenue"])
    margin0 = float(ttm["ebitda_margin"])
    fcf_margin0 = float(ttm["fcf_margin"])
    interest0 = float(ttm["interest_expense"])
    gross_debt = float(debt_stack["gross_debt"])

    rows = []
    for s in SCENARIOS:
        revenue = revenue0 * s.revenue_multiplier
        ebitda_margin = max(-0.20, margin0 + s.ebitda_margin_delta)
        fcf_margin = max(-0.30, fcf_margin0 + s.fcf_margin_delta)
        ebitda = revenue * ebitda_margin
        fcf = revenue * fcf_margin
        interest = interest0 * s.interest_cost_multiplier
        post_fcf_debt = gross_debt - fcf  # negative FCF increases debt in this simple one-period bridge
        rows.append(
            {
                "scenario": s.name,
                "revenue_multiplier": s.revenue_multiplier,
                "ebitda_margin_delta_pp": s.ebitda_margin_delta * 100.0,
                "fcf_margin_delta_pp": s.fcf_margin_delta * 100.0,
                "interest_cost_multiplier": s.interest_cost_multiplier,
                "revenue": revenue,
                "ebitda_proxy": ebitda,
                "ebitda_margin": ebitda_margin,
                "free_cash_flow": fcf,
                "interest_expense": interest,
                "gross_leverage": gross_debt / ebitda if ebitda > 0 else np.inf,
                "post_fcf_gross_debt": post_fcf_debt,
                "post_fcf_gross_leverage": post_fcf_debt / ebitda if ebitda > 0 else np.inf,
                "ebitda_interest_coverage_proxy": ebitda / interest if interest > 0 else np.nan,
            }
        )
    return pd.DataFrame(rows)


def debt_capacity_grid(ttm_ebitda: float, ttm_interest: float, gross_debt: float, target_leverages: tuple[float, ...] = (3.0, 4.0, 5.0, 6.0), target_coverages: tuple[float, ...] = (2.0, 2.5, 3.0, 3.5)) -> pd.DataFrame:
    """
    Illustrative debt-capacity sensitivity, not covenant math.

    For interest-coverage capacity we hold the observed cash-interest rate proxy constant.
    """
    implied_rate = ttm_interest / gross_debt
    rows = []
    for lev in target_leverages:
        rows.append({"constraint": "gross_leverage", "threshold": lev, "debt_capacity": ttm_ebitda * lev})
    for cov in target_coverages:
        rows.append({"constraint": "ebitda_interest_coverage", "threshold": cov, "debt_capacity": ttm_ebitda / (implied_rate * cov)})
    df = pd.DataFrame(rows)
    df["headroom_vs_current_debt"] = df["debt_capacity"] - gross_debt
    df["implied_interest_rate_proxy"] = implied_rate
    return df


def recovery_waterfall(
    scenario_df: pd.DataFrame,
    debt_stack: dict[str, float],
    cash: float,
    ev_multiples: tuple[float, ...] = (3.0, 4.0, 5.0, 6.0, 7.0),
) -> pd.DataFrame:
    """
    Simplified debt-only enterprise-value waterfall.

    This deliberately ignores non-debt priority claims, entity-level guarantee leakage,
    jurisdictional insolvency costs and collateral-specific liquidation haircuts. It is
    a sensitivity framework, not a legal recovery estimate.
    """
    secured = float(debt_stack["secured_subsidiary_guaranteed"])
    guaranteed = float(debt_stack["unsecured_subsidiary_guaranteed"])
    nonguaranteed = float(debt_stack["unsecured_no_subsidiary_guarantee"])
    rows = []
    for _, s in scenario_df.iterrows():
        ebitda = max(0.0, float(s["ebitda_proxy"]))
        for multiple in ev_multiples:
            enterprise_value = ebitda * multiple
            distributable = enterprise_value + max(0.0, float(cash))
            remaining = distributable
            secured_rec = min(secured, remaining)
            remaining -= secured_rec
            guaranteed_rec = min(guaranteed, remaining)
            remaining -= guaranteed_rec
            nonguaranteed_rec = min(nonguaranteed, remaining)
            remaining -= nonguaranteed_rec
            rows.append(
                {
                    "scenario": s["scenario"],
                    "ev_ebitda_multiple": multiple,
                    "enterprise_value": enterprise_value,
                    "cash_added_to_waterfall": max(0.0, float(cash)),
                    "distributable_value": distributable,
                    "secured_recovery_pct": secured_rec / secured if secured > 0 else np.nan,
                    "unsecured_guaranteed_recovery_pct": guaranteed_rec / guaranteed if guaranteed > 0 else np.nan,
                    "unsecured_no_guarantee_recovery_pct": nonguaranteed_rec / nonguaranteed if nonguaranteed > 0 else np.nan,
                    "equity_residual": max(0.0, remaining),
                }
            )
    return pd.DataFrame(rows)


def maturity_coverage(schedule: dict[str, float], liquidity_sources: float) -> pd.DataFrame:
    rows = []
    cumulative = 0.0
    for label, amount in schedule.items():
        if label.lower() == "total":
            continue
        cumulative += float(amount)
        rows.append(
            {
                "maturity_bucket": label,
                "principal_due": float(amount),
                "cumulative_principal_due": cumulative,
                "liquidity_sources": float(liquidity_sources),
                "liquidity_minus_cumulative_maturities": float(liquidity_sources) - cumulative,
            }
        )
    return pd.DataFrame(rows)
