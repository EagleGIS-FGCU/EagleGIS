"""
GIS layer endpoints — each returns a GeoJSON FeatureCollection.

Add these as GeoJSON Feature Layers in ArcGIS Online:
  Map Viewer → Add → Add layer from URL → paste the full endpoint URL.

ArcGIS will poll the URL and render the features using its default renderer.
You can then configure symbology, popups, and labeling in Map Viewer.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from app.data.mock import MockStore
from app.dependencies import get_store
from app.models.geojson import GeoJSONFeatureCollection
from app.services.geojson import build_area_layer, build_point_layer, build_road_layer

router = APIRouter(prefix="/layers", tags=["GIS Layers"])

_GEO_MEDIA = "application/json"


@router.get(
    "/points",
    response_model=GeoJSONFeatureCollection,
    summary="Point layer — all project locations",
    description=(
        "Returns every project location as a GeoJSON **Point** feature. "
        "Properties include project name/status and a meeting summary suitable "
        "for ArcGIS pop-up configuration."
    ),
)
def get_point_layer(
    project_id: Optional[int] = Query(None, description="Restrict to a single project"),
    store: MockStore = Depends(get_store),
):
    fc = build_point_layer(store, project_id=project_id)
    return Response(content=fc.model_dump_json(), media_type=_GEO_MEDIA)


@router.get(
    "/roads",
    response_model=GeoJSONFeatureCollection,
    summary="Road & trail layer — LineString features",
    description=(
        "Returns Road and Trail locations as GeoJSON **LineString** features. "
        "Geometry represents the project corridor centerline."
    ),
)
def get_road_layer(
    project_id: Optional[int] = Query(None),
    store: MockStore = Depends(get_store),
):
    fc = build_road_layer(store, project_id=project_id)
    return Response(content=fc.model_dump_json(), media_type=_GEO_MEDIA)


@router.get(
    "/areas",
    response_model=GeoJSONFeatureCollection,
    summary="Area layer — Polygon features",
    description=(
        "Returns Park and Development locations as GeoJSON **Polygon** features. "
        "Geometry represents the approximate project boundary."
    ),
)
def get_area_layer(
    project_id: Optional[int] = Query(None),
    store: MockStore = Depends(get_store),
):
    fc = build_area_layer(store, project_id=project_id)
    return Response(content=fc.model_dump_json(), media_type=_GEO_MEDIA)
