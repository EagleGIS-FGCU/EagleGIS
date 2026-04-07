from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import export, feature_service

app = FastAPI(
    title=settings.app_name,
    description=(
        "Serves live CSV exports from Supabase for ArcGIS geocoding. "
        "Data updates in Supabase are reflected immediately on the next request."
    ),
    version=settings.app_version,
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

app.include_router(export.router, prefix=settings.api_v1_prefix)
app.include_router(feature_service.router)


@app.get("/", tags=["System"], include_in_schema=False)
def root():
    return {
        "api": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "export": {
            "locations_csv": f"{settings.api_v1_prefix}/export/locations.csv",
        },
    }


@app.get("/health", tags=["System"], summary="Health check")
def health():
    return {"status": "ok"}
