"""
Reference data loader.

Reads YAML files in app/data/reference/ and exposes them as plain dicts/lists.
A small in-memory cache avoids re-reading files on every call. Call
``reload()`` after editing a YAML file in tests or notebooks.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.pipeline import config


def _read_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache(maxsize=1)
def projects() -> list[dict]:
    return list(_read_yaml(config.REF_PROJECTS) or [])


@lru_cache(maxsize=1)
def meeting_types() -> list[dict]:
    return list(_read_yaml(config.REF_MEETING_TYPES) or [])


@lru_cache(maxsize=1)
def locations() -> list[dict]:
    return list(_read_yaml(config.REF_LOCATIONS) or [])


@lru_cache(maxsize=1)
def geometries() -> dict:
    raw = _read_yaml(config.REF_GEOMETRIES) or {}
    return {
        "road_geometries": {int(k): v for k, v in (raw.get("road_geometries") or {}).items()},
        "area_geometries": {int(k): v for k, v in (raw.get("area_geometries") or {}).items()},
    }


def project_ids() -> set[int]:
    return {p["project_id"] for p in projects()}


def meeting_type_ids() -> set[int]:
    return {t["type_id"] for t in meeting_types()}


def location_ids() -> set[int]:
    return {loc["location_id"] for loc in locations()}


def reload() -> None:
    """Drop cached reference data; the next access re-reads from disk."""
    projects.cache_clear()
    meeting_types.cache_clear()
    locations.cache_clear()
    geometries.cache_clear()
