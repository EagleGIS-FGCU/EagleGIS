"""
Publish silver + reference data to Supabase (the gold/serving layer).

Reads:
  * reference YAML  (projects, meeting_types, locations)
  * silver CSVs     (meetings, documents)

Writes (idempotent upsert on primary key):
  * public.projects, public.meeting_types, public.locations
  * public.meetings,  public.documents

Design constraints:

  * **Idempotent.** Running twice produces the same end state.
  * **Non-destructive.** Never deletes rows from Supabase. Drift detection
    is the verifier's job; resolving drift is an explicit operator action.
  * **FK-safe ordering.** Parents (projects, meeting_types, locations) are
    upserted before their children (meetings, documents).
  * **Field-sliced.** Silver carries denormalized helpers
    (e.g. documents.meeting_year) that don't exist in the Supabase schema;
    we slice each row down to the columns the table actually has.
  * **Batched.** Large tables are chunked to stay under PostgREST limits.
"""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Iterable, Iterator

from app.pipeline import config, reference

logger = logging.getLogger(__name__)

BATCH_SIZE = 100

# Columns that exist in the Supabase schema for each table. Fields outside
# this list are dropped before upsert.
TABLE_SPEC: dict[str, dict[str, Any]] = {
    "projects": {
        "pk": "project_id",
        "fields": ["project_id", "project_name", "description", "status"],
    },
    "meeting_types": {
        "pk": "type_id",
        "fields": ["type_id", "type_name", "description"],
    },
    "locations": {
        "pk": "location_id",
        "fields": [
            "location_id", "project_id", "location_name", "location_type",
            "address", "description", "latitude", "longitude",
        ],
    },
    "meetings": {
        "pk": "meeting_id",
        "fields": [
            "meeting_id", "project_id", "type_id", "meeting_date", "meeting_year",
            "location", "start_time", "end_time", "action_taken", "status",
            "approved_by_council_date", "doc_ref_code", "filename", "notes",
        ],
    },
    "documents": {
        "pk": "document_id",
        "fields": [
            "document_id", "meeting_id", "title", "document_type", "file_name",
            "file_url", "upload_date", "notes", "doc_date",
        ],
    },
}

# Tables are upserted in this order so foreign keys resolve cleanly.
PUBLISH_ORDER: tuple[str, ...] = (
    "projects", "meeting_types", "locations", "meetings", "documents",
)


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _coerce_value(v: Any) -> Any:
    """Empty string -> None so Supabase stores NULL, not ''."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def slice_fields(rows: list[dict], fields: list[str]) -> list[dict]:
    """Project each row to the given fields and normalize empties."""
    return [{k: _coerce_value(r.get(k)) for k in fields} for r in rows]


def _batched(seq: list[dict], size: int) -> Iterator[list[dict]]:
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _gather_local_rows() -> dict[str, list[dict]]:
    """Read silver + reference and return a dict of table -> sliced rows."""
    return {
        "projects": slice_fields(reference.projects(), TABLE_SPEC["projects"]["fields"]),
        "meeting_types": slice_fields(reference.meeting_types(), TABLE_SPEC["meeting_types"]["fields"]),
        "locations": slice_fields(reference.locations(), TABLE_SPEC["locations"]["fields"]),
        "meetings": slice_fields(_read_csv(config.SILVER_MEETINGS), TABLE_SPEC["meetings"]["fields"]),
        "documents": slice_fields(_read_csv(config.SILVER_DOCUMENTS), TABLE_SPEC["documents"]["fields"]),
    }


def _upsert_table(client, table: str, rows: list[dict], pk: str, dry_run: bool) -> dict:
    if not rows:
        return {"upserted": 0, "batches": 0, "dry_run": dry_run}
    if dry_run:
        return {
            "upserted": len(rows),
            "batches": (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE,
            "dry_run": True,
        }

    upserted = 0
    batches = 0
    for batch in _batched(rows, BATCH_SIZE):
        client.table(table).upsert(batch, on_conflict=pk).execute()
        upserted += len(batch)
        batches += 1
    return {"upserted": upserted, "batches": batches, "dry_run": False}


def publish(client, *, dry_run: bool = False) -> dict:
    """Upsert local silver+reference data into Supabase. Returns a per-table report."""
    locals_by_table = _gather_local_rows()
    report: dict[str, dict] = {}
    for table in PUBLISH_ORDER:
        spec = TABLE_SPEC[table]
        result = _upsert_table(client, table, locals_by_table[table], spec["pk"], dry_run)
        report[table] = result
        logger.info("publish %s: %s", table, result)
    return report
