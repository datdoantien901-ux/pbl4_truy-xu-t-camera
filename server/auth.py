"""
Xác thực và phân quyền.

Hai lớp bảo vệ:
  1. Client (máy chụp ảnh) → khóa API: gửi header  X-API-Key: <PBL4_API_KEY>
     Áp dụng cho POST /api/images (gửi ảnh) và GET /api/config (lấy cấu hình).
  2. Người dùng Website → đăng nhập (cookie phiên Flask, mật khẩu băm bằng werkzeug):
       viewer  xem ảnh, xem camera YouTube, xem thống kê
       admin   như viewer + xóa ảnh, đổi cấu hình, quản lý người dùng, thêm/xóa camera YouTube

Chính sách "mặc định từ chối": guard() chạy trước MỌI request, route nào không nằm trong
PUBLIC_ENDPOINTS đều phải đăng nhập (hoặc có khóa API với route của Client).
Route chỉ dành cho admin gắn thêm @admin_required.
"""
import hmac
import threading
import time
from functools import wraps

from flask import g, jsonify, redirect, render_template, request, session, url_for

from db import get_db
from settings import API_KEY, LOGIN_LOCK_SECONDS, LOGIN_MAX_FAILS, log

ROLES = ('admin', 'viewer')
PUBLIC_ENDPOINTS = {'web.page_login', 'web.do_login', 'static'}
CLIENT_ENDPOINTS = {('POST', 'images.upload_image'), ('GET', 'config.get_config')}


# ============ KHÓA API CỦA CLIENT ============
def client_key_status():
    """'ok' (khóa đúng / Server không đặt khóa), 'missing' (không gửi header), 'wrong' (sai khóa)."""
    sent = request.headers.get('X-API-Key')
    if not API_KEY:
        return 'ok'
    if sent is None:
        return 'missing'
    # compare_digest: so sánh thời gian hằng → không đoán được khóa qua thời gian phản hồi
    return 'ok' if hmac.compare_digest(sent.encode(), API_KEY.encode()) else 'wrong'


# ============ NGƯỜI DÙNG ĐANG ĐĂNG NHẬP ============
def _load_user():
    uid = session.get('uid')
    if uid is None:
        return None
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, username, role FROM users WHERE id = %s', (uid,))
    user = cur.fetchone()
    conn.close()
    if user is None or session.get('role') != user['role']:
        session.clear()   # tài khoản bị xóa / đổi quyền → bắt đăng nhập lại
        return None
    return user


def _is_api():
    return request.path.startswith('/api/')


def deny(status, message):
    """API → JSON; trang web → chuyển tới trang đăng nhập (401) hoặc trang báo không đủ quyền (403)."""
    if _is_api() or request.path.startswith('/uploads/'):
        return jsonify({'error': message}), status
    if status == 401:
        return redirect(url_for('web.page_login', next=request.full_path.rstrip('?')))
    return render_template('forbidden.html', message=message), status


def guard():
    """before_request: chặn mọi request chưa đăng nhập (trừ trang đăng nhập, file tĩnh, route của Client)."""
    g.user = None
    g.is_client = False
    ep = request.endpoint
    if ep is None or ep in PUBLIC_ENDPOINTS:
        return None

    if (request.method, ep) in CLIENT_ENDPOINTS:
        status = client_key_status()
        if status == 'wrong':
            log.warning('[AUTH] Sai khóa API từ %s (%s %s)', request.remote_addr, request.method, request.path)
            return deny(401, 'Sai khóa API (X-API-Key)')
        if status == 'ok' and (API_KEY or request.method == 'POST' or request.args.get('client_id')):
            g.is_client = True
            return None
        # Không gửi khóa → coi như người dùng Website (GET /api/config từ trang Cấu hình)

    g.user = _load_user()
    if g.user is None:
        if (request.method, ep) == ('POST', 'images.upload_image'):
            return deny(401, 'Thiếu khóa API (header X-API-Key)')
        return deny(401, 'Chưa đăng nhập')
    return None


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if g.get('user') is None or g.user['role'] != 'admin':
            return deny(403, 'Chỉ quản trị viên (admin) được làm việc này')
        return f(*args, **kwargs)
    return wrapper


def template_context():
    user = g.get('user')
    return {'current_user': user, 'is_admin': bool(user and user['role'] == 'admin')}


# ============ CHỐNG DÒ MẬT KHẨU ============
_fails = {}            # ip → [thời điểm các lần đăng nhập sai]
_fails_lock = threading.Lock()


def login_locked(ip):
    """Còn bị khóa bao nhiêu giây (0 = không khóa)."""
    now = time.time()
    with _fails_lock:
        recent = [t for t in _fails.get(ip, []) if now - t < LOGIN_LOCK_SECONDS]
        _fails[ip] = recent
        if len(recent) >= LOGIN_MAX_FAILS:
            return int(LOGIN_LOCK_SECONDS - (now - recent[0])) + 1
    return 0


def login_failed(ip):
    with _fails_lock:
        _fails.setdefault(ip, []).append(time.time())


def login_succeeded(ip):
    with _fails_lock:
        _fails.pop(ip, None)


def init_app(app):
    app.before_request(guard)
    app.context_processor(template_context)
    if not API_KEY:
        log.warning('[AUTH] Chưa đặt PBL4_API_KEY → Server nhận ảnh từ bất kỳ ai. '
                    'Đặt khóa trong server/.env và client/.env.')
