from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import get_settings

security = HTTPBearer()


async def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """Verify the Bearer token from the Authorization header."""
    settings = get_settings()

    if credentials.credentials != settings.bearer_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials
