"""
FastAPI Configuration
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API
    api_title: str = "Universa Doc Processor API"
    api_version: str = "1.0.0"
    debug: bool = False

    # Supabase
    supabase_url: str
    supabase_key: str  # anon key (für Frontend)
    supabase_service_key: str = ""  # service_role key (für Backend, umgeht RLS)
    supabase_jwt_secret: str = ""  # For JWT verification

    # API Authentication
    api_secret_key: str = ""  # For service-to-service calls

    # pdf.co
    pdfco_api_key: str = ""

    # Anthropic Claude API (for receipt parsing)
    anthropic_claude_api_key: str = ""
    anthropic_claude_model: str = "claude-sonnet-4-20250514"  # Model für Vision/Parsing

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        # Eigene Web-Adresse ergänzen, z. B. per Umgebungsvariable
        # CORS_ORIGINS='["http://localhost:5173", "https://<deine-web-app>.run.app"]'
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars like DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
