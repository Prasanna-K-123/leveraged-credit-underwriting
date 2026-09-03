from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


def _money(x: float) -> str:
    return f"${x:,.0f}m"


def build_credit_memo(
    company_name: str,
    ticker: str,
    source_snapshot: dict[str, Any],
    filing: dict[str, Any],
    current: dict[str, float],
    ttm: dict[str, float],
    debt_stack: dict[str, float],
    context: dict[str, Any],
    maturities: dict[str, float],
    scenarios: pd.DataFrame,
    recovery: pd.DataFrame,
) -> str:
    base = scenarios.loc[scenarios["scenario"] == "base"].iloc[0]
    downside = scenarios.loc[scenarios["scenario"] == "downside"].iloc[0]
    severe = scenarios.loc[scenarios["scenario"] == "severe"].iloc[0]
    maturity_2027 = maturities.get("2027", float("nan"))
    maturity_2028 = maturities.get("2028", float("nan"))
    liquidity = current["cash_plus_undrawn_revolver"]

    # 5x recovery snapshots are compact enough for the memo; full matrix is separately persisted.
    rec5 = recovery[recovery["ev_ebitda_multiple"] == 5.0].set_index("scenario")

    return f"""# Public-data leveraged-credit underwriting memo — {company_name} ({ticker})

## Purpose and evidence boundary

This is a reproducible **public-information credit research exercise**, not an investment recommendation, lender diligence package or legal covenant calculation. Financial facts are source-traced to SEC XBRL/filing evidence; forward scenarios and recovery assumptions are explicitly illustrative.

**Underwriting snapshot:** {source_snapshot['captured_at_utc']}  
**Latest filing used for debt/covenant detail:** {filing['form']} for {filing['report_date']}, filed {filing['filed']}  
**Filing accession:** `{filing['accession']}`

## Credit snapshot

- TTM revenue: **{_money(ttm['revenue'])}**
- TTM EBITDA proxy (operating income + D&A): **{_money(ttm['ebitda_proxy'])}**
- TTM EBITDA margin: **{ttm['ebitda_margin']:.1%}**
- TTM free cash flow proxy (CFO - capex): **{_money(ttm['free_cash_flow'])}**
- Gross debt from the filing debt note: **{_money(current['gross_debt'])}**
- Cash: **{_money(current['cash'])}**
- Net debt: **{_money(current['net_debt'])}**
- Gross debt / EBITDA proxy: **{current['gross_leverage']:.2f}x**
- Net debt / EBITDA proxy: **{current['net_leverage']:.2f}x**
- EBITDA / interest proxy: **{current['ebitda_interest_coverage_proxy']:.2f}x**
- FCF / gross debt: **{current['fcf_to_gross_debt']:.1%}**

The agreement's most restrictive minimum interest-coverage covenant is stated as **{context['minimum_interest_coverage_ratio']:.1f}x**, but the public-data EBITDA/interest ratio above is **not the contractual calculation**. Agreement definitions and adjustments are different; no covenant headroom is claimed from the proxy.

## Capital structure and liquidity

- Secured subsidiary-guaranteed debt: **{_money(debt_stack['secured_subsidiary_guaranteed'])}**
- Unsecured subsidiary-guaranteed debt: **{_money(debt_stack['unsecured_subsidiary_guaranteed'])}**
- Unsecured debt without subsidiary guarantee: **{_money(debt_stack['unsecured_no_subsidiary_guarantee'])}**
- Undrawn revolving facility: **{_money(context['undrawn_revolver_millions'])}**
- Cash + undrawn revolver: **{_money(liquidity)}**
- Filing-reported secured collateral book value: **{_money(context['secured_collateral_book_value_millions'])}**
- Book-value collateral / secured debt: **{current['collateral_book_value_to_secured_debt']:.2f}x**

Book value is not liquidation value. Collateral coverage is reported as source evidence, not as an assumed recovery percentage.

## Maturity wall

- 2027 principal maturities: **{_money(maturity_2027)}**
- 2028 principal maturities: **{_money(maturity_2028)}**
- Cash + undrawn revolver / 2027 maturities: **{liquidity / maturity_2027:.2f}x**

Drawing the revolver would itself increase debt, so gross liquidity should not be treated as free debt reduction capacity.

## Downside scenarios

The scenario grid is deliberately mechanical and published before any recovery interpretation:

| Scenario | Revenue | EBITDA proxy | EBITDA margin | FCF | Gross leverage | EBITDA/interest proxy |
|---|---:|---:|---:|---:|---:|---:|
| Base | {_money(base['revenue'])} | {_money(base['ebitda_proxy'])} | {base['ebitda_margin']:.1%} | {_money(base['free_cash_flow'])} | {base['gross_leverage']:.2f}x | {base['ebitda_interest_coverage_proxy']:.2f}x |
| Downside | {_money(downside['revenue'])} | {_money(downside['ebitda_proxy'])} | {downside['ebitda_margin']:.1%} | {_money(downside['free_cash_flow'])} | {downside['gross_leverage']:.2f}x | {downside['ebitda_interest_coverage_proxy']:.2f}x |
| Severe | {_money(severe['revenue'])} | {_money(severe['ebitda_proxy'])} | {severe['ebitda_margin']:.1%} | {_money(severe['free_cash_flow'])} | {severe['gross_leverage']:.2f}x | {severe['ebitda_interest_coverage_proxy']:.2f}x |

These are **analytical stresses, not forecasts or management guidance**.

## Simplified 5x EV / EBITDA recovery sensitivity

| Scenario | Secured | Unsecured guaranteed | Unsecured no guarantee |
|---|---:|---:|---:|
| Base | {rec5.loc['base','secured_recovery_pct']:.1%} | {rec5.loc['base','unsecured_guaranteed_recovery_pct']:.1%} | {rec5.loc['base','unsecured_no_guarantee_recovery_pct']:.1%} |
| Downside | {rec5.loc['downside','secured_recovery_pct']:.1%} | {rec5.loc['downside','unsecured_guaranteed_recovery_pct']:.1%} | {rec5.loc['downside','unsecured_no_guarantee_recovery_pct']:.1%} |
| Severe | {rec5.loc['severe','secured_recovery_pct']:.1%} | {rec5.loc['severe','unsecured_guaranteed_recovery_pct']:.1%} | {rec5.loc['severe','unsecured_no_guarantee_recovery_pct']:.1%} |

This waterfall is intentionally simplified: it adds cash to an EBITDA-multiple enterprise value and allocates value to the three debt buckets in priority order. It omits non-debt priority claims, entity-level guarantee leakage, insolvency costs and collateral-specific legal analysis. It is a **sensitivity framework, not a legal recovery estimate**.

## Underwriting interpretation

The key analytical tension is the combination of still-substantial gross debt and maturity/refinancing exposure against improving cash-generation capacity and meaningful undrawn liquidity. The correct conclusion is not "safe" or "distressed" from a single ratio. The evidence should be judged through the full maturity schedule, cash conversion, interest burden, scenario leverage and legal-structure limitations documented in the source files.

## Reproducibility

The repository persists:

- raw SEC companyfacts and submissions JSON plus SHA-256 hashes;
- the exact latest SEC filing HTML plus SHA-256 hash;
- every XBRL fact used in annual and TTM bridges with tag, accession, filing date and period;
- debt-stack, maturity and covenant extracts from the filing;
- annual history, scenario, debt-capacity and recovery matrices;
- tests covering source selection and monotonic accounting properties.

See `docs/METHODOLOGY.md`, `docs/RESEARCH_PROTOCOL.md`, `results/source_register.csv` and the machine-readable result files.
"""


def plot_scenario_leverage(scenarios: pd.DataFrame, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(scenarios["scenario"], scenarios["gross_leverage"])
    ax.set_ylabel("Gross debt / EBITDA proxy (x)")
    ax.set_title("Illustrative scenario leverage")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)


def plot_recovery_heatmap(recovery: pd.DataFrame, path: Path, claim_col: str = "unsecured_guaranteed_recovery_pct") -> None:
    pivot = recovery.pivot(index="scenario", columns="ev_ebitda_multiple", values=claim_col)
    fig, ax = plt.subplots(figsize=(7, 3.8))
    im = ax.imshow(pivot.to_numpy(), aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(pivot.columns)), [f"{x:.0f}x" for x in pivot.columns])
    ax.set_yticks(range(len(pivot.index)), pivot.index)
    ax.set_xlabel("EV / EBITDA multiple")
    ax.set_title("Simplified unsecured-guaranteed recovery sensitivity")
    fig.colorbar(im, ax=ax, label="Recovery")
    fig.tight_layout()
    fig.savefig(path, dpi=170)
    plt.close(fig)
