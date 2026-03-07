from sqlalchemy import Column, Integer, Text, ForeignKey
from app.core.database import Base
from sqlalchemy.orm import relationship

class Article(Base):
    __tablename__ = "articles"

    id_article = Column(Integer, primary_key=True)
    id_sinta = Column(Integer, nullable=True)
    source = Column(Text, nullable=True)
    article_title = Column(Text, nullable=True)
    author = Column(Text, nullable=True)
    authors = Column(Text, nullable=True)
    publisher = Column(Text, nullable=True)
    year = Column(Text, nullable=True)
    cited = Column(Text, nullable=True)
    quartile = Column(Text, nullable=True)
    url = Column(Text, nullable=True)

    authors_rel = relationship("Author", secondary="author_article", back_populates="articles")

class AuthorArticle(Base):
    __tablename__ = "author_article"

    id_sinta = Column(Integer, ForeignKey("authors.id_sinta"), primary_key=True)
    id_article = Column(Integer, ForeignKey("articles.id_article"), primary_key=True)
