"""
Security utilities for API authentication.
"""

from fastapi import HTTPException, Header, status
from app.core.config import settings


async def verify_api_key(x_api_key: str = Header(..., description="API Key for authentication")):
    """
    Dependency to verify API key from request header.
    
    Usage:
        @router.post("/protected")
        async def protected_route(api_key: str = Depends(verify_api_key)):
            ...
    
    Raises:
        HTTPException: 401 if API key is missing or invalid
    """
    if not settings.api_key:
        # If no API key is configured, skip validation (development mode)
        return x_api_key
    
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return x_api_key


def is_api_key_configured() -> bool:
    """Check if API key protection is enabled."""
    return bool(settings.api_key)
