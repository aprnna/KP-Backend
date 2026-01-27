"""
RawResponse model for storing raw API responses.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Integer, String, DateTime, JSON, ForeignKey
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.database import Base


class RawResponse(Base):
    """
    Model for storing raw API responses for debugging and reprocessing.
    Each response is associated with a scraping job.
    """
    __tablename__ = "raw_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("scraping_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # API source info
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Request and response data
    request_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    response_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Metadata
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    job: Mapped["ScrapingJob"] = relationship("ScrapingJob", back_populates="raw_responses")

    def __repr__(self) -> str:
        return f"<RawResponse(source={self.source}, endpoint={self.endpoint[:50]}...)>"


# Import ScrapingJob here to avoid circular import
from app.models.job import ScrapingJob  # noqa: E402, F401
