"""
SINTA Articles API routes.
Endpoints for retrieving SINTA articles from the database.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.sinta_article import SintaArticle
from app.api.schemas import SintaArticleResponse


logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "",
    response_model=list[SintaArticleResponse],
    summary="List SINTA Articles",
    description="Get a list of all scraped SINTA articles."
)
async def list_sinta_articles(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=1000, description="Items per page"),
    sinta_id: Optional[int] = Query(None, description="Filter by SINTA Author ID"),
    db: AsyncSession = Depends(get_db),
):
    """
    List all SINTA articles.
    """
    offset = (page - 1) * size
    query = select(SintaArticle)
    if sinta_id is not None:
        query = query.where(SintaArticle.id_sinta == sinta_id)
        
    query = query.limit(size).offset(offset)
    result = await db.execute(query)
    articles = result.scalars().all()
    
    return articles
