"""Frozen offline source/financial-proxy and synthetic contract replay."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
from itertools import permutations, product
import json
from pathlib import Path
import tempfile

from research_post_transition.model import source_analysis, synthetic_allocation
from research_sec_quarters.reconcile import verify_capture
from research_sec_quarters.run import INPUT, balance_sheet, compare_reference, unpack_input

ROOT = Path(__file__).resolve().parents[1]
ASSUMPTIONS = {'synthetic_only': True, 'same_estate': True, 'same_priority': True, 'no_other_senior_claims': True}


def frozen_history():
    entries = json.loads((ROOT / 'research_post_transition/HISTORICAL_GIT_BLOBS.json').read_text())
    for original, entry in entries.items():
        b = (ROOT / entry['current_path']).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
        if actual != entry['git_blob_sha']:
            raise ValueError('Historical Git blob changed: ' + original)
    return entries


def synthetic_contract():
    cases, permutation_checks, monotonicity_checks = 0, 0, 0
    maximum_error = Decimal(0)
    tolerance = Decimal('1e-40')
    with localcontext() as context:
        context.prec = 80
        for vector in product(range(4), repeat=3):
            claims = dict(zip(('A', 'B', 'C'), map(str, vector)))
            total = sum(vector)
            previous = None
            for estate in range(13):
                actual = synthetic_allocation(str(estate), claims, assumptions=ASSUMPTIONS)
                payments = {k: Decimal(v) for k, v in actual['payments'].items()}
                paid = sum(payments.values())
                if abs(paid + Decimal(actual['residual']) - estate) > tolerance:
                    raise ValueError('Synthetic conservation failure')
                for k, c in zip(('A', 'B', 'C'), vector):
                    oracle = Fraction(min(estate, total) * c, total) if total else Fraction(0)
                    expected = Decimal(oracle.numerator) / Decimal(oracle.denominator)
                    error = abs(payments[k] - expected)
                    maximum_error = max(maximum_error, error)
                    if error > tolerance or payments[k] < 0 or payments[k] > c:
                        raise ValueError('Independent rational oracle or bounds failure')
                    if previous is not None and payments[k] + tolerance < previous[k]:
                        raise ValueError('Synthetic estate monotonicity failure')
                    if previous is not None:
                        monotonicity_checks += 1
                for ordering in permutations(claims):
                    permuted = {k: claims[k] for k in ordering}
                    if synthetic_allocation(str(estate), permuted, assumptions=ASSUMPTIONS) != actual:
                        raise ValueError('Permutation failure')
                    permutation_checks += 1
                previous = payments
                cases += 1
    return {'scope': 'Constructed finite conformance grid; not observed debtor recoveries',
            'claim_values': [0, 1, 2, 3], 'creditors': 3, 'estate_values': list(range(13)),
            'cases': cases, 'permutation_checks': permutation_checks,
            'individual_monotonicity_checks': monotonicity_checks,
            'independent_oracle': 'Fraction exact proportional allocation, independently evaluated',
            'decimal_precision_digits': 60, 'absolute_tolerance': str(tolerance),
            'max_absolute_oracle_error': str(maximum_error), 'observed_contract_failures': 0,
            'example': synthetic_allocation('7', {'A': '5', 'B': '3', 'C': '2'}, assumptions=ASSUMPTIONS)}


def compute():
    frozen_history()
    with tempfile.TemporaryDirectory(prefix='post-transition-input-') as temp:
        capture = Path(temp) / 'capture'
        unpack_input(INPUT, capture)
        verified, facts, _ = verify_capture(capture)
        if 'q3_2026' not in verified:
            raise ValueError('Registered current Q3 source missing')
        source = verified['q3_2026']
        m = source['manifest']
        if m['accession'] != '0000815097-26-000107' or m['report_end'] != '2026-08-31' or m['filed_on'] != '2026-09-29':
            raise ValueError('Registered post-transition source identity changed')
        balance, balance_evidence = balance_sheet(source, facts)
        if type(balance['cash']) is not float or not balance['cash'].is_integer():
            raise ValueError('Bound integer-million cash required')
        result = source_analysis(source['body'], int(balance['cash']))
        result['source'] = {'accession': m['accession'], 'report_date': m['report_end'], 'filed_on': m['filed_on'],
                            'original_html': source['sources']['filing_html'],
                            'original_zip_sha256': hashlib.sha256(INPUT.read_bytes()).hexdigest(),
                            'capture_scope': 'Current API bodies with frozen original filing; not original-vintage API history'}
        result['whole_entity_cash_balance_context'] = next(r for r in balance_evidence if r['metric'] == 'cash')
    result['synthetic_contract'] = synthetic_contract()
    result['method_scope'] = 'Source-informed registered descriptive debt, financial liquidity proxy and synthetic arithmetic; not legal recovery, covenant compliance, forecast, investment recommendation, independent review or mastery'
    frozen_history()
    return result


def run(output):
    output = output.resolve()
    if output.exists() or not output.parent.is_dir() or output == ROOT or ROOT in output.parents:
        raise ValueError('Fresh output directory outside repository required')
    actual = compute()
    expected = ROOT / 'research_post_transition/reference_summary.json'
    if expected.exists():
        compare_reference(actual, json.loads(expected.read_text()))
    with tempfile.TemporaryDirectory(prefix='post-transition-result-', dir=output.parent) as temp:
        staging = Path(temp)
        (staging / 'summary.json').write_text(json.dumps(actual, indent=2, sort_keys=True, allow_nan=False) + '\n')
        if output.exists():
            raise ValueError('Output appeared during replay')
        staging.rename(output)
    return actual


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args().output)
    print(json.dumps({'instruments': len(result['reported_debt']['instruments']),
                      'source_inline_amounts': len(result['inline_amount_contexts']),
                      'liquidity_proxy': result['financial_liquidity_proxy'],
                      'synthetic_cases': result['synthetic_contract']['cases'],
                      'actual_legal_recovery': result['actual_post_transition_legal_recovery']}, indent=2))


if __name__ == '__main__':
    main()
