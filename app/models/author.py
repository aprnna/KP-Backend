from sqlalchemy import Column, Integer, Text
from app.core.database import Base
from sqlalchemy.orm import relationship

class Author(Base):
    __tablename__ = "authors"

    fullname = Column(Text, nullable=True)
    id_sinta = Column(Integer, primary_key=True)
    nidn = Column(Text, nullable=True)
    profile_url = Column(Text, nullable=True)
    departemen = Column(Text, nullable=True)
    faculty = Column(Text, nullable=True)

    sinta_score_overall = Column(Integer, nullable=True)
    sinta_score_3yr = Column(Integer, nullable=True)
    affil_score = Column(Integer, nullable=True)
    affil_score_3yr = Column(Integer, nullable=True)
    subject_research = Column(Text, nullable=True)
    s_article_scopus = Column(Integer, nullable=True)
    s_citation_scopus = Column(Integer, nullable=True)
    s_cited_document_scopus = Column(Integer, nullable=True)
    s_hindex_scopus = Column(Integer, nullable=True)
    s_i10_index_scopus = Column(Integer, nullable=True)
    s_gindex_scopus = Column(Integer, nullable=True)
    s_article_gscholar = Column(Integer, nullable=True)
    s_citation_gscholar = Column(Integer, nullable=True)
    s_cited_document_gscholar = Column(Integer, nullable=True)
    s_hindex_gscholar = Column(Integer, nullable=True)
    s_i10_index_gscholar = Column(Integer, nullable=True)
    s_gindex_gscholar = Column(Integer, nullable=True)

    s_quartile_scopus_no_q = Column(Integer, nullable=True)
    s_quartile_scopus_q1 = Column(Integer, nullable=True)
    s_quartile_scopus_q2 = Column(Integer, nullable=True)
    s_quartile_scopus_q3 = Column(Integer, nullable=True)
    s_quartile_scopus_q4 = Column(Integer, nullable=True)

    articles = relationship("Article", secondary="author_article", back_populates="authors_rel")
