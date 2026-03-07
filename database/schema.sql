-- TABLE: authors
CREATE TABLE IF NOT EXISTS authors (
    fullname TEXT,
    id_sinta INTEGER PRIMARY KEY,
    nidn TEXT,
    profile_url TEXT,
    departemen TEXT,
    faculty TEXT,
    
    s_hindex_scopus INTEGER,
    s_hindex_gscholar INTEGER,
    sinta_score_3yr INTEGER,
    sinta_score_overall INTEGER,
    affil_score INTEGER,
    affil_score_3yr INTEGER,

    subject_research TEXT,
    s_article_scopus INTEGER,
    s_article_gscholar INTEGER,

    s_citation_scopus INTEGER,
    s_citation_gscholar INTEGER,
    s_cited_document_scopus INTEGER,
    s_cited_document_gscholar INTEGER,
    s_i10_index_scopus INTEGER,
    s_i10_index_gscholar INTEGER,
    s_gindex_scopus INTEGER,
    s_gindex_gscholar INTEGER,
    
    s_quartile_scopus_no_q INTEGER,
    s_quartile_scopus_q1 INTEGER,
    s_quartile_scopus_q2 INTEGER,
    s_quartile_scopus_q3 INTEGER,
    s_quartile_scopus_q4 INTEGER,
);

-- TABLE: articles
CREATE TABLE IF NOT EXISTS articles (
    id_article INTEGER PRIMARY KEY,
    id_sinta INTEGER,
    source TEXT,
    article_title TEXT,
    author TEXT,
    authors TEXT,
    publisher TEXT,
    year TEXT,
    cited TEXT,
    quartile TEXT,
    url TEXT,
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
