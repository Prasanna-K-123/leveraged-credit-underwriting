# Validation and reference-evidence policy

The recruiter-facing reference state is the accepted Carnival public-data underwriting captured at `2026-09-02T11:08:55Z`. It is tied to the 2025 Form 10-K accession `0000815097-26-000007` and the 2026 Q2 Form 10-Q accession `0000815097-26-000096`.

The source validation archive retained complete SEC companyfacts/submissions JSON and filing HTML. Their URLs and SHA-256 identities are pinned in [`../reference/MANIFEST.md`](../reference/MANIFEST.md). This standalone repository commits the exact source-derived financial inputs and the tag/accession-level source register used by the accepted analysis.

CI must pass two distinct gates:

1. unit/invariant tests for source selection and underwriting logic; and
2. deterministic `python verify_reference.py` reproduction of the accepted reference.

The deterministic verifier checks:

- annual and TTM EBITDA/FCF/coverage arithmetic;
- current credit metrics;
- gross-principal versus carrying-value debt distinction;
- balance-sheet and debt-note carrying-value reconciliation;
- maturity schedule to gross-principal debt reconciliation;
- capital-stack rounding reconciliation;
- base/downside/severe scenario output;
- debt-capacity grid;
- simplified recovery waterfall;
- maturity-liquidity bridge; and
- presence of both accepted SEC accessions in the source register.

`python run_credit_research.py` is deliberately a separate live-refresh path. It may select newer SEC filings as they become available, so its output is treated as a new underwriting update rather than an automatic rewrite of the accepted reference.

The recovery waterfall remains a debt-only sensitivity that omits non-debt priority claims, entity-level guarantee leakage, insolvency costs and collateral-specific legal analysis. The public-data EBITDA/interest ratio is not contractual covenant math. These boundaries are validation requirements, not optional disclaimers.
