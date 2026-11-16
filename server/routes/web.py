"""
Các trang web (template trong server/templates/):
    /login        đăng nhập                 (công khai)
    /logout       đăng xuất (POST)
    /login/guest  vào chế độ khách (chỉ xem) (POST, công khai)
    /live         camera trực tiếp (YouTube) — trang mặc định
    /ipcam        camera IP: nhập IP → xem trực tiếp (MJPEG qua Server)
    /             ảnh Client gửi lên (gallery real-time)
    /manage       quản lý ảnh               (đăng nhập; nút xóa chỉ admin thấy)
    /stats        thống kê độ trễ           (đăng nhập)
    /image/<id>   chi tiết 1 ảnh            (đăng nhập)
    /account      tài khoản, đổi mật khẩu   (đăng nhập)
    /config       cấu hình Client từ xa     (admin)
    /users        quản lý người dùng        (admin)
"""
from urllib.parse import urlparse

from flask import Blueprint, abort, g, redirect, render_template, request, session
from werkzeug.security import check_password_hash

from auth import admin_required, login_failed, login_locked, login_succeeded
from db import get_db, to_json
from settings import ALLOW_GUEST, log
from timeutil import now_dt, seconds_between

web_bp = Blueprint('web', __name__)


def _safe_next(url):
    """Chỉ cho chuyển về đường dẫn nội bộ (/...), chặn chuyển hướng sang trang lạ (open redirect)."""
    if url and url.startswith('/') and not url.startswith('//') and not urlparse(url).netloc and url != '/':
        return url
    return '/live'   # trang mặc định sau khi vào: Camera trực tiếp


@web_bp.route('/login', methods=['GET'])
def page_login():
    if session.get('uid') or (session.get('guest') and ALLOW_GUEST):
        return redirect('/live')
    return render_template('login.html', next=_safe_next(request.args.get('next')),
                           allow_guest=ALLOW_GUEST, mode=request.args.get('mode'))


@web_bp.route('/login/guest', methods=['POST'])
def guest_login():
    """Người xem: vào thẳng, không mật khẩu, chỉ xem."""
    if not ALLOW_GUEST:
        return redirect('/login?mode=admin')
    session.clear()
    session.permanent = True
    session['guest'] = True
    log.info('[AUTH] Khách (chỉ xem) vào từ %s', request.remote_addr)
    return redirect(_safe_next(request.form.get('next')))


@web_bp.route('/login', methods=['POST'])
def do_login():
    ip = request.remote_addr
    username = (request.form.get('username') or '').strip()
    next_url = _safe_next(request.form.get('next'))

    wait = login_locked(ip)
    if wait:
        return render_template('login.html', next=next_url, username=username, allow_guest=ALLOW_GUEST,
                               mode='admin', error=f'Sai mật khẩu quá nhiều lần. Thử lại sau {wait} giây.'), 429

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, username, password_hash, role FROM users WHERE username = %s', (username,))
    user = cur.fetchone()
    if user is None or not check_password_hash(user['password_hash'], request.form.get('password') or ''):
        conn.close()
        login_failed(ip)
        log.warning('[AUTH] Đăng nhập sai: "%s" từ %s', username, ip)
        return render_template('login.html', next=next_url, username=username, allow_guest=ALLOW_GUEST,
                               mode='admin', error='Sai tên đăng nhập hoặc mật khẩu.'), 401
    cur.execute('UPDATE users SET last_login = %s WHERE id = %s', (now_dt(), user['id']))
    conn.commit()
    conn.close()

    login_succeeded(ip)
    session.clear()             # cấp phiên mới → chống chiếm phiên (session fixation)
    session.permanent = True    # hết hạn sau SESSION_HOURS
    session['uid'] = user['id']
    session['role'] = user['role']
    log.info('[AUTH] %s (%s) đăng nhập từ %s', user['username'], user['role'], ip)
    return redirect(next_url)


@web_bp.route('/logout', methods=['POST'])
def logout():
    log.info('[AUTH] %s đăng xuất', g.user['username'])
    next_mode = '?mode=admin' if g.user.get('guest') and request.form.get('to') == 'admin' else ''
    session.clear()
    return redirect('/login' + next_mode)


@web_bp.route('/')
def page_index():
    return render_template('index.html')


@web_bp.route('/live')
def page_live():
    return render_template('live.html')


@web_bp.route('/manage')
def page_manage():
    return render_template('manage.html')


@web_bp.route('/config')
@admin_required
def page_config():
    return render_template('config.html')


@web_bp.route('/ipcam')
def page_ipcam():
    return render_template('ipcam.html')


@web_bp.route('/account')
def page_account():
    if g.user.get('guest'):
        return redirect('/login?mode=admin')
    return render_template('account.html')


@web_bp.route('/users')
@admin_required
def page_users():
    return render_template('users.html')


@web_bp.route('/stats')
def page_stats():
    return render_template('stats.html')


@web_bp.route('/image/<int:image_id>')
def page_detail(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        abort(404)
    # detail.html cắt chuỗi thời gian (capture_time[8:10]) → phải truyền chuỗi ISO, không truyền datetime
    img = to_json(row)
    img['capture_to_received'] = seconds_between(row['capture_time'], row['received_time'])
    img['capture_to_display'] = seconds_between(row['capture_time'], row.get('displayed_time'))
    return render_template('detail.html', image=img)
