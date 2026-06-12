"""CLI shim: discover newly-held meetings and write candidate_meetings.csv.

Thin wrapper around ``app.pipeline.extract.meetings.collect_candidate_meetings``
(mirrors ``scripts/scrape_minutes_index.py``).  Never edits bronze; it only
writes the human-review candidate file and prints the count of new candidates.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/scrape_meetings.py` from repo root (CI + local).
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.pipeline.extract.meetings import collect_candidate_meetings


def main() -> int:
    report = collect_candidate_meetings()
    new = report.get("total_new", 0)
    path = report.get("path", "app/data/extract/candidate_meetings.csv")
    print(f"[discover] wrote {path} ({new} new candidate(s))")
    if report.get("errors"):
        for body, err in report["errors"].items():
            print(f"[discover] WARN source '{body}' failed: {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
