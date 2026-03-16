"""
SINTA Authors API routes.
Endpoints for retrieving SINTA authors from the database.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.sinta_author import SintaAuthor
from app.api.schemas import SintaAuthorResponse


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=list[SintaAuthorResponse],
    summary="List SINTA Authors",
    description="Get a list of all scraped SINTA authors."
)
async def list_sinta_authors(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=1000, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all SINTA authors.
    """
    offset = (page - 1) * size
    query = select(SintaAuthor).limit(size).offset(offset)
    result = await db.execute(query)
    authors = result.scalars().all()
    
    return authors
