"""
Scraping Job and Log models for tracking scraping operations.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Integer, String, Text, DateTime, Enum, JSON, ForeignKey
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
import enum

from app.core.database import Base


class JobStatus(str, enum.Enum):
    """Status of a scraping job"""
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class JobSource(str, enum.Enum):
    """Source of data for scraping"""
    SINTA_ARTICLES = "sinta_articles"
    SINTA_AUTHORS = "sinta_authors"
    BOTH = "both"


class LogLevel(str, enum.Enum):
    """Log level for scraping logs"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ScrapingJob(Base):
    """
    Model for tracking scraping jobs.
    Each job represents a single scraping operation (manual or scheduled).
    """
    __tablename__ = "scraping_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        Enum(JobSource, values_callable=lambda x: [e.value for e in x]), 
        nullable=False,
        default=JobSource.BOTH
    )
    status: Mapped[str] = mapped_column(
        Enum(JobStatus, values_callable=lambda x: [e.value for e in x]), 
        nullable=False, 
        default=JobStatus.PENDING,
        index=True
    )
    
    # Progress tracking
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    processed_records: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow,
        index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Error handling
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Job parameters (stored as JSON)
    parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    
    # Relationships
    logs: Mapped[List["ScrapingLog"]] = relationship(
        "ScrapingLog", 
        back_populates="job",
        cascade="all, delete-orphan"
    )
    raw_responses: Mapped[List["RawResponse"]] = relationship(
        "RawResponse",
        back_populates="job",
        cascade="all, delete-orphan"
    )

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage"""
        if self.total_records == 0:
            return 0.0
        return (self.processed_records / self.total_records) * 100

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds"""
        if not self.started_at:
            return None
        end_time = self.finished_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()

    def __repr__(self) -> str:
        return f"<ScrapingJob(job_id={self.job_id}, status={self.status}, progress={self.progress_percentage:.1f}%)>"


class ScrapingLog(Base):
    """
    Model for storing scraping logs.
    Each log entry is associated with a scraping job.
    """
    __tablename__ = "scraping_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("scraping_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    level: Mapped[str] = mapped_column(
        Enum(LogLevel, values_callable=lambda x: [e.value for e in x]),
        default=LogLevel.INFO
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    job: Mapped["ScrapingJob"] = relationship("ScrapingJob", back_populates="logs")

    def __repr__(self) -> str:
        return f"<ScrapingLog(level={self.level}, message={self.message[:50]}...)>"


# Import RawResponse here to avoid circular import
from app.models.raw_response import RawResponse  # noqa: E402, F401
