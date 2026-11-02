"""
Cấu hình chung của Client: đường dẫn, cấu hình mặc định, đọc cấu hình, danh sách camera, log.

Thứ tự ưu tiên cấu hình: DEFAULT_SETTINGS < client_config.json < biến môi trường (CAMERA_URL,
url_env của từng camera, đọc cả từ client/.env) < tham số dòng lệnh.

Nhiều camera: khai báo mảng "cameras" trong client_config.json, mỗi camera chạy một luồng chụp
riêng. Không có "cameras" (hoặc truyền --source-type / --source-url) → 1 camera từ "source".
"""
import copy
import json
import logging
import os
import re
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
ENV_FILE = os.path.join(BASE_DIR, '.env')

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

log = logging.getLogger('client')


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


def load_env_file(path=ENV_FILE):
    """Đọc file .env (mỗi dòng KEY=VALUE) vào biến môi trường. Biến đã đặt sẵn được ưu tiên.
    Dùng để giữ link camera có mật khẩu ngoài git (.env nằm trong .gitignore)."""
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8-sig') as f:  # utf-8-sig: chịu được BOM khi lưu bằng Notepad
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def deep_merge(base, override):
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(args):
    load_env_file()
    settings = copy.deepcopy(DEFAULT_SETTINGS)
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
    if args.source_type or args.source_url:
        settings['cameras'] = None   # chỉ định nguồn trên dòng lệnh → chạy đúng 1 camera đó
    if args.server:
        settings['server_url'] = args.server
    if args.no_preview:
        settings['show_preview'] = False
    settings['server_url'] = settings['server_url'].rstrip('/')
    return settings


def load_cameras(settings):
    """Danh sách camera sẽ chạy, mỗi phần tử: {'id', 'name', 'source': {type, url, rtsp_transport}}.

    Mỗi camera trong client_config.json:
        id       tên ngắn (chữ, số, - _), dùng làm tên luồng, thư mục ảnh, trường "source" gửi lên Server
        name     tên hiển thị (tùy chọn)
        enabled  false → bỏ qua (tùy chọn)
        url_env  tên biến môi trường chứa URL (tùy chọn) — URL có mật khẩu đặt trong client/.env
        source   {type, url, rtsp_transport} như cấu hình 1 nguồn
    Camera chưa có URL → bỏ qua kèm cảnh báo, các camera khác vẫn chạy.
    """
    cams = settings.get('cameras')
    if not cams:
        src = settings['source']
        cams = [{'id': src['type'], 'name': src['type'], 'source': src}]

    result, seen = [], set()
    for i, cam in enumerate(cams, 1):
        cam_id = re.sub(r'[^A-Za-z0-9_-]', '-', str(cam.get('id') or f'cam{i}'))
        if not cam.get('enabled', True):
            log.info('Camera "%s" đang tắt (enabled=false) → bỏ qua', cam_id)
            continue
        if cam_id in seen:
            raise ValueError(f'Trùng id camera "{cam_id}" trong cấu hình')
        seen.add(cam_id)

        src = dict(cam.get('source') or {})
        env = cam.get('url_env')
        if env and os.environ.get(env):
            src['url'] = os.environ[env]
        if src.get('url') in (None, ''):
            log.warning('Camera "%s" chưa có URL%s → bỏ qua', cam_id,
                        f' (đặt {env} trong client/.env)' if env else '')
            continue
        src.setdefault('rtsp_transport', 'tcp')
        result.append({'id': cam_id, 'name': cam.get('name') or cam_id, 'source': src})
    return result
