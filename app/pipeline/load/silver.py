"""
Silver-layer build step.

Reads bronze CSVs (``app/data/meetings.csv`` and ``app/data/documents.csv``),
validates and cleans each row, and writes:

  * ``app/data/silver/meetings.csv``           — validated meetings, cleaned text
  * ``app/data/silver/documents.csv``          — real (non-placeholder) documents
  * ``app/data/silver/documents_planned.csv``  — future placeholder rows kept
                                                 separately so analytics never
                                                 mixes them with real data
  * ``app/data/silver/_rejects.json``          — rows that failed validation

Returns a stage report dict that the orchestrator includes in the run manifest.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.pipeline import config
from app.pipeline.clean.text import clean_action_text
from app.pipeline.validate.schemas import (
    DocumentRow,
    MeetingRow,
    validate_rows,
)

MEETING_OUT_FIELDS = [
    "meeting_id", "project_id", "type_id", "meeting_date", "meeting_year",
    "location", "start_time", "end_time", "action_taken", "status",
    "approved_by_council_date", "doc_ref_code", "filename", "notes",
    "location_id",
]

DOCUMENT_OUT_FIELDS = [
    "document_id", "meeting_id", "title", "file_url", "doc_date",
    "meeting_date", "meeting_year", "status", "type_name", "link_status",
]


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _atomic_write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Write to a tempfile in the same directory then rename, so a crashed
    pipeline never leaves a half-written silver file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in fields})
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _meeting_to_dict(m: MeetingRow) -> dict:
    d = m.model_dump()
    d["action_taken"] = clean_action_text(d.get("action_taken"))
    d["notes"] = clean_action_text(d.get("notes"))
    return d


def _is_future_placeholder(d: DocumentRow) -> bool:
    return (d.link_status or "").strip().lower() == config.FUTURE_PLACEHOLDER_TAG.lower()


def _check_unique(rows: list[dict], key: str) -> list[dict]:
    """Return a list of duplicate-key error reports."""
    seen: dict[Any, int] = {}
    dups: list[dict] = []
    for i, row in enumerate(rows):
        k = row.get(key)
        if k is None:
            continue
        if k in seen:
            dups.append({"row": row, "errors": [f"duplicate {key}={k} (also at row {seen[k]})"]})
        else:
            seen[k] = i
    return dups


def build_silver() -> dict:
    """Run the bronze -> silver step end-to-end and return a report."""
    raw_meetings = _read_csv(config.BRONZE_MEETINGS)
    raw_documents = _read_csv(config.BRONZE_DOCUMENTS)

    valid_meetings, meeting_rejects = validate_rows(raw_meetings, MeetingRow)
    valid_documents, document_rejects = validate_rows(raw_documents, DocumentRow)

    meeting_dicts = [_meeting_to_dict(m) for m in valid_meetings]
    meeting_rejects.extend(_check_unique(meeting_dicts, "meeting_id"))

    document_dicts = [d.model_dump() for d in valid_documents]
    document_rejects.extend(_check_unique(document_dicts, "document_id"))

    valid_meeting_ids = {m["meeting_id"] for m in meeting_dicts}
    fk_warnings = [
        {"row": d, "errors": [f"unknown meeting_id={d['meeting_id']} (kept anyway)"]}
        for d in document_dicts if d["meeting_id"] not in valid_meeting_ids
    ]

    real_docs = [d for d in document_dicts if not _is_future_placeholder_dict(d)]
    planned_docs = [d for d in document_dicts if _is_future_placeholder_dict(d)]

    _atomic_write_csv(config.SILVER_MEETINGS, MEETING_OUT_FIELDS, meeting_dicts)
    _atomic_write_csv(config.SILVER_DOCUMENTS, DOCUMENT_OUT_FIELDS, real_docs)
    _atomic_write_csv(config.SILVER_DOCUMENTS_PLANNED, DOCUMENT_OUT_FIELDS, planned_docs)
    _atomic_write_json(
        config.SILVER_REJECTS,
        {
            "meetings": meeting_rejects,
            "documents": document_rejects,
            "document_fk_warnings": fk_warnings,
        },
    )

    return {
        "meetings": {
            "in": len(raw_meetings),
            "out": len(meeting_dicts),
            "rejects": len(meeting_rejects),
        },
        "documents": {
            "in": len(raw_documents),
            "out_real": len(real_docs),
            "out_planned": len(planned_docs),
            "rejects": len(document_rejects),
            "fk_warnings": len(fk_warnings),
        },
    }


def _is_future_placeholder_dict(d: dict) -> bool:
    return (d.get("link_status") or "").strip().lower() == config.FUTURE_PLACEHOLDER_TAG.lower()
