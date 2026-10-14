"""Offline replay of the fixed original SEC ZIP and unchanged credit model."""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import zipfile

from research_sec_quarters.reconcile import (CIK, clean_text, number, parse_document,
                                            reconcile, verify_capture, visible_numbers)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "research_sec_quarters/input/original_sec_capture_20261014.zip"
INPUT_SHA256 = "f49431e44e83cac39071dd95fdaa56515ca4b540d8522201e400ab6859beed9c"


def historical_blobs():
    expected = json.loads((ROOT / "research_sec_quarters/HISTORICAL_GIT_BLOBS.json").read_text())
    for path, digest in expected.items():
        data = (ROOT / path).read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual != digest:
            raise ValueError(f"Historical source/reference blob changed: {path}")
    return expected


def unpack_input(archive, destination):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != INPUT_SHA256:
        raise ValueError("Frozen original SEC ZIP digest mismatch")
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)) or any(Path(n).is_absolute() or ".." in Path(n).parts for n in names):
            raise ValueError("Unsafe or duplicate ZIP member")
        if zipped.testzip() is not None:
            raise ValueError("Original source ZIP CRC failure")
        zipped.extractall(destination)


def balance_sheet(source, companyfacts):
    from credit_underwriting.facts import INSTANT_TAGS
    manifest = source["manifest"]
    doc, contexts, units = parse_document(source["body"])
    labels = {"cash": "cash and cash equivalents", "debt_current": "current portion of long-term debt",
              "debt_noncurrent": "long-term debt"}
    balance, evidence = {"period_end": manifest["report_end"]}, []
    for metric, tags in INSTANT_TAGS.items():
        matches = []
        for element in doc.iter("ix:nonfraction"):
            tag = element.get("name", "").removeprefix("us-gaap:")
            if tag not in tags:
                continue
            context = contexts.get(element.get("contextref"))
            if not context or context["dimensional"] or context["start"] is not None or context["end"] != manifest["report_end"]:
                continue
            if context["entity"].zfill(10) != CIK:
                raise ValueError("Balance entity mismatch")
            row = next((p for p in element.iterancestors() if p.tag == "tr"), None)
            if row is None or not len(row) or clean_text(row[0]).lower() != labels[metric]:
                continue
            if units.get(element.get("unitref")) != "iso4217:USD" or element.get("scale") != "6" or element.get("sign") is not None:
                raise ValueError("Balance unit/scale/sign mismatch")
            if element.get("format") not in (None, "ixt:num-dot-decimal"):
                raise ValueError("Unsupported balance numeric transformation")
            value = number(clean_text(element))
            displayed = visible_numbers(list(row)[1:])
            if len(displayed) != 2 or displayed[0] != value:
                raise ValueError("Balance inline/visible current column disagreement")
            raw_value = value * Decimal(1_000_000)
            entries = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", [])
            selected = [e for e in entries if e.get("end") == manifest["report_end"] and e.get("start") is None
                        and e.get("accn") == manifest["accession"] and e.get("filed") == manifest["filed_on"]
                        and e.get("form") == manifest["form"]]
            if not selected or any(isinstance(e.get("val"), bool) or not isinstance(e.get("val"), (int, float)) for e in selected):
                raise ValueError("Exact balance Companyfacts context unavailable")
            if any(Decimal(str(e["val"])) != raw_value for e in selected):
                raise ValueError("Balance Companyfacts/statement disagreement")
            matches.append(dict(metric=metric, value_usd_millions=float(value), xbrl_tag=tag,
                context_id=element.get("contextref"), end=context["end"], accession=manifest["accession"],
                form=manifest["form"], filed=manifest["filed_on"], source_sha256=source["sources"]["filing_html"]["sha256"],
                source_url=source["sources"]["filing_html"]["url"]))
        if not matches or len({e["value_usd_millions"] for e in matches}) != 1:
            raise ValueError(f"Missing or contradictory balance context: {metric}")
        balance[metric] = matches[0]["value_usd_millions"]
        evidence.append(dict(matches[0], agreeing_inline_occurrences=len(matches)))
    return balance, evidence


def reported_debt_classes(source):
    """Read exact reported rows; missing secured class is never imputed."""
    doc, _, _ = parse_document(source["body"])
    labels = {
        "unsecured_subsidiary_guaranteed": "total unsecured subsidiary guaranteed",
        "unsecured_no_subsidiary_guarantee": "total unsecured (no subsidiary guarantee)",
        "gross_debt": "total debt",
        "net_debt_reported": "total debt, net of unamortized debt issuance costs and discounts",
        "current_portion_long_term_debt": "less: current portion of long-term debt",
        "long_term_debt": "long-term debt",
    }
    tables = []
    for table in doc.iter("table"):
        rows = {clean_text(r[0]).lower(): r for r in table.iter("tr") if len(r)}
        if set(labels.values()).issubset(rows):
            tables.append((table, rows))
    if len(tables) != 1:
        raise ValueError("Exactly one complete reported debt table required")
    table, rows = tables[0]
    if "total secured subsidiary guaranteed" in rows:
        raise ValueError("Expected Q3 absence of historical secured class is not present")
    result, evidence = {}, []
    for key, label in labels.items():
        numbers = visible_numbers(list(rows[label])[1:])
        if len(numbers) != 2:
            raise ValueError("Debt table current/comparative column schema mismatch")
        result[key] = float(abs(numbers[0]))
        evidence.append(dict(metric=key, label=label, value_usd_millions=result[key],
            accession=source["manifest"]["accession"], report_end=source["manifest"]["report_end"],
            source_sha256=source["sources"]["filing_html"]["sha256"], source_url=source["sources"]["filing_html"]["url"]))
    if result["unsecured_subsidiary_guaranteed"] + result["unsecured_no_subsidiary_guarantee"] != result["gross_debt"]:
        raise ValueError("Reported Q3 unsecured classes do not completely reconcile to total debt")
    text = clean_text(doc).lower()
    if "were no longer secured as of august 31, 2026" not in text or "became unsecured in june 2026" not in text:
        raise ValueError("Q3 reported collateral-status explanation missing")
    return result, evidence


def full_replay(capture):
    from credit_underwriting.filing import (extract_covenant_liquidity_context,
        extract_debt_stack_millions, extract_maturity_schedule_millions)
    from credit_underwriting.underwriting import (current_credit_metrics, debt_capacity_grid,
        maturity_coverage, recovery_waterfall, scenario_analysis)
    source_result = reconcile(capture)
    verified, facts, _ = verify_capture(capture)
    for label, result in source_result["results"].items():
        source = verified[label]
        body = source["body"].decode("utf-8", errors="strict")
        balance, balance_evidence = balance_sheet(source, facts)
        try:
            debt = extract_debt_stack_millions(body)
        except ValueError as error:
            expected_error = "Debt-table row not found or not numeric: Total Secured Subsidiary Guaranteed"
            if label != "q3_2026" or str(error) != expected_error:
                raise
            debt, debt_evidence = reported_debt_classes(source)
            maturities = extract_maturity_schedule_millions(body)
            gaps = dict(carrying_value=balance["debt_current"] + balance["debt_noncurrent"] - debt["net_debt_reported"],
                current_noncurrent=debt["current_portion_long_term_debt"] + debt["long_term_debt"] - debt["net_debt_reported"],
                maturity_total=maturities["Total"] - debt["gross_debt"],
                reported_unsecured_classes=debt["unsecured_subsidiary_guaranteed"] + debt["unsecured_no_subsidiary_guarantee"] - debt["gross_debt"])
            if any(abs(gap) > 2 for gap in gaps.values()):
                raise ValueError(f"Q3 source debt/maturity reconciliation failed: {gaps}")
            ttm = result["metrics"]
            result.update(balance_sheet=balance, balance_evidence=balance_evidence, debt_stack=debt,
                debt_evidence=debt_evidence, maturities=maturities, reconciliation_gaps_usd_millions=gaps,
                underwriting_replay=dict(status="PARTIAL_WITH_RECOVERY_REFUSED", original_parser_error=str(error),
                    reason="The Q3 filing reclassifies debt/guarantees and has no reported secured subtotal. Original three-class collateral/recovery model is unsupported; no zero, old-quarter value or legal inference is substituted."),
                descriptive_credit_ratios=dict(gross_leverage=debt["gross_debt"] / ttm["ebitda_proxy"],
                    net_leverage=(debt["gross_debt"] - balance["cash"]) / ttm["ebitda_proxy"],
                    interest_coverage_proxy=ttm["ebitda_proxy"] / ttm["interest_expense"]),
                scenarios=scenario_analysis(ttm, debt).to_dict("records"),
                debt_capacity=debt_capacity_grid(ttm["ebitda_proxy"], ttm["interest_expense"], debt["gross_debt"]).to_dict("records"),
                recovery=None, covenant_liquidity_context=None, maturity_coverage=None)
            continue
        maturities = extract_maturity_schedule_millions(body)
        context = extract_covenant_liquidity_context(body)
        gaps = dict(carrying_value=balance["debt_current"] + balance["debt_noncurrent"] - debt["net_debt_reported"],
            current_noncurrent=debt["current_portion_long_term_debt"] + debt["long_term_debt"] - debt["net_debt_reported"],
            maturity_total=maturities["Total"] - debt["gross_debt"],
            capital_stack=debt["secured_subsidiary_guaranteed"] + debt["unsecured_subsidiary_guaranteed"] +
                debt["unsecured_no_subsidiary_guarantee"] - debt["gross_debt"])
        if any(abs(gap) > 2 for gap in gaps.values()):
            raise ValueError(f"Registered display reconciliation failed: {label}, {gaps}")
        ttm = result["metrics"]
        scenarios = scenario_analysis(ttm, debt)
        result.update(balance_sheet=balance, balance_evidence=balance_evidence, debt_stack=debt,
            underwriting_replay=dict(status="COMPLETE_UNCHANGED_MODEL_ARITHMETIC", limitations="Simplified consolidated sensitivity; not covenant or legal recovery validation"),
            maturities=maturities, covenant_liquidity_context=context, reconciliation_gaps_usd_millions=gaps,
            current_credit_metrics=current_credit_metrics(ttm, balance, debt, context),
            scenarios=scenarios.to_dict("records"),
            debt_capacity=debt_capacity_grid(ttm["ebitda_proxy"], ttm["interest_expense"], debt["gross_debt"]).to_dict("records"),
            recovery= recovery_waterfall(scenarios, debt, balance["cash"]).to_dict("records"),
            maturity_coverage=maturity_coverage(maturities, balance["cash"] + context["undrawn_revolver_millions"]).to_dict("records"))
    source_result["scope"] = ("Offline genuine SEC Q1/Q3 source/context/table and unchanged-model arithmetic replay; "
        "not original-vintage API, borrower PD, adjusted EBITDA, covenant compliance, legal insolvency recovery, forecast or recommendation. "
        "2026 legal redomiciliation and entity guarantees require separate legal analysis.")
    return source_result


def run(output):
    output = output.resolve()
    if output.exists() or not output.parent.is_dir() or output == ROOT or ROOT in output.parents:
        raise ValueError("Fresh output outside repository required")
    before = historical_blobs()
    with tempfile.TemporaryDirectory(prefix="sec-quarter-replay-") as temp:
        capture = Path(temp) / "capture"
        unpack_input(INPUT, capture)
        result = full_replay(capture)
    if historical_blobs() != before:
        raise ValueError("Historical source/reference mutation")
    with tempfile.TemporaryDirectory(prefix="sec-quarter-result-", dir=output.parent) as temp:
        folder = Path(temp)
        (folder / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
        if output.exists():
            raise ValueError("Output appeared during replay")
        folder.rename(output)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output)
    print(json.dumps({label: dict(ttm=r["metrics"], replay=r["underwriting_replay"],
                                current=r.get("current_credit_metrics", r.get("descriptive_credit_ratios")),
                                gaps=r["reconciliation_gaps_usd_millions"])
                      for label, r in result["results"].items()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
