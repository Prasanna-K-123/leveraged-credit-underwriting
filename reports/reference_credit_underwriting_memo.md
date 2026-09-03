# Public-data leveraged-credit underwriting memo — Carnival Corporation Ltd. (CCL)

## Purpose and evidence boundary

This is a reproducible **public-information credit research exercise**, not an investment recommendation, lender diligence package or legal covenant calculation. Financial facts are source-traced to SEC XBRL/filing evidence; forward scenarios and recovery assumptions are explicitly illustrative.

**Reference snapshot:** 2026-09-02T11:08:55Z  
**Debt/covenant filing:** Form 10-Q for 2026-05-31, filed 2026-06-26  
**Filing accession:** `0000815097-26-000096`

## Credit snapshot

- TTM revenue: **$27,311m**
- TTM EBITDA proxy (operating income + D&A): **$7,327m**
- TTM EBITDA margin: **26.8%**
- TTM free cash flow proxy (CFO - capex): **$3,200m**
- Gross principal debt from the filing debt note: **$25,570m**
- Carrying-value debt: **$24,889m**
- Cash: **$2,243m**
- Net debt against gross principal: **$23,327m**
- Gross principal debt / EBITDA proxy: **3.49x**
- Net debt / EBITDA proxy: **3.18x**
- EBITDA / interest proxy: **6.07x**
- FCF / gross principal debt: **12.5%**

The agreement's most restrictive minimum interest-coverage covenant is stated as **3.0x**, but the public-data EBITDA/interest ratio above is **not the contractual calculation**. Agreement definitions and adjustments are different; no covenant headroom is claimed from the proxy.

## Capital structure and liquidity

- Secured subsidiary-guaranteed debt: **$3,098m**
- Unsecured subsidiary-guaranteed debt: **$19,674m**
- Unsecured debt without subsidiary guarantee: **$2,799m**
- Undrawn revolving facility: **$4,500m**
- Cash + undrawn revolver: **$6,743m**
- Filing-reported secured collateral book value: **$22,400m**
- Book-value collateral / secured debt: **7.23x**

Book value is not liquidation value. Collateral coverage is reported as source evidence, not as an assumed recovery percentage.

## Maturity wall

- Remainder-of-2026 principal: **$745m**
- 2027 principal: **$2,523m**
- 2028 principal: **$3,967m**
- Cash + undrawn revolver / 2027 principal: **2.67x**

Drawing the revolver would itself increase debt, so gross liquidity should not be treated as free debt reduction capacity.

## Downside scenarios

| Scenario | Revenue | EBITDA proxy | EBITDA margin | FCF | Gross leverage | EBITDA/interest proxy |
|---|---:|---:|---:|---:|---:|---:|
| Base | $28,130m | $7,547m | 26.8% | $3,296m | 3.39x | 6.25x |
| Downside | $24,580m | $5,857m | 23.8% | $1,651m | 4.37x | 4.41x |
| Severe | $21,849m | $4,551m | 20.8% | $375m | 5.62x | 3.01x |

These are **analytical stresses, not forecasts or management guidance**.

## Simplified 5x EV / EBITDA recovery sensitivity

| Scenario | Secured | Unsecured guaranteed | Unsecured no guarantee |
|---|---:|---:|---:|
| Base | 100.0% | 100.0% | 100.0% |
| Downside | 100.0% | 100.0% | 100.0% |
| Severe | 100.0% | 100.0% | 79.5% |

This waterfall is intentionally simplified: it adds cash to an EBITDA-multiple enterprise value and allocates value to the three debt buckets in priority order. It omits non-debt priority claims, entity-level guarantee leakage, insolvency costs and collateral-specific legal analysis. It is a **sensitivity framework, not a legal recovery estimate**.

## Underwriting interpretation

The analytical tension is the combination of still-substantial gross debt and maturity/refinancing exposure against improving cash generation and meaningful undrawn liquidity. The evidence should be judged through the full maturity schedule, cash conversion, interest burden, scenario leverage and legal-structure limitations rather than a single ratio.

## Reproducibility

The accepted reference pack under `reference/` commits the exact source-derived inputs and tag/accession-level source register used for the dated result. Full raw SEC responses are retained in the validation archive and identified by source URLs and SHA-256 hashes in `reference/MANIFEST.md`. `python verify_reference.py` deterministically re-runs every downstream underwriting sensitivity from the committed reference inputs.
