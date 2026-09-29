from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # API Authentication
    bearer_token: str

    # Universa Credentials
    universa_username: str
    universa_password: str

    # Session Settings
    session_timeout_seconds: int = 300

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
