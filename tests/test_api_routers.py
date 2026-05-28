"""
Smoke tests for the CSV/silver-backed read-API and GeoJSON GIS layers.

These build a fresh ``FastAPI()`` app that includes ONLY the six read
routers, deliberately avoiding ``app.main`` so the Supabase/db import path
is never touched. The tests are credential-free and fast.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import (
    documents,
    layers,
    locations,
    meeting_types,
    meetings,
    projects,
)


def _client() -> TestClient:
    app = FastAPI()
    for module in (meetings, projects, documents, meeting_types, locations, layers):
        app.include_router(module.router)
    return TestClient(app)


def test_list_endpoints_return_nonempty_lists():
    client = _client()
    for path in ("/meetings/", "/projects/", "/documents/", "/meeting-types/", "/locations/"):
        res = client.get(path)
        assert res.status_code == 200, f"{path} -> {res.status_code}"
        body = res.json()
        assert isinstance(body, list)
        assert len(body) > 0, f"{path} returned an empty list"


def test_project_detail_has_enriched_fields():
    client = _client()
    first = client.get("/projects/").json()[0]
    res = client.get(f"/projects/{first['project_id']}")
    assert res.status_code == 200
    detail = res.json()
    assert "meeting_count" in detail
    assert "location_count" in detail
    assert detail["project_id"] == first["project_id"]


def test_meeting_detail_has_documents_and_context():
    client = _client()
    first = client.get("/meetings/").json()[0]
    res = client.get(f"/meetings/{first['meeting_id']}")
    assert res.status_code == 200
    detail = res.json()
    assert "project_name" in detail
    assert "meeting_type_name" in detail
    assert "documents" in detail
    assert isinstance(detail["documents"], list)


def test_points_layer_is_geojson_with_features():
    client = _client()
    res = client.get("/layers/points")
    assert res.status_code == 200
    fc = res.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0
    props = fc["features"][0]["properties"]
    for key in ("project_name", "project_status", "meeting_count"):
        assert key in props


def test_roads_layer_has_at_least_two_linestrings():
    client = _client()
    res = client.get("/layers/roads")
    assert res.status_code == 200
    fc = res.json()
    assert fc["type"] == "FeatureCollection"
    line_features = [f for f in fc["features"] if f["geometry"]["type"] == "LineString"]
    assert len(line_features) >= 2
