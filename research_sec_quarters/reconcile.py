"""Fixed Carnival Q1/Q3 source reconciliation; original Q2 files are untouched.

The parser deliberately supports only the registered whole-entity USD-million
statement rows and IX numeric formats. It refuses ambiguous or unknown inputs.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import tempfile

from lxml import html

from research_sec_intake.intake import verify
from research_sec_quarters.capture import CIK, CUTOFF, TARGETS, select_targets
from credit_underwriting.period_bridge import build_ttm_metrics_period_aware, calendar_period_plan

METRICS = {
    "revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "total revenues", "income"),
    "operating_income": ("OperatingIncomeLoss", "operating income", "income"),
    "depreciation_amortization": ("DepreciationAndAmortization", "depreciation and amortization", "cashflow"),
    "interest_expense": ("InterestExpenseNonoperating", "interest expense, net of capitalized interest", "income"),
    "cash_from_operations": ("NetCashProvidedByUsedInOperatingActivities", "net cash provided by operating activities", "cashflow"),
    "capital_expenditures": ("PaymentsToAcquirePropertyPlantAndEquipment", "purchases of property and equipment", "cashflow"),
}
MAGNITUDES = {"depreciation_amortization", "interest_expense", "capital_expenditures"}


def clean_text(element):
    return " ".join(" ".join(element.itertext()).split())


def number(text):
    numeric = r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?"
    if not re.fullmatch(rf"\s*\$?\s*(?:-?{numeric}|\(\s*\$?\s*{numeric}\s*\))\s*", text):
        raise ValueError("Unsupported visible numeric cell")
    text = "".join(text.split()).replace("$", "").replace(",", "")
    try:
        value = -Decimal(text[1:-1]) if text.startswith("(") else Decimal(text)
    except InvalidOperation as error:
        raise ValueError("Invalid numeric cell") from error
    if not value.is_finite():
        raise ValueError("Nonfinite numeric cell")
    return value


def one_text(element, tag):
    values = list(element.iter(tag))
    if len(values) != 1:
        raise ValueError(f"Exactly one {tag} is required")
    return clean_text(values[0])


def visible_numbers(cells):
    result = []
    for cell in cells:
        text = clean_text(cell)
        try:
            result.append(number(text))
        except ValueError:
            if text and text not in ("$", "(", ")"):
                raise ValueError("Unexpected nonnumeric statement cell")
    return result


def parse_document(body):
    doc = html.fromstring(body)
    contexts, units = {}, {}
    for element in doc.iter("xbrli:context"):
        identifier = element.get("id")
        if not identifier or identifier in contexts:
            raise ValueError("Duplicate or missing context ID")
        entity = one_text(element, "xbrli:identifier")
        identifiers = list(element.iter("xbrli:identifier"))
        if identifiers[0].get("scheme") != "http://www.sec.gov/CIK" or not re.fullmatch(r"\d{1,10}", entity):
            raise ValueError("SEC CIK identifier scheme required")
        starts, ends = list(element.iter("xbrli:startdate")), list(element.iter("xbrli:enddate"))
        instants = list(element.iter("xbrli:instant"))
        contexts[identifier] = dict(entity=entity,
            start=clean_text(starts[0]) if len(starts) == 1 else None,
            end=clean_text(ends[0]) if len(ends) == 1 else clean_text(instants[0]) if len(instants) == 1 else None,
            dimensional=any(True for _ in element.iter("xbrli:segment")) or
                        any(True for _ in element.iter("xbrli:scenario")))
    for element in doc.iter("xbrli:unit"):
        identifier = element.get("id")
        if not identifier or identifier in units:
            raise ValueError("Duplicate or missing unit ID")
        units[identifier] = clean_text(element)
    if not contexts or not units:
        raise ValueError("Inline XBRL contexts and units required")
    return doc, contexts, units


def extract_metric(body, metric, start, end, *, report_end, form):
    tag, label, kind = METRICS[metric]
    doc, contexts, units = parse_document(body)
    matches = []
    for element in doc.iter("ix:nonfraction"):
        if element.get("name") != "us-gaap:" + tag:
            continue
        context = contexts.get(element.get("contextref"))
        if not context or context["dimensional"] or context["start"] != start or context["end"] != end:
            continue
        if context["entity"].zfill(10) != CIK:
            raise ValueError("Statement context entity mismatch")
        row = next((parent for parent in element.iterancestors() if parent.tag == "tr"), None)
        table = next((parent for parent in element.iterancestors() if parent.tag == "table"), None)
        if row is None or table is None:
            continue
        cells = [child for child in row if child.tag in ("th", "td")]
        if not cells:
            continue
        row_label = clean_text(cells[0]).lower()
        if metric == "cash_from_operations" and row_label == "net cash provided by (used in) operating activities":
            row_label = label
        unlabeled_q1_revenue = metric == "revenue" and report_end == "2025-02-28" and not row_label
        if row_label != label and not unlabeled_q1_revenue:
            continue
        table_labels = {clean_text(next(iter(r))).lower() for r in table.iter("tr") if len(r)}
        terms = (("revenues" if report_end == "2025-02-28" else "total revenues"), "operating income") if kind == "income" else ("operating activities", "investing activities")
        if not all(term in table_labels for term in terms):
            continue
        if units.get(element.get("unitref")) != "iso4217:USD" or element.get("scale") != "6":
            raise ValueError("Registered statement USD-million units/scale required")
        if element.get("format") not in (None, "ixt:num-dot-decimal") or element.get("sign") not in (None, "-"):
            raise ValueError("Unsupported inline numeric transformation/sign")
        if element.get("xsi:nil") in ("true", "1"):
            raise ValueError("Nil numeric statement value")
        value = number(clean_text(element)) * (-1 if element.get("sign") == "-" else 1)
        raw_value = value * Decimal(10) ** int(element.get("scale"))
        # Independent visible table parsing: no IX values, context IDs or scales.
        visible = visible_numbers(cells[1:])
        if unlabeled_q1_revenue:
            components = []
            for component_label in ("passenger ticket", "onboard and other"):
                rows = [r for r in table.iter("tr") if len(r) and clean_text(next(iter(r))).lower() == component_label]
                # Onboard also appears as an operating expense: use the first
                # named revenue row before the registered subtotal, and verify
                # its exact two-column schema rather than a loose text match.
                table_rows = list(table.iter("tr"))
                preceding = [r for r in rows if r in table_rows[:table_rows.index(row)]]
                if not preceding:
                    raise ValueError("Unlabelled revenue subtotal lacks named components")
                component = visible_numbers(list(preceding[0])[1:])
                if len(component) != 2:
                    raise ValueError("Revenue component column schema mismatch")
                components.append(component)
            if len(visible) != 2 or any(abs(visible[i] - sum(c[i] for c in components)) > 1 for i in range(2)):
                raise ValueError("Unlabelled revenue subtotal fails independent component sum")
        header = " ".join(clean_text(r) for r in table.iter("tr") if r is not row)
        year = int(report_end[:4])
        if form == "10-K":
            expected = 3
            index = year - int(end[:4])
            if "Years Ended" not in header or index not in (0, 1, 2):
                raise ValueError("Annual table header/year mapping unsupported")
        else:
            quarter = calendar_period_plan(report_end, "2025-11-30").fiscal_quarter if year == 2026 else (1 if report_end[5:] == "02-28" else 3)
            months_word = {1: "Three", 3: "Nine"}[quarter]
            if f"{months_word} Months Ended" not in header:
                raise ValueError("Quarter YTD table header missing")
            expected = 4 if quarter == 3 and kind == "income" else 2
            index = expected - 2 + year - int(end[:4])
            if year - int(end[:4]) not in (0, 1):
                raise ValueError("Quarter table comparative year unsupported")
        if len(visible) != expected or not 0 <= index < len(visible):
            raise ValueError("Visible table column schema unsupported")
        displayed = visible[index]
        normalized = abs(value) if metric in MAGNITUDES else value
        normalized_display = abs(displayed) if metric in MAGNITUDES else displayed
        if normalized != normalized_display:
            raise ValueError("Inline value disagrees with independent visible table column")
        matches.append(dict(metric=metric, xbrl_tag=tag, context_id=element.get("contextref"),
                            start=start, end=end, unit="USD", value_raw=float(abs(raw_value) if metric in MAGNITUDES else raw_value),
                            value_usd_millions=float(normalized), visible_signed_millions=float(displayed),
                            filing_table_label=label if not unlabeled_q1_revenue else "unlabelled revenue subtotal; passenger ticket plus onboard and other",
                            table_columns=len(visible), selected_column=index))
    if len(matches) != 1:
        raise ValueError(f"Exactly one registered primary statement context is required for {metric}: {start}..{end}; found {len(matches)}")
    return matches[0]


def fact_parity(companyfacts, row, manifest):
    entries = companyfacts.get("facts", {}).get("us-gaap", {}).get(row["xbrl_tag"], {}).get("units", {}).get("USD", [])
    selected = [entry for entry in entries if entry.get("start") == row["start"] and entry.get("end") == row["end"]
                and entry.get("accn") == manifest["accession"] and entry.get("form") == manifest["form"]
                and entry.get("filed") == manifest["filed_on"]]
    if not selected or any(isinstance(entry.get("val"), bool) or not isinstance(entry.get("val"), (int, float)) for entry in selected):
        raise ValueError("Exact Companyfacts period/accession/form/date/value unavailable")
    values = {Decimal(str(entry["val"])) for entry in selected}
    if len(values) != 1 or next(iter(values)) != Decimal(str(row["value_raw"])):
        raise ValueError("Companyfacts and original statement context disagree")
    return dict(matches=len(selected), raw_value=float(next(iter(values))))


def verify_capture(root):
    status = json.loads((root / "CAPTURE_STATUS.json").read_text())
    if status.get("status") != "PASS_ORIGINAL_BYTE_CAPTURE_ONLY" or status.get("cik") != CIK or status.get("cutoff") != CUTOFF:
        raise ValueError("Complete registered capture status required")
    discovery = (root / "discovery_submissions.json").read_bytes()
    if len(discovery) != status["discovery"]["bytes"] or hashlib.sha256(discovery).hexdigest() != status["discovery"]["sha256"]:
        raise ValueError("Discovery original body identity mismatch")
    targets = select_targets(json.loads(discovery))
    if status.get("resolved_targets") != targets:
        raise ValueError("Capture plan differs from original submissions")
    expected = {"CAPTURE_STATUS.json", "discovery_submissions.json"} | {t[0] for t in TARGETS}
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError("Registered collection has missing or extra members")
    verified, facts = {}, []
    for target in targets:
        label = target["label"]
        manifest = verify(root / label, expected_cik=CIK)
        if any(manifest[key] != target[key] for key in ("form", "report_end", "accession", "filed_on")) or manifest["as_of"] != CUTOFF:
            raise ValueError("Capture metadata differs from registered plan")
        if not any(c.get("label") == label and c.get("manifest") == manifest for c in status.get("captures", [])):
            raise ValueError("Capture status manifest mismatch")
        sources = {s["kind"]: s for s in manifest["sources"]}
        body = (root / label / sources["filing_html"]["filename"]).read_bytes()
        facts_body = (root / label / sources["companyfacts"]["filename"]).read_bytes()
        facts.append(facts_body)
        verified[label] = dict(manifest=manifest, sources=sources, body=body)
    if any(body != facts[0] for body in facts[1:]):
        raise ValueError("Companyfacts changed during registered multi-filing capture")
    return verified, json.loads(facts[0]), status


def reconcile(root):
    verified, companyfacts, status = verify_capture(root)
    results = {}
    for current_label, original_label in (("q1_2026", "q1_2025_original"), ("q3_2026", "q3_2025_original")):
        current, annual, original = verified[current_label], verified["annual_2025"], verified[original_label]
        plan = calendar_period_plan(current["manifest"]["report_end"], annual["manifest"]["report_end"])
        overrides, checks, comparison = {}, [], []
        for metric in METRICS:
            overrides[metric] = {}
            for role, period, source in (("latest_fy", plan.annual, annual),
                                         ("current_ytd", plan.current_ytd, current),
                                         ("prior_ytd", plan.prior_ytd, current)):
                m = source["manifest"]
                row = extract_metric(source["body"], metric, period.start, period.end,
                                     report_end=m["report_end"], form=m["form"])
                parity = fact_parity(companyfacts, row, m)
                row.update(source_type="sec_filing_table", source_sha256=source["sources"]["filing_html"]["sha256"],
                           source_url=source["sources"]["filing_html"]["url"], accession=m["accession"],
                           form=m["form"], filed=m["filed_on"], ttm_bridge_role=role, companyfacts_parity=parity)
                overrides[metric][period.end] = dict(value_usd_millions=row["value_usd_millions"], source_row=row)
                checks.append(row)
                if role == "prior_ytd":
                    om = original["manifest"]
                    prior = extract_metric(original["body"], metric, period.start, period.end,
                                           report_end=om["report_end"], form=om["form"])
                    fact_parity(companyfacts, prior, om)
                    if prior["value_raw"] != row["value_raw"]:
                        raise ValueError("Originally filed prior-period value differs from current comparative column")
                    comparison.append(dict(metric=metric, start=period.start, end=period.end,
                        current_comparative=row["value_usd_millions"], original_value=prior["value_usd_millions"],
                        original_accession=om["accession"], original_source_sha256=original["sources"]["filing_html"]["sha256"],
                        original_context_id=prior["context_id"]))
            # Exact independent three-term decimal arithmetic, separate from API.
            vals = [Decimal(str(r["value_usd_millions"])) for r in checks if r["metric"] == metric]
            if len(vals) != 3:
                raise ValueError("Three exact independent roles required")
        metrics, register = build_ttm_metrics_period_aware(companyfacts, current["manifest"]["report_end"],
            annual["manifest"]["report_end"], filing_cutoff=CUTOFF, duration_overrides=overrides)
        for metric in METRICS:
            vals = [Decimal(str(r["value_usd_millions"])) for r in checks if r["metric"] == metric]
            if Decimal(str(metrics[metric])) != vals[0] + vals[1] - vals[2]:
                raise ValueError("API bridge disagrees with independent decimal arithmetic")
        results[current_label] = dict(fiscal_quarter=plan.fiscal_quarter, report_end=current["manifest"]["report_end"],
            metrics=metrics, verified_sources=register.to_dict("records"), original_comparisons=comparison)
    return dict(schema_version=1, kind="real_SEC_exact_period_and_independent_table_reconciliation",
                cutoff=CUTOFF, cik=CIK, original_capture_status=status,
                results=results, scope="Authentic original byte, statement/Companyfacts parity and Q1/Q3 TTM; not a new debt/legal/covenant or historical-vintage validation")


def write_result(root, output):
    root, output = root.resolve(), output.resolve()
    repo = Path(__file__).resolve().parents[1]
    if output == root or root in output.parents or output == repo or repo in output.parents:
        raise ValueError("Output must be outside original capture and repository")
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Fresh output directory with existing parent required")
    before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    result = reconcile(root)
    after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob("*") if p.is_file()}
    if before != after:
        raise ValueError("Original capture changed during reconciliation")
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="quarter-result-") as temp:
        folder = Path(temp)
        (folder / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
        if output.exists():
            raise ValueError("Output appeared during reconciliation")
        folder.rename(output)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = write_result(args.capture, args.output)
    print(json.dumps({label: value["metrics"] for label, value in result["results"].items()}, sort_keys=True))


if __name__ == "__main__":
    main()
