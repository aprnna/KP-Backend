-- Quick fix: Add missing source column to existing scraping_jobs table
-- Run this if you don't want to recreate the entire database

ALTER TABLE scraping_jobs 
ADD COLUMN source ENUM('crossref', 'openalex', 'both') NOT NULL DEFAULT 'both'
AFTER job_id;
