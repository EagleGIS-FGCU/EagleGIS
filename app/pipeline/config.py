"""
Single source of truth for pipeline filesystem paths.

Importing this module is cheap; nothing here touches disk.
"""
from __future__ import annotations

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BRONZE_DIR = DATA_DIR
REFERENCE_DIR = DATA_DIR / "reference"
SILVER_DIR = DATA_DIR / "silver"
RUNS_DIR = DATA_DIR / "runs"

BRONZE_MEETINGS = BRONZE_DIR / "meetings.csv"
BRONZE_DOCUMENTS = BRONZE_DIR / "documents.csv"

SILVER_MEETINGS = SILVER_DIR / "meetings.csv"
SILVER_DOCUMENTS = SILVER_DIR / "documents.csv"
SILVER_DOCUMENTS_PLANNED = SILVER_DIR / "documents_planned.csv"
SILVER_REJECTS = SILVER_DIR / "_rejects.json"

REF_PROJECTS = REFERENCE_DIR / "projects.yaml"
REF_MEETING_TYPES = REFERENCE_DIR / "meeting_types.yaml"
REF_LOCATIONS = REFERENCE_DIR / "locations.yaml"
REF_GEOMETRIES = REFERENCE_DIR / "geometries.yaml"

ESTERO_BBOX = {
    "min_lat": 26.30,
    "max_lat": 26.55,
    "min_lon": -81.95,
    "max_lon": -81.65,
}

FUTURE_PLACEHOLDER_TAG = "Future Placeholder"
