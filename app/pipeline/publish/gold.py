"""
Gold-layer publish step: denormalized public CSV for the GitHub Pages frontend.

Joins silver meetings + reference YAML + silver documents (+ optional
minutes_index.json) into the 14-column schema expected by index.html:

  ProjectName, MeetingType, MeetingDate, MeetingYear, Status, ActionTaken,
  StartTime, StaffCode, Title, MinutesURL, DocDate, LocationName,
  Latitude, Longitude
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.pipeline import config, reference
from app.pipeline.collect.minutes import load_minutes_index, minutes_body_key, resolve_minutes_url
from app.pipeline.load.silver import _atomic_write_csv, _read_csv
from app.pipeline.validate.schemas import in_estero_bbox

# Frontend filter chips / colors key off these display names (see index.html TYPES).
TYPE_DISPLAY_NAMES: dict[str, str] = {
    "Village Council": "Regular Council Meeting",
    "Planning Zoning & Design Board": "PZDB Meeting",
    "Public Hearing": "Public Hearing",
    "Workshop": "Council Workshop",
}

GOLD_FIELDS = [
    "ProjectName",
    "MeetingType",
    "MeetingDate",
    "MeetingYear",
    "Status",
    "ActionTaken",
    "StartTime",
    "StaffCode",
    "Title",
    "MinutesURL",
    "DocDate",
    "LocationName",
    "Latitude",
    "Longitude",
]

# Additive companion file: one row per structured meeting action. Kept SEPARATE
# from GOLD_FIELDS so the 14-column public meetings contract is never touched.
GOLD_ACTION_FIELDS = [
    "ActionId",
    "MeetingId",
    "MeetingDate",
    "ProjectName",
    "MeetingType",
    "Sequence",
    "Kind",
    "ReferenceCode",
    "AmountUSD",
    "RawText",
]


def _index_by_id(rows: list[dict], key: str) -> dict[int, dict]:
    return {int(r[key]): r for r in rows if r.get(key) is not None}


def _locations_by_project(locations: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for loc in locations:
        pid = loc.get("project_id")
        if pid is None:
            continue
        out.setdefault(int(pid), []).append(loc)
    return out


def _resolve_location(
    meeting: dict,
    loc_by_id: dict[int, dict],
    locs_by_project: dict[int, list[dict]],
    geocoded_location_ids: set[int] | None = None,
) -> tuple[str, str, str, str]:
    """Return (location_name, latitude, longitude, confidence)."""
    geocoded_location_ids = geocoded_location_ids or set()
    lid = meeting.get("location_id")
    if lid not in (None, ""):
        lid_int = int(lid)
        loc = loc_by_id.get(lid_int)
        if loc:
            confidence = (
                "geocoded" if lid_int in geocoded_location_ids else "exact_location_id"
            )
            return (
                loc.get("location_name") or meeting.get("location") or "",
                _fmt_coord(loc.get("latitude")),
                _fmt_coord(loc.get("longitude")),
                confidence,
            )
    pid = meeting.get("project_id")
    if pid is not None:
        for loc in locs_by_project.get(int(pid), []):
            loc_id = loc.get("location_id")
            confidence = (
                "geocoded" if loc_id in geocoded_location_ids else "project_fallback"
            )
            return (
                loc.get("location_name") or meeting.get("location") or "",
                _fmt_coord(loc.get("latitude")),
                _fmt_coord(loc.get("longitude")),
                confidence,
            )
    if meeting.get("location"):
        return (meeting.get("location") or "", "", "", "text_only")
    return ("", "", "", "missing")


def _fmt_coord(val: Any) -> str:
    if val is None or val == "":
        return ""
    try:
        return str(float(val))
    except (TypeError, ValueError):
        return str(val)


def _documents_by_meeting(documents: list[dict]) -> dict[int, dict]:
    """Prefer documents with a confirmed upload over placeholders."""
    best: dict[int, dict] = {}
    for doc in documents:
        mid = doc.get("meeting_id")
        if mid is None:
            continue
        mid = int(mid)
        prev = best.get(mid)
        if prev is None:
            best[mid] = doc
            continue
        prev_ok = (prev.get("link_status") or "").lower() == "uploaded"
        cur_ok = (doc.get("link_status") or "").lower() == "uploaded"
        if cur_ok and not prev_ok:
            best[mid] = doc
    return best


def _meeting_type_display(type_name: str) -> str:
    return TYPE_DISPLAY_NAMES.get(type_name, type_name or "Other")


def _resolve_minutes_url_for_row(
    meeting: dict,
    type_name: str,
    doc: dict | None,
    minutes_index: dict[str, Any],
) -> str:
    if doc and doc.get("file_url"):
        return str(doc["file_url"]).strip()
    iso = str(meeting.get("meeting_date", ""))[:10]
    return resolve_minutes_url(
        minutes_index,
        iso,
        type_name=type_name,
        type_id=meeting.get("type_id"),
    ) or ""


def _build_title(type_display: str, meeting_date: str, doc: dict | None) -> str:
    if doc and doc.get("title"):
        return str(doc["title"])
    return f"{type_display} — {meeting_date}"


def _is_valid_coord_pair(lat: str, lon: str) -> bool:
    if not lat or not lon:
        return False
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False
    return in_estero_bbox(lat_f, lon_f)


def build_gold(*, geocoded_location_ids: set[int] | None = None) -> dict[str, Any]:
    """Emit app/data/gold/meetings_public.csv and return a stage report."""
    meetings = _read_csv(config.SILVER_MEETINGS)
    documents = _read_csv(config.SILVER_DOCUMENTS)
    minutes_index = load_minutes_index()

    projects = _index_by_id(reference.projects(), "project_id")
    types = _index_by_id(reference.meeting_types(), "type_id")
    loc_by_id = _index_by_id(reference.locations(), "location_id")
    locs_by_project = _locations_by_project(reference.locations())
    docs_by_meeting = _documents_by_meeting(documents)

    rows: list[dict[str, str]] = []
    with_pdf = 0
    location_quality: dict[str, Any] = {
        "exact_location_id": 0,
        "project_fallback": 0,
        "geocoded": 0,
        "text_only": 0,
        "missing": 0,
        "with_coords": 0,
        "outside_bbox_or_invalid": 0,
        "strict_violations": [],
    }
    for m in meetings:
        pid = int(m["project_id"])
        tid = int(m["type_id"])
        project = projects.get(pid, {})
        mtype = types.get(tid, {})
        type_name = mtype.get("type_name", "")
        type_display = _meeting_type_display(type_name)
        meeting_date = str(m.get("meeting_date", ""))[:10]
        doc = docs_by_meeting.get(int(m["meeting_id"]))

        loc_name, lat, lon, confidence = _resolve_location(
            m,
            loc_by_id,
            locs_by_project,
            geocoded_location_ids=geocoded_location_ids,
        )
        location_quality[confidence] += 1
        has_coords = bool(lat and lon)
        if has_coords and _is_valid_coord_pair(lat, lon):
            location_quality["with_coords"] += 1
        elif has_coords:
            location_quality["outside_bbox_or_invalid"] += 1
            if len(location_quality["strict_violations"]) < 25:
                location_quality["strict_violations"].append(
                    f"meeting_id={m.get('meeting_id')} resolved outside ESTERO_BBOX or invalid coords"
                )
        elif confidence in {"text_only", "missing"}:
            if len(location_quality["strict_violations"]) < 25:
                location_quality["strict_violations"].append(
                    f"meeting_id={m.get('meeting_id')} has unresolved location confidence={confidence}"
                )
        minutes_url = _resolve_minutes_url_for_row(m, type_name, doc, minutes_index)
        if minutes_url:
            with_pdf += 1

        doc_date = ""
        if doc and doc.get("doc_date"):
            doc_date = str(doc["doc_date"])[:10]
        elif minutes_url:
            doc_date = meeting_date

        rows.append({
            "ProjectName": project.get("project_name", ""),
            "MeetingType": type_display,
            "MeetingDate": meeting_date,
            "MeetingYear": str(m.get("meeting_year", "")),
            "Status": m.get("status") or "Accepted",
            "ActionTaken": m.get("action_taken") or "",
            "StartTime": m.get("start_time") or "",
            "StaffCode": m.get("doc_ref_code") or "",
            "Title": _build_title(type_display, meeting_date, doc),
            "MinutesURL": minutes_url,
            "DocDate": doc_date,
            "LocationName": loc_name,
            "Latitude": lat,
            "Longitude": lon,
        })

    rows.sort(key=lambda r: (r["MeetingDate"], r["ProjectName"]), reverse=True)
    _atomic_write_csv(config.GOLD_MEETINGS_PUBLIC, GOLD_FIELDS, rows)

    action_report = _build_gold_actions(meetings, projects, types)

    return {
        "rows": len(rows),
        "with_minutes_url": with_pdf,
        "path": str(config.GOLD_MEETINGS_PUBLIC.relative_to(config.DATA_DIR.parent.parent)),
        "actions": action_report,
        "location_quality": location_quality,
    }


def _read_meeting_actions() -> list[dict]:
    """Read silver meeting_actions.csv, returning [] if it hasn't been built."""
    if not config.SILVER_MEETING_ACTIONS.exists():
        return []
    return _read_csv(config.SILVER_MEETING_ACTIONS)


def _build_gold_actions(
    meetings: list[dict],
    projects: dict[int, dict],
    types: dict[int, dict],
) -> dict[str, Any]:
    """Emit the additive app/data/gold/meeting_actions_public.csv.

    Denormalizes each structured action with its meeting's date, project and
    type for the public frontend. Gracefully no-ops (writes an empty file) when
    silver meeting_actions are missing.
    """
    actions = _read_meeting_actions()
    meetings_by_id = _index_by_id(meetings, "meeting_id")

    rows: list[dict[str, str]] = []
    for a in actions:
        mid = a.get("meeting_id")
        try:
            mid_int = int(mid)
        except (TypeError, ValueError):
            mid_int = None
        meeting = meetings_by_id.get(mid_int, {}) if mid_int is not None else {}
        project = projects.get(int(meeting["project_id"]), {}) if meeting.get("project_id") else {}
        mtype = types.get(int(meeting["type_id"]), {}) if meeting.get("type_id") else {}
        rows.append({
            "ActionId": a.get("action_id", ""),
            "MeetingId": mid if mid is not None else "",
            "MeetingDate": str(meeting.get("meeting_date", ""))[:10],
            "ProjectName": project.get("project_name", ""),
            "MeetingType": _meeting_type_display(mtype.get("type_name", "")),
            "Sequence": a.get("sequence", ""),
            "Kind": a.get("kind", ""),
            "ReferenceCode": a.get("reference_code", ""),
            "AmountUSD": a.get("amount_usd", ""),
            "RawText": a.get("raw_text", ""),
        })

    rows.sort(key=lambda r: (r["MeetingDate"], str(r["MeetingId"]), str(r["Sequence"])), reverse=True)
    _atomic_write_csv(config.GOLD_MEETING_ACTIONS_PUBLIC, GOLD_ACTION_FIELDS, rows)
    return {
        "rows": len(rows),
        "path": str(config.GOLD_MEETING_ACTIONS_PUBLIC.relative_to(config.DATA_DIR.parent.parent)),
    }
