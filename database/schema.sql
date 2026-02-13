-- TABLE: authors
CREATE TABLE IF NOT EXISTS authors (
    fullname TEXT,
    id_sinta INTEGER PRIMARY KEY,
    nidn TEXT,
    degree TEXT,
    major TEXT,
    faculty TEXT,
    sinta_score_overall INTEGER,
    sinta_score_3yr INTEGER,
    affil_score INTEGER,
    affil_score_3yr INTEGER,
    subject_research TEXT,
    s_article_scopus INTEGER,
    s_citation_scopus INTEGER,
    s_cited_document_scopus INTEGER,
    s_hindex_scopus INTEGER,
    s_i10_index_scopus INTEGER,
    s_gindex_scopus INTEGER,
    s_article_gscholar INTEGER,
    s_citation_gscholar INTEGER,
    s_cited_document_gscholar INTEGER,
    s_hindex_gscholar INTEGER,
    s_i10_index_gscholar INTEGER,
    s_gindex_gscholar INTEGER,
    _fullname_norm TEXT
);

-- TABLE: articles
CREATE TABLE IF NOT EXISTS articles (
    id_article INTEGER PRIMARY KEY,
    id_sinta INTEGER,
    doi TEXT,
    title TEXT,
    authors TEXT,
    journal_title TEXT,
    short_journal_title TEXT,
    publisher TEXT,
    issue TEXT,
    volume TEXT,
    page TEXT,
    published TEXT,
    type TEXT,
    pdf_link TEXT,
    issn TEXT,
    issn_type TEXT,
    indexed_date_time TEXT,
    indexed_date_parts TEXT,
    url TEXT
);

-- TABLE: author_article (junction)
CREATE TABLE IF NOT EXISTS author_article (
    id_sinta INTEGER NOT NULL,
    id_article INTEGER NOT NULL,
    PRIMARY KEY (id_sinta, id_article),
    FOREIGN KEY (id_sinta) REFERENCES authors(id_sinta),
    FOREIGN KEY (id_article) REFERENCES articles(id_article)
);

CREATE INDEX IF NOT EXISTS idx_author_article_sinta ON author_article (id_sinta);
CREATE INDEX IF NOT EXISTS idx_author_article_article ON author_article (id_article);
