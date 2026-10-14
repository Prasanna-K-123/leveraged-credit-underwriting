> 13 October2026: a separate strict Q1/Q2/Q3 **calculation API** is now implemented and checked using144 synthetic calendar/context cases. The original default live CLI and heuristic table parser remain Q2-only. Read the [new exact-period review](docs/EXPLICIT_PERIOD_BRIDGE_REVIEW.md) for method, reproducibility and the empirical-refresh boundary. Accepted reference outputs are unchanged.

## Original SEC Q1/Q3 evidence — October 2026

The separate [registered quarter study](research_sec_quarters/PROTOCOL.md) now retains five authentic SEC filing captures, their original hashes, exact whole-entity USD contexts, independent visible-column checks and both originally filed comparators. The [source/rights notice](research_sec_quarters/SOURCES.md) keeps these third-party filings separate from the code licence.

Q1 FY2026 TTM revenue is $26,977m, EBITDA proxy $7,379m and FCF proxy $2,986m. Q3 TTM revenue is $27,593m, EBITDA proxy $7,311m and FCF proxy $3,176m. These are mechanical statement bridges, not adjusted EBITDA, management guidance or borrower credit estimates.

**Q3 changes the debt structure.** The [adverse finding](research_sec_quarters/ADVERSE_FINDING.md) records the unchanged historical model's failed Q3 debt parsing. The new path verifies the reported Q3 debt and maturity totals and retains descriptive/scenario arithmetic; it explicitly refuses the old secured-collateral, covenant-liquidity and recovery calculation. It never supplies a made-up secured zero or another quarter's values. The registered two-quarter full-model success criterion remains unmet. Q1 supports the complete unchanged illustrative-model replay; legal recovery and covenant certification are outside both releases.

Reproduce the pinned evidence offline after installing the repository dependencies:

```bash
python -m research_sec_quarters.run --output /tmp/ccl-quarter-evidence-new
```

The output path must be fresh and outside the repository. The frozen original source ZIP is checked before use; historical source/reference blob identities are checked before and after. The dedicated [offline quarter workflow](.github/workflows/sec-quarter-replay.yml) validates this bounded source/replay contract and its Q3 refusal. Source capture and tests are not independent practitioner endorsement or historical-vintage API completeness.

The original Q2 reference, source/model and default CLI remain intact below. That default CLI deliberately refuses a latest non-Q2 refresh; use the separate command for these pinned Q1/Q3 observations. All prior adverse findings and assumptions remain visible.


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

That command intentionally queries current SEC data and may select newer filings. **Important current limitation:** `build_ttm_metrics()` hard-codes a **150–220-day YTD duration filter** for both current and prior 10-Q inputs, appropriate to the accepted **Q2** snapshot but not a period-general Q1/Q3 bridge. The current source now **fails closed** unless the selected 10-Q period end is 150–220 days after the most recent fiscal year end (the accepted Q2-like window), both at the refresh entry point before retrieving filing HTML and inside `build_ttm_metrics()`. Unsupported Q1/Q3/stale-FY cases raise `ValueError` rather than computing a misleading TTM. This is a **guardrail, not a general quarter-aware bridge** and does not establish that every date in the window has a correct source context. [PR #1](https://github.com/Prasanna-K-123/leveraged-credit-underwriting/pull/1) passed unit tests and exact accepted-reference reproduction in GitHub Actions run 38289602398; do not claim a non-Q2 refresh is supported. The accepted pinned 2026 Q2 reference and its exact file hashes are unchanged. Do not overwrite that reference with a refresh without a separately specified, tested quarter-aware bridge. Its output is a **new timestamped underwriting update** only when independently checked and cannot silently replace the dated accepted reference result.

## Evidence boundary

- The EBITDA metric is a public-data proxy, **not company-defined adjusted EBITDA**.
- Simple EBITDA/interest is **not the contractual covenant calculation**.
- Scenarios are analyst-created stresses, **not management guidance**.
- Recovery is a simplified sensitivity, **not a legal recovery estimate**.
- No investment recommendation, target price, private information, covenant-headroom conclusion or lender-diligence claim is made.

See [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md), [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md), and [`docs/VALIDATION.md`](docs/VALIDATION.md).

## Exact-context fiscal-period API — 13 October2026

A separately registered `credit_underwriting.period_bridge.build_ttm_metrics_period_aware` supports fixed month-end Q1/Q2/Q3 fiscal calendars using exact duration starts/ends and an explicit filing cutoff. It refuses unrelated single-quarter rows, unavailable future filings, ambiguous current facts, unsupported calendars and table overrides without real interval/provenance fields. The new19 substantive checks include all144 calendar cases and their2,592 synthetic source contexts.

[Method registration](docs/EXPLICIT_PERIOD_BRIDGE_PROTOCOL.md) · [complete execution review](docs/EXPLICIT_PERIOD_BRIDGE_REVIEW.md) · [full synthetic reference](research_period_bridge/reference_summary.json).

This separate API does not change or retrospectively certify the original Q2 live refresh and table parser. Actual Q1/Q3 issuer refreshes remain unverified. No accepted reference number, original source/parser/workflow or adverse underwriting finding is changed; the former README is preserved exactly in the dated history document.


## Post-transition Q3 debt and financial liquidity extension

[Source-bound review, frozen results and reproduction](docs/POST_TRANSITION_DEBT_LIQUIDITY_REVIEW.md) distinguish the changed current debt categories, 21 instruments, 63 inline amount contexts, conditional revolver and ship-specific financing. A separate static maturity proxy preserves negative later-bucket differences. The disclosed rounding amendment retains nonzero comparative gaps and the initial strict-check failure.

The original full Q3 recovery criterion remains failed. Exact creditor estates, legal priorities, collateral recovery and agreement-defined covenant headroom are refused. The separate 832-case synthetic pari-passu contract and rational oracle are arithmetic checks under explicit assumptions, not observed Q3 recovery. All previous code, source, results and adverse findings remain preserved; the full previous README is [retained here](docs/HISTORICAL_README_BEFORE_POSTTRANSITION_20261014.md).
