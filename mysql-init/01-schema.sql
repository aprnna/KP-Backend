-- Backend Database Schema
-- Database: kp_scrapping (SINTA Scraping Data)

CREATE DATABASE IF NOT EXISTS `kp_scrapping` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE `kp_scrapping`;

-- Table: sinta_authors
-- Stores author bibliometric data scraped from SINTA
CREATE TABLE IF NOT EXISTS `sinta_authors` (
    `id_sinta` INT PRIMARY KEY,
    `fullname` TEXT,
    `major` TEXT,
    `degree` TEXT,
    `faculty` TEXT,
    `sinta_score_overall` INT,
    `sinta_score_3yr` INT,
    `affil_score` INT,
    `affil_score_3yr` INT,
    `s_article_scopus` INT,
    `s_citation_scopus` INT,
    `s_cited_document_scopus` INT,
    `s_hindex_scopus` INT,
    `s_i10_index_scopus` INT,
    `s_gindex_scopus` INT,
    `s_article_gscholar` INT,
    `s_citation_gscholar` INT,
    `s_cited_document_gscholar` INT,
    `s_hindex_gscholar` INT,
    `s_i10_index_gscholar` INT,
    `s_gindex_gscholar` INT,
    `subject_research` TEXT,
    `scraped_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX `idx_faculty` (`faculty`(100)),
    INDEX `idx_sinta_score` (`sinta_score_overall`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: sinta_articles
-- Stores articles scraped from SINTA (4 views per author)
CREATE TABLE IF NOT EXISTS `sinta_articles` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `id_sinta` INT,
    `source` VARCHAR(255),
    `article_title` TEXT,
    `authors` TEXT,
    `publisher` TEXT,
    `year` VARCHAR(10),
    `cited` INT,
    `quartile` VARCHAR(100),
    `url` TEXT,
    `doi` VARCHAR(255),
    `sinta_rank` INT,
    `pdf_link` TEXT,
    `raw_type` VARCHAR(50),
    `issn` VARCHAR(20),
    `issn_type` VARCHAR(20),
    `indexed_date_time` DATETIME,
    `indexed_date_parts` VARCHAR(50),
    `short_journal_title` VARCHAR(255),
    `journal_title` VARCHAR(255),
    `issue` VARCHAR(50),
    `volume` VARCHAR(50),
    `scraped_at` DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX `idx_id_sinta` (`id_sinta`),
    INDEX `idx_source` (`source`),
    INDEX `idx_year` (`year`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: scraping_jobs
-- Stores metadata for scraping jobs
CREATE TABLE IF NOT EXISTS `scraping_jobs` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `job_id` VARCHAR(36) UNIQUE NOT NULL,
    `source` ENUM('sinta_authors', 'sinta_articles', 'both') NOT NULL DEFAULT 'both',
    `status` ENUM('pending', 'running', 'finished', 'failed') NOT NULL DEFAULT 'pending',
    `total_records` INT DEFAULT 0,
    `processed_records` INT DEFAULT 0,
    `progress_percentage` DECIMAL(5,2) DEFAULT 0,
    `parameters` JSON,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `started_at` DATETIME NULL,
    `finished_at` DATETIME NULL,
    `duration_seconds` INT NULL,
    `error_message` TEXT NULL,
    `run_logs` JSON NULL,

    INDEX `idx_job_id` (`job_id`),
    INDEX `idx_status` (`status`),
    INDEX `idx_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;