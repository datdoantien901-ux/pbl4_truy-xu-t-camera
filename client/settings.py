"""
Cấu hình chung của Client: đường dẫn, cấu hình mặc định, đọc cấu hình, log.

Thứ tự ưu tiên cấu hình: DEFAULT_SETTINGS < client_config.json < biến môi trường CAMERA_URL
< tham số dòng lệnh.
"""
import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Đường dẫn tính theo vị trí file, không phụ thuộc thư mục đang đứng khi chạy
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_DIR = os.path.join(DATA_DIR, 'images')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
DB_PATH = os.path.join(DATA_DIR, 'client.db')
CONFIG_FILE = os.path.join(BASE_DIR, 'client_config.json')

DEFAULT_SETTINGS = {
    'client_id': 'client-01',
    'source': {
        'type': 'youtube',
        'url': 'https://www.youtube.com/watch?v=oC8ttZHG50I',
        'rtsp_transport': 'tcp',
    },
    'server_url': 'http://127.0.0.1:5000',
    'capture': {'capture_interval': 5, 'jpeg_quality': 80, 'resize_width': 854},
    'config_poll_interval': 10,
    'upload_enabled': True,
    'upload_queue_size': 50,
    'show_preview': True,
    'preview_fps': 5,
}


def now_iso():
    """Thời gian ISO 8601 có mili-giây, thống nhất với Server: 2026-10-29T22:15:03.512"""
    return datetime.now().isoformat(timespec='milliseconds')


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    fmt = logging.Formatter('%(asctime)s [%(threadName)-13s] %(levelname)-5s %(name)s: %(message)s')
    file_h = RotatingFileHandler(os.path.join(LOG_DIR, 'client.log'),
                                 maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    file_h.setFormatter(fmt)
    console_h = logging.StreamHandler(sys.stdout)
    console_h.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [file_h, console_h]


def deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(args):
    settings = dict(DEFAULT_SETTINGS)
    path = args.config or CONFIG_FILE
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            settings = deep_merge(settings, json.load(f))
    # Biến môi trường (để không phải ghi mật khẩu camera vào file commit lên git)
    if os.environ.get('CAMERA_URL'):
        settings['source']['url'] = os.environ['CAMERA_URL']
    # Tham số dòng lệnh ưu tiên cao nhất
    if args.source_type:
        settings['source']['type'] = args.source_type
    if args.source_url:
        settings['source']['url'] = args.source_url
    if args.server:
        settings['server_url'] = args.server
    if args.no_preview:
        settings['show_preview'] = False
    settings['server_url'] = settings['server_url'].rstrip('/')
    return settings
