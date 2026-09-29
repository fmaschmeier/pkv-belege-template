"""
Authentication - Supabase Auth Verification
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import requests
from typing import Optional

from .config import get_settings
from .database import get_supabase

security = HTTPBearer()


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    Verify Supabase JWT token via Supabase Auth API.
    Returns the decoded token payload with user info.
    """
    token = credentials.credentials
    settings = get_settings()

    # Verify token via Supabase Auth API
    try:
        response = requests.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_key,
            },
            timeout=10,
        )

        if response.status_code == 200:
            user_data = response.json()
            return {
                "sub": user_data.get("id"),
                "email": user_data.get("email"),
                "role": user_data.get("role", "authenticated"),
                "user": user_data,
            }
        elif response.status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token ungültig oder abgelaufen",
                headers={"WWW-Authenticate": "Bearer"},
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Auth-Fehler: {response.status_code}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except requests.RequestException as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Auth-Service nicht erreichbar: {str(e)}",
        )


def get_current_user(token_data: dict = Depends(verify_token)) -> dict:
    """Get current user from token."""
    user_id = token_data.get("sub")
    email = token_data.get("email")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID nicht im Token",
        )

    return {
        "id": user_id,
        "email": email,
        "role": token_data.get("role", "authenticated"),
    }


# Optional: API Key authentication for service-to-service calls
async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """
    Verify API key for service calls.
    Use this for automated imports etc.
    """
    settings = get_settings()

    if credentials.credentials == settings.api_secret_key:
        return True

    # Fall back to JWT verification
    verify_token(credentials)
    return True
