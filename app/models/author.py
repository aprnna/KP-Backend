"""
Author ORM model.
"""

from typing import List, Optional
from sqlalchemy import Integer, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.database import Base


class Author(Base):
    """
    ORM model for the `authors` table.
    Represents a faculty member / researcher whose publications are scraped.
    Bibliometric stats (Google Scholar, Scopus) are populated by the scraping pipeline.
    """

    __tablename__ = "authors"

    id_sinta: Mapped[int] = mapped_column(Integer, primary_key=True)
    fullname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    nidn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    degree: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    major: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    faculty: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sinta_score_overall: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sinta_score_3yr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    affil_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    affil_score_3yr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    subject_research: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scopus bibliometric stats
    s_article_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_citation_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_cited_document_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_hindex_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_i10_index_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_gindex_scopus: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Google Scholar / OpenAlex bibliometric stats (updated by scraping pipeline)
    s_article_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_citation_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_cited_document_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_hindex_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_i10_index_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    s_gindex_gscholar: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Normalized fullname used for reliable DB matching (strip_titles applied)
    _fullname_norm: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    articles: Mapped[List["Article"]] = relationship(
        "Article", secondary="author_article", back_populates="authors_rel"
    )
