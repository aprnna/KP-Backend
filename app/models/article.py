"""
Article and AuthorArticle ORM models.
"""

from typing import List, Optional
from sqlalchemy import Integer, Text, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column

from app.core.database import Base


class Article(Base):
    """
    ORM model for the `articles` table.
    Stores publication metadata scraped from Crossref.
    Each article may be linked to one or more Authors via the AuthorArticle join table.
    """

    __tablename__ = "articles"

    id_article: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_sinta: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    short_journal_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    volume: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    page: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pdf_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issn: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issn_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    indexed_date_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    indexed_date_parts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    authors_rel: Mapped[List["Author"]] = relationship(
        "Author", secondary="author_article", back_populates="articles"
    )


class AuthorArticle(Base):
    """
    ORM model for the `author_article` join table.
    Links Author records to Article records (many-to-many).
    """

    __tablename__ = "author_article"

    id_sinta: Mapped[int] = mapped_column(
        Integer, ForeignKey("authors.id_sinta"), primary_key=True
    )
    id_article: Mapped[int] = mapped_column(
        Integer, ForeignKey("articles.id_article"), primary_key=True
    )
