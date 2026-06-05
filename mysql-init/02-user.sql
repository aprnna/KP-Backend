-- Backend Database User Creation
-- Run after schema initialization

-- Create application user (if not using root)
-- GRANT ALL PRIVILEGES ON kp_scrapping.* TO 'backend_user'@'%' IDENTIFIED BY 'your_password_here';
-- FLUSH PRIVILEGES;

-- Note: In production, use environment variables for credentials
-- The docker-compose will set DB_USER and DB_PASSWORD which MySQL creates automatically

-- Optimize tables after initial data load (optional)
-- ANALYZE TABLE sinta_authors, sinta_articles, scraping_jobs;