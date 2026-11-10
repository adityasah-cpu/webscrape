-- Location-Based Management Dashboard Migration
-- Run with: mysql -u root -p job_portal < migration_location_dashboard.sql

-- Add location column to users table if it doesn't exist
ALTER TABLE users ADD COLUMN IF NOT EXISTS location VARCHAR(100) DEFAULT 'Unknown';

-- Create table for tracking CV uploads by location
CREATE TABLE IF NOT EXISTS user_cv_uploads (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_email VARCHAR(255) NOT NULL,
    location VARCHAR(100) NOT NULL,
    cv_filename VARCHAR(255),
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_size INT,
    extraction_status VARCHAR(50) DEFAULT 'pending',
    INDEX idx_location_date (location, uploaded_at),
    INDEX idx_user_email (user_email)
);

-- Create table for tracking user events (job views, clicks, applications)
CREATE TABLE IF NOT EXISTS user_events (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_email VARCHAR(255) NOT NULL,
    location VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,  -- 'job_viewed', 'job_clicked', 'job_applied'
    job_id VARCHAR(255),
    job_title VARCHAR(255),
    event_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_location_date (location, event_date),
    INDEX idx_user_email (user_email),
    INDEX idx_event_type (event_type)
);

-- Create table for tracking unique users per day/week/month
CREATE TABLE IF NOT EXISTS user_sessions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_email VARCHAR(255) NOT NULL,
    location VARCHAR(100) NOT NULL,
    login_date DATE,
    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_count INT DEFAULT 1,
    UNIQUE KEY unique_user_date (user_email, login_date),
    INDEX idx_location_date (location, login_date)
);

-- Create table for tracking admin access
CREATE TABLE IF NOT EXISTS admin_access_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_email VARCHAR(255) NOT NULL,
    action VARCHAR(255),
    location VARCHAR(100),
    accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_email (admin_email),
    INDEX idx_accessed_date (accessed_at)
);

-- Add columns to track CV upload status in users
ALTER TABLE users ADD COLUMN IF NOT EXISTS cv_uploaded BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_cv_upload_date DATETIME;

-- Create index for faster location-based queries
CREATE INDEX IF NOT EXISTS idx_users_location ON users(location);

-- Add admin role support
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;

COMMIT;
