"""
SintaArticle ORM model — scraping database.
Stores articles scraped from SINTA per author (4 views).
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, Text, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SintaArticle(Base):
    """
    ORM model for the `sinta_articles` table in the scraping database.
    Each row is one article entry scraped from a specific SINTA profile view.
    """

    __tablename__ = "sinta_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Author link — references id_sinta in the main DB
    id_sinta: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # SINTA view source: scopus | garuda | googlescholar | rama
    source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Article metadata as scraped from SINTA HTML
    article_title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    cited: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    quartile: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp recorded when the row was scraped
    scraped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, default=datetime.utcnow
    )
