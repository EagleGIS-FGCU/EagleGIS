"""
Refresh the frontend-facing dataset (``pdfs/Estero_Meetings_Final.csv``) by
re-extracting each row's ``ActionTaken`` straight from the source PDF using the
hardened pipeline in :mod:`pdf_pipeline`.

We deliberately keep the manually curated columns intact:

  - ProjectName, LocationName, Latitude, Longitude  (project assignment +
    geocoding the team did by hand)
  - Title, MeetingType, MeetingYear, MeetingDate, DocDate, MinutesURL

We only refresh:

  - ActionTaken    (cleaner cleaning + better Action: extraction)
  - MeetingType    (categorized from filename + document title line)
  - StartTime      (when missing or "null")
  - StaffCode      (when missing or "null")
  - Status         (Cancelled detection)

If a PDF can't be located the row's MeetingType is still classified from the
URL/filename (good enough for PZDB rows where the PDFs live elsewhere) and
the rest of the row is left as-is.
"""
from __future__ import annotations

import csv
import os
import re
from urllib.parse import unquote

from pdf_pipeline import extract_meeting_type, process_pdf

CSV_PATH = os.path.join("pdfs", "Estero_Meetings_Final.csv")
PDF_DIR = "pdfs"


def filename_from_url(url: str) -> str:
    if not url:
        return ""
    base = url.rsplit("/", 1)[-1]
    return unquote(base).strip()


_PDF_INDEX: dict[str, str] | None = None


def _build_pdf_index() -> dict[str, str]:
    """Map of normalized PDF basename -> actual filesystem name.

    The CSV's filenames sometimes drift from disk by a single character
    (extra space, casing). Normalising for lookup absorbs that drift.
    """
    idx: dict[str, str] = {}
    if not os.path.isdir(PDF_DIR):
        return idx
    for name in os.listdir(PDF_DIR):
        if not name.lower().endswith(".pdf"):
            continue
        key = re.sub(r"\s+", " ", name).strip().lower()
        idx[key] = name
    return idx


def resolve_pdf(filename: str) -> str | None:
    """Return the actual disk path for ``filename`` (tolerant matcher)."""
    global _PDF_INDEX
    if _PDF_INDEX is None:
        _PDF_INDEX = _build_pdf_index()
    direct = os.path.join(PDF_DIR, filename)
    if os.path.exists(direct):
        return direct
    key = re.sub(r"\s+", " ", filename).strip().lower()
    real = _PDF_INDEX.get(key)
    if real:
        return os.path.join(PDF_DIR, real)
    return None


def is_blank(value: str) -> bool:
    if value is None:
        return True
    v = value.strip().lower()
    return v in {"", "null", "none", "n/a", "no action found",
                 "no action extracted - verify pdf"}


def main() -> None:
    if not os.path.exists(CSV_PATH):
        raise SystemExit(f"Cannot find {CSV_PATH}")

    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    refreshed = blanks_filled = missing_pdfs = retyped = 0
    for row in rows:
        fn = filename_from_url(row.get("MinutesURL", ""))
        if not fn:
            continue
        pdf_path = resolve_pdf(fn)

        if not pdf_path:
            # PDF not available locally (e.g. PZDB rows whose source lives on
            # estero-fl.gov). We can still classify it from its filename.
            missing_pdfs += 1
            new_type = extract_meeting_type(fn, "")
            if new_type and row.get("MeetingType") != new_type:
                row["MeetingType"] = new_type
                retyped += 1
            continue

        try:
            result = process_pdf(pdf_path)
        except Exception as e:
            print(f"[warn] failed to process {fn}: {e}")
            continue

        old_action = row.get("ActionTaken", "") or ""
        new_action = result["action_text"]

        if result["status"] == "Cancelled":
            row["ActionTaken"] = "Meeting Cancelled"
            row["Status"] = "Cancelled"
        elif new_action:
            row["ActionTaken"] = new_action
            if is_blank(old_action) or "Approve d" in old_action \
               or "A pprove" in old_action or "A ction" in old_action \
               or "Vo te" in old_action or "Approve da" in old_action \
               or len(old_action) < len(new_action) * 0.5:
                refreshed += 1
            if is_blank(old_action):
                blanks_filled += 1

        new_type = result["meeting_type"]
        if new_type and row.get("MeetingType") != new_type:
            row["MeetingType"] = new_type
            retyped += 1

        if is_blank(row.get("StartTime", "")) and result["start_time"]:
            row["StartTime"] = result["start_time"]
        if is_blank(row.get("StaffCode", "")) and result["staff_code"]:
            row["StaffCode"] = result["staff_code"]
        if is_blank(row.get("Status", "")):
            row["Status"] = result["status"]

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[refine] {len(rows)} rows processed")
    print(f"[refine]   {refreshed} ActionTaken values refreshed")
    print(f"[refine]   {blanks_filled} previously-blank cells filled")
    print(f"[refine]   {retyped} MeetingType values updated")
    if missing_pdfs:
        print(f"[refine]   {missing_pdfs} rows had no local PDF "
              f"(filename-only classification applied)")


if __name__ == "__main__":
    main()
