"""
API cấu hình từ xa:
    GET    /api/config                 Client định kỳ gọi để lấy cấu hình mới nhất
    POST   /api/config                 Website thiết lập tham số (giới hạn trong CONFIG_LIMITS)
    GET    /api/config/history         lịch sử thay đổi cấu hình
"""
from flask import Blueprint, jsonify, request

from db import get_db, to_json, touch_client
from settings import CONFIG_LIMITS, log
from storage import cleanup_old_images
from timeutil import now_dt

config_bp = Blueprint('config', __name__)


@config_bp.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config WHERE id = 1')
    row = to_json(cur.fetchone())
    touch_client(cur, request.args.get('client_id'), 'config_poll')
    conn.commit()
    conn.close()
    return jsonify(row)


@config_bp.route('/api/config', methods=['POST'])
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


@config_bp.route('/api/config/history', methods=['GET'])
def config_history():
    limit = min(max(1, request.args.get('limit', 50, type=int)), 500)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM config_history ORDER BY id DESC LIMIT %s', (limit,))
    rows = [to_json(r) for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)
