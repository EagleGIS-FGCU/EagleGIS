"""
Supabase client singleton.
Reads SUPABASE_URL and SUPABASE_KEY from environment variables.
Set these in Railway → Variables before deploying.
"""
from functools import lru_cache
from supabase import create_client, Client
from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY environment variables must be set."
        )
    return create_client(settings.supabase_url, settings.supabase_key)
