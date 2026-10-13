import copy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research_sec_intake.intake import acquire, verify, SEC_ARCHIVES, SEC_DATA

CIK = '0000815097'
ACCESSION = '0000815097-26-000107'
FILED = '2026-09-29'
REPORT = '2026-08-31'
CUTOFF = '2026-10-13'
PRIMARY = 'ccl-20260831.htm'
URL_SUB = f'{SEC_DATA}/submissions/CIK{CIK}.json'
URL_FACTS = f'{SEC_DATA}/api/xbrl/companyfacts/CIK{CIK}.json'
URL_HTML = f'{SEC_ARCHIVES}/815097/{ACCESSION.replace("-", "")}/{PRIMARY}'


class MockResponse:
    def __init__(self, url, content, status=200, redirect=None):
        self.url = redirect or url
        self.content = content
        self.status_code = status


class MockTransport:
    def __init__(self, bodies):
        self.bodies = bodies
        self.history = []
        self.bad_status = {}
        self.redirects = {}
        self.fail_url = None

    def get(self, url, headers, timeout, allow_redirects):
        self.history.append((url, dict(headers), timeout, allow_redirects))
        if self.fail_url == url:
            raise ConnectionError('Synthetic transport offline')
        return MockResponse(url, self.bodies[url], self.bad_status.get(url, 200), self.redirects.get(url))


def fixtures():
    subs = {'cik': 815097, 'filings': {'recent': {
        'accessionNumber': [ACCESSION], 'form': ['10-Q'],
        'reportDate': [REPORT], 'filingDate': [FILED], 'primaryDocument': [PRIMARY]}}}
    facts = {'cik': 815097, 'facts': {'us-gaap': {'Revenues': {'units': {'USD': []}}}}}
    return {URL_SUB: json.dumps(subs, sort_keys=True).encode(),
            URL_FACTS: json.dumps(facts, sort_keys=True).encode(),
            URL_HTML: b'<!doctype html>\n<html><body>synthetic filing placeholder</body></html>'}


class SECIntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dest = self.root / 'evidence'
        self.body = fixtures()
        self.transport = MockTransport(self.body)
        self.params = {'cik': CIK, 'accession': ACCESSION, 'form': '10-Q',
                       'report_end': REPORT, 'filed_on': FILED, 'as_of': CUTOFF,
                       'output_dir': self.dest,
                       'user_agent': 'Academic research analyst contact example@example.com',
                       'session': self.transport}

    def go(self, **overrides):
        return acquire(**dict(self.params, **overrides))

    def test_success_original_bytes_and_sha256(self):
        saved = self.go()
        self.assertEqual([x['kind'] for x in saved['sources']], ['submissions', 'companyfacts', 'filing_html'])
        self.assertEqual(verify(self.dest, expected_cik=CIK), saved)
        for row in saved['sources']:
            self.assertEqual((self.dest / row['filename']).read_bytes(), self.body[row['url']])
            self.assertEqual(row['sha256'], hashlib.sha256(self.body[row['url']]).hexdigest())

    def test_user_agent_and_no_redirects(self):
        self.go()
        self.assertEqual(len(self.transport.history), 3)
        for url, headers, timeout, redirect in self.transport.history:
            self.assertEqual(headers['User-Agent'], self.params['user_agent'])
            self.assertEqual(timeout, 45)
            self.assertIs(redirect, False)
            self.assertTrue(url.startswith('https://'))

    def test_output_collision_disallows_overwrite(self):
        self.go()
        before = (self.dest / 'manifest.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'must not exist'): self.go()
        self.assertEqual((self.dest / 'manifest.json').read_bytes(), before)

    def test_parent_must_exist(self):
        with self.assertRaisesRegex(ValueError, 'parent'): self.go(output_dir=self.root / 'missing' / 'evidence')

    def test_no_partial_commit_on_network_failure(self):
        self.transport.fail_url = URL_HTML
        with self.assertRaises(ConnectionError): self.go()
        self.assertFalse(self.dest.exists())

    def test_accession_missing_is_closed(self):
        self.body[URL_SUB] = self.body[URL_SUB].replace(ACCESSION.encode(), b'0000815097-26-000108')
        with self.assertRaisesRegex(ValueError, 'not unique'): self.go()
        self.assertFalse(self.dest.exists())

    def test_accession_duplicate_is_closed(self):
        subs = json.loads(self.body[URL_SUB]);rec = subs['filings']['recent']
        for k in rec: rec[k].append(rec[k][0])
        self.body[URL_SUB] = json.dumps(subs).encode()
        with self.assertRaisesRegex(ValueError, 'not unique'): self.go()

    def test_mismatching_filing_fields(self):
        for k, mismatch in [('form', '10-K'), ('reportDate','2026-05-31'), ('filingDate','2026-09-30')]:
            with self.subTest(k=k):
                a = json.loads(fixtures()[URL_SUB]);a['filings']['recent'][k][0] = mismatch
                self.body[URL_SUB] = json.dumps(a).encode()
                with self.assertRaisesRegex(ValueError, 'disagreement'): self.go()

    def test_redirect_refused(self):
        for url in (URL_SUB, URL_FACTS, URL_HTML):
            with self.subTest(url=url):
                self.transport.redirects = {url: 'https://evil.example.com/download'}
                with self.assertRaisesRegex(ValueError, 'redirected'): self.go()
                self.transport.redirects = {}

    def test_http_403_refused(self):
        for url in (URL_SUB, URL_FACTS, URL_HTML):
            with self.subTest(url=url):
                self.transport.bad_status = {url: 403}
                with self.assertRaisesRegex(ValueError, 'unavailable'): self.go()
                self.transport.bad_status = {}

    def test_bad_json_refused(self):
        for url in (URL_SUB, URL_FACTS):
            with self.subTest(url=url):
                old = self.body[url]; self.body[url] = b'<html>Sorry 429</html>'
                with self.assertRaisesRegex(ValueError, 'JSON'): self.go()
                self.body[url] = old

    def test_bad_cik_refused(self):
        for url in (URL_SUB, URL_FACTS):
            with self.subTest(url=url):
                obj = json.loads(self.body[url]);obj['cik'] = 1
                old = self.body[url];self.body[url] = json.dumps(obj).encode()
                with self.assertRaisesRegex(ValueError, 'CIK mismatch'): self.go()
                self.body[url] = old

    def test_invalid_companyfacts_structure_refused(self):
        for facts in ({}, {'dei': {}}, []):
            with self.subTest(facts=facts):
                old=self.body[URL_FACTS];self.body[URL_FACTS] = json.dumps({'cik':815097,'facts':facts}).encode()
                with self.assertRaises(ValueError): self.go()
                self.body[URL_FACTS] = old

    def test_submissions_array_alignment_refused(self):
        a=json.loads(self.body[URL_SUB]);a['filings']['recent']['form'].append('10-Q')
        self.body[URL_SUB] = json.dumps(a).encode()
        with self.assertRaisesRegex(ValueError,'misaligned'):self.go()

    def test_strict_path_rejects_dangerous_primary_document(self):
        for v in ('../../bad.htm', 'https://evil.com/index.htm', 'bad.html.exe', 'index.htm?x=1', '../go.html'):
            with self.subTest(v=v):
                a=json.loads(fixtures()[URL_SUB]);a['filings']['recent']['primaryDocument'][0]=v
                self.body[URL_SUB] = json.dumps(a).encode()
                with self.assertRaisesRegex(ValueError, 'primaryDocument'): self.go()

    def test_bad_html_refused(self):
        self.body[URL_HTML] = b'{"message":"blocked"}'
        with self.assertRaisesRegex(ValueError,'HTML'): self.go()

    def test_malformed_dates_refused(self):
        for field,bad in [('report_end','2026-08-3'),('filed_on','2026-02-30'),('as_of','20261013')]:
            with self.subTest(field=field):
                with self.assertRaises(ValueError): self.go(**{field:bad})

    def test_date_order_refused(self):
        for d in ({'filed_on':'2026-08-01'}, {'as_of':'2026-09-01'}, {'as_of': '2099-01-01'}):
            with self.subTest(d=d):
                with self.assertRaisesRegex(ValueError,'dates'): self.go(**d)

    def test_wrong_cik_in_requested_accession_refused(self):
        for accession in ('0000000001-26-000107','foo','0000815097-26-107'):
            with self.subTest(acc=accession):
                with self.assertRaisesRegex(ValueError, 'Accession'): self.go(accession=accession)

    def test_unsupported_form_refused(self):
        with self.assertRaisesRegex(ValueError,'10-Q and 10-K'): self.go(form='8-K')

    def test_missing_or_noncontact_agent_refused(self):
        for ua in ('', 'bot@example.com', 'testbot', None):
            with self.subTest(ua=ua):
                with self.assertRaises(ValueError): self.go(user_agent=ua)

    def test_corrupt_original_byte_detected(self):
        rec=self.go();file=self.dest / rec['sources'][2]['filename'];file.write_bytes(file.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'identity verification'):verify(self.dest,expected_cik=CIK)

    def test_missing_original_detected(self):
        rec=self.go();(self.dest / rec['sources'][0]['filename']).unlink()
        with self.assertRaises(FileNotFoundError): verify(self.dest,expected_cik=CIK)

    def test_extra_file_detected(self):
        self.go();(self.dest/'unregistered.txt').write_text('secret')
        with self.assertRaisesRegex(ValueError,'extra'):verify(self.dest,expected_cik=CIK)

    def test_altered_manifest_bytes_detected(self):
        self.go();p=self.dest/'manifest.json'; obj=json.loads(p.read_text());obj['sources'][0]['sha256']='0'*64
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,'identity verification'):verify(self.dest,expected_cik=CIK)

    def test_manifest_filing_date_corruption_refused(self):
        self.go()
        p = self.dest / 'manifest.json'
        obj = json.loads(p.read_text()); obj['filed_on'] = '2026-09-30'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'not grounded'): verify(self.dest, expected_cik=CIK)

    def test_manifest_submissions_url_corruption_refused(self):
        self.go()
        p = self.dest / 'manifest.json'
        obj = json.loads(p.read_text()); obj['sources'][0]['url'] = 'https://evil.example.com/foo'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'URL/path mismatch'): verify(self.dest, expected_cik=CIK)

    def test_manifest_html_url_corruption_refused(self):
        self.go()
        p = self.dest / 'manifest.json'
        obj = json.loads(p.read_text()); obj['sources'][2]['url'] += '-wrong'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'not grounded'): verify(self.dest, expected_cik=CIK)

    def test_manifest_duplicate_kind_refused(self):
        self.go()
        p = self.dest / 'manifest.json'
        obj = json.loads(p.read_text()); obj['sources'][1]['kind'] = 'submissions'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'Duplicate source kinds'): verify(self.dest, expected_cik=CIK)

    def test_manifest_asof_before_filing_refused(self):
        self.go()
        p = self.dest / 'manifest.json'
        obj = json.loads(p.read_text()); obj['as_of'] = '2026-09-01'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'dates inconsistent'): verify(self.dest, expected_cik=CIK)

    def test_unsupported_asof_history_claim_absent(self):
        r=self.go();self.assertEqual(r['kind'],'raw_SEC_byte_capture_not_asof_history')
        self.assertNotIn('as_of_verified_source_content',r)

    def test_no_input_mutation(self):
        before=copy.deepcopy(self.body)
        self.go();self.assertEqual(self.body,before)

if __name__=='__main__':unittest.main()
