import copy
from datetime import date, timedelta
import math
from pathlib import Path
import tempfile
import unittest

from credit_underwriting.facts import DURATION_TAGS
from credit_underwriting.period_bridge import calendar_period_plan, build_ttm_metrics_period_aware
from research_period_bridge.fixtures import fixture, calendar_cases, ANNUAL_MILLIONS
from research_period_bridge.run import compare, legacy_blob_hashes, run, ROOT


class ExplicitPeriodBridgeTests(unittest.TestCase):
    def calculate(self, bundle, quarter_end, annual_end, cutoff, overrides=None):
        return build_ttm_metrics_period_aware(bundle, quarter_end, annual_end, filing_cutoff=cutoff, duration_overrides=overrides)

    def rows(self, bundle, metric="revenue"):
        return bundle["facts"]["us-gaap"][DURATION_TAGS[metric][0]]["units"]["USD"]

    def test_registered_144_calendar_cases_and_all_source_roles(self):
        count = 0
        for year, month, quarter, data in calendar_cases():
            with self.subTest(year=year, month=month, quarter=quarter):
                bundle, q_end, fy_end, cutoff, plan, multiplier = data
                before = copy.deepcopy(bundle)
                values, sources = self.calculate(bundle, q_end, fy_end, cutoff)
                for metric, annual in ANNUAL_MILLIONS.items():
                    self.assertAlmostEqual(values[metric], annual * multiplier, places=10)
                self.assertAlmostEqual(values["ebitda_proxy"], 200 * multiplier, places=10)
                self.assertAlmostEqual(values["free_cash_flow"], 100 * multiplier, places=10)
                self.assertAlmostEqual(values["ebitda_margin"], .2, places=10)
                self.assertAlmostEqual(values["fcf_margin"], .1, places=10)
                self.assertAlmostEqual(values["ebitda_interest_coverage"], 8, places=10)
                self.assertEqual(len(sources), 18)
                self.assertEqual(set(sources.fiscal_quarter), {quarter})
                for role, period in (("latest_fy", plan.annual), ("current_ytd", plan.current_ytd), ("prior_ytd", plan.prior_ytd)):
                    selected = sources[sources.ttm_bridge_role == role]
                    self.assertEqual(len(selected), 6)
                    self.assertEqual(set(selected.start), {period.start})
                    self.assertEqual(set(selected.end), {period.end})
                    self.assertTrue(all(selected.filed <= cutoff))
                self.assertEqual(bundle, before)
                count += 1
        self.assertEqual(count, 144)

    def test_leap_february_comparison_is_month_end(self):
        plan = calendar_period_plan("2024-02-29", "2023-11-30")
        self.assertEqual(plan.current_ytd.start, "2023-12-01")
        self.assertEqual(plan.prior_ytd.end, "2023-02-28")
        self.assertEqual(plan.prior_ytd.start, "2022-12-01")

    def test_off_calendar_stale_fy_and_invalid_dates_refused(self):
        for q, fy in (("2026-08-30", "2025-11-30"), ("2026-04-30", "2025-11-30"),
                      ("2026-11-30", "2025-11-30"), ("2027-05-31", "2025-11-30"),
                      ("2025-08-31", "2025-11-30"), ("2026-05-31", "2025-11-29"),
                      ("20260228", "2025-11-30"), ("bad", "2025-11-30")):
            with self.subTest(q=q, fy=fy), self.assertRaises(ValueError): calendar_period_plan(q, fy)

    def test_single_quarter_only_cannot_replace_ytd(self):
        bundle, q, fy, cutoff, plan, _ = fixture(2025, 11, 3)
        rows = self.rows(bundle)
        rows[:] = [row for row in rows if not (row["start"] == plan.current_ytd.start and row["end"] == q)]
        with self.assertRaisesRegex(ValueError, "Missing exact"): self.calculate(bundle, q, fy, cutoff)

    def test_no_available_current_fact_before_filing(self):
        bundle, q, fy, _, _, _ = fixture()
        cutoff = (date.fromisoformat(q) + timedelta(days=29)).isoformat()
        with self.assertRaisesRegex(ValueError, "Missing exact"): self.calculate(bundle, q, fy, cutoff)

    def test_latest_available_restatement_changes_only_correct_context(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        newer = dict(self.rows(bundle)[1]);newer.update(filed=(date.fromisoformat(q) + timedelta(days=33)).isoformat(), val=710000000, accn="0000000000-26-000002")
        self.rows(bundle).append(newer)
        values, sources = self.calculate(bundle, q, fy, cutoff)
        self.assertEqual(values["revenue"], 1210)
        selected = sources[(sources.metric == "revenue") & (sources.ttm_bridge_role == "current_ytd")].iloc[0]
        self.assertEqual(selected.accession, newer["accn"])

    def test_conflicting_same_filing_date_values_fail_closed(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        bad = dict(self.rows(bundle)[1]);bad["val"] += 1
        self.rows(bundle).append(bad)
        with self.assertRaisesRegex(ValueError, "Conflicting"): self.calculate(bundle, q, fy, cutoff)

    def test_equivalent_concept_migration_and_conflict(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        tag = DURATION_TAGS["revenue"][1]
        bundle["facts"]["us-gaap"][tag] = copy.deepcopy(bundle["facts"]["us-gaap"].pop(DURATION_TAGS["revenue"][0]))
        values, sources = self.calculate(bundle, q, fy, cutoff)
        self.assertEqual(values["revenue"], 1200)
        self.assertEqual(set(sources[sources.metric == "revenue"].xbrl_tag), {tag})
        bundle["facts"]["us-gaap"][DURATION_TAGS["revenue"][0]] = copy.deepcopy(bundle["facts"]["us-gaap"][tag])
        self.rows(bundle)[1]["val"] += 1
        with self.assertRaisesRegex(ValueError, "Conflicting"): self.calculate(bundle, q, fy, cutoff)

    def test_wrong_units_and_missing_context_are_not_guessed(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        fact = bundle["facts"]["us-gaap"][DURATION_TAGS["revenue"][0]]
        fact["units"]["EUR"] = fact["units"].pop("USD")
        with self.assertRaisesRegex(ValueError, "Missing exact"): self.calculate(bundle, q, fy, cutoff)

    def test_nonfinite_boolean_and_malformed_accession_refused(self):
        for value in (float("nan"), float("inf"), True, "1000"):
            bundle, q, fy, cutoff, _, _ = fixture();self.rows(bundle)[1]["val"] = value
            with self.assertRaises(ValueError): self.calculate(bundle, q, fy, cutoff)
        bundle, q, fy, cutoff, _, _ = fixture();self.rows(bundle)[1]["accn"] = "not-an-accession"
        with self.assertRaises(ValueError): self.calculate(bundle, q, fy, cutoff)

    def test_future_cutoff_invalid_or_premature_filing_refused(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        for bad_cutoff in ("bad", (date.fromisoformat(q) - timedelta(days=1)).isoformat()):
            with self.assertRaises(ValueError): self.calculate(bundle, q, fy, bad_cutoff)
        self.rows(bundle)[1]["filed"] = (date.fromisoformat(q) - timedelta(days=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "before its period"): self.calculate(bundle, q, fy, cutoff)

    def override(self, bundle, metric="depreciation_amortization"):
        point = copy.deepcopy(self.rows(bundle, metric)[1])
        # All identifiers and digest here are synthetic syntax fixtures, not retrieved evidence.
        source = dict(metric=metric, source_type="sec_filing_table", unit="USD", start=point["start"], end=point["end"],
                      filed=point["filed"], accession=point["accn"], form=point["form"], value_raw=point["val"],
                      value_usd_millions=point["val"] / 1e6, source_sha256="0" * 64,
                      source_url="https://www.sec.gov/Archives/edgar/data/0/000000000026000001/SYNTHETIC_FIXTURE.htm")
        return {metric: {point["end"]: {"value_usd_millions": point["val"] / 1e6, "source_row": source}}}

    def test_exact_table_override_is_used_and_not_mutated(self):
        bundle, q, fy, cutoff, _, _ = fixture();overrides = self.override(bundle);before = copy.deepcopy(overrides)
        values, sources = self.calculate(bundle, q, fy, cutoff, overrides)
        self.assertEqual(values["depreciation_amortization"], 60)
        self.assertEqual(sum(sources.source_type == "sec_filing_table"), 1)
        self.assertEqual(overrides, before)

    def test_table_override_context_provenance_units_and_values_refused(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        alterations = (("start", None), ("unit", "EUR"), ("source_sha256", "bad"),
                       ("source_url", "https://www.sec.gov.evil.example/Archives/edgar/data/0/000000000026000001/fake"),
                       ("accession", "0000000000-26-000999"), ("value_raw", 1), ("metric", "revenue"))
        for key, value in alterations:
            overrides = self.override(bundle);overrides["depreciation_amortization"][q]["source_row"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): self.calculate(bundle, q, fy, cutoff, overrides)

    def test_negative_operating_outcome_is_retained(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        for row in self.rows(bundle, "operating_income"): row["val"] = -row["val"]
        values, _ = self.calculate(bundle, q, fy, cutoff)
        self.assertEqual(values["operating_income"], -180)
        self.assertEqual(values["ebitda_proxy"], -120)
        self.assertEqual(values["ebitda_interest_coverage"], -4)

    def test_zero_revenue_is_refused_and_zero_interest_is_diagnostic(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        for row in self.rows(bundle): row["val"] = 0
        with self.assertRaisesRegex(ValueError, "revenue positive"): self.calculate(bundle, q, fy, cutoff)
        bundle, q, fy, cutoff, _, _ = fixture()
        for row in self.rows(bundle, "interest_expense"): row["val"] = 0
        values, _ = self.calculate(bundle, q, fy, cutoff)
        self.assertTrue(math.isnan(values["ebitda_interest_coverage"]))

    def test_malformed_input_mappings_refused(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        for malformed in ({"facts": None}, {"facts": {"us-gaap": []}},
                          {"facts": {"us-gaap": {"Revenues": {"units": None}}}}):
            with self.assertRaises(ValueError): self.calculate(malformed, q, fy, cutoff)
        with self.assertRaises(ValueError): self.calculate(bundle, q, fy, cutoff, {"revenue": None})

    def test_positive_interest_coverage_overflow_refused(self):
        bundle, q, fy, cutoff, _, _ = fixture()
        for row in self.rows(bundle, "interest_expense"): row["val"] = 1e-310
        with self.assertRaisesRegex(ValueError, "coverage is not finite"): self.calculate(bundle, q, fy, cutoff)

    def test_typed_reference_and_corruption_guard(self):
        expected = {"cases": 144, "value": 1.0}
        compare(expected, expected)
        for actual in ({"cases": True, "value": 1.0}, {"cases": 144, "value": 1},
                       {"cases": 144, "value": float("nan")}, {"cases": 143, "value": 1.0}):
            with self.assertRaises(ValueError): compare(actual, expected)

    def test_runner_refuses_existing_and_committed_evidence_paths(self):
        before = legacy_blob_hashes()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError): run(Path(directory))
        for target in (ROOT, ROOT / "reference/new-output", ROOT / "results/new-output"):
            with self.assertRaises(ValueError): run(target)
        self.assertEqual(legacy_blob_hashes(), before)


if __name__ == "__main__": unittest.main()
