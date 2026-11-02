"""
Web Server / RESTful API nhận và quản lý ảnh từ Client — file khởi động.

Mỗi chức năng nằm ở một file riêng:
    settings.py         cấu hình (đường dẫn, MySQL, giới hạn tham số) + log
    timeutil.py         xử lý thời gian (DATETIME(3) ↔ chuỗi ISO, tính độ trễ)
    db.py               kết nối MySQL, tạo / nâng cấp bảng, ghi nhận Client
    storage.py          file ảnh trong uploads/: kiểm tra định dạng, xóa, dọn ảnh cũ
    routes/images.py    API ảnh       /api/images..., /uploads/<file>
    routes/config.py    API cấu hình  /api/config, /api/config/history
    routes/monitor.py   API giám sát  /api/stats, /api/clients
    routes/web.py       trang web     /  /manage  /config  /stats  /image/<id>

CSDL: MySQL, cấu hình qua biến môi trường MYSQL_HOST, MYSQL_PORT, MYSQL_USER,
      MYSQL_PASSWORD, MYSQL_DATABASE (database và bảng tự tạo khi chạy).

Chạy:  python Server.py               (mặc định lắng nghe 0.0.0.0:5000, debug tắt)
       PBL4_PORT=8000 python Server.py
"""
import os

from flask import Flask
from flask_cors import CORS

from db import init_db
from routes.config import config_bp
from routes.images import images_bp
from routes.monitor import monitor_bp
from routes.web import web_bp
from settings import MAX_CONTENT_LENGTH, log

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
CORS(app)
for bp in (images_bp, config_bp, monitor_bp, web_bp):
    app.register_blueprint(bp)

# Khởi tạo DB ngay khi import (chạy được cả bằng `python Server.py` lẫn `flask run`)
init_db()

if __name__ == '__main__':
    host = os.environ.get('PBL4_HOST', '0.0.0.0')   # 0.0.0.0 để máy khác trong LAN truy cập được
    port = int(os.environ.get('PBL4_PORT', 5000))
    debug = os.environ.get('PBL4_DEBUG') == '1'     # KHÔNG bật debug khi mở ra LAN (lỗ hổng chạy code từ xa)
    log.info('Server lắng nghe %s:%d (debug=%s)', host, port, debug)
    app.run(host=host, port=port, debug=debug, threaded=True)
