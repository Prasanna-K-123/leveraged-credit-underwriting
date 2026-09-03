from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import requests

SEC_ROOT = "https://data.sec.gov"
ARCHIVES_ROOT = "https://www.sec.gov/Archives/edgar/data"


@dataclass(frozen=True)
class SourceSnapshot:
    captured_at_utc: str
    cik: str
    companyfacts_url: str
    companyfacts_sha256: str
    submissions_url: str
    submissions_sha256: str


def _headers() -> dict[str, str]:
    ua = os.environ.get("SEC_USER_AGENT", "Prasanna K prasannak0911@gmail.com academic credit research")
    return {
        "User-Agent": ua,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def _get_json(url: str, timeout: int = 30) -> tuple[dict[str, Any], bytes]:
    response = requests.get(url, headers=_headers(), timeout=timeout)
    response.raise_for_status()
    raw = response.content
    return response.json(), raw


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fetch_sec_bundle(cik: str, raw_dir: Path) -> tuple[dict[str, Any], dict[str, Any], SourceSnapshot]:
    """Fetch SEC companyfacts and submissions JSON, retain raw bytes and hashes."""
    cik10 = str(cik).zfill(10)
    raw_dir.mkdir(parents=True, exist_ok=True)
    companyfacts_url = f"{SEC_ROOT}/api/xbrl/companyfacts/CIK{cik10}.json"
    submissions_url = f"{SEC_ROOT}/submissions/CIK{cik10}.json"

    companyfacts, companyfacts_raw = _get_json(companyfacts_url)
    submissions, submissions_raw = _get_json(submissions_url)

    (raw_dir / f"CIK{cik10}_companyfacts.json").write_bytes(companyfacts_raw)
    (raw_dir / f"CIK{cik10}_submissions.json").write_bytes(submissions_raw)

    snapshot = SourceSnapshot(
        captured_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        cik=cik10,
        companyfacts_url=companyfacts_url,
        companyfacts_sha256=sha256_bytes(companyfacts_raw),
        submissions_url=submissions_url,
        submissions_sha256=sha256_bytes(submissions_raw),
    )
    (raw_dir / "source_snapshot.json").write_text(json.dumps(asdict(snapshot), indent=2), encoding="utf-8")
    return companyfacts, submissions, snapshot


def latest_filing(submissions: dict[str, Any], form: str) -> dict[str, str]:
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    for i, current_form in enumerate(forms):
        if current_form == form:
            accession = recent["accessionNumber"][i]
            primary = recent["primaryDocument"][i]
            filed = recent["filingDate"][i]
            report = recent.get("reportDate", [""] * len(forms))[i]
            cik_numeric = str(int(submissions["cik"]))
            accession_compact = accession.replace("-", "")
            url = f"{ARCHIVES_ROOT}/{cik_numeric}/{accession_compact}/{primary}"
            return {
                "form": form,
                "accession": accession,
                "filed": filed,
                "report_date": report,
                "primary_document": primary,
                "url": url,
            }
    raise ValueError(f"No recent {form} filing found")
