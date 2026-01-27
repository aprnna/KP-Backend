from typing import Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, JSON, func, Boolean, ForeignKey
from app.core.database import Base

class Work(Base):
    __tablename__ = "works"

    # Legacy Columns
    author_query = Column(String(255), nullable=True)
    doi = Column(String(255), nullable=True, unique=True, index=True)
    title = Column(Text, nullable=True)
    authors = Column(Text, nullable=True)
    container_title = Column(String(255), nullable=True)
    short_container_title = Column(String(255), nullable=True)
    publisher = Column(String(255), nullable=True)
    issue = Column(String(255), nullable=True)
    volume = Column(String(255), nullable=True)
    page = Column(String(255), nullable=True)
    published = Column(String(255), nullable=True)
    type = Column(String(255), nullable=True)
    source = Column(String(255), nullable=True)
    pdf_link = Column(Text, nullable=True)
    all_links = Column(Text, nullable=True)
    abstract = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    issn = Column(String(255), nullable=True)
    issn_type = Column(String(255), nullable=True)
    indexed_date_time = Column(String(255), nullable=True)
    indexed_date_parts = Column(String(255), nullable=True)
    url = Column(String(255), nullable=True)
    id_work = Column(String(255), primary_key=True)

    # New Columns for Scraper
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class AuthorWork(Base):
    __tablename__ = "author_works"

    id = Column(Integer, primary_key=True, autoincrement=True)
    id_author = Column(Integer, ForeignKey("authors.id_author", ondelete="CASCADE"), nullable=False)
    id_work = Column(String(255), ForeignKey("works.id_work", ondelete="CASCADE"), nullable=False)
    author_query = Column(String(500), nullable=True)
    is_corresponding = Column(Boolean, default=False)
