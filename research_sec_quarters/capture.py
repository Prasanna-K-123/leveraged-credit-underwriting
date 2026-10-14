"""One bounded original-SEC capture, without retries or repository writes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from research_sec_intake import intake

CIK = "0000815097"
CUTOFF = "2026-10-14"
TARGETS = (
    ("annual_2025", "10-K", "2025-11-30", "0000815097-26-000007"),
    ("q1_2026", "10-Q", "2026-02-28", "0000815097-26-000037"),
    ("q3_2026", "10-Q", "2026-08-31", "0000815097-26-000107"),
    ("q1_2025_original", "10-Q", "2025-02-28", None),
    ("q3_2025_original", "10-Q", "2025-08-31", "0000815097-25-000084"),
)


class LimitedSession:
    def __init__(self, session, clock=time.monotonic, pause=time.sleep):
        self.session, self.clock, self.pause = session, clock, pause
        self.last_start = None

    def get(self, *args, **kwargs):
        now = self.clock()
        if self.last_start is not None and now - self.last_start < 0.2:
            self.pause(0.2 - (now - self.last_start))
        self.last_start = self.clock()
        return self.session.get(*args, **kwargs)


def select_targets(submissions):
    # Reuse the pre-existing strict parser, including CIK and parallel arrays.
    raw = json.dumps(submissions).encode()
    recent = intake._parse(raw, "submissions", CIK)["filings"]["recent"]
    selected = []
    for label, form, report, expected in TARGETS:
        indices = [i for i, value in enumerate(recent["form"])
                   if value == form and recent["reportDate"][i] == report]
        if len(indices) != 1:
            raise ValueError(f"Target {label} is not unique in submissions.recent")
        i = indices[0]
        accession, filed = recent["accessionNumber"][i], recent["filingDate"][i]
        if expected is not None and accession != expected:
            raise ValueError(f"Registered accession disagrees for {label}")
        if not report <= filed <= CUTOFF:
            raise ValueError(f"Registered cutoff or period violation for {label}")
        selected.append(dict(label=label, form=form, report_end=report,
                             accession=accession, filed_on=filed))
    return selected


def capture(output: Path, user_agent: str, session):
    if output.exists() or not output.parent.is_dir():
        raise ValueError("Fresh output directory with existing parent required")
    agent = intake._validate_agent(user_agent)
    output.mkdir()
    status = dict(schema_version=1, status="FAILED", source_base_commit="606ea14054443873d432c259548e100bda6f20af",
                  cutoff=CUTOFF, cik=CIK, captures=[],
                  started_at_utc=datetime.now(timezone.utc).isoformat())
    try:
        limited = LimitedSession(session)
        url = f"{intake.SEC_DATA}/submissions/CIK{CIK}.json"
        raw = intake._source_bytes(limited, url, agent, CIK, "submissions")
        (output / "discovery_submissions.json").write_bytes(raw)
        status["discovery"] = dict(url=url, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        targets = select_targets(json.loads(raw))
        status["resolved_targets"] = targets
        for target in targets:
            args = {key: value for key, value in target.items() if key != "label"}
            folder = output / target["label"]
            manifest = intake.acquire(cik=CIK, as_of=CUTOFF, output_dir=folder,
                                      user_agent=agent, session=limited, **args)
            intake.verify(folder, expected_cik=CIK)
            status["captures"].append(dict(label=target["label"], manifest=manifest))
        status["status"] = "PASS_ORIGINAL_BYTE_CAPTURE_ONLY"
        status["scope"] = "Five verified captures; financial/context reconciliation is not performed here"
    except Exception as error:
        status["error_type"] = type(error).__name__
        # Do not dump request headers, response bodies or credentials to logs.
        status["error"] = str(error)[:500]
        raise
    finally:
        status["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "CAPTURE_STATUS.json").write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    return status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import requests
    with requests.Session() as session:
        status = capture(args.output, os.environ.get("SEC_USER_AGENT", ""), session)
    print(json.dumps({"status": status["status"], "verified_captures": len(status["captures"])}))


if __name__ == "__main__":
    main()
