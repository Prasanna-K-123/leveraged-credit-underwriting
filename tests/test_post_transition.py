from decimal import Decimal, ROUND_DOWN, localcontext
from pathlib import Path
import tempfile
import unittest

from lxml import html

from research_post_transition.model import (AGGREGATES, amount, debt_instruments,
    disclosed_terms, liquidity_proxy, maturities, obligor_group, refuse_unsupported,
    source_analysis, spans, synthetic_allocation, unique_table, value)
from research_post_transition.run import ASSUMPTIONS, ROOT, compute, run, synthetic_contract
from research_sec_quarters.reconcile import clean_text, parse_document, verify_capture
from research_sec_quarters.run import INPUT, unpack_input


class PostTransitionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as temp:
            capture = Path(temp) / 'capture'
            unpack_input(INPUT, capture)
            verified, _, _ = verify_capture(capture)
            cls.body = verified['q3_2026']['body']
        cls.actual = source_analysis(cls.body, 1220)

    def doc(self):
        return parse_document(self.body)[0]

    def instrument_cell(self, doc, label='Notes (c)', start=15):
        table = unique_table(doc, AGGREGATES)
        row = next(r for r in table.iter('tr') if len(r) and clean_text(r[0]) == label)
        return next(c for a, b, c in spans(row, 24) if start <= a < start + 3 and any(True for _ in c.iter('ix:nonfraction')))

    def test_all21_instruments_and_both_reported_classes(self):
        rows = self.actual['reported_debt']['instruments']
        self.assertEqual(len(rows), 21)
        counts = {k: sum(r['reported_category'] == k for r in rows) for k in ('Unsecured Subsidiary Guaranteed', 'Unsecured (No Subsidiary Guarantee)')}
        self.assertEqual(list(counts.values()), [8, 13])
        self.assertEqual(self.actual['reported_debt']['subtotals']['Total Debt']['current_usd_millions'], 24559)

    def test_accepted_comparative_rounding_gaps_are_visible(self):
        gaps = self.actual['reported_debt']['actual_signed_display_gaps_usd_millions']
        self.assertEqual(list(gaps['current'].values()), [0, 0, 0])
        self.assertEqual(list(gaps['comparative'].values()), [1, 1, -1])
        self.assertEqual(self.actual['reported_debt']['subtotals']['Total Debt']['comparative_usd_millions'], 27383)

    def test_absent_secured_category_and_actual_recovery_are_null(self):
        self.assertIsNone(self.actual['reported_debt']['absent_secured_subtotal'])
        self.assertIsNone(self.actual['actual_post_transition_legal_recovery'])
        self.assertEqual(self.actual['old_full_recovery_criterion'], 'FAILED_AND_UNCHANGED')

    def test_numeric_inline_context_population(self):
        evidence = self.actual['inline_amount_contexts']
        self.assertEqual(len(evidence), 63)
        self.assertTrue(all(r['entity'] == '0000815097' and r['units'] == 'USD million' for r in evidence))
        self.assertEqual({r['report_date'] for r in evidence}, {'2026-08-31', '2025-11-30'})

    def test_positive_xbrl_accounts_remain_distinct_from_displayed_subtractions(self):
        rows = [r for r in self.actual['inline_amount_contexts'] if r['presentation_direction'] == -1]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(r['xbrl_account_value'] > 0 and r['displayed_amount'] < 0 for r in rows))
        doc = self.doc();cell = self.instrument_cell(doc, 'Less: Current portion of long-term debt')
        next(cell.iter('ix:nonfraction')).set('sign', '-')
        with self.assertRaisesRegex(ValueError, 'account semantics'):
            source_analysis(html.tostring(doc), 1220)

    def test_header_column_swap_is_refused(self):
        doc = self.doc()
        table = unique_table(doc, AGGREGATES)
        row = next(r for r in table.iter('tr') if len(r) and clean_text(r[0]) == '(in millions)')
        cell = next(c for a, b, c in spans(row, 24) if a == 15)
        cell.clear();cell.set('colspan', '3');cell.text = 'November 30, 2025'
        with self.assertRaisesRegex(ValueError, 'dates'):
            debt_instruments(doc)

    def test_missing_instrument_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc);row = cell.getparent();row.getparent().remove(row)
        with self.assertRaises(ValueError):
            debt_instruments(doc)

    def test_blank_is_not_zero(self):
        doc = self.doc();cell = self.instrument_cell(doc, 'Convertible Notes');cell.clear();cell.set('colspan', '1')
        with self.assertRaises(ValueError):
            debt_instruments(doc)

    def test_malformed_comma_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc)
        next(cell.iter('ix:nonfraction')).text = '1,9,2'
        with self.assertRaises(ValueError):
            debt_instruments(doc)

    def test_out_of_tolerance_instrument_gap_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc);next(cell.iter('ix:nonfraction')).text = '195'
        with self.assertRaisesRegex(ValueError, 'Instrument/subtotal'):
            debt_instruments(doc)

    def test_nonzero_category_total_gap_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc, 'Total Debt');next(cell.iter('ix:nonfraction')).text = '24,560'
        with self.assertRaisesRegex(ValueError, 'Category/total'):
            debt_instruments(doc)

    def test_wrong_currency_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc);next(cell.iter('ix:nonfraction')).set('unitref', 'number')
        with self.assertRaisesRegex(ValueError, 'currency'):
            source_analysis(html.tostring(doc), 1220)

    def test_wrong_million_scale_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc);next(cell.iter('ix:nonfraction')).set('scale', '3')
        with self.assertRaisesRegex(ValueError, 'scale'):
            source_analysis(html.tostring(doc), 1220)

    def test_wrong_instant_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc);e = next(cell.iter('ix:nonfraction'))
        current = e.get('contextref')
        context = next(c for c in doc.iter('xbrli:context') if c.get('id') == current)
        next(context.iter('xbrli:instant')).text = '2026-05-31'
        with self.assertRaisesRegex(ValueError, 'instant'):
            source_analysis(html.tostring(doc), 1220)

    def test_unknown_transformation_is_refused(self):
        doc = self.doc();cell = self.instrument_cell(doc);next(cell.iter('ix:nonfraction')).set('format', 'unknown:transform')
        with self.assertRaisesRegex(ValueError, 'transformation'):
            source_analysis(html.tostring(doc), 1220)

    def test_maturities_independently_sum_to_principal(self):
        schedule = self.actual['reported_maturities']
        self.assertEqual([r['principal_usd_millions'] for r in schedule.values()], [301, 2517, 3961, 3631, 2885, 11264, 24559])

    def test_missing_maturity_bucket_is_refused(self):
        doc = self.doc();table = unique_table(doc, ('Year', 'Remainder of 2026', 'Thereafter', 'Total'))
        row = next(r for r in table.iter('tr') if len(r) and clean_text(r[0]) == '2028');row.getparent().remove(row)
        with self.assertRaises(ValueError):
            maturities(doc, 24559)

    def test_negative_pledge_is_not_collateral(self):
        terms = self.actual['disclosed_terms']
        self.assertEqual(terms['negative_pledge']['book_value_usd_millions'], 20600)
        self.assertIsNone(terms['negative_pledge']['secured_recovery_pool'])
        self.assertEqual(terms['sun_princess_exception']['rounded_disclosed_usd_millions'], 1700)
        self.assertIsNone(terms['sun_princess_exception']['exact_instrument_estate_mapping'])

    def test_export_credit_is_excluded_from_general_liquidity(self):
        self.assertEqual(self.actual['disclosed_terms']['ship_export_facilities']['undrawn_usd_millions'], 10700)
        proxy = self.actual['financial_liquidity_proxy']
        self.assertEqual(proxy['cash_plus_conditional_revolver_usd_millions'], 5720)
        self.assertFalse(proxy['ship_specific_export_facilities_included'])

    def test_static_maturity_proxy_and_reserve_preserve_negative_values(self):
        rows = self.actual['financial_liquidity_proxy']['buckets']
        self.assertEqual(rows[1]['cumulative_principal_usd_millions'], 2818)
        self.assertEqual(rows[1]['cash_plus_revolver_after_fixed_reserve_minus_cumulative'], 1402)
        self.assertEqual(rows[2]['cash_plus_revolver_minus_cumulative'], -1059)
        self.assertIsNone(self.actual['financial_liquidity_proxy']['agreement_defined_covenant_headroom'])

    def test_revolver_conditionality_cannot_be_removed(self):
        modified = self.body.replace(b'subject to the satisfaction of the conditions in the facility', b'available without any conditions')
        self.assertNotEqual(modified, self.body)
        with self.assertRaisesRegex(ValueError, 'available for borrowing'):
            disclosed_terms(parse_document(modified)[0])

    def test_duplicate_disclosure_is_refused(self):
        doc = self.doc()
        from research_post_transition.model import paragraph
        e = paragraph(doc, 'sun princess limited', ('august 31, 2026',))
        e.getparent().append(html.fromstring(html.tostring(e)))
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            disclosed_terms(doc)

    def test_agreement_thresholds_are_reported_not_recalculated(self):
        terms = self.actual['disclosed_terms']
        self.assertEqual(terms['interest_threshold']['reported_minimum_ratio'], '3.0')
        self.assertEqual(terms['capital_threshold']['reported_minimum_usd_millions'], 5000)
        self.assertEqual(terms['debt_capital_threshold']['reported_maximum_percent'], 65)
        self.assertEqual(terms['liquidity_threshold']['reported_minimum_usd_millions'], 1500)
        self.assertIsNone(terms['issuer_compliance']['independently_recalculated_agreement_compliance'])

    def test_obligor_intercompany_basis_is_retained(self):
        group = self.actual['reported_obligor_summary']
        self.assertEqual(group['reported_combined_balances']['Current assets - due from Non-Obligor Subsidiaries']['current_usd_millions'], 3093)
        self.assertIsNone(group['nonobligor_assets_inferred_by_subtraction'])
        self.assertIsNone(group['existing_debt_instrument_estate_mapping'])

    def test_obligor_basis_mutation_is_refused(self):
        doc = self.doc()
        from research_post_transition.model import paragraph
        e = paragraph(doc, 'the following summarized financial information')
        text = clean_text(e).replace('have been excluded', 'have been included')
        e.clear();e.text = text
        with self.assertRaisesRegex(ValueError, 'summarized financial'):
            disclosed_terms(doc)

    def test_actual_legal_requests_are_refused(self):
        for r in self.actual['unsupported_requests']:
            self.assertEqual(r['status'], 'REFUSED');self.assertIsNone(r['value'])
        with self.assertRaises(ValueError):
            refuse_unsupported('unregistered_request')

    def test_bad_display_types_and_tokens_are_refused(self):
        for token in [None, True, 0, '', 'NaN', '1,2', '$1', '1 000', '-1', '(1,2)']:
            with self.subTest(token=token), self.assertRaises(ValueError):
                value(token)
        self.assertEqual(value('\u2014'), 0)
        self.assertEqual(value('( 647 )'), -647)

    def test_input_hash_has_no_display_tolerance(self):
        with tempfile.TemporaryDirectory() as temp:
            wrong = Path(temp) / 'altered.zip';wrong.write_bytes(INPUT.read_bytes() + b'X')
            with self.assertRaisesRegex(ValueError, 'digest'):
                unpack_input(wrong, Path(temp) / 'capture')

    def test_existing_or_repository_output_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'outside repository'):
            run(ROOT)


class SyntheticAllocationTests(unittest.TestCase):
    def test_independent_oracle_and_all_declared_grid_properties(self):
        result = synthetic_contract()
        self.assertEqual(result['cases'], 832)
        self.assertEqual(result['permutation_checks'], 4992)
        self.assertEqual(result['individual_monotonicity_checks'], 2304)
        self.assertEqual(result['observed_contract_failures'], 0)
        self.assertLessEqual(Decimal(result['max_absolute_oracle_error']), Decimal(result['absolute_tolerance']))

    def test_zero_claims_and_full_payment_boundaries(self):
        a = synthetic_allocation('7', {'A': '0', 'B': '0'}, assumptions=ASSUMPTIONS)
        self.assertEqual(a['payments'], {'A': '0', 'B': '0'});self.assertEqual(a['residual'], '7')
        a = synthetic_allocation('12', {'A': '3', 'B': '4'}, assumptions=ASSUMPTIONS)
        self.assertEqual(a['payments'], {'A': '3', 'B': '4'});self.assertEqual(a['residual'], '5')

    def test_ambient_decimal_context_does_not_change_the_contract(self):
        baseline = synthetic_allocation('1', {'A': '1', 'B': '2'}, assumptions=ASSUMPTIONS)
        with localcontext() as context:
            context.prec = 7
            context.rounding = ROUND_DOWN
            self.assertEqual(synthetic_allocation('1', {'A': '1', 'B': '2'}, assumptions=ASSUMPTIONS), baseline)

    def test_all_explicit_synthetic_assumptions_are_required(self):
        for k in ASSUMPTIONS:
            for replacement in [False, None, 1, 'true']:
                assumptions = dict(ASSUMPTIONS);assumptions[k] = replacement
                with self.subTest(k=k, replacement=replacement), self.assertRaises(ValueError):
                    synthetic_allocation('1', {'A': '1'}, assumptions=assumptions)
        with self.assertRaises(ValueError):
            synthetic_allocation('1', {'A': '1'}, assumptions={})

    def test_nonfinite_negative_or_unbounded_inputs_are_refused(self):
        for bad in [True, 1, None, 'NaN', 'Infinity', '-1', '1e2', '01', '1.', '1' * 19]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                synthetic_allocation(bad, {'A': '1'}, assumptions=ASSUMPTIONS)
        with self.assertRaises(ValueError):
            synthetic_allocation('1', {}, assumptions=ASSUMPTIONS)

    def test_synthetic_result_never_claims_actual_issuer_recovery(self):
        a = synthetic_allocation('7', {'A': '5', 'B': '3', 'C': '2'}, assumptions=ASSUMPTIONS)
        self.assertEqual(a['payments'], {'A': '3.5', 'B': '2.1', 'C': '1.4'})
        self.assertIsNone(a['actual_issuer_recovery']);self.assertIsNone(a['currency_rounding_or_legal_priority'])


if __name__ == '__main__':
    unittest.main()
