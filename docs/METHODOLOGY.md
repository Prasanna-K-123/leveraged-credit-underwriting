# Methodology — public-data leveraged-credit underwriting

## Source selection

The project uses SEC primary-source material only in the reference run. Companyfacts duration facts are restricted to 10-K FY periods for annual history. When multiple filings report the same period, the latest filed fact is selected so later comparative restatements can supersede earlier values. Latest 10-Q and 10-K identities come from SEC submissions JSON.

Every selected XBRL fact is persisted to `results/source_register.csv` with the tag, value, period, form, filing date and accession.

## TTM construction

For a latest six-month 10-Q, each duration metric is bridged as:

`TTM = latest fiscal year + current six-month YTD - prior-year comparable six-month YTD`

This is applied separately to revenue, operating income, depreciation/amortization, interest expense, cash from operations and capex. The derived EBITDA and FCF proxies are calculated only after the TTM bridge.

This avoids mixing a current balance sheet with stale annual-only operating metrics where a comparable interim period exists.

## Debt semantics

The filing debt note distinguishes gross principal from balance-sheet debt net of unamortized issuance costs/discounts. The underwriting analysis therefore uses:

- **gross principal** for leverage, maturity and recovery sensitivities;
- **balance-sheet carrying value** as a reconciliation check;
- **cash** from the latest balance sheet;
- **net debt** = gross principal - cash for the principal-based leverage view.

This prevents a common but material presentation error: calling the carrying amount gross debt.

## Covenant treatment

The latest filing's minimum interest-coverage, maximum debt-to-capital and minimum-liquidity terms are extracted as source evidence. The project does not recompute legal covenant compliance because agreement-defined adjusted EBITDA, interest charges, capital and permitted adjustments are not the same as simple public financial-statement proxies.

A simple EBITDA/interest proxy is shown only as an operating-credit diagnostic and explicitly labelled as such.

## Downside framework

Base/downside/severe scenarios are deterministic stresses from the research protocol, not forecasts. They perturb revenue, EBITDA margin, FCF margin and interest cost. Gross leverage, post-FCF leverage and EBITDA/interest proxy are then recalculated without silently assuming refinancing or equity issuance.

## Debt capacity

A sensitivity grid asks what debt level would correspond to selected gross-leverage or simple EBITDA/interest thresholds. For interest-based capacity, the observed TTM interest/gross-debt ratio is held constant. These thresholds are analyst sensitivities; they are not contractual tests.

## Maturity/liquidity analysis

The filing's principal maturity schedule is reconciled to total gross debt. Cash plus undrawn revolver is compared with cumulative maturities as a gross liquidity-source view. The analysis explicitly notes that drawing the revolver adds debt and that facility availability remains subject to agreement conditions.

## Recovery framework

The simplified recovery grid uses scenario EBITDA and EV/EBITDA multiples from 3x to 7x. Cash is added to enterprise value, then the value is allocated in the following simplified order:

1. secured subsidiary-guaranteed debt;
2. unsecured subsidiary-guaranteed debt;
3. unsecured debt without subsidiary guarantees;
4. residual equity value.

This is deliberately not a full restructuring model. The legal/entity/collateral limitations are documented in the protocol and memo.

## Audit standard

The project is accepted only if:

- SEC source acquisition succeeds and hashes are recorded;
- required XBRL periods reconcile across annual and TTM bridges;
- filing tables parse to complete debt and maturity structures;
- debt reconciliation gates pass;
- unit tests pass;
- output claims remain within the documented evidence boundary.
