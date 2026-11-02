"""
Chuyển dữ liệu cũ từ server.db (SQLite) sang MySQL. Chỉ cần chạy 1 lần.

    python migrate_sqlite_to_mysql.py

Dùng cùng cấu hình MySQL với Server.py (MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, ...).
Chạy lại nhiều lần không bị trùng: dòng nào đã có (cùng khóa chính) sẽ được bỏ qua.
"""
import os
import sqlite3

# import Server sẽ tự chạy init_db() → database + bảng bên MySQL đã sẵn sàng
from Server import BASE_DIR, get_db, normalize_time

SQLITE_PATH = os.path.join(BASE_DIR, 'server.db')

# Bảng → các cột thời gian (SQLite lưu chuỗi ISO, MySQL là DATETIME(3))
TABLES = {
    'images': ('capture_time', 'received_time', 'sent_time', 'displayed_time'),
    'config_history': ('changed_at',),
    'clients': ('last_seen',),
}


def _sqlite_tables(src):
    return {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def _mysql_columns(cur, table):
    cur.execute('''SELECT COLUMN_NAME FROM information_schema.COLUMNS
                   WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s''', (table,))
    return {r['COLUMN_NAME'] for r in cur.fetchall()}


def copy_table(src, cur, table, time_cols):
    rows = src.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
    if not rows:
        print(f'{table}: trống')
        return
    cols = [c for c in rows[0].keys() if c in _mysql_columns(cur, table)]
    sql = (f'INSERT IGNORE INTO {table} ({", ".join(cols)}) '
           f'VALUES ({", ".join(["%s"] * len(cols))})')
    added = 0
    for r in rows:
        added += cur.execute(sql, [normalize_time(r[c]) if c in time_cols else r[c] for c in cols])
    print(f'{table}: {added}/{len(rows)} dòng được thêm')


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f'Không thấy {SQLITE_PATH}, không có gì để chuyển.')
        return

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = get_db()
    cur = dst.cursor()
    existing = _sqlite_tables(src)

    for table, time_cols in TABLES.items():
        if table in existing:
            copy_table(src, cur, table, time_cols)

    # --- config (chỉ 1 dòng, đã có sẵn bên MySQL → cập nhật) ---
    if 'config' in existing:
        c = src.execute('SELECT * FROM config WHERE id = 1').fetchone()
        if c is not None:
            keys = c.keys()
            cur.execute('''
                UPDATE config SET capture_interval = %s, jpeg_quality = %s,
                       resize_width = %s, max_images = %s, updated_at = %s
                WHERE id = 1
            ''', (c['capture_interval'], c['jpeg_quality'], c['resize_width'],
                  c['max_images'] if 'max_images' in keys else 100,
                  normalize_time(c['updated_at'])))
            print('config: đã chép')

    dst.commit()
    dst.close()
    src.close()
    print('✅ Xong.')


if __name__ == '__main__':
    main()
