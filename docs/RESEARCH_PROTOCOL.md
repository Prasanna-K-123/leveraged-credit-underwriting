# Research protocol — FLAGSHIP-CREDIT-001

## Question

Can a public-information underwriting workflow reconstruct a source-traceable current credit picture, maturity/refinancing risk, downside leverage and simplified debt recoveries for Carnival using SEC filings without quietly mixing company-defined metrics, analyst assumptions and legal conclusions?

## Frozen source hierarchy

1. SEC companyfacts JSON for machine-readable financial facts.
2. SEC submissions JSON for filing identity/accession information.
3. Latest filed 10-Q for debt stack, maturity schedule, covenant language, revolver availability and collateral book-value context.
4. No third-party estimate is permitted in the reference run.

Raw downloaded source files are retained with SHA-256 hashes.

## Metric rules fixed before interpretation

- Monetary values are converted to USD millions only after source selection.
- EBITDA proxy = operating income + depreciation & amortization.
- Free-cash-flow proxy = cash from operations - capital expenditures.
- Latest TTM duration metrics = latest 10-K FY + latest 10-Q YTD - prior-year comparable YTD.
- Gross debt comes from the filing debt-note principal table; balance-sheet long-term debt is treated as carrying value net of unamortized issuance costs/discounts where the filing says so.
- Net debt = gross debt principal - cash. This differs intentionally from a carrying-value net-debt calculation.
- Simple EBITDA/interest is not relabeled as the contractual covenant calculation.

## Reconciliation gates

The run must fail if, beyond small filing-table rounding tolerance:

- current + long-term debt carrying value does not reconcile to the filing-reported net-of-unamortized-cost debt;
- maturity-schedule total does not reconcile to gross debt principal;
- debt priority buckets do not reconcile to gross debt principal.

## Scenario assumptions

These are explicitly **analytical stresses**, not forecasts or management guidance:

- Base: revenue 1.03x TTM, unchanged EBITDA/FCF margins, unchanged interest cost.
- Downside: revenue 0.90x TTM, EBITDA margin -3pp, FCF margin -5pp, interest cost 1.10x.
- Severe: revenue 0.80x TTM, EBITDA margin -6pp, FCF margin -10pp, interest cost 1.25x.

No scenario is modified after seeing which recovery outcome looks more attractive.

## Recovery protocol

A deliberately simplified debt-only enterprise-value waterfall is shown across 3x–7x EV/EBITDA. It allocates enterprise value plus cash first to secured subsidiary-guaranteed debt, then unsecured subsidiary-guaranteed debt, then unsecured debt without subsidiary guarantees.

The model deliberately states what it omits: non-debt priority claims, entity-level structural subordination details, jurisdiction-specific insolvency costs, collateral-specific liquidation haircuts and legal enforcement complexity. It is a sensitivity model, not a legal recovery estimate.

## Claims that are prohibited

The reference project will not claim:

- company-defined adjusted EBITDA when using the public operating-income + D&A proxy;
- contractual covenant headroom from the proxy coverage calculation;
- management guidance from analyst-created scenarios;
- lender-grade recovery conclusions from the simplified waterfall;
- investment recommendation, target price or trading signal;
- private/deal information.

Negative evidence, tight maturity years and assumptions that weaken recoveries are retained rather than suppressed.
