-- Complete Database Migration for Job Portal
-- Creates all necessary tables and indexes

USE job_portal;

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    picture VARCHAR(500),
    location VARCHAR(100) DEFAULT 'Vizianagaram' NOT NULL,
    cv_uploaded BOOLEAN DEFAULT FALSE,
    last_cv_upload_date DATETIME,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_users_email (email),
    INDEX idx_users_location (location),
    INDEX idx_users_cv_uploaded (cv_uploaded),
    INDEX idx_users_created_at (created_at),
    INDEX idx_users_is_admin (is_admin)
);

-- Create user events table
CREATE TABLE IF NOT EXISTS user_events (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_email VARCHAR(255) NOT NULL,
    location VARCHAR(100),
    event_type VARCHAR(50),
    job_id VARCHAR(255),
    job_title VARCHAR(255),
    event_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_user_events_email (user_email),
    INDEX idx_user_events_location (location),
    INDEX idx_user_events_type (event_type),
    INDEX idx_user_events_location_type (location, event_type),
    INDEX idx_user_events_date (event_date)
);

-- Create user sessions table
CREATE TABLE IF NOT EXISTS user_sessions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_email VARCHAR(255) NOT NULL,
    location VARCHAR(100),
    login_date DATE,
    last_activity DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_count INT DEFAULT 1,
    UNIQUE KEY unique_user_date (user_email, login_date),
    INDEX idx_user_sessions_email (user_email),
    INDEX idx_user_sessions_location (location),
    INDEX idx_user_sessions_date (login_date),
    INDEX idx_user_sessions_location_date (location, login_date)
);

-- Create CV uploads table
CREATE TABLE IF NOT EXISTS user_cv_uploads (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_email VARCHAR(255) NOT NULL,
    location VARCHAR(100),
    cv_filename VARCHAR(255),
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_size INT,
    extraction_status VARCHAR(50) DEFAULT 'pending',
    INDEX idx_cv_uploads_email (user_email),
    INDEX idx_cv_uploads_location (location),
    INDEX idx_cv_uploads_date (uploaded_at)
);

-- Create admin access logs table
CREATE TABLE IF NOT EXISTS admin_access_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    admin_email VARCHAR(255) NOT NULL,
    action VARCHAR(255),
    location VARCHAR(100),
    accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_email (admin_email),
    INDEX idx_accessed_date (accessed_at)
);

COMMIT;
