"""
Chuyển dữ liệu cũ từ server.db (SQLite) sang MySQL. Chỉ cần chạy 1 lần.

    python migrate_sqlite_to_mysql.py

Dùng cùng cấu hình MySQL với Server.py (MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, ...).
Chạy lại nhiều lần không bị trùng: ảnh nào đã có (cùng id) sẽ được bỏ qua.
"""
import os
import sqlite3

from Server import init_db, get_db, BASE_DIR

SQLITE_PATH = os.path.join(BASE_DIR, 'server.db')


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f'Không thấy {SQLITE_PATH}, không có gì để chuyển.')
        return

    init_db()  # tạo database + bảng bên MySQL nếu chưa có

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = get_db()
    cur = dst.cursor()

    # --- images ---
    rows = src.execute('SELECT * FROM images ORDER BY id').fetchall()
    added = 0
    for r in rows:
        added += cur.execute('''
            INSERT IGNORE INTO images
                (id, file_name, file_path, capture_time, received_time, file_size_kb, width, height)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (r['id'], r['file_name'], r['file_path'], r['capture_time'] or None,
              r['received_time'], r['file_size_kb'], r['width'], r['height']))
    print(f'images: {added}/{len(rows)} dòng được thêm')

    # --- config (chỉ 1 dòng) ---
    c = src.execute('SELECT * FROM config WHERE id = 1').fetchone()
    if c is not None:
        keys = c.keys()
        cur.execute('''
            UPDATE config SET capture_interval = %s, jpeg_quality = %s,
                   resize_width = %s, max_images = %s, updated_at = %s
            WHERE id = 1
        ''', (c['capture_interval'], c['jpeg_quality'], c['resize_width'],
              c['max_images'] if 'max_images' in keys else 100,
              c['updated_at'] or None))
        print('config: đã chép')

    dst.commit()
    dst.close()
    src.close()
    print('✅ Xong.')


if __name__ == '__main__':
    main()
