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
import os
import statistics
from datetime import datetime

from flask import Flask, abort, jsonify, render_template, request
from flask_cors import CORS

from db import get_db, init_db, to_json, touch_client
from routes.images import images_bp
from settings import CONFIG_LIMITS, MAX_CONTENT_LENGTH, UPLOAD_FOLDER, log
from storage import cleanup_old_images
from timeutil import iso, now_dt, seconds_between

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
CORS(app)
app.register_blueprint(images_bp)


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
