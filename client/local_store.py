"""
CSDL cục bộ của Client (SQLite).

Bảng `captures` vừa là nơi lưu metadata, vừa đóng vai trò hàng đợi bền vững
(persistent queue): ảnh nào uploaded = 0 thì chưa lên server. Khi mất mạng
hoặc tắt Client, ảnh vẫn nằm ở đây và sẽ được gửi bù ở lần chạy sau.

Nhiều luồng cùng ghi (Capture ghi ảnh mới, Upload cập nhật trạng thái) nên:
  - bật chế độ WAL để đọc/ghi đồng thời không khóa nhau,
  - mỗi lần thao tác mở connection riêng (sqlite3 connection không nên chia sẻ giữa các luồng),
  - dùng threading.Lock bao quanh các lệnh ghi.
"""
import sqlite3
import threading

UPLOAD_PENDING = 0
UPLOAD_DONE = 1
UPLOAD_REJECTED = -1   # server từ chối (4xx) → không gửi lại nữa


class LocalStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self._write_lock = threading.Lock()
        self._init()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS captures (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name       TEXT    NOT NULL,
                    file_path       TEXT    NOT NULL,
                    capture_time    TEXT    NOT NULL,
                    file_size_kb    REAL,
                    width           INTEGER,
                    height          INTEGER,
                    source          TEXT,
                    interval_used   INTEGER,
                    quality_used    INTEGER,
                    uploaded        INTEGER DEFAULT 0,
                    server_id       INTEGER,
                    upload_attempts INTEGER DEFAULT 0,
                    uploaded_time   TEXT,
                    last_error      TEXT
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_captures_uploaded ON captures(uploaded)')

    def add_capture(self, file_name, file_path, capture_time, size_kb,
                    width, height, source, interval_used, quality_used):
        with self._write_lock, self._connect() as conn:
            cur = conn.execute('''
                INSERT INTO captures (file_name, file_path, capture_time, file_size_kb,
                                      width, height, source, interval_used, quality_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (file_name, file_path, capture_time, size_kb, width, height,
                  source, interval_used, quality_used))
            return cur.lastrowid

    def get(self, capture_id):
        with self._connect() as conn:
            row = conn.execute('SELECT * FROM captures WHERE id = ?', (capture_id,)).fetchone()
            return dict(row) if row else None

    def pending_ids(self, limit=50, exclude=()):
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT id FROM captures WHERE uploaded = ? ORDER BY id ASC LIMIT ?',
                (UPLOAD_PENDING, limit + len(exclude))).fetchall()
        ids = [r['id'] for r in rows if r['id'] not in exclude]
        return ids[:limit]

    def count_pending(self):
        with self._connect() as conn:
            return conn.execute('SELECT COUNT(*) FROM captures WHERE uploaded = ?',
                                (UPLOAD_PENDING,)).fetchone()[0]

    def mark_uploaded(self, capture_id, server_id, uploaded_time):
        with self._write_lock, self._connect() as conn:
            conn.execute('''
                UPDATE captures SET uploaded = ?, server_id = ?, uploaded_time = ?,
                       upload_attempts = upload_attempts + 1, last_error = NULL
                WHERE id = ?
            ''', (UPLOAD_DONE, server_id, uploaded_time, capture_id))

    def mark_failed(self, capture_id, error, permanent=False):
        status = UPLOAD_REJECTED if permanent else UPLOAD_PENDING
        with self._write_lock, self._connect() as conn:
            conn.execute('''
                UPDATE captures SET uploaded = ?, upload_attempts = upload_attempts + 1,
                       last_error = ?
                WHERE id = ?
            ''', (status, str(error)[:300], capture_id))
