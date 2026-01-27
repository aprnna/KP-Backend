-- Academic Scraper Database Schema
-- MySQL 8.0+

-- Drop tables if exist (in reverse order of dependencies)
DROP TABLE IF EXISTS scraping_logs;
DROP TABLE IF EXISTS raw_responses;
DROP TABLE IF EXISTS author_works;
DROP TABLE IF EXISTS works;
DROP TABLE IF EXISTS authors;
DROP TABLE IF EXISTS scraping_jobs;

-- ============================================
-- Scraping Jobs Table (New for Scraper)
-- ============================================
CREATE TABLE scraping_jobs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id VARCHAR(36) UNIQUE NOT NULL,
    source ENUM('crossref', 'openalex', 'both') NOT NULL DEFAULT 'both',
    status ENUM('pending', 'running', 'finished', 'failed') NOT NULL DEFAULT 'pending',
    total_records INT DEFAULT 0,
    processed_records INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    started_at DATETIME NULL,
    finished_at DATETIME NULL,
    error_message TEXT NULL,
    parameters JSON NULL,
    
    INDEX idx_job_id (job_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- Authors Table (Merged with Legacy)
-- ============================================
CREATE TABLE authors (
    -- Legacy Columns
    id_author INT AUTO_INCREMENT PRIMARY KEY,
    nidn VARCHAR(255) NULL,
    nama VARCHAR(255) NULL, -- Added to match reference
    fullname VARCHAR(255) NULL,
    academic_grade_raw VARCHAR(255) NULL,
    academic_grade VARCHAR(255) NULL,
    gelar_depan VARCHAR(255) NULL,
    gelar_belakang VARCHAR(255) NULL,
    last_education VARCHAR(255) NULL,
    sinta_score_v2_overall INT NULL,
    sinta_score_v2_3year INT NULL,
    sinta_score_v3_overall INT NULL,
    sinta_score_v3_3year INT NULL,
    affiliation_score_v3_overall INT NULL,
    affiliation_score_v3_3year INT NULL,
    affiliation_id INT NULL,
    affiliation_code INT NULL,
    programs_code INT NULL,
    programs_level VARCHAR(255) NULL,
    programs_name VARCHAR(255) NULL,
    
    -- New Columns for Scraper
    openalex_id VARCHAR(255) UNIQUE NULL,
    name VARCHAR(500) NULL, -- Alternate for fullname if needed, or mapped to fullname
    orcid VARCHAR(50) NULL,
    works_count INT DEFAULT 0,
    cited_by_count INT DEFAULT 0,
    h_index DOUBLE DEFAULT 0,
    i10_index DOUBLE DEFAULT 0,
    mean_citedness_2yr DOUBLE DEFAULT 0,
    relevance_score DOUBLE NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_nidn (nidn),
    INDEX idx_fullname (fullname(100)),
    INDEX idx_openalex_id (openalex_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- Works Table (Merged with Legacy)
-- ============================================
CREATE TABLE works (
    -- Legacy Columns
    author_query VARCHAR(255) DEFAULT NULL,
    doi VARCHAR(255) DEFAULT NULL,
    title TEXT,
    authors TEXT,
    container_title VARCHAR(255) DEFAULT NULL,
    short_container_title VARCHAR(255) DEFAULT NULL,
    publisher VARCHAR(255) DEFAULT NULL,
    issue VARCHAR(255) DEFAULT NULL,
    volume VARCHAR(255) DEFAULT NULL,
    page VARCHAR(255) DEFAULT NULL,
    published VARCHAR(255) DEFAULT NULL, -- Legacy uses varchar for date
    type VARCHAR(255) DEFAULT NULL,
    source VARCHAR(255) DEFAULT NULL,
    pdf_link TEXT,
    all_links TEXT,
    abstract TEXT,
    score DOUBLE DEFAULT NULL,
    issn VARCHAR(255) DEFAULT NULL,
    issn_type VARCHAR(255) DEFAULT NULL,
    indexed_date_time VARCHAR(255) DEFAULT NULL,
    indexed_date_parts VARCHAR(255) DEFAULT NULL,
    url VARCHAR(255) DEFAULT NULL,
    id_work VARCHAR(255) NOT NULL, -- Legacy primary identifier
    
    -- New Columns for Scraper (mapped where possible, added if new)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    PRIMARY KEY (id_work),
    UNIQUE KEY uk_doi (doi),
    INDEX idx_title (title(100)),
    FULLTEXT idx_title_abstract (title, abstract)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- Author-Work Relationship Table
-- ============================================
CREATE TABLE author_works (
    id INT AUTO_INCREMENT PRIMARY KEY,
    id_author INT NOT NULL,
    id_work VARCHAR(255) NOT NULL,
    author_query VARCHAR(500) NULL,
    is_corresponding BOOLEAN DEFAULT FALSE,
    
    FOREIGN KEY (id_author) REFERENCES authors(id_author) ON DELETE CASCADE,
    FOREIGN KEY (id_work) REFERENCES works(id_work) ON DELETE CASCADE,
    UNIQUE KEY uk_author_work (id_author, id_work),
    INDEX idx_author_id (id_author),
    INDEX idx_work_id (id_work)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- Raw API Responses Table (New)
-- ============================================
CREATE TABLE raw_responses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    source VARCHAR(50) NOT NULL,
    endpoint VARCHAR(255) NOT NULL,
    request_params JSON NULL,
    response_data JSON NULL,
    status_code INT NULL,
    response_time_ms INT NULL,
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (job_id) REFERENCES scraping_jobs(id) ON DELETE CASCADE,
    INDEX idx_job_source (job_id, source)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================
-- Scraping Logs Table (New)
-- ============================================
CREATE TABLE scraping_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    job_id INT NOT NULL,
    level ENUM('DEBUG', 'INFO', 'WARNING', 'ERROR') DEFAULT 'INFO',
    message TEXT NOT NULL,
    extra_data JSON NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (job_id) REFERENCES scraping_jobs(id) ON DELETE CASCADE,
    INDEX idx_job_level (job_id, level),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

