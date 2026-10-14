# Carnival Q3: post-transition debt and financial liquidity

This source-informed descriptive extension addresses the changed August 31,
2026 debt disclosure. It preserves the original Q2 model, original Q1/Q3 source
release, every adverse finding and the failed full Q3 recovery criterion.
It provides reported classifications and a static liquidity sensitivity.
Actual legal creditor recovery and agreement-defined covenant headroom remain
refused.

[Registered method](../research_post_transition/PROTOCOL.md) ·
[Disclosed rounding amendment](../research_post_transition/AMENDMENT_DISPLAY_ROUNDING.md) ·
[Frozen results](../research_post_transition/reference_summary.json) ·
[Parser and explicit refusal](../research_post_transition/model.py) ·
[Offline reproduction](../research_post_transition/run.py) ·
[Verification workflow](../.github/workflows/post-transition.yml) ·
[Original adverse finding](../research_sec_quarters/ADVERSE_FINDING.md).

## Original disclosure and checked quantities

The input is the already frozen original SEC capture, SHA256
`f49431e44e83cac39071dd95fdaa56515ca4b540d8522201e400ab6859beed9c`.
The Q3 [original10-Q](https://www.sec.gov/Archives/edgar/data/815097/000081509726000107/ccl-20260831.htm)
has accession `0000815097-26-000107`, reported August 31 and filed September 29,
2026, with original HTML SHA256
`e3754e6754f83dc620d85fb672452401ea121e63c5b929d1458a9f0475bc4d3d`.
No new source copy or latest-quarter substitution is introduced.

The extension binds all **21 displayed instruments** to their two actually
reported unsecured categories. All **63 numeric inline contexts** are checked
against issuer, instant date, USD currency, million scale, transformation and
displayed amount. Positive XBRL account balances used on subtraction rows retain
their positive account value and separate negative display direction.

| Reported amount, USDm | August 31, 2026 | Comparative November 30, 2025 |
|---|---:|---:|
| Unsecured with subsidiary guarantees | 10,953 | 13,619 |
| Unsecured without subsidiary guarantees | 13,606 | 13,764 |
| Principal debt | 24,559 | 27,383 |
| Unamortized costs/discounts deducted | 647 | 744 |
| Net carrying balance | 23,912 | 26,640 |

The comparative categories are presented in this Q3 filing. They are not a
reconstruction of original November 2025 security status. Current instrument
sums agree exactly with the displayed categories. Comparative instrument sums
are higher by USD1m in each category; comparative principal less costs is USD1m
below the carrying balance. Those gaps remain visible. The initial strict-exact
check failed; the disclosed amendment uses the repository's existing USD2m
display tolerance rather than altering values or erasing the failure. Category
subtotals/total debt, current/noncurrent and maturity/total checks remain exact.
Original source hashes remain hard equality checks independent of rounding.

## Financial liquidity sensitivity

Current cash is USD1,220m, bound independently to its whole-entity original
inline/Companyfacts context. The filing reports USD4,500m available under the
revolver, subject to facility conditions. The static combined proxy is USD5,720m.
The USD10,700m undrawn export facilities fund specified ship deliveries and are
excluded from general available cash.

| Through bucket | Cumulative principal, USDm | Cash only minus principal | Cash plus conditional revolver minus principal | After fixed USD1,500m reserve |
|---|---:|---:|---:|---:|
| Remainder of 2026 | 301 | 919 | 5,419 | 3,919 |
| 2027 | 2,818 | −1,598 | 2,902 | 1,402 |
| 2028 | 6,779 | −5,559 | −1,059 | −2,559 |
| 2029 | 10,410 | −9,190 | −4,690 | −6,190 |
| 2030 | 13,295 | −12,075 | −7,575 | −9,075 |
| Thereafter | 24,559 | −23,339 | −18,839 | −20,339 |

These are static financial proxies. They omit future operating cash flows,
capital spending, refinancing, drawings, changing revolver access and contractual
liquidity definitions. The fixed reserve is a sensitivity, not verified legal
covenant headroom. Negative later-bucket differences are retained and do not
predict default.

## Why actual creditor recovery is refused

The Note3 security and guarantee changes are traced to exact source locations
and paragraph hashes. The reported rounded Sun Princess exception is retained
without assigning it to an exact instrument or insolvency estate. Ship book
value subject to negative pledges is not labelled a secured collateral pool.

The five combined Obligor Group balance rows are retained with their intercompany
balances and excluded-investment basis. Subtracting that summary from consolidated
assets cannot establish other legal-entity assets. The possible future shelf
guarantee description does not establish every existing instrument's guarantee
package. Issuer-reported covenant compliance remains separate from independently
recomputed agreement-defined compliance.

Exact agreements, obligor/guarantor and asset/claim mapping, jurisdictional
priority, senior non-debt claims and independent legal/entity analysis are still
needed before an actual recovery estimate. The extension returns explicit null
refusals for actual Q3 recovery, entity mapping, covenant compliance and legal
opinion.

## Constructed arithmetic verification

A separate generic helper requires explicit synthetic, same-estate, same-priority
and no-other-senior-claims assumptions. It returns unrounded analytical pro-rata
amounts at fixed Decimal precision, never issuer payment instructions. An
independently evaluated exact rational-number oracle checks **832 constructed
cases**, **4,992 creditor-order permutations** and **2,304 individual monotonicity
comparisons**, including zero claims, zero assets and fully covered claims.
No contract failure is observed on this finite grid. These are engineered
conformance cases, not a real debtor sample or independent practitioner review.

The 35 added local tests cover source identity, amount/date/column/scale/sign,
rounding, missing/altered data, duplicate narratives, facility conditionality,
unsupported requests, synthetic assumptions, finite input bounds, numeric-context
independence and the rational oracle. The frozen summary is replayed offline;
all 60 historical Git blob identities are checked, including the full pre-change
README at its historical path. Existing workflows and references are preserved.

Reproduce from the repository root after installing the existing dependencies:

```bash
python -W error -m unittest discover -s tests -p test_post_transition.py -v
python -W error -m research_post_transition.run --output /tmp/ccl-post-transition-review
```

The output path must be fresh and outside the repository. The original issuer
text retains its upstream rights; original project MIT does not relicense it.
This is independent portfolio work developed with AI assistance, not investment
advice, a legal opinion, a production deployment, a new credential, practitioner
endorsement or assessed candidate mastery.
