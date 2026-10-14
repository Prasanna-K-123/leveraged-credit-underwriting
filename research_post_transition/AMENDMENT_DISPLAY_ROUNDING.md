# Disclosed amendment: rounded statement reconciliation

14 October 2026, after the first strict-exact instrument reconciliation failed
and before any new output/reference was accepted. The original protocol remains
byte-preserved at `5f23dccd87359d48532a55bed0f7b178315f0780`; its strict-exact
interpretation did not pass. This is an explicitly source-informed amendment,
not a previously registered successful criterion or prospective validation.

The original filing reports integer USD millions. Current instrument sums match
their categories exactly. Comparative instrument sums are 13,620 and 13,765,
while the displayed category subtotals are 13,619 and 13,764. Comparative
principal minus displayed debt costs is 26,639 versus the reported 26,640
carrying value. Those nonzero differences must be visible in the output.

Use the repository's already established absolute **USD2m display tolerance**
for instrument/subtotal and principal/carrying reconciliations. Keep exact
category-subtotal/total-debt, current/noncurrent and maturity/total checks.
Bind and preserve every original displayed amount, date, source hash, field,
identity, group and sign. Missing rows and malformed numbers remain errors;
an absent category is never supplied as zero. Refuse discrepancies beyond the
existing tolerance and disclose the actual signed gaps, including accepted
nonzero comparative rounding gaps. Do not replace reported category totals
with computed sums or change old source/model/reference bytes.

The source-body/ZIP hashes remain hard equality checks independent of numerical
tolerance. The unchanged original full Q3 legal-recovery criterion stays failed,
and actual estate-level recovery and covenant headroom stay refused.
