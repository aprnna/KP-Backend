from sqlalchemy import Column, Integer, Text, ForeignKey
from app.core.database import Base
from sqlalchemy.orm import relationship

class Article(Base):
    __tablename__ = "articles"

    id_article = Column(Integer, primary_key=True)
    id_sinta = Column(Integer, nullable=True)
    doi = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    authors = Column(Text, nullable=True)
    journal_title = Column(Text, nullable=True)
    short_journal_title = Column(Text, nullable=True)
    publisher = Column(Text, nullable=True)
    issue = Column(Text, nullable=True)
    volume = Column(Text, nullable=True)
    page = Column(Text, nullable=True)
    published = Column(Text, nullable=True)
    type = Column(Text, nullable=True)
    pdf_link = Column(Text, nullable=True)
    issn = Column(Text, nullable=True)
    issn_type = Column(Text, nullable=True)
    indexed_date_time = Column(Text, nullable=True)
    indexed_date_parts = Column(Text, nullable=True)
    url = Column(Text, nullable=True)

    authors_rel = relationship("Author", secondary="author_article", back_populates="articles")

class AuthorArticle(Base):
    __tablename__ = "author_article"

    id_sinta = Column(Integer, ForeignKey("authors.id_sinta"), primary_key=True)
    id_article = Column(Integer, ForeignKey("articles.id_article"), primary_key=True)
