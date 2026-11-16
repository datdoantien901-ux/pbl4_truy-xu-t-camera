"""
API livestream YouTube (trang /live "Camera YouTube"):
    GET    /api/streams                danh sách livestream đã lưu                 (đăng nhập)
    POST   /api/streams                thêm link {url, title?} — Server kiểm tra   (admin)
    DELETE /api/streams/<id>           xóa                                          (admin)
    PATCH  /api/streams/<id>           {capture: true/false} bật/tắt Client chụp ảnh (admin)
    POST   /api/streams/<id>/select    chọn camera Client chụp (chỉ camera này)        (admin)
    GET    /api/streams/search?q=...   tìm livestream đang phát trên YouTube       (admin)
    GET    /api/streams/<id>/check     kiểm tra link còn phát không                 (đăng nhập)
"""
from flask import Blueprint, g, jsonify, request

import youtube
from auth import admin_required
from db import get_db, to_json
from settings import log
from timeutil import now_dt

streams_bp = Blueprint('streams', __name__)


def _all_streams(cur):
    cur.execute('SELECT * FROM live_streams ORDER BY id')
    return [to_json(r) for r in cur.fetchall()]


@streams_bp.route('/api/streams', methods=['GET'])
def list_streams():
    conn = get_db()
    rows = _all_streams(conn.cursor())
    conn.close()
    return jsonify(rows)


@streams_bp.route('/api/streams', methods=['POST'])
@admin_required
def add_stream():
    data = request.get_json(silent=True) or {}
    video_id = youtube.parse_video_id(data.get('url'))
    if not video_id:
        return jsonify({'error': 'Không nhận ra link YouTube. Dán link dạng youtube.com/watch?v=... '
                                 'hoặc youtu.be/...'}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id FROM live_streams WHERE video_id = %s', (video_id,))
    exists = cur.fetchone()
    conn.close()
    if exists:
        return jsonify({'error': 'Link này đã có trong danh sách'}), 409

    # Hỏi YouTube (1–2 giây) — không giữ kết nối MySQL trong lúc chờ
    info = youtube.inspect(video_id) if youtube.available() else {}
    if 'error' in info:
        return jsonify({'error': 'YouTube báo lỗi: ' + info['error']}), 400
    if info and not info['embeddable']:
        return jsonify({'error': 'Chủ kênh không cho nhúng video này vào trang web khác, '
                                 'không xem được trên Website. Chọn link khác.'}), 400

    title = (data.get('title') or '').strip()[:255] or info.get('title') or video_id
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT IGNORE INTO live_streams (video_id, title, channel, added_by, added_at)
                   VALUES (%s, %s, %s, %s, %s)''',
                (video_id, title, info.get('channel'), g.user['username'], now_dt()))
    conn.commit()   # INSERT IGNORE: 2 admin thêm cùng lúc → chỉ 1 dòng, không lỗi
    cur.execute('SELECT * FROM live_streams WHERE video_id = %s', (video_id,))
    row = to_json(cur.fetchone())
    conn.close()
    log.info('[STREAM] %s thêm %s (%s)', g.user['username'], video_id, title)
    row['live_status'] = info.get('live_status')
    return jsonify(row), 201


@streams_bp.route('/api/streams/<int:stream_id>', methods=['DELETE'])
@admin_required
def delete_stream(stream_id):
    conn = get_db()
    cur = conn.cursor()
    n = cur.execute('DELETE FROM live_streams WHERE id = %s', (stream_id,))
    conn.commit()
    conn.close()
    if not n:
        return jsonify({'error': 'Không tìm thấy'}), 404
    log.info('[STREAM] %s xóa #%d', g.user['username'], stream_id)
    return jsonify({'id': stream_id})


@streams_bp.route('/api/streams/<int:stream_id>', methods=['PATCH'])
@admin_required
def set_capture(stream_id):
    """{capture: true/false} → bật/tắt "Client chụp ảnh" từ livestream này."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data.get('capture'), bool):
        return jsonify({'error': 'Thiếu capture: true / false'}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE live_streams SET capture = %s WHERE id = %s', (int(data['capture']), stream_id))
    cur.execute('SELECT * FROM live_streams WHERE id = %s', (stream_id,))
    row = cur.fetchone()
    conn.commit()
    conn.close()
    if row is None:
        return jsonify({'error': 'Không tìm thấy'}), 404
    log.info('[STREAM] %s %s chụp ảnh từ %s', g.user['username'], 'BẬT' if data['capture'] else 'TẮT', row['video_id'])
    return jsonify(to_json(row))


@streams_bp.route('/api/streams/<int:stream_id>/select', methods=['POST'])
@admin_required
def select_for_capture(stream_id):
    """Admin chọn camera này ở trang Camera trực tiếp → Client chuyển sang chụp ĐÚNG camera này
    (tắt chụp các livestream khác). Client nhận thay đổi ở lần hỏi /api/config kế tiếp (≤ 10 giây)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM live_streams WHERE id = %s', (stream_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'Không tìm thấy'}), 404
    changed = cur.execute('UPDATE live_streams SET capture = (id = %s)', (stream_id,))
    conn.commit()
    conn.close()
    if changed:
        log.info('[STREAM] %s chọn camera %s (%s) cho Client chụp', g.user['username'], row['video_id'], row['title'])
    return jsonify({'id': stream_id, 'video_id': row['video_id'], 'capture': 1})


@streams_bp.route('/api/streams/<int:stream_id>/check', methods=['GET'])
def check_stream(stream_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT video_id FROM live_streams WHERE id = %s', (stream_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Không tìm thấy'}), 404
    return jsonify(youtube.inspect(row['video_id']))


@streams_bp.route('/api/streams/search', methods=['GET'])
@admin_required
def search_streams():
    q = (request.args.get('q') or '').strip()[:100]
    if not q:
        return jsonify({'error': 'Nhập từ khóa tìm kiếm'}), 400
    if not youtube.available():
        return jsonify({'error': 'Server chưa cài yt-dlp (pip install yt-dlp)'}), 503
    try:
        results = youtube.search_live(q)
    except Exception as e:
        log.warning('[STREAM] Tìm "%s" lỗi: %s', q, e)
        return jsonify({'error': 'Không tìm được trên YouTube (kiểm tra kết nối mạng của Server)'}), 502
    conn = get_db()
    added = {r['video_id'] for r in _all_streams(conn.cursor())}
    conn.close()
    for r in results:
        r['added'] = r['video_id'] in added
    return jsonify(results)
