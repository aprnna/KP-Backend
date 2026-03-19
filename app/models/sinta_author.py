"""
SintaAuthor ORM model — scraping database.
Stores author bibliometric stats scraped from SINTA profile pages.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SintaAuthor(Base):
    """
    ORM model for the `sinta_authors` table in the scraping database.
    Each row mirrors all bibliometric data that can be scraped from one
    SINTA author profile. Upserted on every scraping run.
    """

    __tablename__ = "sinta_authors"

    id_sinta: Mapped[int] = mapped_column(Integer, primary_key=True)
    fullname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    major: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    degree: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    faculty: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # SINTA scores from affiliation list page
    sinta_score_overall: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sinta_score_3yr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    affil_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    affil_score_3yr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Scopus bibliometric stats from detail profile page
    s_article_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_citation_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_cited_document_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_hindex_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_i10_index_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_gindex_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Google Scholar bibliometric stats from detail profile page
    s_article_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_citation_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_cited_document_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_hindex_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_i10_index_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_gindex_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Research subjects (semicolon-separated list)
    subject_research: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp recorded when the row was last scraped
    scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, default=datetime.utcnow
    )
