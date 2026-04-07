"""
CSV-backed data store.

Reads meetings and documents from CSV files in app/data/.
Projects, locations, and geometries remain as structured data since
the CSVs do not include coordinates.

To update the data: edit the CSV files and push to GitHub.
CI/CD will redeploy and ArcGIS will pick up the changes automatically.
"""
import csv
from datetime import date
from pathlib import Path
from typing import Optional
from copy import deepcopy

_DATA_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Static data (no coordinates in CSV — keep structured)
# ---------------------------------------------------------------------------

MEETING_TYPES: list[dict] = [
    {"type_id": 1, "type_name": "Village Council",                  "description": "Regular Village Council meeting"},
    {"type_id": 2, "type_name": "Planning Zoning & Design Board",   "description": "Combined planning, zoning, and design review board"},
    {"type_id": 3, "type_name": "Public Hearing",                   "description": "Public input sessions on proposed projects"},
    {"type_id": 4, "type_name": "Workshop",                         "description": "Informational workshops for Council and staff"},
]

PROJECTS: list[dict] = [
    {
        "project_id": 1,
        "project_name": "BERT Rail Trail",
        "description": "Multi-use trail along the Bonita-Estero Regional Trail (BERT) corridor through the Village of Estero.",
        "start_year": 2021,
        "status": "Active",
    },
    {
        "project_id": 2,
        "project_name": "Septic to Sewer Conversion",
        "description": (
            "Utility extension project converting multiple Estero neighborhoods "
            "from septic systems to central sewer, including Estero Bay Village, "
            "Sunny Grove, Cypress Bend, and Broadway Avenue East."
        ),
        "start_year": 2021,
        "status": "Active",
    },
    {
        "project_id": 3,
        "project_name": "Corkscrew Road Widening",
        "description": "Corkscrew Road widening, intersection improvements, and traffic signal installations.",
        "start_year": 2021,
        "status": "Active",
    },
    {
        "project_id": 4,
        "project_name": "PZ&DB General Meeting Records",
        "description": "Administrative meeting records for the Village of Estero Planning, Zoning & Design Board.",
        "start_year": 2021,
        "status": "Active",
    },
]

LOCATIONS: list[dict] = [
    {
        "location_id": 1, "project_id": 1,
        "location_name": "BERT Rail Trail Corridor",
        "location_type": "Trail",
        "address": "Estero, FL 33928",
        "description": "Multi-use trail along the BERT corridor.",
        "latitude": 26.433900, "longitude": -81.815700,
    },
    {
        "location_id": 2, "project_id": 2,
        "location_name": "Estero Bay Village Septic Area",
        "location_type": "Infrastructure",
        "address": "Estero Bay Village, Estero FL",
        "description": "Septic to sewer conversion zone.",
        "latitude": 26.440800, "longitude": -81.822500,
    },
    {
        "location_id": 3, "project_id": 2,
        "location_name": "Sunny Grove Septic Area",
        "location_type": "Infrastructure",
        "address": "Sunny Grove, Estero FL",
        "description": "Septic to sewer conversion zone.",
        "latitude": 26.437200, "longitude": -81.825100,
    },
    {
        "location_id": 4, "project_id": 2,
        "location_name": "Cypress Bend Septic Area",
        "location_type": "Infrastructure",
        "address": "Cypress Bend, Estero FL",
        "description": "Septic to sewer conversion zone.",
        "latitude": 26.435500, "longitude": -81.820300,
    },
    {
        "location_id": 5, "project_id": 3,
        "location_name": "Corkscrew Road Corridor",
        "location_type": "Road",
        "address": "Corkscrew Road, Estero FL",
        "description": "Corkscrew Road widening corridor.",
        "latitude": 26.438600, "longitude": -81.808400,
    },
    {
        "location_id": 6, "project_id": 4,
        "location_name": "Village of Estero Council Chambers",
        "location_type": "Infrastructure",
        "address": "9401 Corkscrew Palms Blvd, Estero FL 33928",
        "description": "Primary meeting location for Village Council and PZ&DB.",
        "latitude": 26.436100, "longitude": -81.806200,
    },
]

ROAD_GEOMETRIES: dict[int, list[list[float]]] = {
    # BERT Trail: rough centerline from south to north through Estero
    1: [
        [-81.8200, 26.4200], [-81.8185, 26.4250], [-81.8170, 26.4300],
        [-81.8157, 26.4339], [-81.8145, 26.4380], [-81.8130, 26.4420],
    ],
    # Corkscrew Road: east-west corridor
    5: [
        [-81.8300, 26.4386], [-81.8200, 26.4386], [-81.8100, 26.4386],
        [-81.8000, 26.4386], [-81.7900, 26.4386],
    ],
}

AREA_GEOMETRIES: dict[int, list[list[list[float]]]] = {}


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------

def _null(value: str) -> Optional[str]:
    """Return None for empty or 'null' strings."""
    v = value.strip()
    return None if v in ("", "null", "NULL", "None") else v


def _parse_date(value: str) -> Optional[date]:
    v = _null(value)
    if v is None:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _parse_int(value: str) -> Optional[int]:
    v = _null(value)
    if v is None:
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _load_meetings() -> list[dict]:
    path = _DATA_DIR / "meetings.csv"
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "meeting_id":               _parse_int(row["meeting_id"]),
                "project_id":               _parse_int(row["project_id"]),
                "type_id":                  _parse_int(row["type_id"]),
                "meeting_date":             _parse_date(row["meeting_date"]),
                "meeting_year":             _parse_int(row["meeting_year"]),
                "location":                 _null(row.get("location", "")),
                "start_time":               _null(row.get("start_time", "")),
                "end_time":                 _null(row.get("end_time", "")),
                "action_taken":             _null(row.get("action_taken", "")),
                "status":                   _null(row.get("status", "")) or "Accepted",
                "approved_by_council_date": _parse_date(row.get("approved_by_council_date", "")),
                "doc_ref_code":             _null(row.get("doc_ref_code", "")),
                "filename":                 _null(row.get("filename", "")),
                "notes":                    _null(row.get("notes", "")),
                "location_id":              _parse_int(row.get("location_id", "")),
            })
    return rows


def _load_documents() -> list[dict]:
    path = _DATA_DIR / "documents.csv"
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "document_id":   _parse_int(row["document_id"]),
                "meeting_id":    _parse_int(row["meeting_id"]),
                "title":         _null(row.get("title", "")) or "Untitled",
                "document_type": None,
                "file_name":     None,
                "file_url":      _null(row.get("file_url", "")),
                "upload_date":   _parse_date(row.get("doc_date", "")),
                "notes":         None,
                "doc_date":      _parse_date(row.get("doc_date", "")),
                "link_status":   _null(row.get("link_status", "")),
            })
    return rows


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class CSVStore:
    """
    Data access interface backed by CSV files and structured location data.

    Drop-in replacement for MockStore — all routers and services call
    the same methods with no changes required.
    """

    def __init__(self) -> None:
        self._meetings  = _load_meetings()
        self._documents = _load_documents()

    def get_projects(self, status: Optional[str] = None) -> list[dict]:
        rows = deepcopy(PROJECTS)
        if status:
            rows = [r for r in rows if r["status"] == status]
        return rows

    def get_project(self, project_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in PROJECTS if r["project_id"] == project_id), None)

    def get_meeting_types(self) -> list[dict]:
        return deepcopy(MEETING_TYPES)

    def get_meeting_type(self, type_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in MEETING_TYPES if r["type_id"] == type_id), None)

    def get_meetings(
        self,
        project_id: Optional[int] = None,
        year: Optional[int] = None,
        status: Optional[str] = None,
        type_id: Optional[int] = None,
        location_id: Optional[int] = None,
    ) -> list[dict]:
        rows = deepcopy(self._meetings)
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        if year is not None:
            rows = [r for r in rows if r["meeting_year"] == year]
        if status:
            rows = [r for r in rows if r["status"] == status]
        if type_id is not None:
            rows = [r for r in rows if r["type_id"] == type_id]
        if location_id is not None:
            rows = [r for r in rows if r.get("location_id") == location_id]
        return rows

    def get_meeting(self, meeting_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in self._meetings if r["meeting_id"] == meeting_id), None)

    def get_locations(
        self,
        project_id: Optional[int] = None,
        location_type: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(LOCATIONS)
        if project_id is not None:
            rows = [r for r in rows if r["project_id"] == project_id]
        if location_type:
            rows = [r for r in rows if r["location_type"] == location_type]
        return rows

    def get_location(self, location_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in LOCATIONS if r["location_id"] == location_id), None)

    def get_documents(
        self,
        meeting_id: Optional[int] = None,
        document_type: Optional[str] = None,
    ) -> list[dict]:
        rows = deepcopy(self._documents)
        if meeting_id is not None:
            rows = [r for r in rows if r["meeting_id"] == meeting_id]
        if document_type:
            rows = [r for r in rows if r["document_type"] == document_type]
        return rows

    def get_document(self, document_id: int) -> Optional[dict]:
        return next((deepcopy(r) for r in self._documents if r["document_id"] == document_id), None)

    def get_road_geometry(self, location_id: int) -> Optional[list[list[float]]]:
        return ROAD_GEOMETRIES.get(location_id)

    def get_area_geometry(self, location_id: int) -> Optional[list[list[list[float]]]]:
        return AREA_GEOMETRIES.get(location_id)
