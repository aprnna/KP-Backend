from sqlalchemy import Column, Integer, Text, ForeignKey
from app.core.database import Base
from sqlalchemy.orm import relationship

class Article(Base):
    __tablename__ = "articles"

    id_article = Column(Integer, primary_key=True)
    id_sinta = Column(Integer, nullable=True)

    title = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    tahun = Column(Integer, nullable=True)
    quartile_jurnal = Column(Text, nullable=True)
    nama_jurnal = Column(Text, nullable=True)

    author_order = Column(Text, nullable=True)
    creator_leader = Column(Text, nullable=True)

    jumlah_cited = Column(Integer, nullable=True)
    source_view = Column(Text, nullable=True)

    penerbit_publisher = Column(Text, nullable=True)

    authors = Column(Text, nullable=True)

    pendanaan = Column(Text, nullable=True)
    status = Column(Text, nullable=True)
    pendanaan_dari = Column(Text, nullable=True)

    nomor_permohonan = Column(Text, nullable=True)
    hak = Column(Text, nullable=True)
    category = Column(Text, nullable=True)

    kota = Column(Text, nullable=True)
    isbn = Column(Text, nullable=True)
    institusi = Column(Text, nullable=True)

    doi = Column(Text, nullable=True)

    authors_rel = relationship(
        "Author",
        secondary="author_article",
        back_populates="articles"
    )


class AuthorArticle(Base):
    __tablename__ = "author_article"

    id_sinta = Column(
        Integer,
        ForeignKey("authors.id_sinta"),
        primary_key=True
    )

    id_article = Column(
        Integer,
        ForeignKey("articles.id_article"),
        primary_key=True
    )
