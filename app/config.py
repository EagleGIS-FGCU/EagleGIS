import os


class Settings:
    app_name: str = "EagleAPI"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Populated from .env when you connect to Supabase
    database_url: str = os.getenv("DATABASE_URL", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")

    # CORS — tighten this to your ArcGIS domain in production
    allowed_origins: list[str] = os.getenv("ALLOWED_ORIGINS", "*").split(",")


settings = Settings()
