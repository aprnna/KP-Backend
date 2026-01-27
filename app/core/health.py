from fastapi import APIRouter
from app.core.schema import BaseResponse

from app.services.health import health as health_service

router = APIRouter()

@router.get("/health", tags=["health"], response_model=BaseResponse)
async def health():
    return health_service()
