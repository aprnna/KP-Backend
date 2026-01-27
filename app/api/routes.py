from fastapi import APIRouter
from app.core.schema import BaseResponse, create_success_response

router = APIRouter(prefix="/api", tags=["api"])

@router.get("/ping", response_model=BaseResponse)
async def ping():
    return create_success_response(message="Ping successful", data="Pong!")
