"""
Web Server / RESTful API nhận và quản lý ảnh từ Client.

API ảnh:
    POST   /api/images                 nhận ảnh mới (multipart/form-data)
    GET    /api/images                 danh sách (phân trang, lọc theo thời gian)
    GET    /api/images/<id>            chi tiết 1 ảnh
    DELETE /api/images/<id>            xóa ảnh
    POST   /api/images/<id>/displayed  trình duyệt báo ảnh đã hiển thị (đo độ trễ)
API cấu hình từ xa:
    GET    /api/config                 Client định kỳ gọi để lấy cấu hình mới nhất
    POST   /api/config                 Website thiết lập tham số
    GET    /api/config/history         lịch sử thay đổi cấu hình
Giám sát / kiểm thử:
    GET    /api/stats                  thống kê độ trễ, chu kỳ chụp thực tế
    GET    /api/clients                các Client đang kết nối (IP, lần cuối thấy)
Web: /  (gallery real-time)   /manage   /config   /stats   /image/<id>

CSDL: MySQL, cấu hình qua biến môi trường MYSQL_HOST, MYSQL_PORT, MYSQL_USER,
      MYSQL_PASSWORD, MYSQL_DATABASE (database và bảng tự tạo khi chạy).

Chạy:  python Server.py               (mặc định lắng nghe 0.0.0.0:5000, debug tắt)
       PBL4_PORT=8000 python Server.py
"""
import logging
import os
import statistics
import uuid
from datetime import datetime
from logging.handlers import RotatingFileHandler

import pymysql
import pymysql.cursors
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

# ============ CẤU HÌNH ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
LOG_DIR = os.path.join(BASE_DIR, 'logs')

# --- MySQL: đổi trực tiếp ở đây hoặc đặt biến môi trường ---
MYSQL_CONFIG = {
    'host':     os.getenv('MYSQL_HOST', 'localhost'),
    'port':     int(os.getenv('MYSQL_PORT', 3306)),
    'user':     os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', 'pbl4_camera'),
}

ALLOWED_EXT = ('.jpg', '.jpeg', '.png')
CONFIG_LIMITS = [  # (tên, min, max)
    ('capture_interval', 1, 3600),
    ('jpeg_quality', 10, 100),
    ('resize_width', 160, 3840),
    ('max_images', 1, 10000),
]

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB/ảnh
CORS(app)

# ============ LOG ============
log = logging.getLogger('server')
if not log.handlers:
    _h = RotatingFileHandler(os.path.join(LOG_DIR, 'server.log'),
                             maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    _h.setFormatter(logging.Formatter('%(asctime)s [%(threadName)s] %(levelname)s: %(message)s'))
    log.addHandler(_h)
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)


# ============ THỜI GIAN ============
# Cột thời gian trong MySQL là DATETIME(3) → lưu đến mili giây (cần cho đo độ trễ).
def _ms(dt):
    return dt.replace(microsecond=dt.microsecond // 1000 * 1000)


def now_dt():
    return _ms(datetime.now())


def parse_time(value):
    """Chấp nhận datetime, '2026-10-13 10:17:07', '2026-10-13T10:17:07', '...07.512', '2026-10-13T10:17'."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).strip().replace(' ', 'T'))
    except ValueError:
        return None


def normalize_time(value):
    """Chuỗi thời gian từ Client/Website → datetime (làm tròn mili giây) để lưu / lọc trong MySQL."""
    dt = parse_time(value)
    return _ms(dt) if dt else None


def iso(dt):
    return dt.isoformat(timespec='milliseconds') if dt else None


def seconds_between(a, b):
    da, db = parse_time(a), parse_time(b)
    if da is None or db is None:
        return None
    return round((db - da).total_seconds(), 3)


# ============ DATABASE ============
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
    conn.commit()
    conn.close()
    log.info('MySQL sẵn sàng: %s@%s:%s/%s', MYSQL_CONFIG['user'], MYSQL_CONFIG['host'],
             MYSQL_CONFIG['port'], MYSQL_CONFIG['database'])


def touch_client(cur, client_id, activity):
    if not client_id:
        return
    cur.execute('''
        INSERT INTO clients (client_id, ip, last_seen, last_activity) VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE ip = VALUES(ip), last_seen = VALUES(last_seen),
                                last_activity = VALUES(last_activity)
    ''', (client_id, request.remote_addr, now_dt(), activity))


# ============ DỌN DẸP ẢNH CŨ ============
def cleanup_old_images():
    """Nếu số ảnh vượt max_images → xóa ảnh cũ nhất (file + DB record)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT max_images FROM config WHERE id = 1')
    row = cur.fetchone()
    max_images = row['max_images'] if row else None
    if not max_images or max_images < 1:
        conn.close()
        return

    cur.execute('SELECT COUNT(*) AS n FROM images')
    total = cur.fetchone()['n']
    if total > max_images:
        excess = total - max_images
        cur.execute('SELECT id, file_path FROM images ORDER BY id ASC LIMIT %s', (excess,))
        for r in cur.fetchall():
            _remove_file(r['file_path'])
            cur.execute('DELETE FROM images WHERE id = %s', (r['id'],))
        conn.commit()
        log.info('[CLEANUP] %d ảnh > giới hạn %d → đã xóa %d ảnh cũ nhất', total, max_images, excess)
    conn.close()


def _remove_file(rel_path):
    abs_path = os.path.join(BASE_DIR, rel_path)
    if os.path.exists(abs_path):
        try:
            os.remove(abs_path)
        except OSError as e:
            log.warning('Lỗi xóa file %s: %s', abs_path, e)


def _looks_like_image(head, ext):
    if ext in ('.jpg', '.jpeg'):
        return head[:3] == b'\xff\xd8\xff'
    if ext == '.png':
        return head[:8] == b'\x89PNG\r\n\x1a\n'
    return False


# ============ PHỤC VỤ FILE ẢNH ============
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ============ API: ẢNH ============
@app.route('/api/images', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'Thiếu field "file" trong form-data'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Tên file rỗng'}), 400

    ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Chỉ nhận .jpg / .jpeg / .png'}), 400
    if not _looks_like_image(file.stream.read(8), ext):
        return jsonify({'error': 'Nội dung file không phải ảnh JPEG/PNG hợp lệ'}), 400
    file.stream.seek(0)

    received_time = now_dt()
    form = request.form
    capture_time = normalize_time(form.get('capture_time')) or received_time
    client_id = form.get('client_id')
    client_capture_id = form.get('client_capture_id', type=int)

    conn = get_db()
    cur = conn.cursor()
    # Client gửi lại ảnh đã nhận (mất gói phản hồi) → trả lại id cũ, không lưu trùng
    if client_id and client_capture_id is not None:
        cur.execute('''SELECT * FROM images WHERE client_id = %s AND client_capture_id = %s
                       AND capture_time = %s''', (client_id, client_capture_id, capture_time))
        dup = cur.fetchone()
        if dup:
            conn.close()
            return jsonify({**to_json(dup), 'duplicate': True}), 201

    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(file_path)
    file_size_kb = round(os.path.getsize(file_path) / 1024, 2)

    cur.execute('''
        INSERT INTO images (file_name, file_path, capture_time, received_time, file_size_kb,
                            width, height, sent_time, client_id, client_capture_id, client_ip,
                            original_name, source, interval_used, quality_used)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (unique_name, f'uploads/{unique_name}', capture_time, received_time, file_size_kb,
          form.get('width', type=int), form.get('height', type=int),
          normalize_time(form.get('sent_time')), client_id, client_capture_id,
          request.remote_addr, file.filename, form.get('source'),
          form.get('interval_used', type=int), form.get('quality_used', type=int)))
    image_id = cur.lastrowid
    touch_client(cur, client_id, 'upload')
    conn.commit()
    conn.close()

    log.info('[RECV] #%d từ %s (%s) | %.2f KB | trễ chụp→nhận %ss', image_id,
             client_id or '?', request.remote_addr, file_size_kb,
             seconds_between(capture_time, received_time))
    cleanup_old_images()

    return jsonify({
        'id': image_id,
        'file_name': unique_name,
        'file_path': f'uploads/{unique_name}',
        'file_size_kb': file_size_kb,
        'received_time': iso(received_time),
    }), 201


@app.route('/api/images', methods=['GET'])
def list_images():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    start = normalize_time(request.args.get('start'))
    end = normalize_time(request.args.get('end'))
    q = (request.args.get('q') or '').strip()

    where, params = [], []
    if start:
        where.append('capture_time >= %s')
        params.append(start)
    if end:
        where.append('capture_time <= %s')
        params.append(end)
    if q:
        where.append('(file_name LIKE %s OR original_name LIKE %s OR client_id LIKE %s)')
        params += [f'%{q}%'] * 3
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) AS n FROM images {where_sql}', params)
    total = cur.fetchone()['n']
    cur.execute(f'SELECT * FROM images {where_sql} ORDER BY id DESC LIMIT %s OFFSET %s',
                params + [per_page, (page - 1) * per_page])
    items = [to_json(r) for r in cur.fetchall()]
    conn.close()

    return jsonify({
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': (total + per_page - 1) // per_page,
        'items': items,
    })


@app.route('/api/images/<int:image_id>', methods=['GET'])
def get_image(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Không tìm thấy ảnh'}), 404
    return jsonify(to_json(row))


@app.route('/api/images/<int:image_id>', methods=['DELETE'])
def delete_image(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT file_path FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'Không tìm thấy ảnh'}), 404
    _remove_file(row['file_path'])
    cur.execute('DELETE FROM images WHERE id = %s', (image_id,))
    conn.commit()
    conn.close()
    log.info('[DELETE] #%d bởi %s', image_id, request.remote_addr)
    return jsonify({'message': 'Đã xóa', 'id': image_id})


@app.route('/api/images/<int:image_id>/displayed', methods=['POST'])
def mark_displayed(image_id):
    """Gallery gọi khi ảnh lần đầu hiện lên màn hình → đo độ trễ chụp → hiển thị."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE images SET displayed_time = %s WHERE id = %s AND displayed_time IS NULL',
                (now_dt(), image_id))
    conn.commit()
    conn.close()
    return jsonify({'id': image_id})


# ============ API: CONFIG ============
@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config WHERE id = 1')
    row = to_json(cur.fetchone())
    touch_client(cur, request.args.get('client_id'), 'config_poll')
    conn.commit()
    conn.close()
    return jsonify(row)


@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json(silent=True) or {}
    fields = {}
    for key, lo, hi in CONFIG_LIMITS:
        if key in data:
            try:
                v = int(data[key])
            except (ValueError, TypeError):
                return jsonify({'error': f'{key} không phải số'}), 400
            if not (lo <= v <= hi):
                return jsonify({'error': f'{key} phải trong [{lo}, {hi}]'}), 400
            fields[key] = v
    if not fields:
        return jsonify({'error': 'Không có field hợp lệ nào'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config WHERE id = 1')
    old = cur.fetchone()
    changed_at = now_dt()
    for k, v in fields.items():
        if old.get(k) != v:
            cur.execute('''INSERT INTO config_history (changed_at, field, old_value, new_value, changed_by)
                           VALUES (%s, %s, %s, %s, %s)''', (changed_at, k, old.get(k), v, request.remote_addr))
            log.info('[CONFIG] %s: %s → %s (bởi %s)', k, old.get(k), v, request.remote_addr)

    fields['updated_at'] = changed_at
    set_clause = ', '.join(f'{k} = %s' for k in fields)
    cur.execute(f'UPDATE config SET {set_clause} WHERE id = 1', list(fields.values()))
    conn.commit()
    cur.execute('SELECT * FROM config WHERE id = 1')
    row = to_json(cur.fetchone())
    conn.close()

    if 'max_images' in fields:
        cleanup_old_images()
    return jsonify(row)


@app.route('/api/config/history', methods=['GET'])
def config_history():
    limit = min(max(1, request.args.get('limit', 50, type=int)), 500)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config_history ORDER BY id DESC LIMIT %s', (limit,))
    rows = [to_json(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


# ============ API: GIÁM SÁT ============
@app.route('/api/clients', methods=['GET'])
def list_clients():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM clients ORDER BY last_seen DESC')
    rows = cur.fetchall()
    conn.close()
    now = datetime.now()
    result = []
    for r in rows:
        seen = r['last_seen']
        item = to_json(r)
        item['seconds_ago'] = round((now - seen).total_seconds(), 1) if seen else None
        item['online'] = item['seconds_ago'] is not None and item['seconds_ago'] < 30
        result.append(item)
    return jsonify(result)


def _summary(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals_sorted = sorted(vals)
    p95 = vals_sorted[min(len(vals_sorted) - 1, int(round(0.95 * (len(vals_sorted) - 1))))]
    return {'count': len(vals), 'avg': round(statistics.mean(vals), 3),
            'min': round(vals_sorted[0], 3), 'max': round(vals_sorted[-1], 3), 'p95': round(p95, 3)}


@app.route('/api/stats', methods=['GET'])
def stats():
    """
    Độ trễ (giây) cho N ảnh gần nhất:
      capture_to_received : chụp ở Client → Server nhận xong
      sent_to_received    : Client bắt đầu gửi → Server nhận xong (thời gian truyền qua mạng)
      capture_to_display  : chụp → ảnh hiện trên Website
      actual_gap          : khoảng cách thực tế giữa 2 lần chụp (so với interval_used)
    Lưu ý: Client và Server ở 2 máy khác nhau phải đồng bộ đồng hồ (NTP) thì số liệu mới đúng.
    """
    limit = min(max(2, request.args.get('limit', 100, type=int)), 1000)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images ORDER BY capture_time DESC, id DESC LIMIT %s', (limit,))
    rows = cur.fetchall()
    cur.execute('SELECT COUNT(*) AS n FROM images')
    total = cur.fetchone()['n']
    conn.close()

    rows.reverse()  # cũ → mới để tính khoảng cách giữa các lần chụp
    items = []
    prev_capture = None
    prev_client = None
    for r in rows:
        gap = None
        if prev_capture and r.get('client_id') and r.get('client_id') == prev_client:
            gap = seconds_between(prev_capture, r['capture_time'])
        items.append({
            'id': r['id'],
            'client_id': r.get('client_id'),
            'capture_time': iso(r['capture_time']),
            'interval_used': r.get('interval_used'),
            'actual_gap': gap,
            'capture_to_received': seconds_between(r['capture_time'], r['received_time']),
            'sent_to_received': seconds_between(r.get('sent_time'), r['received_time']),
            'capture_to_display': seconds_between(r['capture_time'], r.get('displayed_time')),
            'file_size_kb': r['file_size_kb'],
        })
        prev_capture, prev_client = r['capture_time'], r.get('client_id')
    items.reverse()

    return jsonify({
        'total_images': total,
        'sample_size': len(items),
        'summary': {k: _summary([i[k] for i in items])
                    for k in ('capture_to_received', 'sent_to_received', 'capture_to_display', 'actual_gap')},
        'items': items,
    })


# ============ WEB UI ============
@app.route('/')
def page_index():
    return render_template('index.html')


@app.route('/manage')
def page_manage():
    return render_template('manage.html')


@app.route('/config')
def page_config():
    return render_template('config.html')


@app.route('/stats')
def page_stats():
    return render_template('stats.html')


@app.route('/image/<int:image_id>')
def page_detail(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        abort(404)
    img = to_json(row)
    img['capture_to_received'] = seconds_between(row['capture_time'], row['received_time'])
    img['capture_to_display'] = seconds_between(row['capture_time'], row.get('displayed_time'))
    return render_template('detail.html', image=img)


# Khởi tạo DB ngay khi import (chạy được cả bằng `python Server.py` lẫn `flask run`)
init_db()

if __name__ == '__main__':
    host = os.environ.get('PBL4_HOST', '0.0.0.0')   # 0.0.0.0 để máy khác trong LAN truy cập được
    port = int(os.environ.get('PBL4_PORT', 5000))
    debug = os.environ.get('PBL4_DEBUG') == '1'     # KHÔNG bật debug khi mở ra LAN (lỗ hổng chạy code từ xa)
    log.info('Server lắng nghe %s:%d (debug=%s)', host, port, debug)
    app.run(host=host, port=port, debug=debug, threaded=True)
