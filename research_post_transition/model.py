"""Source-bound descriptive Q3 analysis; legal recovery is deliberately refused."""
from __future__ import annotations

from decimal import Context, Decimal, localcontext
import hashlib
import re

from research_sec_quarters.reconcile import clean_text, parse_document

CURRENT = 'August 31, 2026'
COMPARATIVE = 'November 30, 2025'
GROUPS = ('Unsecured Subsidiary Guaranteed', 'Unsecured (No Subsidiary Guarantee)')
AGGREGATES = (
    'Total Unsecured Subsidiary Guaranteed',
    'Total Unsecured (No Subsidiary Guarantee)',
    'Total Debt',
    'Less: unamortized debt issuance costs and discounts',
    'Total Debt, net of unamortized debt issuance costs and discounts',
    'Less: Current portion of long-term debt',
    'Long-Term Debt',
)


def value(text):
    """Displayed integer USD millions; only an explicit dash denotes zero."""
    if not isinstance(text, str):
        raise ValueError('Displayed amount must be text')
    token = text.strip()
    if token == '\u2014':
        return Decimal(0)
    negative = token.startswith('(') and token.endswith(')')
    if negative:
        token = token[1:-1].strip()
    if not re.fullmatch(r'(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)', token):
        raise ValueError('Missing or malformed displayed amount')
    result = Decimal(token.replace(',', ''))
    return -result if negative else result


def spans(row, width):
    result, offset = [], 0
    for cell in list(row):
        raw = cell.get('colspan', '1')
        if not re.fullmatch(r'[1-9]\d?', raw):
            raise ValueError('Invalid table span')
        count = int(raw)
        if offset + count > width:
            raise ValueError('Unexpected table width')
        result.append((offset, offset + count, cell))
        offset += count
    if offset != width:
        raise ValueError('Unexpected table width')
    return result


def group_text(cells, start, width=3):
    selected = []
    for a, b, cell in cells:
        if a < start + width and b > start:
            if a < start or b > start + width:
                raise ValueError('Cell crosses column-group boundary')
            selected.append(clean_text(cell))
    return ' '.join(t for t in selected if t).strip()


def amount(cells, start, width=3):
    tokens = []
    for a, b, cell in cells:
        if a < start + width and b > start:
            if a < start or b > start + width:
                raise ValueError('Amount crosses column-group boundary')
            text = clean_text(cell)
            if text and text != '$':
                tokens.append(text)
    if len(tokens) != 1:
        raise ValueError('Exactly one displayed numeric token required')
    return value(tokens[0])


def unique_table(doc, required):
    tables = []
    for table in doc.iter('table'):
        labels = {clean_text(row[0]) for row in table.iter('tr') if len(row)}
        if set(required).issubset(labels):
            tables.append(table)
    if len(tables) != 1:
        raise ValueError('Exactly one complete target table required')
    return tables[0]


def trace(doc, element):
    return {'xpath': doc.getroottree().getpath(element),
            'normalized_text_sha256': hashlib.sha256(clean_text(element).encode()).hexdigest()}


def currency_contexts(doc, table, column_dates, width, contexts, units):
    evidence = []
    for row in table.iter('tr'):
        if not clean_text(row):
            continue
        cells = spans(row, width)
        for start, date in column_dates.items():
            inline = [e for a, b, cell in cells if start <= a < start + 3
                      for e in cell.iter('ix:nonfraction')]
            if not inline:
                continue
            displayed = amount(cells, start)
            for element in inline:
                context = contexts.get(element.get('contextref'))
                if not context or context['entity'].zfill(10) != '0000815097' or context['start'] is not None or context['end'] != date:
                    raise ValueError('Numeric amount has wrong issuer or instant context')
                if units.get(element.get('unitref')) != 'iso4217:USD' or element.get('scale') != '6':
                    raise ValueError('Numeric amount has wrong currency or million scale')
                token = clean_text(element)
                transformation = element.get('format')
                if transformation not in (None, 'ixt:num-dot-decimal', 'ixt:fixed-zero') or (token == '\u2014') != (transformation == 'ixt:fixed-zero'):
                    raise ValueError('Unknown or inconsistent numeric transformation')
                sign = element.get('sign')
                if sign not in (None, '-'):
                    raise ValueError('Invalid numeric sign')
                n = value(token) * (-1 if sign == '-' else 1)
                label = clean_text(row[0])
                deduction_tags = {
                    'Less: unamortized debt issuance costs and discounts': 'us-gaap:DeferredFinanceCostsNet',
                    'Less: Current portion of long-term debt': 'us-gaap:LongTermDebtCurrent',
                }
                direction = -1 if label in deduction_tags else 1
                if direction == -1 and (element.get('name') != deduction_tags[label] or n < 0):
                    raise ValueError('Subtraction row has unsupported account semantics')
                if n * direction != displayed:
                    raise ValueError('Inline/visible amount disagreement')
                evidence.append({'element_id': element.get('id'), 'tag': element.get('name'),
                                 'context_id': element.get('contextref'), 'report_date': date,
                                 'entity': context['entity'], 'dimensional': context['dimensional'],
                                 'units': 'USD million', 'xbrl_account_value': integer_json(n),
                                 'displayed_amount': integer_json(displayed), 'presentation_direction': direction,
                                 'trace': trace(doc, element)})
    return evidence


def paragraph(doc, marker, required=()):
    candidates = []
    for element in doc.iter('div'):
        text = clean_text(element)
        if len(text) > 3000 or marker not in text.lower():
            continue
        if any(marker in clean_text(child).lower() for child in element.iterdescendants('div')):
            continue
        if all(term in text.lower() for term in required):
            candidates.append(element)
    if len(candidates) != 1:
        raise ValueError(f'Missing/ambiguous current disclosure: {marker}')
    return candidates[0]


def integer_json(n):
    if n != n.to_integral_value():
        raise ValueError('Unexpected fractional statement amount')
    return int(n)


def debt_instruments(doc):
    table = unique_table(doc, AGGREGATES)
    rows = list(table.iter('tr'))
    headers = [r for r in rows if len(r) and clean_text(r[0]) == '(in millions)']
    if len(headers) != 1:
        raise ValueError('Debt units/header missing')
    header = spans(headers[0], 24)
    if group_text(header, 15) != CURRENT or group_text(header, 21) != COMPARATIVE:
        raise ValueError('Debt current/comparative dates changed')
    if group_text(header, 3) != 'Maturity' or group_text(header, 9) != 'Rate (a)':
        raise ValueError('Debt table schema changed')
    instruments, totals, group, kind = [], {}, None, None
    for row in rows:
        label = clean_text(row[0]) if len(row) else ''
        if not label or label == '(in millions)':
            continue
        cells = spans(row, 24)
        if label in GROUPS:
            group, kind = label, None
            if group_text(cells, 15) or group_text(cells, 21):
                raise ValueError('Debt category heading contains amounts')
            continue
        if label in AGGREGATES:
            if label in totals:
                raise ValueError('Duplicate debt subtotal')
            totals[label] = {'current': amount(cells, 15), 'comparative': amount(cells, 21), 'trace': trace(doc, row)}
            continue
        maturity, rate = group_text(cells, 3), group_text(cells, 9)
        if label in ('Notes', 'Loans', 'Export Credit Facilities') and not maturity and not rate:
            if group is None:
                raise ValueError('Instrument kind outside debt group')
            if group_text(cells, 15) or group_text(cells, 21):
                raise ValueError('Instrument subheading has quantities')
            kind = label
            continue
        if group is None or kind is None or not maturity or not rate:
            raise ValueError('Unmapped instrument or unsupported debt category')
        current, prior = amount(cells, 15), amount(cells, 21)
        if min(current, prior) < 0:
            raise ValueError('Negative principal')
        instruments.append({'reported_category': group, 'kind': kind, 'label': label,
                            'maturity_display': maturity, 'rate_display': rate,
                            'current_usd_millions': integer_json(current),
                            'comparative_usd_millions': integer_json(prior),
                            'trace': trace(doc, row)})
    if set(totals) != set(AGGREGATES) or len(instruments) != 21:
        raise ValueError('Incomplete registered instrument/subtotal population')
    gaps = {}
    for period, key in [('current', 'current_usd_millions'), ('comparative', 'comparative_usd_millions')]:
        gaps[period] = {}
        for group in GROUPS:
            subtotal = sum(Decimal(i[key]) for i in instruments if i['reported_category'] == group)
            target = totals['Total ' + group][period]
            gap = subtotal - target
            gaps[period][group + ' instrument_sum_minus_reported_subtotal'] = integer_json(gap)
            if abs(gap) > 2:
                raise ValueError('Instrument/subtotal reconciliation failed')
        if sum(totals['Total ' + g][period] for g in GROUPS) != totals['Total Debt'][period]:
            raise ValueError('Category/total principal reconciliation failed')
        gross = totals['Total Debt'][period]
        costs = totals[AGGREGATES[3]][period]
        carrying = totals[AGGREGATES[4]][period]
        current_deduction = totals[AGGREGATES[5]][period]
        noncurrent = totals[AGGREGATES[6]][period]
        carrying_gap = gross + costs - carrying
        gaps[period]['principal_minus_costs_minus_carrying'] = integer_json(carrying_gap)
        if costs > 0 or current_deduction > 0 or abs(carrying_gap) > 2 or carrying + current_deduction != noncurrent:
            raise ValueError('Principal/carrying/current debt reconciliation failed')
    serial = {label: {'current_usd_millions': integer_json(v['current']),
                       'comparative_usd_millions': integer_json(v['comparative']),
                       'trace': v['trace']} for label, v in totals.items()}
    return {'instruments': instruments, 'subtotals': serial,
            'current_date': '2026-08-31', 'comparative_date': '2025-11-30',
            'comparative_classification_basis': 'Presentation in Q3 filing, not original-vintage security/guarantee status',
            'absent_secured_subtotal': None, 'source_table_trace': trace(doc, table),
            'actual_signed_display_gaps_usd_millions': gaps,
            'pre_existing_display_tolerance_usd_millions': 2}


def maturities(doc, gross_debt):
    paragraph(doc, 'scheduled maturities of our debt', ('as of august 31, 2026',))
    table = unique_table(doc, ('Year', 'Remainder of 2026', 'Thereafter', 'Total'))
    expected = ('Remainder of 2026', '2027', '2028', '2029', '2030', 'Thereafter', 'Total')
    data = {}
    for row in table.iter('tr'):
        label = clean_text(row[0]) if len(row) else ''
        if not label:
            continue
        cells = spans(row, 9)
        if label == '(in millions)':
            continue
        if label == 'Year' and group_text(cells, 6) == 'Principal Payments':
            continue
        if label not in expected or label in data:
            raise ValueError('Unexpected maturity row')
        n = amount(cells, 6)
        if n < 0:
            raise ValueError('Negative maturity amount')
        data[label] = {'principal_usd_millions': integer_json(n), 'trace': trace(doc, row)}
    if tuple(data) != expected or sum(data[k]['principal_usd_millions'] for k in expected[:-1]) != gross_debt or data['Total']['principal_usd_millions'] != gross_debt:
        raise ValueError('Maturity/principal total or ordering mismatch')
    return data


def disclosed_terms(doc):
    specs = {
        'security_released_2027_2028': ('were no longer secured', ('november 30, 2025', 'august 31, 2026', '7.88', '4.00')),
        'security_released_redeemed_2029': ('became unsecured in june 2026', ('redeemed',)),
        'subsidiary_guarantees_changed': ('were no longer subject', ('august 31, 2026', 'subsidiary guarantees')),
        'sun_princess_exception': ('sun princess limited', ('august 31, 2026', 'sun princess ii limited', 'do not guarantee')),
        'revolver': ('available for borrowing under', ('august 31, 2026', 'subject to the satisfaction', 'june 2030')),
        'ship_export_facilities': ('undrawn export credit facilities to fund ship deliveries', ('august 31, 2026', 'through 2033')),
        'negative_pledge': ('subject to negative pledges', ('august 31, 2026', 'net book value')),
        'covenant_period': ('most restrictive covenants', ('august 31, 2026',)),
        'interest_threshold': ('minimum interest coverage', ('as defined in the agreements',)),
        'capital_threshold': ('minimum issued capital', ('as defined in the agreements',)),
        'debt_capital_threshold': ('debt to capital', ('as defined in the agreements',)),
        'liquidity_threshold': ('minimum liquidity', ()),
        'issuer_compliance': ('in compliance with the applicable covenants', ('august 31, 2026', 'cross-default')),
        'possible_future_shelf': ('shelf registration statement on form s-3', ('september 29, 2026', 'may from time to time', 'carnival uk ltd.')),
        'obligor_group_basis': ('the following summarized financial information', ('intercompany balances', 'have been eliminated', 'have been excluded', 'non-obligor subsidiaries')),
    }
    elements = {key: paragraph(doc, marker, req) for key, (marker, req) in specs.items()}
    text = {key: clean_text(e) for key, e in elements.items()}

    def quantity(key, pattern, multiplier=1):
        matches = re.findall(pattern, text[key], re.I)
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous disclosed quantity: ' + key)
        return Decimal(matches[0]) * multiplier

    result = {key: {'trace': trace(doc, e)} for key, e in elements.items()}
    result['revolver'].update(available_usd_millions=integer_json(quantity('revolver', r'\$\s*(\d+\.\d+)\s+billion', 1000)), availability='Conditional on facility terms; not unrestricted cash')
    result['ship_export_facilities'].update(undrawn_usd_millions=integer_json(quantity('ship_export_facilities', r'had\s*\$\s*(\d+\.\d+)\s*billion\s*of undrawn export credit facilities', 1000)), use='Specified future ship deliveries; excluded from general liquidity proxy')
    result['negative_pledge'].update(book_value_usd_millions=integer_json(quantity('negative_pledge', r'negative pledges was\s*\$\s*(\d+\.\d+)\s*billion', 1000)), secured_recovery_pool=None)
    result['sun_princess_exception'].update(rounded_disclosed_usd_millions=integer_json(quantity('sun_princess_exception', r'\$\s*(\d+\.\d+)\s+billion', 1000)), exact_instrument_estate_mapping=None)
    result['interest_threshold']['reported_minimum_ratio'] = str(quantity('interest_threshold', r'not less than\s*(\d+\.\d+)\s*to\s*1\.0'))
    result['capital_threshold']['reported_minimum_usd_millions'] = integer_json(quantity('capital_threshold', r'\$\s*(\d+\.\d+)\s+billion', 1000))
    result['debt_capital_threshold']['reported_maximum_percent'] = integer_json(quantity('debt_capital_threshold', r'not to exceed\s*(\d+)\s*%'))
    result['liquidity_threshold']['reported_minimum_usd_millions'] = integer_json(quantity('liquidity_threshold', r'\$\s*(\d+\.\d+)\s+billion', 1000))
    result['issuer_compliance'].update(kind='Issuer-reported compliance', independently_recalculated_agreement_compliance=None)
    result['possible_future_shelf']['existing_instrument_guarantee_mapping'] = None
    return result


def obligor_group(doc):
    labels = ('Current assets - excluding due from Non-Obligor Subsidiaries',
              'Current assets - due from Non-Obligor Subsidiaries', 'Noncurrent assets',
              'Current liabilities', 'Noncurrent liabilities')
    table = unique_table(doc, labels)
    result, header = {}, False
    for row in table.iter('tr'):
        if not clean_text(row):
            continue
        cells = spans(row, 12)
        label = clean_text(row[0])
        if not label:
            if header or group_text(cells, 3) != CURRENT or group_text(cells, 9) != COMPARATIVE:
                raise ValueError('Obligor current/comparative header mismatch')
            header = True
            continue
        if label not in labels or label in result:
            raise ValueError('Unexpected Obligor Group row')
        current, prior = amount(cells, 3), amount(cells, 9)
        if min(current, prior) < 0:
            raise ValueError('Negative Obligor summary balance')
        result[label] = {'current_usd_millions': integer_json(current), 'comparative_usd_millions': integer_json(prior), 'trace': trace(doc, row)}
    if not header or set(result) != set(labels):
        raise ValueError('Incomplete Obligor Group summary')
    return {'reported_combined_balances': result,
            'units': 'USD million; supplemental table has no inline XBRL amount tags',
            'intercompany_due_from_nonobligors_retained': True,
            'investments_in_nonobligor_subsidiaries_excluded': True,
            'nonobligor_assets_inferred_by_subtraction': None,
            'existing_debt_instrument_estate_mapping': None}


def liquidity_proxy(cash, revolver, schedule, reserve):
    inputs = [cash, revolver, reserve]
    if any(type(x) is not int or x < 0 for x in inputs):
        raise ValueError('Nonnegative integer financial inputs required')
    cumulative, rows = 0, []
    for bucket, row in schedule.items():
        if bucket == 'Total':
            continue
        principal = row['principal_usd_millions']
        if type(principal) is not int or principal < 0:
            raise ValueError('Invalid principal amount')
        cumulative += principal
        rows.append({'bucket': bucket, 'principal_usd_millions': principal,
                     'cumulative_principal_usd_millions': cumulative,
                     'cash_only_minus_cumulative': cash - cumulative,
                     'cash_plus_revolver_minus_cumulative': cash + revolver - cumulative,
                     'cash_plus_revolver_after_fixed_reserve_minus_cumulative': max(0, cash + revolver - reserve) - cumulative})
    return {'cash_usd_millions': cash, 'conditional_revolver_usd_millions': revolver,
            'fixed_reserve_sensitivity_usd_millions': reserve,
            'cash_plus_conditional_revolver_usd_millions': cash + revolver,
            'ship_specific_export_facilities_included': False, 'buckets': rows,
            'basis': 'Static financial proxy; excludes future operating cash, investment needs, refinancing and legal availability tests',
            'agreement_defined_covenant_headroom': None, 'legal_maturity_coverage': None}


def synthetic_allocation(estate, claims, *, assumptions):
    """Unrounded analytical amounts, never actual legal payment instructions."""
    required = ('synthetic_only', 'same_estate', 'same_priority', 'no_other_senior_claims')
    if type(assumptions) is not dict or set(assumptions) != set(required) or any(assumptions[k] is not True for k in required):
        raise ValueError('All four explicit synthetic same-estate assumptions required')
    if type(claims) is not dict or not 1 <= len(claims) <= 16 or any(type(k) is not str or not k.strip() or k != k.strip() or len(k) > 80 for k in claims):
        raise ValueError('Named bounded synthetic claims required')

    def decimal_arg(s):
        if type(s) is not str or not re.fullmatch(r'(?:0|[1-9]\d{0,17})(?:\.\d{1,18})?', s):
            raise ValueError('Canonical finite nonnegative decimal text required')
        return Decimal(s)

    asset = decimal_arg(estate)
    amounts = {k: decimal_arg(claims[k]) for k in sorted(claims)}
    with localcontext(Context(prec=60)):
        total = sum(amounts.values(), Decimal(0))
        available = min(asset, total)
        payments = {k: (available * v / total if total else Decimal(0)) for k, v in amounts.items()}
        return {'scope': 'Synthetic single-estate pari-passu analytical sensitivity',
                'claims': {k: str(v) for k, v in amounts.items()},
                'estate': str(asset), 'payments': {k: str(v) for k, v in payments.items()},
                'residual': str(asset - available), 'precision_digits': 60,
                'currency_rounding_or_legal_priority': None, 'actual_issuer_recovery': None}


def refuse_unsupported(request):
    refused = ('actual_q3_recovery', 'legal_entity_mapping', 'covenant_compliance', 'legal_opinion')
    if request not in refused:
        raise ValueError('Unknown request')
    return {'request': request, 'status': 'REFUSED', 'value': None,
            'reason': 'The current filing does not establish complete agreements, entity/asset/claim/priority mapping and independent legal analysis'}


def source_analysis(body, cash):
    doc, contexts, units = parse_document(body)
    debt = debt_instruments(doc)
    gross = debt['subtotals']['Total Debt']['current_usd_millions']
    schedule = maturities(doc, gross)
    terms = disclosed_terms(doc)
    obligors = obligor_group(doc)
    proxy = liquidity_proxy(cash, terms['revolver']['available_usd_millions'], schedule, 1500)
    numeric_evidence = currency_contexts(doc, unique_table(doc, AGGREGATES),
                                         {15: '2026-08-31', 21: '2025-11-30'}, 24, contexts, units)
    numeric_evidence += currency_contexts(doc, unique_table(doc, ('Year', 'Remainder of 2026', 'Thereafter', 'Total')),
                                          {6: '2026-08-31'}, 9, contexts, units)
    return {'reported_debt': debt, 'reported_maturities': schedule,
            'inline_amount_contexts': numeric_evidence,
            'disclosed_terms': terms, 'reported_obligor_summary': obligors,
            'financial_liquidity_proxy': proxy,
            'unsupported_requests': [refuse_unsupported(k) for k in ('actual_q3_recovery', 'legal_entity_mapping', 'covenant_compliance', 'legal_opinion')],
            'old_full_recovery_criterion': 'FAILED_AND_UNCHANGED',
            'actual_post_transition_legal_recovery': None}
