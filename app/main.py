from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    documents,
    layers,
    locations,
    meeting_types,
    meetings,
    projects,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pre-warm the store singleton on startup.
    # Replace this with DB pool initialisation when you connect to Supabase.
    from app.dependencies import get_store
    get_store()
    yield
    # Teardown: close DB connections here if needed.


app = FastAPI(
    title=settings.app_name,
    description=(
        "GIS-connected API for tracking Estero public meetings and infrastructure projects. "
        "Returns spatial data as GeoJSON for direct consumption as ArcGIS feature layers.\n\n"
        "**Layer endpoints** (`/api/v1/layers/*`) return `application/geo+json` FeatureCollections. "
        "Add them to ArcGIS Online via *Map Viewer → Add → Add layer from URL*."
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
_p = settings.api_v1_prefix

app.include_router(projects.router,      prefix=_p)
app.include_router(meeting_types.router, prefix=_p)
app.include_router(meetings.router,      prefix=_p)
app.include_router(locations.router,     prefix=_p)
app.include_router(documents.router,     prefix=_p)
app.include_router(layers.router,        prefix=_p)


# ---------------------------------------------------------------------------
# Root & health
# ---------------------------------------------------------------------------

@app.get("/", tags=["System"], include_in_schema=False)
def root():
    return {
        "api": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "layers": {
            "points": f"{_p}/layers/points",
            "roads":  f"{_p}/layers/roads",
            "areas":  f"{_p}/layers/areas",
        },
    }


@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok"}
