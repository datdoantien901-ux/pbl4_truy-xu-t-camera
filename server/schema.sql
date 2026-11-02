-- Schema MySQL cho server PBL4 (truy xuất camera)
-- Server.py tự tạo các bảng này khi chạy, file này để import tay bằng
-- MySQL Workbench / phpMyAdmin hoặc: mysql -u root -p < schema.sql
-- Cột thời gian dùng DATETIME(3) (đến mili giây) để đo độ trễ.

CREATE DATABASE IF NOT EXISTS pbl4_camera
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pbl4_camera;

CREATE TABLE IF NOT EXISTS images (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    file_name         VARCHAR(255) NOT NULL,
    file_path         VARCHAR(500) NOT NULL,
    capture_time      DATETIME(3) NULL,
    received_time     DATETIME(3) NOT NULL,
    file_size_kb      DOUBLE,
    width             INT,
    height            INT,
    sent_time         DATETIME(3) NULL,
    displayed_time    DATETIME(3) NULL,
    client_id         VARCHAR(100),
    client_capture_id INT,
    client_ip         VARCHAR(45),
    original_name     VARCHAR(255),
    source            VARCHAR(255),
    interval_used     INT,
    quality_used      INT,
    INDEX idx_capture_time (capture_time),
    INDEX idx_images_client_capture (client_id, client_capture_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS config (
    id               INT PRIMARY KEY,
    capture_interval INT DEFAULT 5,
    jpeg_quality     INT DEFAULT 80,
    resize_width     INT DEFAULT 854,
    max_images       INT DEFAULT 100,
    updated_at       DATETIME(3),
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO config (id, capture_interval, jpeg_quality, resize_width, max_images, updated_at)
VALUES (1, 5, 80, 854, 100, NOW(3));

CREATE TABLE IF NOT EXISTS config_history (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    changed_at DATETIME(3) NOT NULL,
    field      VARCHAR(50) NOT NULL,
    old_value  INT,
    new_value  INT,
    changed_by VARCHAR(45)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS clients (
    client_id     VARCHAR(100) PRIMARY KEY,
    ip            VARCHAR(45),
    last_seen     DATETIME(3),
    last_activity VARCHAR(50)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
