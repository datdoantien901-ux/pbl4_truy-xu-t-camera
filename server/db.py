"""
Kết nối MySQL và khởi tạo / nâng cấp schema.
Mỗi request mở một kết nối riêng (get_db) → an toàn khi Flask chạy threaded=True.
Đổi schema thì sửa cả init_db(), schema.sql và migrate_sqlite_to_mysql.py.
"""
from datetime import datetime

import pymysql
import pymysql.cursors
from flask import request

from settings import MYSQL_CONFIG, log
from timeutil import iso, now_dt


def get_db():
    """Mở kết nối MySQL (mỗi request 1 kết nối riêng). Mỗi dòng trả về là dict."""
    return pymysql.connect(
        host=MYSQL_CONFIG['host'],
        port=MYSQL_CONFIG['port'],
        user=MYSQL_CONFIG['user'],
        password=MYSQL_CONFIG['password'],
        database=MYSQL_CONFIG['database'],
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )


def to_json(row):
    """Đổi các cột DATETIME sang chuỗi ISO 'YYYY-MM-DDTHH:MM:SS.mmm' (định dạng Website đang dùng)."""
    if row is None:
        return None
    return {k: (iso(v) if isinstance(v, datetime) else v) for k, v in row.items()}


def _columns(cur, table):
    cur.execute('''SELECT COLUMN_NAME, DATA_TYPE, DATETIME_PRECISION, IS_NULLABLE
                   FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s''', (table,))
    return {r['COLUMN_NAME']: r for r in cur.fetchall()}


def _add_column(cur, table, col, decl):
    if col not in _columns(cur, table):
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {decl}')
        log.info('Đã thêm cột %s.%s', table, col)


def _add_index(cur, table, name, cols):
    cur.execute('''SELECT 1 FROM information_schema.STATISTICS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s
                   LIMIT 1''', (table, name))
    if cur.fetchone() is None:
        cur.execute(f'CREATE INDEX {name} ON {table}({cols})')


def _datetime_to_ms(cur, table):
    """DB tạo bởi bản cũ dùng DATETIME (chỉ đến giây) → nâng lên DATETIME(3)."""
    for col, info in _columns(cur, table).items():
        if info['DATA_TYPE'] == 'datetime' and not info['DATETIME_PRECISION']:
            null = 'NULL' if info['IS_NULLABLE'] == 'YES' else 'NOT NULL'
            cur.execute(f'ALTER TABLE {table} MODIFY {col} DATETIME(3) {null}')
            log.info('Đã đổi %s.%s sang DATETIME(3)', table, col)


def init_db():
    # 1. Tạo database nếu chưa có
    conn = pymysql.connect(host=MYSQL_CONFIG['host'], port=MYSQL_CONFIG['port'],
                           user=MYSQL_CONFIG['user'], password=MYSQL_CONFIG['password'],
                           charset='utf8mb4')
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_CONFIG['database']}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()

    # 2. Tạo bảng (InnoDB khóa theo dòng → nhiều request đồng thời đọc/ghi không chặn nhau)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS images (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            file_name     VARCHAR(255) NOT NULL,
            file_path     VARCHAR(500) NOT NULL,
            capture_time  DATETIME(3) NULL,
            received_time DATETIME(3) NOT NULL,
            file_size_kb  DOUBLE,
            width         INT,
            height        INT,
            INDEX idx_capture_time (capture_time)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')
    # Các cột mới (tự thêm nếu DB cũ chưa có)
    for col, decl in [('sent_time', 'DATETIME(3) NULL'), ('displayed_time', 'DATETIME(3) NULL'),
                      ('client_id', 'VARCHAR(100)'), ('client_capture_id', 'INT'),
                      ('client_ip', 'VARCHAR(45)'), ('original_name', 'VARCHAR(255)'),
                      ('source', 'VARCHAR(255)'),
                      ('interval_used', 'INT'), ('quality_used', 'INT')]:
        _add_column(cur, 'images', col, decl)
    _datetime_to_ms(cur, 'images')
    _add_index(cur, 'images', 'idx_images_client_capture', 'client_id, client_capture_id')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS config (
            id               INT PRIMARY KEY,
            capture_interval INT DEFAULT 5,
            jpeg_quality     INT DEFAULT 80,
            resize_width     INT DEFAULT 854,
            max_images       INT DEFAULT 100,
            updated_at       DATETIME(3),
            CHECK (id = 1)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')
    _add_column(cur, 'config', 'max_images', 'INT DEFAULT 100')
    _datetime_to_ms(cur, 'config')
    cur.execute('''
        INSERT IGNORE INTO config
            (id, capture_interval, jpeg_quality, resize_width, max_images, updated_at)
        VALUES (1, 5, 80, 854, 100, %s)
    ''', (now_dt(),))

    cur.execute('''
        CREATE TABLE IF NOT EXISTS config_history (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            changed_at DATETIME(3) NOT NULL,
            field      VARCHAR(50) NOT NULL,
            old_value  INT,
            new_value  INT,
            changed_by VARCHAR(45)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            client_id     VARCHAR(100) PRIMARY KEY,
            ip            VARCHAR(45),
            last_seen     DATETIME(3),
            last_activity VARCHAR(50)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')
    # Danh sách id camera Client khai báo (vd 'youtube,nha') → Website biết cả camera chưa gửi ảnh
    _add_column(cur, 'clients', 'cameras', 'VARCHAR(500)')
    conn.commit()
    conn.close()
    log.info('MySQL sẵn sàng: %s@%s:%s/%s', MYSQL_CONFIG['user'], MYSQL_CONFIG['host'],
             MYSQL_CONFIG['port'], MYSQL_CONFIG['database'])


def touch_client(cur, client_id, activity, cameras=None):
    """Ghi nhận Client vừa hoạt động (IP, thời điểm) — dùng trong request upload / lấy config.
    cameras: chuỗi id camera Client khai báo ('youtube,nha'); None → giữ giá trị cũ."""
    if not client_id:
        return
    cur.execute('''
        INSERT INTO clients (client_id, ip, last_seen, last_activity, cameras) VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE ip = VALUES(ip), last_seen = VALUES(last_seen),
                                last_activity = VALUES(last_activity),
                                cameras = COALESCE(VALUES(cameras), cameras)
    ''', (client_id, request.remote_addr, now_dt(), activity, cameras))
