"""Scrape canonical meeting-minute PDF URLs from estero-fl.gov.

The Village of Estero publishes Village Council and Planning, Zoning & Design
Board (PZDB) meeting minutes as PDFs in a predictable directory structure
under ``/wp-content/uploads/library-ada/minutes/...``. Two public index pages
list every minutes PDF the Village has published:

  * /villagecouncilminutes/  -> Council meeting minutes (327+ links)
  * /pzdbminutes/            -> PZDB meeting minutes  (68+ links)

This script downloads both pages, extracts every minutes PDF URL it can find,
parses the meeting date out of the filename, and writes a small JSON manifest
to ``app/data/minutes_index.json`` that the EagleGIS front-end can load to
resolve canonical PDF links for both historical CSV rows and live Tribe
Events API events.

The script is deliberately dependency-light (``urllib.request`` only) so it
can run in CI without touching the existing ``requirements.txt``.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCES = {
    "council": "https://estero-fl.gov/villagecouncilminutes/",
    "pzdb": "https://estero-fl.gov/pzdbminutes/",
}

# Match every PDF that lives under the Village's ADA-compliant minutes folder.
PDF_RE = re.compile(
    r'href="(https://estero-fl\.gov/wp-content/uploads/library-ada/minutes/[^"]+\.pdf[^"]*)"',
    re.IGNORECASE,
)

# Filenames on estero-fl.gov use several date formats over the years. We try
# each in priority order so the most specific (8-digit MMDDYYYY) wins over
# the looser ones (MMDDYY).
DATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # MMDDYYYY -- modern era, e.g. "01072026.pdf"
    ("mmddyyyy", re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{4})(?!\d)")),
    # YYYY-MM-DD -- 2019/2020 council, e.g. "2020-01-08 Council Meeting..."
    ("iso", re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")),
    # YYYYMMDD -- late 2019 council, e.g. "20191016 Council Meeting..."
    ("yyyymmdd", re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)")),
    # MMDDYY -- 2015-2018, e.g. "010318 Council Meeting Approved Minutes"
    ("mmddyy", re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)")),
)

MONTH_RE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
    re.IGNORECASE,
)
MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

USER_AGENT = (
    "Mozilla/5.0 (compatible; EagleGIS-Minutes-Indexer/1.0; "
    "+https://github.com/EagleGIS-FGCU/EagleGIS)"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _safe_date(year: int, month: int, day: int) -> str | None:
    """Return an ISO date string if (y, m, d) is a real calendar date."""
    if not (2000 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return None
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def iso_date_from_filename(filename: str) -> str | None:
    """Pull a meeting date out of a decoded PDF filename in any known format.

    Skips obvious non-minutes filenames (cancellation notices, etc.) up front
    so the date heuristics don't accidentally match the cancellation page's
    publication number.
    """
    low = filename.lower()
    if low.startswith("cancel") or "cancellation" in low or "rescheduled" in low:
        return None

    # Month-name format first -- it's unambiguous when present.
    m = MONTH_RE.search(filename)
    if m:
        month = MONTHS[m.group(1).lower()]
        return _safe_date(int(m.group(3)), month, int(m.group(2)))

    for kind, pat in DATE_PATTERNS:
        m = pat.search(filename)
        if not m:
            continue
        if kind == "mmddyyyy":
            mm, dd, yyyy = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
            if iso:
                return iso
        elif kind == "iso":
            yyyy, mm, dd = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
            if iso:
                return iso
        elif kind == "yyyymmdd":
            yyyy, mm, dd = m.groups()
            iso = _safe_date(int(yyyy), int(mm), int(dd))
            if iso:
                return iso
        elif kind == "mmddyy":
            mm, dd, yy = m.groups()
            yyyy = 2000 + int(yy) if int(yy) < 50 else 1900 + int(yy)
            iso = _safe_date(yyyy, int(mm), int(dd))
            if iso:
                return iso
    return None


def extract_pdfs(html: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in PDF_RE.finditer(html):
        url = match.group(1)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def build_section(html: str) -> tuple[dict[str, str], list[str]]:
    """Return (date -> url mapping, list of unparseable filenames)."""
    mapping: dict[str, str] = {}
    skipped: list[str] = []
    for url in extract_pdfs(html):
        filename = urllib.parse.unquote(url.rsplit("/", 1)[-1])
        iso = iso_date_from_filename(filename)
        if not iso:
            skipped.append(filename)
            continue
        # If we somehow see the same date twice (re-uploads, "Approved" vs
        # "Draft"), prefer the URL that mentions "Approved"/"Final".
        existing = mapping.get(iso)
        if existing is None:
            mapping[iso] = url
        else:
            score_new = sum(
                kw in filename.lower() for kw in ("approved", "final", "signed")
            )
            score_old = sum(
                kw in urllib.parse.unquote(existing).lower()
                for kw in ("approved", "final", "signed")
            )
            if score_new > score_old:
                mapping[iso] = url
    return mapping, skipped


def main() -> int:
    out_path = Path(__file__).resolve().parent.parent / "app" / "data" / "minutes_index.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result: dict = {"_meta": {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_pages": SOURCES,
        "skipped": {},
    }}

    total = 0
    for key, url in SOURCES.items():
        print(f"[scrape] {key:<8} <- {url}", flush=True)
        html = fetch(url)
        mapping, skipped = build_section(html)
        # Sort by date descending for human-friendly diffs.
        result[key] = dict(sorted(mapping.items(), reverse=True))
        result["_meta"]["skipped"][key] = skipped
        print(
            f"          extracted={len(mapping)} skipped={len(skipped)}",
            flush=True,
        )
        total += len(mapping)

    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[scrape] wrote {out_path.relative_to(out_path.parents[2])} "
          f"({total} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
