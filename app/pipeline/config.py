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
SILVER_MEETING_ACTIONS = SILVER_DIR / "meeting_actions.csv"
SILVER_REJECTS = SILVER_DIR / "_rejects.json"

GOLD_DIR = DATA_DIR / "gold"
GOLD_MEETINGS_PUBLIC = GOLD_DIR / "meetings_public.csv"
GOLD_MEETING_ACTIONS_PUBLIC = GOLD_DIR / "meeting_actions_public.csv"

MINUTES_INDEX = DATA_DIR / "minutes_index.json"

REF_PROJECTS = REFERENCE_DIR / "projects.yaml"
REF_MEETING_TYPES = REFERENCE_DIR / "meeting_types.yaml"
REF_LOCATIONS = REFERENCE_DIR / "locations.yaml"
REF_GEOMETRIES = REFERENCE_DIR / "geometries.yaml"

# Cache of geocoder responses keyed by query address (see app/pipeline/enrich/geocode.py).
GEOCODE_CACHE = REFERENCE_DIR / "geocode_cache.json"

ESTERO_BBOX = {
    "min_lat": 26.30,
    "max_lat": 26.55,
    "min_lon": -81.95,
    "max_lon": -81.65,
}

FUTURE_PLACEHOLDER_TAG = "Future Placeholder"
