from sqlalchemy import Column, Integer, Text
from app.core.database import Base
from sqlalchemy.orm import relationship

class Author(Base):
    __tablename__ = "authors"

    id_sinta = Column(Integer, primary_key=True)

    nama = Column(Text, nullable=True)
    jurusan = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)

    scopus_hindex = Column(Integer, nullable=True)
    gs_hindex = Column(Integer, nullable=True)

    sinta_score = Column(Integer, nullable=True)
    sinta_score_3yr = Column(Integer, nullable=True)

    affil_score = Column(Integer, nullable=True)
    affil_score_3yr = Column(Integer, nullable=True)

    Q1 = Column(Integer, nullable=True)
    Q2 = Column(Integer, nullable=True)
    Q3 = Column(Integer, nullable=True)
    Q4 = Column(Integer, nullable=True)
    No_Q = Column(Integer, nullable=True)

    article_scopus = Column(Integer, nullable=True)
    article_gscholar = Column(Integer, nullable=True)

    citation_scopus = Column(Integer, nullable=True)
    citation_gscholar = Column(Integer, nullable=True)

    cited_document_scopus = Column(Integer, nullable=True)
    cited_document_gscholar = Column(Integer, nullable=True)

    h_index_scopus = Column(Integer, nullable=True)
    h_index_gscholar = Column(Integer, nullable=True)

    i10_index_scopus = Column(Integer, nullable=True)
    i10_index_gscholar = Column(Integer, nullable=True)

    g_index_scopus = Column(Integer, nullable=True)
    g_index_gscholar = Column(Integer, nullable=True)

    articles = relationship(
        "Article",
        secondary="author_article",
        back_populates="authors_rel"
    )
