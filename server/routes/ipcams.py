"""
Camera IP xem trực tiếp (trang /ipcam):
    GET    /api/ipcams                 danh sách camera đã lưu (URL đã ẩn mật khẩu)      (đăng nhập)
    GET    /api/ipcams/presets         các loại camera / mẫu đường dẫn theo hãng          (đăng nhập)
    POST   /api/ipcams/test            thử kết nối {preset, ip, port, user, password} hoặc {url}
                                       → 1 ảnh JPEG chụp từ camera                        (admin)
    POST   /api/ipcams                 lưu camera {name, ...như test}                       (admin)
    DELETE /api/ipcams/<id>            xóa                                                  (admin)
    GET    /ipcam/<id>/stream          luồng MJPEG để trình duyệt hiển thị bằng <img>      (đăng nhập)
    GET    /api/ipcams/<id>/status     luồng đọc đang chạy? bao nhiêu người xem? lỗi?      (đăng nhập)

Chỉ admin được nhập IP / URL mới: Server sẽ kết nối tới địa chỉ đó, không để người xem
bắt Server dò các máy khác trong mạng (SSRF).
"""
from flask import Blueprint, Response, g, jsonify, request

import ipcam
from auth import admin_required
from db import get_db, to_json
from settings import log
from timeutil import now_dt

ipcams_bp = Blueprint('ipcams', __name__)


def _url_from(data):
    """Body {url} hoặc {preset, ip, port, user, password} → (url, lỗi)."""
    if data.get('url'):
        return ipcam.check_url(data['url'])
    return ipcam.build_url(data.get('preset'), data.get('ip'), data.get('port'),
                           (data.get('user') or '').strip(), data.get('password') or '')


def _public(row):
    row = to_json(row)
    row['url'] = ipcam.mask_url(row['url'])   # không gửi mật khẩu camera ra trình duyệt
    return row


def _get(cam_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM ip_cameras WHERE id = %s', (cam_id,))
    row = cur.fetchone()
    conn.close()
    return row


@ipcams_bp.route('/api/ipcams', methods=['GET'])
def list_ipcams():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM ip_cameras ORDER BY id')
    rows = [_public(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        r['status'] = ipcam.hub.status(r['id'])
    return jsonify(rows)


@ipcams_bp.route('/api/ipcams/presets', methods=['GET'])
def presets():
    return jsonify([{'id': k, 'name': v[0], 'pattern': v[1].replace('{auth}', ''), 'port': v[2]}
                    for k, v in ipcam.PRESETS.items()] + [{'id': 'url', 'name': 'Tự nhập URL đầy đủ'}])


@ipcams_bp.route('/api/ipcams/test', methods=['POST'])
@admin_required
def test_ipcam():
    if not ipcam.available():
        return jsonify({'error': 'Server chưa cài OpenCV (pip install opencv-python)'}), 503
    url, err = _url_from(request.get_json(silent=True) or {})
    if err:
        return jsonify({'error': err}), 400
    log.info('[IPCAM] %s thử kết nối %s', g.user['username'], ipcam.mask_url(url))
    jpg, w, h, err = ipcam.snapshot(url)
    if err:
        return jsonify({'error': err, 'url': ipcam.mask_url(url)}), 502
    return Response(jpg, mimetype='image/jpeg', headers={'X-Width': str(w), 'X-Height': str(h),
                                                          'Cache-Control': 'no-store'})


@ipcams_bp.route('/api/ipcams', methods=['POST'])
@admin_required
def add_ipcam():
    data = request.get_json(silent=True) or {}
    url, err = _url_from(data)
    if err:
        return jsonify({'error': err}), 400
    name = (data.get('name') or '').strip()[:100] or ipcam.mask_url(url)[:100]
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT INTO ip_cameras (name, url, added_by, added_at) VALUES (%s, %s, %s, %s)',
                (name, url, g.user['username'], now_dt()))
    new_id = cur.lastrowid
    conn.commit()
    cur.execute('SELECT * FROM ip_cameras WHERE id = %s', (new_id,))
    row = _public(cur.fetchone())
    conn.close()
    log.info('[IPCAM] %s lưu camera #%d %s (%s)', g.user['username'], new_id, name, row['url'])
    return jsonify(row), 201


@ipcams_bp.route('/api/ipcams/<int:cam_id>', methods=['DELETE'])
@admin_required
def delete_ipcam(cam_id):
    conn = get_db()
    cur = conn.cursor()
    n = cur.execute('DELETE FROM ip_cameras WHERE id = %s', (cam_id,))
    conn.commit()
    conn.close()
    if not n:
        return jsonify({'error': 'Không tìm thấy camera'}), 404
    ipcam.hub.stop(cam_id)
    log.info('[IPCAM] %s xóa camera #%d', g.user['username'], cam_id)
    return jsonify({'id': cam_id})


@ipcams_bp.route('/api/ipcams/<int:cam_id>/status', methods=['GET'])
def ipcam_status(cam_id):
    return jsonify(ipcam.hub.status(cam_id))


@ipcams_bp.route('/ipcam/<int:cam_id>/stream')
def stream(cam_id):
    if not ipcam.available():
        return jsonify({'error': 'Server chưa cài OpenCV'}), 503
    row = _get(cam_id)
    if row is None:
        return jsonify({'error': 'Không tìm thấy camera'}), 404
    return Response(ipcam.hub.mjpeg(cam_id, row['url'], row['name']),
                    mimetype='multipart/x-mixed-replace; boundary=frame',
                    headers={'Cache-Control': 'no-store'})
