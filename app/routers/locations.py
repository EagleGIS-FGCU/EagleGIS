from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app.data.mock import MockStore
from app.dependencies import get_store
from app.models.schemas import Location, LocationDetail, LocationType

router = APIRouter(prefix="/locations", tags=["Locations"])


@router.get("/", response_model=list[Location], summary="List project locations")
def list_locations(
    project_id: Optional[int] = Query(None, description="Filter by project"),
    location_type: Optional[LocationType] = Query(None, description="Filter by feature type"),
    store: MockStore = Depends(get_store),
):
    return store.get_locations(project_id=project_id, location_type=location_type)


@router.get("/{location_id}", response_model=LocationDetail, summary="Get a location with project name and meeting count")
def get_location(location_id: int, store: MockStore = Depends(get_store)):
    location = store.get_location(location_id)
    if not location:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")

    project = store.get_project(location["project_id"])
    loc_meetings = store.get_meetings(
        project_id=location["project_id"],
        location_id=location_id,
    )
    return {
        **location,
        "project_name": project["project_name"] if project else None,
        "meeting_count": len(loc_meetings),
    }
