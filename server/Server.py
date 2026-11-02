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

from flask import Flask, abort, render_template
from flask_cors import CORS

from db import get_db, init_db, to_json
from routes.config import config_bp
from routes.images import images_bp
from routes.monitor import monitor_bp
from settings import MAX_CONTENT_LENGTH, UPLOAD_FOLDER, log
from timeutil import seconds_between

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
CORS(app)
app.register_blueprint(images_bp)
app.register_blueprint(config_bp)
app.register_blueprint(monitor_bp)


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
