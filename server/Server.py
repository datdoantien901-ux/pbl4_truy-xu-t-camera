import os
import pymysql
import pymysql.cursors
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from flask_cors import CORS

# ============ CẤU HÌNH ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

# --- MySQL: đổi trực tiếp ở đây hoặc đặt biến môi trường ---
MYSQL_CONFIG = {
    'host':     os.getenv('MYSQL_HOST', 'localhost'),
    'port':     int(os.getenv('MYSQL_PORT', 3306)),
    'user':     os.getenv('MYSQL_USER', 'root'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'database': os.getenv('MYSQL_DATABASE', 'pbl4_camera'),
}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB/ảnh
CORS(app)


# ============ DATABASE ============
def get_db():
    """Mở kết nối MySQL. Mỗi dòng trả về là dict (giống sqlite3.Row cũ)."""
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
    """Đổi các cột DATETIME sang chuỗi ISO (vd 2026-10-13T10:02:31) để giữ đúng định dạng cũ."""
    if row is None:
        return None
    return {k: (v.isoformat(timespec='seconds') if isinstance(v, datetime) else v)
            for k, v in row.items()}


def init_db():
    # 1. Tạo database nếu chưa có
    conn = pymysql.connect(host=MYSQL_CONFIG['host'], port=MYSQL_CONFIG['port'],
                           user=MYSQL_CONFIG['user'], password=MYSQL_CONFIG['password'],
                           charset='utf8mb4')
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_CONFIG['database']}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    conn.close()

    # 2. Tạo bảng
    conn = get_db()
    cur = conn.cursor()

    cur.execute('''
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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS config (
            id               INT PRIMARY KEY,
            capture_interval INT DEFAULT 5,
            jpeg_quality     INT DEFAULT 80,
            resize_width     INT DEFAULT 854,
            max_images       INT DEFAULT 100,
            updated_at       DATETIME,
            CHECK (id = 1)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    ''')

    # Chỉ có 1 dòng config
    cur.execute('''
        INSERT IGNORE INTO config
            (id, capture_interval, jpeg_quality, resize_width, max_images, updated_at)
        VALUES (1, 5, 80, 854, 100, %s)
    ''', (datetime.now().replace(microsecond=0),))

    conn.commit()
    conn.close()
    print(f"✅ MySQL sẵn sàng: {MYSQL_CONFIG['user']}@{MYSQL_CONFIG['host']}:"
          f"{MYSQL_CONFIG['port']}/{MYSQL_CONFIG['database']}")


# ============ DỌN DẸP ẢNH CŨ ============
def cleanup_old_images():
    """Nếu số ảnh vượt max_images → xóa ảnh cũ nhất (file + DB record)."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute('SELECT max_images FROM config WHERE id = 1')
    row = cur.fetchone()
    if row is None:
        conn.close()
        return

    max_images = row['max_images']
    if not max_images or max_images < 1:
        conn.close()
        return

    cur.execute('SELECT COUNT(*) AS n FROM images')
    total = cur.fetchone()['n']

    if total <= max_images:
        conn.close()
        return

    excess = total - max_images
    print(f'[CLEANUP] Co {total} anh > gioi han {max_images}. Xoa {excess} anh cu nhat.')

    cur.execute('''
        SELECT id, file_path FROM images
        ORDER BY id ASC
        LIMIT %s
    ''', (excess,))
    rows = cur.fetchall()

    for r in rows:
        abs_path = os.path.join(BASE_DIR, r['file_path'])
        if os.path.exists(abs_path):
            try:
                os.remove(abs_path)
            except Exception as e:
                print(f'[CLEANUP] Loi xoa file {abs_path}: {e}')
        cur.execute('DELETE FROM images WHERE id = %s', (r['id'],))

    conn.commit()
    conn.close()


# ============ PHỤC VỤ FILE ẢNH ============
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ============ API: ẢNH ============
@app.route('/api/images', methods=['POST'])
def upload_image():
    # 1. Kiểm tra file
    if 'file' not in request.files:
        return jsonify({'error': 'Thiếu field "file" trong form-data'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Tên file rỗng'}), 400

    # 2. Kiểm tra định dạng
    ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
    if ext not in ('.jpg', '.jpeg', '.png'):
        return jsonify({'error': 'Chỉ nhận .jpg / .jpeg / .png'}), 400

    # 3. Đọc metadata client gửi kèm
    capture_time = request.form.get('capture_time') or datetime.now().isoformat(timespec='seconds')
    width = request.form.get('width', type=int)
    height = request.form.get('height', type=int)

    # 4. Sinh tên file duy nhất
    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    file.save(file_path)

    # 5. Ghi DB
    file_size_kb = round(os.path.getsize(file_path) / 1024, 2)
    received_time = datetime.now().isoformat(timespec='seconds')

    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO images (file_name, file_path, capture_time, received_time, file_size_kb, width, height)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (unique_name, f'uploads/{unique_name}', capture_time, received_time,
          file_size_kb, width, height))
    image_id = cur.lastrowid
    conn.commit()
    conn.close()

    # 6. Dọn ảnh cũ nếu vượt giới hạn
    cleanup_old_images()

    return jsonify({
        'id': image_id,
        'file_name': unique_name,
        'file_path': f'uploads/{unique_name}',
        'file_size_kb': file_size_kb,
        'received_time': received_time
    }), 201


@app.route('/api/images', methods=['GET'])
def list_images():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    start = request.args.get('start')
    end = request.args.get('end')

    where, params = [], []
    if start:
        where.append('capture_time >= %s')
        params.append(start)
    if end:
        where.append('capture_time <= %s')
        params.append(end)
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    conn = get_db()
    cur = conn.cursor()

    cur.execute(f'SELECT COUNT(*) AS n FROM images {where_sql}', params)
    total = cur.fetchone()['n']

    offset = (page - 1) * per_page
    cur.execute(f'''
        SELECT * FROM images {where_sql}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
    ''', params + [per_page, offset])
    items = [to_json(r) for r in cur.fetchall()]
    conn.close()

    return jsonify({
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': (total + per_page - 1) // per_page,
        'items': items
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

    abs_path = os.path.join(BASE_DIR, row['file_path'])
    if os.path.exists(abs_path):
        os.remove(abs_path)

    cur.execute('DELETE FROM images WHERE id = %s', (image_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Đã xóa', 'id': image_id})


# ============ API: CONFIG ============
@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config WHERE id = 1')
    row = to_json(cur.fetchone())
    conn.close()
    return jsonify(row)


@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json(silent=True) or {}

    fields = {}
    for key, caster, lo, hi in [
        ('capture_interval', int, 1,    3600),
        ('jpeg_quality',     int, 10,   100),
        ('resize_width',     int, 160,  3840),
        ('max_images',       int, 1,    10000),
    ]:
        if key in data:
            try:
                v = caster(data[key])
            except (ValueError, TypeError):
                return jsonify({'error': f'{key} không phải số'}), 400
            if not (lo <= v <= hi):
                return jsonify({'error': f'{key} phải trong [{lo}, {hi}]'}), 400
            fields[key] = v

    if not fields:
        return jsonify({'error': 'Không có field hợp lệ nào'}), 400

    fields['updated_at'] = datetime.now().replace(microsecond=0)
    set_clause = ', '.join(f'{k} = %s' for k in fields)
    params = list(fields.values()) + [1]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'UPDATE config SET {set_clause} WHERE id = %s', params)
    conn.commit()
    cur.execute('SELECT * FROM config WHERE id = 1')
    row = to_json(cur.fetchone())
    conn.close()

    # Nếu vừa giảm max_images → dọn ngay
    if 'max_images' in fields:
        cleanup_old_images()

    return jsonify(row)


# ============ WEB UI ============
@app.route('/')
def page_index():
    return render_template('index.html')


@app.route('/config')
def page_config():
    return render_template('config.html')


@app.route('/image/<int:image_id>')
def page_detail(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        abort(404)
    return render_template('detail.html', image=to_json(row))


# ============ MAIN ============
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)