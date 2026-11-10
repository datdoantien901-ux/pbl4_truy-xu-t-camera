"""
Cấu hình chung của Server: đường dẫn, kết nối MySQL, giới hạn tham số, log.
Đổi cấu hình MySQL bằng biến môi trường MYSQL_HOST, MYSQL_PORT, MYSQL_USER,
MYSQL_PASSWORD, MYSQL_DATABASE, hoặc ghi vào server/.env (chép từ .env.example;
file .env không commit lên git).
"""
import logging
import os
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path):
    """Đọc file .env (mỗi dòng KEY=VALUE) vào biến môi trường. Biến đã đặt sẵn được ưu tiên."""
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8-sig') as f:  # utf-8-sig: chịu được BOM khi lưu bằng Notepad
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


_load_env_file(os.path.join(BASE_DIR, '.env'))

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
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB/ảnh
CONFIG_LIMITS = [  # (tên, min, max)
    ('capture_interval', 1, 3600),
    ('jpeg_quality', 10, 100),
    ('resize_width', 160, 3840),
    ('max_images', 1, 10000),
]

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ============ LOG ============
log = logging.getLogger('server')
if not log.handlers:
    _h = RotatingFileHandler(os.path.join(LOG_DIR, 'server.log'),
                             maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    _h.setFormatter(logging.Formatter('%(asctime)s [%(threadName)s] %(levelname)s: %(message)s'))
    log.addHandler(_h)
    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.INFO)
