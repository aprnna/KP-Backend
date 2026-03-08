"""
Pydantic schemas for API requests and responses.
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, field_validator
from enum import Enum


# ============================================
# Enums
# ============================================

class JobStatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


class JobSourceEnum(str, Enum):
    CROSSREF = "crossref"
    OPENALEX = "openalex"
    BOTH = "both"


# ============================================
# Request Schemas
# ============================================

class ScrapeRequest(BaseModel):
    """Request body for triggering a scrape job."""
    source: JobSourceEnum = Field(
        default=JobSourceEnum.BOTH,
        description="Data source to scrape from"
    )
    year_start: Optional[int] = Field(
        default=None,
        description="Start year for scraping (inclusive)",
        ge=1900,
        le=2100
    )
    year_end: Optional[int] = Field(
        default=None,
        description="End year for scraping (inclusive)",
        ge=1900,
        le=2100
    )
    authors: Optional[List[str]] = Field(
        default=None,
        max_length=500,
        description="List of author names to scrape (max 500). If not provided, uses default list."
    )
    filter_unikom: Optional[bool] = Field(
        default=None,
        description="Filter for UNIKOM affiliation (Crossref only)"
    )

    @field_validator("authors", mode="before")
    @classmethod
    def authors_must_not_contain_blanks(cls, v):
        if v is None:
            return v
        cleaned = [a.strip() for a in v if isinstance(a, str)]
        invalid = [a for a in cleaned if not a]
        if invalid:
            raise ValueError("authors list must not contain empty or blank strings")
        return cleaned

    class Config:
        json_schema_extra = {
            "example": {
                "source": "both",
                "year_start": 2021,
                "year_end": 2024,
                "authors": ["John Doe", "Jane Smith"],
                "filter_unikom": False
            }
        }


# ============================================
# Response Schemas
# ============================================

class ScrapeResponse(BaseModel):
    """Response after triggering a scrape job."""
    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatusEnum = Field(..., description="Current job status")
    message: str = Field(..., description="Status message")
    created_at: datetime = Field(..., description="Job creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "message": "Scraping job created successfully",
                "created_at": "2024-01-15T10:30:00Z"
            }
        }


class JobLogSchema(BaseModel):
    """Schema for job log entries."""
    id: int
    level: str
    message: str
    extra_data: Optional[Dict[str, Any]] = None
    created_at: datetime


class JobSchema(BaseModel):
    """Schema for job details."""
    job_id: str
    source: JobSourceEnum
    status: JobStatusEnum
    total_records: int
    processed_records: int
    progress_percentage: float
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "job_id": "550e8400-e29b-41d4-a716-446655440000",
                "source": "both",
                "status": "running",
                "total_records": 100,
                "processed_records": 45,
                "progress_percentage": 45.0,
                "created_at": "2024-01-15T10:30:00Z",
                "started_at": "2024-01-15T10:30:01Z",
                "finished_at": None,
                "duration_seconds": 120.5,
                "error_message": None,
                "parameters": {"year_start": 2021, "year_end": 2024}
            }
        }


class JobDetailResponse(BaseModel):
    """Detailed job response with logs."""
    job: JobSchema
    logs: List[JobLogSchema] = Field(default_factory=list)


class JobListResponse(BaseModel):
    """Response for job listing."""
    jobs: List[JobSchema]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment")
    database: str = Field(..., description="Database connection status")
    scheduler: Dict[str, Any] = Field(..., description="Scheduler status")
    timestamp: datetime = Field(..., description="Current server time")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "version": "1.0.0",
                "environment": "development",
                "database": "connected",
                "scheduler": {
                    "enabled": True,
                    "running": True,
                    "next_run": "2024-02-01T02:00:00Z"
                },
                "timestamp": "2024-01-15T10:30:00Z"
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[Any] = Field(None, description="Additional error details")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "ValidationError",
                "message": "Invalid request parameters",
                "detail": {"year_start": "must be less than year_end"}
            }
        }


# ============================================
# Domain Schemas
# ============================================

class ArticleSchema(BaseModel):
    """Schema for article details."""
    id_article: int
    id_sinta: Optional[int] = None
    doi: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    journal_title: Optional[str] = None
    short_journal_title: Optional[str] = None
    publisher: Optional[str] = None
    issue: Optional[str] = None
    volume: Optional[str] = None
    page: Optional[str] = None
    published: Optional[str] = None
    type: Optional[str] = None
    pdf_link: Optional[str] = None
    issn: Optional[str] = None
    issn_type: Optional[str] = None
    indexed_date_time: Optional[str] = None
    indexed_date_parts: Optional[str] = None
    url: Optional[str] = None

    class Config:
        from_attributes = True


class AuthorSchema(BaseModel):
    """Schema for author details."""
    fullname: Optional[str] = None
    id_sinta: int
    nidn: Optional[str] = None
    degree: Optional[str] = None
    major: Optional[str] = None
    faculty: Optional[str] = None
    sinta_score_overall: Optional[int] = None
    sinta_score_3yr: Optional[int] = None
    affil_score: Optional[int] = None
    affil_score_3yr: Optional[int] = None
    subject_research: Optional[str] = None
    s_article_scopus: Optional[int] = None
    s_citation_scopus: Optional[int] = None
    s_cited_document_scopus: Optional[int] = None
    s_hindex_scopus: Optional[int] = None
    s_i10_index_scopus: Optional[int] = None
    s_gindex_scopus: Optional[int] = None
    s_article_gscholar: Optional[int] = None
    s_citation_gscholar: Optional[int] = None
    s_cited_document_gscholar: Optional[int] = None
    s_hindex_gscholar: Optional[int] = None
    s_i10_index_gscholar: Optional[int] = None
    s_gindex_gscholar: Optional[int] = None
    _fullname_norm: Optional[str] = None

    articles: List[ArticleSchema] = []

    class Config:
        from_attributes = True
