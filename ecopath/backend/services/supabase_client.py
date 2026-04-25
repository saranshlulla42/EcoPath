"""
EcoPath — Supabase Client Singleton
Uses service_role key for backend operations.
"""

from functools import lru_cache

from supabase import create_client, Client
from config import get_settings


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    settings = get_settings()
    client = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
    )
    return client


@lru_cache(maxsize=1)
def get_supabase_anon() -> Client:
    """Anon client for RLS-restricted reads."""
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
    )
