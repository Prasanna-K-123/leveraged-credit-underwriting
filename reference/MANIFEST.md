# Accepted reference evidence

This directory freezes the recruiter-facing reference state independently of future SEC filings or expiring GitHub Actions artifacts.

## Reference identity

- Accepted validation run: `33623045176`
- Analytical commit: `d9a489b0c049c91f9982e496b4092a21e44f15e9`
- Evidence capture: `2026-09-02T11:08:55Z`
- Issuer: Carnival Corporation Ltd. (`CCL`), CIK `0000815097`

### SEC source snapshots

- Companyfacts: `https://data.sec.gov/api/xbrl/companyfacts/CIK0000815097.json`
  - SHA-256: `261b8d59e592337dd2775456e5b57b32e0c63c53f3fcbc5bdfcdab32b0d8a288`
- Submissions: `https://data.sec.gov/submissions/CIK0000815097.json`
  - SHA-256: `f550fb092619c6bbde7b5929ca069a31ee311b93a8948b852404dc56be0b153d`
- 2025 Form 10-K, accession `0000815097-26-000007`, filed 2026-01-27, report date 2025-11-30
  - Filing URL: `https://www.sec.gov/Archives/edgar/data/815097/000081509726000007/ccl-20251130.htm`
  - SHA-256: `307743c441119288b242f47b6a848722db7ebabf24f8266ab8af90be60b00e7e`
- 2026 Q2 Form 10-Q, accession `0000815097-26-000096`, filed 2026-06-26, report date 2026-05-31
  - Filing URL: `https://www.sec.gov/Archives/edgar/data/815097/000081509726000096/ccl-20260531.htm`
  - SHA-256: `dce36a74defb095f215aa57da62f279b60991ccecfb32be785a16871711a5533`

The accepted validation archive retained the complete raw companyfacts/submissions JSON and filing HTML. This standalone recruiter-facing repository does not duplicate those multi-megabyte public files; instead it commits the exact source-derived financial inputs, the tag/accession-level source register, source URLs, and cryptographic hashes above.

## Reference files

- `annual_history.csv` — accepted three-year operating history.
- `ttm_metrics.csv` — accepted mechanical TTM bridge output.
- `balance_sheet_snapshot.csv` — accepted cash/carrying-value debt facts.
- `debt_stack.csv` — accepted debt-note principal/capital-stack reconstruction.
- `maturity_schedule.csv` — accepted gross-principal maturity schedule.
- `covenant_liquidity_context.csv` — filing-derived covenant/liquidity context with explicit proxy warning.
- `source_register.csv` — XBRL/filing-table fact provenance, periods, accessions and table hashes.
- `scenario_analysis.csv`, `debt_capacity_sensitivity.csv`, `recovery_waterfall_sensitivity.csv`, `maturity_liquidity_coverage.csv` — accepted downstream analytical tables.

`python verify_reference.py` recomputes the derived ratios, scenario analysis, debt-capacity grid, recovery sensitivity, maturity-liquidity bridge and reconciliation gates from the pinned inputs, then compares the generated analytical tables numerically against the accepted tables with tight tolerances.

`python run_credit_research.py` is deliberately separate: it queries current SEC data and may select a later filing. Such a run is a new timestamped underwriting update, not a silent rewrite of this accepted reference.
