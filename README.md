# Leveraged Credit Underwriting, Debt Capacity & Downside Recovery

[![Validation](https://github.com/Prasanna-K-123/leveraged-credit-underwriting/actions/workflows/validation.yml/badge.svg?branch=main)](https://github.com/Prasanna-K-123/leveraged-credit-underwriting/actions/workflows/validation.yml)

A source-traceable public-information credit-underwriting project using Carnival SEC filings to reconstruct annual and TTM operating performance, gross-principal debt, carrying-value reconciliation, maturity/refinancing exposure, covenant context, downside leverage and a deliberately simplified recovery waterfall.

The project is designed to keep **reported fact, derived metric, analyst stress and legal conclusion** separate. It does not convert public ratios into unsupported lender or investment claims.

## Recruiter snapshot

| Signal | Verified evidence |
|---|---|
| Source discipline | pinned Carnival 2025 10-K and 2026 Q2 10-Q accessions, source URLs, tag/accession register and raw-file SHA-256 identities |
| Debt reconciliation | **$24,889m** carrying-value debt vs **$25,570m** gross principal/maturities; each definition reconciles internally, with only a **$1m** filing-table rounding gap in capital-stack buckets |
| TTM credit profile | revenue **$27,311m**, EBITDA proxy **$7,327m**, FCF proxy **$3,200m**, interest **$1,208m** |
| Current leverage/coverage | gross principal debt / EBITDA proxy **3.49x**; EBITDA / interest proxy **6.07x** |
| Downside analysis | severe stress reaches **5.62x** gross leverage and **3.01x** coverage; at 5x EV/EBITDA the simplified severe waterfall gives about **79.5%** to unsecured debt without subsidiary guarantee |

**Direct evidence:** [`reference manifest`](reference/MANIFEST.md) · [`source register`](reference/source_register.csv) · [`TTM metrics`](reference/ttm_metrics.csv) · [`scenario analysis`](reference/scenario_analysis.csv) · [`recovery sensitivity`](reference/recovery_waterfall_sensitivity.csv) · [`dated underwriting memo`](reports/reference_credit_underwriting_memo.md)

## Validated reference snapshot

The accepted reference evidence was captured on **2026-09-02** from Carnival Corporation Ltd. (`CCL`) public SEC data and is pinned under [`reference/`](reference/). The debt/covenant detail is tied to Form 10-Q accession `0000815097-26-000096` for the period ended 2026-05-31; annual history is tied to the 2025 Form 10-K accession `0000815097-26-000007`.

- carrying-value debt: **$24,889m**, exactly reconciled to current + non-current debt;
- gross principal debt / maturity schedule: **$25,570m**, exactly reconciled;
- capital-stack bucket sum: within **$1m** of gross principal debt, consistent with filing-table rounding;
- TTM revenue: **$27,311m**;
- TTM EBITDA proxy: **$7,327m**;
- TTM free-cash-flow proxy: **$3,200m**;
- TTM interest expense: **$1,208m**;
- gross principal debt / EBITDA proxy: **3.49x**;
- EBITDA / interest proxy: **6.07x**.

The accepted source URLs, accessions and raw-file SHA-256 identities are documented in [`reference/MANIFEST.md`](reference/MANIFEST.md). Full raw SEC responses are identified by those hashes and retained in the validation archive; this standalone repository commits the exact source-derived inputs and tag/accession-level source register needed to audit and reproduce the accepted underwriting without duplicating multi-megabyte public filings.

## Research architecture

- SEC companyfacts + submissions evidence with cryptographic source identities;
- pinned 10-K and 10-Q accessions for the accepted reference result;
- three-year annual history with tag/accession-level source register;
- mechanical TTM bridge: latest FY + current YTD - prior comparable YTD;
- EBITDA proxy = operating income + D&A;
- FCF proxy = CFO - capex;
- debt-note reconstruction separating carrying-value debt from gross principal debt;
- principal maturity schedule, liquidity and covenant-context extraction;
- base/downside/severe analytical stresses;
- leverage and interest-coverage sensitivity;
- debt-capacity grid;
- simplified debt-priority recovery waterfall across 3x–7x EV/EBITDA;
- deterministic reference reproduction, tests and CI.

## Selected downside evidence

| Scenario | Revenue | EBITDA proxy | FCF | Gross leverage | EBITDA/interest proxy |
|---|---:|---:|---:|---:|---:|
| Base | $28,130m | $7,547m | $3,296m | 3.39x | 6.25x |
| Downside | $24,580m | $5,857m | $1,651m | 4.37x | 4.41x |
| Severe | $21,849m | $4,551m | $375m | 5.62x | 3.01x |

At a **5x EV/EBITDA** sensitivity, the simplified waterfall returns 100% to all three modeled debt buckets in base/downside; in the severe stress it returns 100% to secured and unsecured-guaranteed debt and approximately **79.5%** to unsecured debt without subsidiary guarantee. This is explicitly **not a legal recovery estimate**.

See the dated [`reference credit memo`](reports/reference_credit_underwriting_memo.md) for the full interpretation.

## Reproduce the accepted analysis

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest tests -q
python verify_reference.py
```

`verify_reference.py` checks the accepted source-derived inputs, reconstructs the current credit ratios and all downstream analytical grids, compares regenerated scenario/debt-capacity/recovery/maturity outputs to the accepted tables using strict numeric equivalence, and reruns the debt reconciliations.

## Run a current SEC refresh

```bash
SEC_USER_AGENT='Your Name your-email@example.com research' python run_credit_research.py
```

That command intentionally queries current SEC data and may select newer filings. Its output is a **new timestamped underwriting update** and cannot silently replace the dated accepted reference result.

## Evidence boundary

- The EBITDA metric is a public-data proxy, **not company-defined adjusted EBITDA**.
- Simple EBITDA/interest is **not the contractual covenant calculation**.
- Scenarios are analyst-created stresses, **not management guidance**.
- Recovery is a simplified sensitivity, **not a legal recovery estimate**.
- No investment recommendation, target price, private information, covenant-headroom conclusion or lender-diligence claim is made.

See [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md), [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md), and [`docs/VALIDATION.md`](docs/VALIDATION.md).
