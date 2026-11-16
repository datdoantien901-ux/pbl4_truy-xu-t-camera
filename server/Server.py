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
    routes/web.py       trang web     /login  /  /live  /manage  /config  /users  /stats  /image/<id>
    routes/streams.py   API camera YouTube  /api/streams...
    routes/ipcams.py    API camera IP /api/ipcams..., luồng MJPEG /ipcam/<id>/stream
    ipcam.py            đọc camera IP bằng OpenCV, phát MJPEG (1 luồng đọc / camera)
    routes/users.py     API tài khoản /api/me, /api/users...
    auth.py             đăng nhập (admin / viewer) + khóa API của Client
    youtube.py          kiểm tra / tìm livestream YouTube bằng yt-dlp

CSDL: MySQL, cấu hình qua biến môi trường MYSQL_HOST, MYSQL_PORT, MYSQL_USER,
      MYSQL_PASSWORD, MYSQL_DATABASE (database và bảng tự tạo khi chạy).

Chạy:  python Server.py               (mặc định lắng nghe 0.0.0.0:5000, debug tắt)
       PBL4_PORT=8000 python Server.py
"""
import os
import secrets

from flask import Flask

import auth
from db import init_db
from routes.config import config_bp
from routes.images import images_bp
from routes.ipcams import ipcams_bp
from routes.monitor import monitor_bp
from routes.streams import streams_bp
from routes.users import users_bp
from routes.web import web_bp
from settings import MAX_CONTENT_LENGTH, SECRET_KEY, log

app = Flask(__name__)
app.config.update(
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
    SECRET_KEY=SECRET_KEY or secrets.token_hex(32),   # khóa ký cookie phiên đăng nhập
    SESSION_COOKIE_HTTPONLY=True,     # JavaScript không đọc được cookie phiên
    SESSION_COOKIE_SAMESITE='Lax',    # trang web lạ không gửi kèm cookie khi POST/DELETE (chống CSRF)
)
# Không bật CORS: Website và API cùng một địa chỉ, trang web khác không được gọi API bằng phiên đăng nhập
for bp in (images_bp, config_bp, monitor_bp, streams_bp, ipcams_bp, users_bp, web_bp):
    app.register_blueprint(bp)
auth.init_app(app)
if not SECRET_KEY:
    log.warning('[AUTH] Chưa đặt PBL4_SECRET_KEY → mỗi lần khởi động lại Server phải đăng nhập lại')

# Khởi tạo DB ngay khi import (chạy được cả bằng `python Server.py` lẫn `flask run`)
init_db()

if __name__ == '__main__':
    host = os.environ.get('PBL4_HOST', '0.0.0.0')   # 0.0.0.0 để máy khác trong LAN truy cập được
    port = int(os.environ.get('PBL4_PORT', 5000))
    debug = os.environ.get('PBL4_DEBUG') == '1'     # KHÔNG bật debug khi mở ra LAN (lỗ hổng chạy code từ xa)
    log.info('Server lắng nghe %s:%d (debug=%s)', host, port, debug)
    app.run(host=host, port=port, debug=debug, threaded=True)
