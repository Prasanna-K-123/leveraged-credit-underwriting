"""Safe, file-based SEC source acquisition preflight; never computes issuer metrics.

Dependencies: Python standard library and requests-compatible HTTP session.
This library only attests the bytes returned by an explicitly chosen SEC URL;
it cannot authenticate the SEC's own disclosure or certify as-of completeness.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import urlparse

SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
MAX_RESPONSE_BYTES = 60_000_000
ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}\Z")
CIK = re.compile(r"\d{1,10}\Z")


def _iso(value: str, name: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be ISO YYYY-MM-DD")
    try:
        value_date = date.fromisoformat(value)
    except ValueError as ex:
        raise ValueError(f"{name} must be ISO YYYY-MM-DD") from ex
    if value_date.isoformat() != value:
        raise ValueError(f"{name} must be ISO YYYY-MM-DD")
    return value_date


def _required_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {name}")
    return value


def _cik(value: str) -> str:
    if not isinstance(value, str) or not CIK.fullmatch(value):
        raise ValueError("CIK must be 1-10 decimal digits")
    return value.zfill(10)


def _validate_agent(value: str) -> str:
    v = _required_string(value, "SEC_USER_AGENT")
    if len(v) > 160 or "@" not in v or " " not in v:
        raise ValueError("Supply a descriptive SEC_USER_AGENT with a real contact email")
    return v


def _parse(body: bytes, kind: str, cik: str) -> dict[str, Any] | None:
    if not isinstance(body, bytes) or not body or len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("Empty, non-byte or excessive SEC response")
    if kind == "filing_html":
        # Original raw HTML is deliberately retained, not rewritten/re-serialized.
        if b"<html" not in body[:150000].lower():
            raise ValueError("SEC filing response lacks HTML structure")
        return None
    try:
        content = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid {kind} JSON") from exc
    if not isinstance(content, dict):
        raise ValueError("SEC JSON root must be an object")
    if _cik(str(content.get("cik", ""))) != cik:
        raise ValueError(f"SEC {kind} CIK mismatch")
    if kind == "companyfacts":
        if not isinstance(content.get("facts"), dict) or not isinstance(content["facts"].get("us-gaap"), dict):
            raise ValueError("Companyfacts lacks us-gaap facts mapping")
    elif kind == "submissions":
        rec = content.get("filings", {}).get("recent", {}) if isinstance(content.get("filings"), dict) else {}
        keys = ("accessionNumber", "form", "reportDate", "filingDate", "primaryDocument")
        if not isinstance(rec, dict) or any(not isinstance(rec.get(k), list) for k in keys):
            raise ValueError("Submissions recent array mapping missing")
        if len({len(rec[k]) for k in keys}) != 1:
            raise ValueError("Submissions arrays misaligned")
    else:
        raise ValueError("Unknown SEC evidence kind")
    return content


def _source_bytes(session: Any, url: str, agent: str, cik: str, kind: str) -> bytes:
    # We only ever request hard-coded SEC roots or URLs built from vetted source metadata.
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError("Noncanonical source URL")
    if kind == "filing_html":
        if parsed.netloc != "www.sec.gov" or not parsed.path.startswith("/Archives/edgar/data/"):
            raise ValueError("Not a SEC Archives document")
    elif parsed.netloc != "data.sec.gov":
        raise ValueError("Not a SEC data endpoint")
    response = session.get(url, headers={"User-Agent": agent, "Accept-Encoding": "gzip, deflate"},
                           timeout=45, allow_redirects=False)
    # Some test response objects implement status_code only; live requests supports both.
    if response.status_code != 200 or getattr(response, "url", url) != url:
        raise ValueError(f"SEC source unavailable or redirected: {kind}")
    body = response.content
    _parse(body, kind, cik)
    return body


def acquire(*, cik: str, accession: str, form: str, report_end: str, filed_on: str,
            as_of: str, output_dir: Path, user_agent: str, session: Any) -> dict[str, Any]:
    """Pin one filing via SEC submissions and acquire three raw source snapshots.

    The source directory is created atomically only after complete verification.
    Content is time-of-download SEC API state, *not* a historical as-of API replay.
    """
    cik10 = _cik(cik)
    agent = _validate_agent(user_agent)
    if not isinstance(accession, str) or not ACCESSION.fullmatch(accession) or accession[:10] != cik10:
        raise ValueError("Accession must match the company CIK")
    if form not in ("10-Q", "10-K"):
        raise ValueError("Only standard 10-Q and 10-K accepted")
    report, filed, cutoff = _iso(report_end, "report_end"), _iso(filed_on, "filed_on"), _iso(as_of, "as_of")
    if not report <= filed <= cutoff <= datetime.now(timezone.utc).date():
        raise ValueError("Inconsistent filing/period/as-of/future dates")
    dest = Path(output_dir).resolve()
    if dest.exists() or dest.parent == dest:
        raise ValueError("Output directory must not exist; no overwrites")
    if not dest.parent.is_dir():
        raise ValueError("Output parent directory does not exist")
    if dest.is_symlink():
        raise ValueError("Symlink destinations refused")
    url_sub = f"{SEC_DATA}/submissions/CIK{cik10}.json"
    url_facts = f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik10}.json"
    bodies: dict[str, tuple[str, bytes]] = {}
    bodies["submissions"] = (url_sub, _source_bytes(session, url_sub, agent, cik10, "submissions"))
    recent = _parse(bodies["submissions"][1], "submissions", cik10)["filings"]["recent"]
    matches = [i for i, a in enumerate(recent["accessionNumber"]) if a == accession]
    if len(matches) != 1:
        raise ValueError("Target accession not unique in submissions.recent; historical archive unsupported")
    idx = matches[0]
    if any(recent[k][idx] != v for k, v in (("form", form), ("reportDate", report_end), ("filingDate", filed_on))):
        raise ValueError("Submissions filing form/date disagreement")
    primary = recent["primaryDocument"][idx]
    if not isinstance(primary, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+\.htm[l]?", primary):
        raise ValueError("Unexpected SEC primaryDocument filename")
    filing_url = f"{SEC_ARCHIVES}/{int(cik10)}/{accession.replace('-', '')}/{primary}"
    bodies["companyfacts"] = (url_facts, _source_bytes(session, url_facts, agent, cik10, "companyfacts"))
    bodies["filing_html"] = (filing_url, _source_bytes(session, filing_url, agent, cik10, "filing_html"))
    captured = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    filenames = {"submissions": f"CIK{cik10}_submissions.json",
                 "companyfacts": f"CIK{cik10}_companyfacts.json",
                 "filing_html": f"{form.replace('-', '')}_{report_end}_{accession.replace('-', '')}.html"}
    record = {"schema_version": 1, "kind": "raw_SEC_byte_capture_not_asof_history",
              "cik": cik10, "accession": accession, "form": form,
              "report_end": report_end, "filed_on": filed_on, "as_of": as_of,
              "captured_at_utc": captured, "sources": []}
    with tempfile.TemporaryDirectory(prefix="sec-stage-", dir=dest.parent) as tmp:
        p = Path(tmp)
        for kind in ("submissions", "companyfacts", "filing_html"):
            url, body = bodies[kind]
            filename = filenames[kind]
            (p / filename).write_bytes(body)
            record["sources"].append({"kind": kind, "url": url, "filename": filename,
                                      "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
        (p / "manifest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify(p, expected_cik=cik10)
        # Atomic move to a previously absent destination. Recheck for a race; refuse a prior existence.
        if dest.exists():
            raise ValueError("Output destination appeared during acquisition")
        p.rename(dest)
    return record


def verify(directory: Path, *, expected_cik: str) -> dict[str, Any]:
    folder = Path(directory)
    record = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if record.get("schema_version") != 1 or record.get("cik") != _cik(expected_cik):
        raise ValueError("Bad manifest schema/CIK")
    if not isinstance(record.get("sources"), list) or len(record["sources"]) != 3:
        raise ValueError("Exactly three source identities required")
    accession = record.get("accession")
    cik10 = _cik(expected_cik)
    if not isinstance(accession, str) or not ACCESSION.fullmatch(accession) or accession[:10] != cik10:
        raise ValueError("Manifest accession/CIK mismatch")
    form = record.get("form")
    if form not in ("10-Q", "10-K"):
        raise ValueError("Manifest form invalid")
    report, filed, cutoff = (_iso(record.get(key), key) for key in ("report_end", "filed_on", "as_of"))
    if not report <= filed <= cutoff:
        raise ValueError("Manifest dates inconsistent")
    expected_by_kind = {
        "submissions": (f"{SEC_DATA}/submissions/CIK{cik10}.json", f"CIK{cik10}_submissions.json"),
        "companyfacts": (f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik10}.json", f"CIK{cik10}_companyfacts.json"),
    }
    expected_names = {"manifest.json"}
    seen_kinds = set()
    decoded_submissions = None
    for item in record["sources"]:
        kind, name = item["kind"], item["filename"]
        if kind not in ("submissions", "companyfacts", "filing_html") or not isinstance(name, str) or Path(name).name != name:
            raise ValueError("Invalid source member")
        if kind in seen_kinds:
            raise ValueError("Duplicate source kinds")
        seen_kinds.add(kind)
        if kind in expected_by_kind and (item.get("url"), name) != expected_by_kind[kind]:
            raise ValueError("SEC API source URL/path mismatch")
        if kind == "filing_html":
            target_file = f"{form.replace('-', '')}_{report.isoformat()}_{accession.replace('-', '')}.html"
            url = item.get("url", "")
            if name != target_file or not isinstance(url, str) or not url.startswith(
                    f"{SEC_ARCHIVES}/{int(cik10)}/{accession.replace('-', '')}/"):
                raise ValueError("SEC Archives source URL/path mismatch")
        expected_names.add(name)
        data = (folder / name).read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Source bytes fail identity verification")
        parsed = _parse(data, kind, cik10)
        if kind == "submissions":
            decoded_submissions = parsed
    if seen_kinds != {"submissions", "companyfacts", "filing_html"}:
        raise ValueError("Required source kinds missing")
    recent = decoded_submissions["filings"]["recent"]
    matches = [i for i, a in enumerate(recent["accessionNumber"]) if a == accession]
    if len(matches) != 1:
        raise ValueError("Manifest accession not uniquely grounded in submissions")
    idx = matches[0]
    if any(recent[k][idx] != v for k, v in (("form", form), ("reportDate", report.isoformat()),
                                           ("filingDate", filed.isoformat()))):
        raise ValueError("Manifest filing metadata not grounded in submissions")
    primary = recent["primaryDocument"][idx]
    expected_html_url = f"{SEC_ARCHIVES}/{int(cik10)}/{accession.replace('-', '')}/{primary}"
    observed = next(i for i in record["sources"] if i["kind"] == "filing_html")
    if observed["url"] != expected_html_url:
        raise ValueError("Manifest HTML URL not grounded in submissions")
    if len(expected_names) != 4 or {p.name for p in folder.iterdir()} != expected_names:
        raise ValueError("Missing, duplicate, or extra source files")
    if not isinstance(record.get("accession"), str) or not ACCESSION.fullmatch(record["accession"]):
        raise ValueError("Invalid accession in manifest")
    return record
