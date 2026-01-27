from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.core.database import Base

class Author(Base):
    __tablename__ = "authors"

    # Legacy Columns
    id_author = Column(Integer, primary_key=True, autoincrement=True)
    nidn = Column(String(255), nullable=True, index=True)
    nama = Column(String(255), nullable=True) # Added to match reference
    fullname = Column(String(255), nullable=True, index=True)
    academic_grade_raw = Column(String(255), nullable=True)
    academic_grade = Column(String(255), nullable=True)
    gelar_depan = Column(String(255), nullable=True)
    gelar_belakang = Column(String(255), nullable=True)
    last_education = Column(String(255), nullable=True)
    sinta_score_v2_overall = Column(Integer, nullable=True)
    sinta_score_v2_3year = Column(Integer, nullable=True)
    sinta_score_v3_overall = Column(Integer, nullable=True)
    sinta_score_v3_3year = Column(Integer, nullable=True)
    affiliation_score_v3_overall = Column(Integer, nullable=True)
    affiliation_score_v3_3year = Column(Integer, nullable=True)
    affiliation_id = Column(Integer, nullable=True)
    affiliation_code = Column(Integer, nullable=True)
    programs_code = Column(Integer, nullable=True)
    programs_level = Column(String(255), nullable=True)
    programs_name = Column(String(255), nullable=True)

    # New Columns for Scraper
    openalex_id = Column(String(255), unique=True, nullable=True, index=True)
    name = Column(String(500), nullable=True)
    orcid = Column(String(50), nullable=True)
    works_count = Column(Integer, default=0)
    cited_by_count = Column(Integer, default=0)
    h_index = Column(Float, default=0)
    i10_index = Column(Float, default=0)
    mean_citedness_2yr = Column(Float, default=0)
    relevance_score = Column(Float, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
