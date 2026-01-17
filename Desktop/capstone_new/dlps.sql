drop database IF EXISTS DLPS;
create database DLPS;
USE DLPS;

CREATE TABLE User (
    ID INT PRIMARY KEY AUTO_INCREMENT,
    fullname VARCHAR(255) NOT NULL,
    username VARCHAR(255) NOT NULL,
    email VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    position VARCHAR(50) NOT NULL,
    otp VARCHAR(10),
    otp_expiry DATETIME,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_admin BOOLEAN DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE File (
    file_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,     
    original_filename VARCHAR(255) NOT NULL,  -- Original filename
    filepath VARCHAR(500) NOT NULL,  -- Path where the file is stored
    filetype VARCHAR(50) NOT NULL,  -- File type
    file_size BIGINT NOT NULL,    -- Original file size in bytes
    description TEXT,      -- 32-byte random
    shared_with TEXT,   -- 32-byte random
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending', -- pending, scanned, flagged, safe
    sensitivity INT,  -- 1-10
    action VARCHAR(50),  -- e.g., 'block', 'quarantine', 'alert'
    FOREIGN KEY (user_id) REFERENCES User(ID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE AuditLog (
    log_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT,
    action_type VARCHAR(50) NOT NULL,  -- e.g., 'upload', 'delete', 'share'
    details TEXT,  -- Additional details about the action
    status VARCHAR(50) DEFAULT 'success', -- success, failed
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES User(ID) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert admin user
-- Note: This uses a pre-hashed password for 'admin'
-- username: admin, password: 123
INSERT INTO User (fullname, username, email, password, position, is_admin, created_at) 
VALUES ('admin', 'admin', 'admin@admin.com', 'scrypt:32768:8:1$1HQpElXMtXWRWYBr$0750c8266caee9698e3cc39eaaa71cf3fac245f7f6407d27c7e878d07489d64b0fc9a4deb71731903f4d23584264e9be48bb249b045b44a62c41652206d43e95', 'admin', 1, CURRENT_TIMESTAMP);

-- Add audit log for admin creation
INSERT INTO AuditLog (user_id, action_type, details, timestamp)
VALUES (1, 'admin_create', 'Admin user created during database initialization', CURRENT_TIMESTAMP);