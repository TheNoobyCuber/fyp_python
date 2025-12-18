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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_admin BOOLEAN DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE File (
    file_id INT PRIMARY KEY AUTO_INCREMENT,
    user_id INT NOT NULL,
    filename VARCHAR(255) NOT NULL,     
    -- Encryption parameters
    encrypted_content LONGBLOB NOT NULL,  -- Encrypted file content
    encrypted_key BLOB NOT NULL,  -- HMAC-SHA256(master_key, master_salt)
    file_salt BLOB NOT NULL,      -- 32-byte random
    master_salt BLOB NOT NULL,    -- 32-byte random
    iv BLOB NOT NULL,             -- 16-byte initialization vector
    file_size BIGINT NOT NULL,    -- Original file size in bytes
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES User(ID) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;