"""
Supabase Client

Das Backend nutzt den service_role Key um RLS zu umgehen.
Die Authentifizierung erfolgt über verify_token() in auth.py.
"""
from functools import lru_cache
from supabase import create_client, Client
from .config import get_settings


@lru_cache
def get_supabase() -> Client:
    """
    Get cached Supabase client with service_role key.

    Der service_role Key umgeht Row Level Security (RLS).
    Die User-Authentifizierung erfolgt separat über JWT-Verification.

    Falls kein service_key konfiguriert ist, fällt es auf den anon key zurück.
    """
    settings = get_settings()

    # Bevorzuge service_role key (umgeht RLS)
    key = settings.supabase_service_key or settings.supabase_key

    return create_client(settings.supabase_url, key)
