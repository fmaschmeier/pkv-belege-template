"""
Supabase Client

Das Backend nutzt den service_role Key um RLS zu umgehen.
Die Authentifizierung erfolgt über verify_token() in auth.py.
"""
from functools import lru_cache
from typing import Any, Callable
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


def fetch_all(build_query: Callable[[], Any], page_size: int = 1000) -> list[dict]:
    """
    Liest alle Zeilen einer Abfrage, Seite für Seite.

    Supabase liefert je Anfrage höchstens so viele Zeilen, wie unter "Max rows" in den
    API-Einstellungen steht (Standard 1000), auch bei größerem limit(). Was darüber liegt,
    fehlt ohne Fehlermeldung.

    build_query muss die Abfrage bei jedem Aufruf neu bauen (z. B. lambda: sb.table("x").select("*")),
    weil range() die Parameter eines Builders ergänzt statt sie zu ersetzen. Die Abfrage selbst
    enthält kein limit() und kein range(). Zusätzlich wird nach id sortiert, damit sich die Seiten
    weder überschneiden noch Lücken lassen; eine eigene Sortierung der Abfrage bleibt vorrangig.
    Gelesen wird, bis eine Seite leer ist, damit auch ein kleineres "Max rows" nichts abschneidet.
    """
    rows: list[dict] = []
    while True:
        start = len(rows)
        chunk = build_query().order("id").range(start, start + page_size - 1).execute().data or []
        if not chunk:
            return rows
        rows.extend(chunk)
