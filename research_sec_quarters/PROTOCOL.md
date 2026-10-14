# Registered real SEC quarter source and reconciliation study

Registered 2026-10-14 before original-byte acquisition and new issuer calculations. Repository base: `606ea14054443873d432c259548e100bda6f20af`. This is a separate research release; the accepted 2026 Q2 default pipeline, reference CSVs, reports and old source remain unchanged.

## Fixed question and sample

Can the existing strict calendar-period API reproduce Carnival's filed fiscal Q1 and Q3 trailing metrics using authentic SEC response bytes, exact economic periods, and independently read statement tables? Retain missing contexts, restatements, contradictions and source-access failures. No model fitting, financial recommendation, covenant assertion or performance optimisation.

The fixed issuer is CIK0000815097. Capture submissions, Companyfacts and primary 10-K/10-Q HTML for these five report ends: 2025-11-30 annual, 2026-02-28 Q1, 2026-08-31 Q3, 2025-02-28 original Q1 comparator, and 2025-08-31 original Q3 comparator. Resolve each form/report end uniquely from authentic submissions.recent. Known annual accession0000815097-26-000007, Q1 accession0000815097-26-000037 and Q3 accession0000815097-26-000107 must match. Filing dates must be on or before the fixed cutoff2026-10-14. This is a time-of-capture snapshot filtered by filed dates, not an archived historical API state.

## Acquisition and integrity

Run the existing `research_sec_intake.intake.acquire` and standalone verifier unchanged. Use an explicit descriptive SEC User-Agent with the researcher's public contact; never add credentials. Requests are sequential and limited to at most five starts per second, with no retry, redirect, bot challenge workaround or alternative source substitution. The GitHub job has read-only contents permission, no secret input and a ten-minute timeout. It may publish its bounded source evidence as a workflow artifact; it never commits captured source, writes repository refs or sends messages. On a source failure, report FAILED and retain only a clearly labelled diagnostic or completed individually verified captures; never call a partial collection successful.

Original response bodies and SHA256/length are retained. The downloaded artifact must pass ZIP CRC, capture manifest verification and byte hashes locally before it becomes evidence. These raw source captures are not financial outputs.

## Predeclared reconciliation

For each quarter, use FY2025 + current YTD2026 - matching YTD2025. The six duration metrics are revenue, operating income, depreciation/amortisation, interest expense, cash from operations and capital expenditures. Require exact start/end, USD units, filing form, accession and cutoff. Compare each selected Companyfacts context with independently identified income or cash-flow table values and inline XBRL periods in the corresponding original HTML. Where standard Companyfacts omits an extension-tag value, only a fully identified original filing-table/inline context with raw HTML digest may supply an explicit override; no unlabeled imputation. Expense/spend magnitudes and display rounding must be explicit. Compare originally filed prior-quarter statements against current comparative columns and retain differences.

The Q3 previously transcribed table calculation is an external check, not raw input: revenue27593, operating income4413, depreciation2898, interest1177, operating cash6821, capex3645, all USD millions. Do not tune contexts to achieve these values; disagreement requires investigation and a reported result. Q1 values are not yet computed in this study.

Require independent algebraic reconciliation, nonmutation of all original Q2 reference/source blobs, meaningful parser/provenance regression tests and complete matching-head CI for any published implementation. A source-only success is not full end-to-end underwriting, debt-stack, liquidity, legal-obligor or covenant validation. The legacy Q2 CLI guard remains until a separately validated replacement is released.
