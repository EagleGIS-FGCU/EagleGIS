"""
CSV export endpoint for ArcGIS.

ArcGIS geocode tool workflow:
  1. Open ArcGIS Pro → Geocoding Tools → Geocode Addresses
  2. Use this URL as the input table source, or download the CSV and point to it
  3. Set Address Field to 'address', or use latitude/longitude fields directly

Endpoint:
  GET /export/locations.csv  — all locations joined with project info
"""
import csv
import io
from fastapi import APIRouter
from fastapi.responses import Response
from app.db import get_client

router = APIRouter(prefix="/export", tags=["Export"])


@router.get(
    "/locations.csv",
    summary="Export locations as CSV for ArcGIS geocoding",
    description=(
        "Returns all locations from Supabase as a CSV file. "
        "Includes address, coordinates, project name, and status. "
        "Use this URL in ArcGIS to geocode or plot locations live."
    ),
)
def export_locations_csv():
    client = get_client()

    rows = (
        client.table("locations")
        .select("location_id, location_name, location_type, address, description, latitude, longitude, projects(project_name, status)")
        .execute()
        .data
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "location_id",
        "location_name",
        "location_type",
        "address",
        "description",
        "latitude",
        "longitude",
        "project_name",
        "project_status",
    ])

    for row in rows:
        project = row.get("projects") or {}
        writer.writerow([
            row.get("location_id"),
            row.get("location_name"),
            row.get("location_type"),
            row.get("address"),
            row.get("description"),
            row.get("latitude"),
            row.get("longitude"),
            project.get("project_name"),
            project.get("status"),
        ])

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "inline; filename=locations.csv"},
    )
