import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from research_sec_quarters.capture import CIK, LimitedSession, select_targets
from research_sec_quarters.reconcile import (extract_metric, fact_parity, METRICS,
    number, parse_document, reconcile, verify_capture, write_result)
from research_sec_quarters.run import INPUT, balance_sheet, historical_blobs, unpack_input, reported_debt_classes


def statement(value="10", visible=None, metric="operating_income", context_entity=CIK,
              dimensional=False, scale="6", unit="iso4217:USD", context="c1", sign=""):
    tag, label, kind = METRICS[metric]
    cells = ["11", "12", value if visible is None else visible, "13"] if kind == "income" else [value if visible is None else visible, "13"]
    index = 2 if kind == "income" else 0
    cells[index] = f'<ix:nonfraction name="us-gaap:{tag}" contextref="{context}" unitref="usd" scale="{scale}" {sign}>{value}</ix:nonfraction>' if visible is None else cells[index]
    # A mismatch fixture keeps the printed cell outside the hidden IX node;
    # the hidden value has no primary-row provenance and cannot be selected.
    extra = f'<ix:nonfraction name="us-gaap:{tag}" contextref="{context}" unitref="usd" scale="{scale}">{value}</ix:nonfraction>' if visible is not None else ""
    terms = '<tr><td>Total Revenues</td></tr><tr><td>Operating Income</td></tr>' if kind == "income" else '<tr><td>OPERATING ACTIVITIES</td></tr><tr><td>INVESTING ACTIVITIES</td></tr>'
    if metric == "operating_income":
        terms = '<tr><td>Total Revenues</td></tr>'
    segment = '<xbrli:segment><xbrldi:explicitmember dimension="x">y</xbrldi:explicitmember></xbrli:segment>' if dimensional else ""
    return (f'<html><xbrli:context id="c1"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">{context_entity}</xbrli:identifier>{segment}</xbrli:entity>'
            '<xbrli:period><xbrli:startdate>2025-12-01</xbrli:startdate><xbrli:enddate>2026-08-31</xbrli:enddate></xbrli:period></xbrli:context>'
            f'<xbrli:unit id="usd"><xbrli:measure>{unit}</xbrli:measure></xbrli:unit>{extra}<table>'
            '<tr><td>Nine Months Ended August 31, 2026 2025</td></tr>' + terms +
            f'<tr><td>{label}</td>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr></table></html>').encode()


class ParserTests(unittest.TestCase):
    def extract(self, body, metric="operating_income"):
        return extract_metric(body, metric, "2025-12-01", "2026-08-31", report_end="2026-08-31", form="10-Q")

    def test_independent_numeric_magnitudes(self):
        self.assertEqual(number("( $ 1,234 )"), Decimal(-1234))
        self.assertEqual(number("-17.25"), Decimal("-17.25"))
        for text in ["1abc", "1/2", "NaN", "inf", "--1", "1 2x", "(1", "1e6"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                number(text)

    def test_exact_three_quarter_column(self):
        r = self.extract(statement())
        self.assertEqual(r["value_raw"], 10_000_000)
        self.assertEqual(r["selected_column"], 2)
        self.assertEqual(r["table_columns"], 4)

    def test_negative_operating_result_retained(self):
        r = self.extract(statement(value="10", sign='sign="-"').replace(b'</ix:nonfraction>', b'</ix:nonfraction>)').replace(b'><ix:nonfraction', b'>(<ix:nonfraction'))
        self.assertEqual(r["value_usd_millions"], -10)

    def test_expense_parentheses_are_magnitude(self):
        body = statement(value="10", metric="interest_expense").replace(b'</ix:nonfraction>', b'</ix:nonfraction>)').replace(b'><ix:nonfraction', b'>(<ix:nonfraction')
        r = self.extract(body, "interest_expense")
        self.assertEqual(r["value_usd_millions"], 10)
        self.assertEqual(r["visible_signed_millions"], -10)

    def test_wrong_period_and_dangling_context_refused(self):
        for body in [statement().replace(b'2025-12-01', b'2026-06-01'), statement(context="missing")]:
            with self.assertRaises(ValueError): self.extract(body)

    def test_dimensions_and_wrong_entity_refused(self):
        for body in [statement(dimensional=True), statement(context_entity="0000000001")]:
            with self.assertRaises(ValueError): self.extract(body)

    def test_unit_scale_and_transform_refused(self):
        for body in [statement(unit="iso4217:EUR"), statement(scale="3"), statement().replace(b'scale="6"', b'scale="6" format="unsupported"')]:
            with self.assertRaises(ValueError): self.extract(body)

    def test_duplicate_context_and_statement_refused(self):
        body = statement()
        c = body[body.index(b'<xbrli:context'):body.index(b'</xbrli:context>') + len(b'</xbrli:context>')]
        with self.assertRaises(ValueError): self.extract(body.replace(b'<table>', c + b'<table>'))
        row = body[body.index(b'<tr><td>operating income'):body.index(b'</table>')]
        with self.assertRaises(ValueError): self.extract(body.replace(b'</table>', row + b'</table>'))

    def test_visible_column_mismatch_refused(self):
        # Change the registration-relevant visible column count without
        # changing the tagged context: a loose row parser would accept it.
        body = statement().replace(b'<td>12</td>', b'<td>12</td><td>99</td>')
        with self.assertRaises(ValueError): self.extract(body)
        with self.assertRaises(ValueError): self.extract(statement(visible="99"))

    def test_exact_companyfacts_identity_and_conflict(self):
        r = self.extract(statement())
        m = dict(accession="0000815097-26-000107", form="10-Q", filed_on="2026-09-29")
        entry = dict(start=r["start"], end=r["end"], val=10_000_000, accn=m["accession"], form=m["form"], filed=m["filed_on"])
        cf = {"facts": {"us-gaap": {r["xbrl_tag"]: {"units": {"USD": [entry]}}}}}
        self.assertEqual(fact_parity(cf, r, m)["matches"], 1)
        for key, value in [("start", "2026-06-01"), ("end", "2026-05-31"), ("accn", "0000815097-26-000037"),
                           ("filed", "2026-10-15"), ("form", "10-K"), ("val", True), ("val", 11_000_000)]:
            bad = copy.deepcopy(cf);bad["facts"]["us-gaap"][r["xbrl_tag"]]["units"]["USD"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): fact_parity(bad, r, m)


class OriginalSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name) / "capture"
        unpack_input(INPUT, cls.root)
        cls.verified, cls.facts, cls.status = verify_capture(cls.root)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_all_original_sources_and_complete_plan(self):
        self.assertEqual(len(self.verified), 5)
        self.assertEqual(len(self.status["captures"]), 5)
        targets = select_targets(json.loads((self.root / "discovery_submissions.json").read_text()))
        self.assertEqual(targets, self.status["resolved_targets"])
        self.assertEqual(targets[3]["accession"], "0000815097-25-000025")

    def test_plan_ambiguity_wrong_accession_and_future_refused(self):
        base = json.loads((self.root / "discovery_submissions.json").read_text())
        for fault in ["duplicate", "wrong_accession", "future"]:
            bad = copy.deepcopy(base);rec = bad["filings"]["recent"]
            i = rec["accessionNumber"].index("0000815097-26-000107")
            if fault == "duplicate":
                for key in rec: rec[key].append(rec[key][i])
            elif fault == "wrong_accession": rec["accessionNumber"][i] = "0000815097-26-000108"
            else: rec["filingDate"][i] = "2026-10-15"
            with self.subTest(fault=fault), self.assertRaises(ValueError): select_targets(bad)

    def test_original_q1_unlabelled_revenue_component_check(self):
        source = self.verified["q1_2025_original"]
        args = dict(metric="revenue", start="2024-12-01", end="2025-02-28", report_end="2025-02-28", form="10-Q")
        self.assertEqual(extract_metric(source["body"], **args)["value_usd_millions"], 5810)
        corrupted = source["body"].replace(b'3,832', b'9,832')
        with self.assertRaises(ValueError): extract_metric(corrupted, **args)

    def test_real_both_quarters_and_prior_originals(self):
        result = reconcile(self.root)
        expected = {"q1_2026": [26977,4547,2832,1263,6556,3570], "q3_2026": [27593,4413,2898,1177,6821,3645]}
        for label, values in expected.items():
            actual = result["results"][label]
            self.assertEqual([actual["metrics"][k] for k in METRICS], values)
            self.assertEqual(len(actual["verified_sources"]), 18)
            self.assertEqual(len(actual["original_comparisons"]), 6)
            for r in actual["original_comparisons"]: self.assertEqual(r["original_value"], r["current_comparative"])

    def test_balance_is_exact_quarter_not_latest(self):
        q1, q1_evidence = balance_sheet(self.verified["q1_2026"], self.facts)
        q3, q3_evidence = balance_sheet(self.verified["q3_2026"], self.facts)
        self.assertEqual(q1["period_end"], "2026-02-28")
        self.assertEqual(q3["period_end"], "2026-08-31")
        self.assertEqual(len(q1_evidence), 3);self.assertEqual(len(q3_evidence), 3)
        for e in q1_evidence: self.assertEqual(e["accession"], "0000815097-26-000037")
        for e in q3_evidence: self.assertEqual(e["accession"], "0000815097-26-000107")
        self.assertNotEqual(q1["cash"], q3["cash"])

    def test_actual_balance_source_conflict_refused(self):
        bad = copy.deepcopy(self.facts)
        values = bad["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"]["units"]["USD"]
        for e in values:
            if e.get("end") == "2026-02-28" and e.get("accn") == "0000815097-26-000037": e["val"] += 1
        with self.assertRaises(ValueError): balance_sheet(self.verified["q1_2026"], bad)

    def test_q3_reported_debt_and_missing_secured_model_input(self):
        debt, evidence = reported_debt_classes(self.verified["q3_2026"])
        self.assertEqual(debt["gross_debt"], 24559)
        self.assertEqual(debt["unsecured_subsidiary_guaranteed"], 10953)
        self.assertEqual(debt["unsecured_no_subsidiary_guarantee"], 13606)
        self.assertNotIn("secured_subsidiary_guaranteed", debt)
        self.assertEqual(len(evidence), 6)
        bad = dict(self.verified["q3_2026"])
        bad["body"] = bad["body"].replace(b'13,606', b'13,607')
        with self.assertRaises(ValueError): reported_debt_classes(bad)

    def test_q3_collateral_status_must_be_original_disclosure(self):
        bad = dict(self.verified["q3_2026"])
        bad["body"] = bad["body"].replace(b'were no longer secured as of August 31, 2026', b'were secured as of August 31, 2026')
        with self.assertRaises(ValueError): reported_debt_classes(bad)

    def test_raw_corruption_and_partial_collection_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "bad";shutil.copytree(self.root, root)
            p = root / "q3_2026" / self.verified["q3_2026"]["sources"]["filing_html"]["filename"]
            p.write_bytes(p.read_bytes() + b' ')
            with self.assertRaises(ValueError): verify_capture(root)
            shutil.rmtree(root / "q3_2026")
            with self.assertRaises(ValueError): verify_capture(root)

    def test_zip_identity_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "changed.zip";p.write_bytes(INPUT.read_bytes() + b' ')
            with self.assertRaises(ValueError): unpack_input(p, Path(temp) / "out")

    def test_atomic_nonoverwrite_and_input_nonmutation(self):
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "result";write_result(self.root, out)
            saved = (out / "summary.json").read_bytes()
            with self.assertRaises(ValueError): write_result(self.root, out)
            self.assertEqual(saved, (out / "summary.json").read_bytes())
        after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        with self.assertRaises(ValueError): write_result(self.root, self.root / "out")

    def test_all_historical_blobs_preserved(self):
        self.assertEqual(len(historical_blobs()), 46)


class RateTests(unittest.TestCase):
    def test_sequential_rate_limit_without_retry(self):
        times, calls = [0.0], []
        class Session:
            def get(self, url, **kwargs): calls.append((url, times[0]));return url
        def pause(seconds): times[0] += seconds
        session = LimitedSession(Session(), clock=lambda: times[0], pause=pause)
        for i in range(4): self.assertEqual(session.get(str(i)), str(i))
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(b[1] - a[1] >= 0.2 - 1e-12 for a,b in zip(calls,calls[1:])))


if __name__ == "__main__": unittest.main()
