-- Schema MySQL cho server PBL4 (truy xuất camera)
-- Server.py tự tạo các bảng này khi chạy, file này để import tay bằng
-- MySQL Workbench / phpMyAdmin hoặc: mysql -u root -p < schema.sql

CREATE DATABASE IF NOT EXISTS pbl4_camera
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pbl4_camera;

CREATE TABLE IF NOT EXISTS images (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    file_name     VARCHAR(255) NOT NULL,
    file_path     VARCHAR(500) NOT NULL,
    capture_time  DATETIME NULL,
    received_time DATETIME NOT NULL,
    file_size_kb  DOUBLE,
    width         INT,
    height        INT,
    INDEX idx_capture_time (capture_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS config (
    id               INT PRIMARY KEY,
    capture_interval INT DEFAULT 5,
    jpeg_quality     INT DEFAULT 80,
    resize_width     INT DEFAULT 854,
    max_images       INT DEFAULT 100,
    updated_at       DATETIME,
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO config (id, capture_interval, jpeg_quality, resize_width, max_images, updated_at)
VALUES (1, 5, 80, 854, 100, NOW());
