"""
API tài khoản:
    GET    /api/me                     người dùng đang đăng nhập             (đăng nhập)
    POST   /api/me/password            tự đổi mật khẩu {old, new}            (đăng nhập)
    GET    /api/users                  danh sách tài khoản                   (admin)
    POST   /api/users                  tạo tài khoản {username, password, role}  (admin)
    PATCH  /api/users/<id>             đổi quyền / đặt lại mật khẩu {role?, password?}  (admin)
    DELETE /api/users/<id>             xóa tài khoản                         (admin)
Không cho admin tự xóa / tự hạ quyền mình, không xóa admin cuối cùng (tránh mất quyền quản trị).
"""
import re

from flask import Blueprint, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from auth import ROLES, admin_required
from db import get_db, to_json
from settings import log
from timeutil import now_dt

users_bp = Blueprint('users', __name__)
MIN_PASSWORD = 6


def _check_password(pw):
    if not isinstance(pw, str) or len(pw) < MIN_PASSWORD:
        return f'Mật khẩu phải có ít nhất {MIN_PASSWORD} ký tự'
    return None


@users_bp.route('/api/me', methods=['GET'])
def me():
    return jsonify(g.user)


@users_bp.route('/api/me/password', methods=['POST'])
def change_own_password():
    data = request.get_json(silent=True) or {}
    err = _check_password(data.get('new'))
    if err:
        return jsonify({'error': err}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT password_hash FROM users WHERE id = %s', (g.user['id'],))
    row = cur.fetchone()
    if not check_password_hash(row['password_hash'], data.get('old') or ''):
        conn.close()
        return jsonify({'error': 'Mật khẩu hiện tại không đúng'}), 400
    cur.execute('UPDATE users SET password_hash = %s WHERE id = %s',
                (generate_password_hash(data['new']), g.user['id']))
    conn.commit()
    conn.close()
    log.info('[USER] %s đổi mật khẩu', g.user['username'])
    return jsonify({'message': 'Đã đổi mật khẩu'})


@users_bp.route('/api/users', methods=['GET'])
@admin_required
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, username, role, created_at, last_login FROM users ORDER BY id')
    rows = [to_json(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)


@users_bp.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    role = data.get('role', 'viewer')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}', username):
        return jsonify({'error': 'Tên đăng nhập 3–50 ký tự, chỉ gồm chữ không dấu, số, . _ -'}), 400
    if role not in ROLES:
        return jsonify({'error': 'Quyền phải là admin hoặc viewer'}), 400
    err = _check_password(data.get('password'))
    if err:
        return jsonify({'error': err}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM users WHERE username = %s', (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({'error': f'Tên đăng nhập "{username}" đã có'}), 409
    cur.execute('INSERT INTO users (username, password_hash, role, created_at) VALUES (%s, %s, %s, %s)',
                (username, generate_password_hash(data['password']), role, now_dt()))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    log.info('[USER] %s tạo tài khoản %s (%s)', g.user['username'], username, role)
    return jsonify({'id': new_id, 'username': username, 'role': role}), 201


def _admin_count(cur):
    cur.execute("SELECT COUNT(*) AS n FROM users WHERE role = 'admin'")
    return cur.fetchone()['n']


@users_bp.route('/api/users/<int:user_id>', methods=['PATCH'])
@admin_required
def update_user(user_id):
    data = request.get_json(silent=True) or {}
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, username, role FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    if user is None:
        conn.close()
        return jsonify({'error': 'Không tìm thấy tài khoản'}), 404

    changes = []
    if 'role' in data and data['role'] != user['role']:
        if data['role'] not in ROLES:
            conn.close()
            return jsonify({'error': 'Quyền phải là admin hoặc viewer'}), 400
        if user_id == g.user['id']:
            conn.close()
            return jsonify({'error': 'Không tự hạ quyền của chính mình'}), 400
        cur.execute('UPDATE users SET role = %s WHERE id = %s', (data['role'], user_id))
        changes.append(f"quyền → {data['role']}")
    if data.get('password'):
        err = _check_password(data['password'])
        if err:
            conn.close()
            return jsonify({'error': err}), 400
        cur.execute('UPDATE users SET password_hash = %s WHERE id = %s',
                    (generate_password_hash(data['password']), user_id))
        changes.append('đặt lại mật khẩu')
    conn.commit()
    conn.close()
    if changes:
        log.info('[USER] %s sửa %s: %s', g.user['username'], user['username'], ', '.join(changes))
    return jsonify({'id': user_id, 'changes': changes})


@users_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    if user_id == g.user['id']:
        return jsonify({'error': 'Không tự xóa tài khoản đang đăng nhập'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT username, role FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    if user is None:
        conn.close()
        return jsonify({'error': 'Không tìm thấy tài khoản'}), 404
    if user['role'] == 'admin' and _admin_count(cur) <= 1:
        conn.close()
        return jsonify({'error': 'Không xóa admin cuối cùng'}), 400
    cur.execute('DELETE FROM users WHERE id = %s', (user_id,))
    conn.commit()
    conn.close()
    log.info('[USER] %s xóa tài khoản %s', g.user['username'], user['username'])
    return jsonify({'id': user_id})

