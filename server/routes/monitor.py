"""
API giám sát / kiểm thử:
    GET    /api/stats                  thống kê độ trễ, chu kỳ chụp thực tế
    GET    /api/clients                các Client đang kết nối (IP, lần cuối thấy)
    GET    /api/cameras                các camera: đã gửi ảnh (cột source) + Client khai báo
"""
import statistics
from datetime import datetime

from flask import Blueprint, jsonify, request

from db import get_db, to_json
from timeutil import iso, seconds_between

monitor_bp = Blueprint('monitor', __name__)


@monitor_bp.route('/api/clients', methods=['GET'])
def list_clients():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM clients ORDER BY last_seen DESC')
    rows = cur.fetchall()
    conn.close()
    now = datetime.now()
    result = []
    for r in rows:
        seen = r['last_seen']
        item = to_json(r)
        item['seconds_ago'] = round((now - seen).total_seconds(), 1) if seen else None
        item['online'] = item['seconds_ago'] is not None and item['seconds_ago'] < 30
        result.append(item)
    return jsonify(result)


@monitor_bp.route('/api/cameras', methods=['GET'])
def list_cameras():
    """Danh sách camera cho ô chọn trên Website. Thứ tự: camera Client khai báo (đúng thứ tự cấu hình),
    sau đó camera chỉ còn ảnh cũ (vd Client đã bỏ camera đó khỏi cấu hình)."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''SELECT source, COUNT(*) AS n, MAX(capture_time) AS last_capture FROM images
                   WHERE source IS NOT NULL AND source <> '' GROUP BY source''')
    stats = {r['source']: r for r in cur.fetchall()}
    cur.execute("SELECT client_id, cameras FROM clients WHERE cameras IS NOT NULL AND cameras <> '' "
                'ORDER BY client_id')
    declared = {}
    for r in cur.fetchall():
        for cam in r['cameras'].split(','):
            declared.setdefault(cam, []).append(r['client_id'])
    conn.close()

    result = []
    for cam in list(declared) + sorted(set(stats) - set(declared)):
        s = stats.get(cam)
        result.append({'id': cam,
                       'image_count': s['n'] if s else 0,
                       'last_capture': iso(s['last_capture']) if s else None,
                       'clients': declared.get(cam, [])})
    return jsonify(result)


def _summary(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    vals_sorted = sorted(vals)
    p95 = vals_sorted[min(len(vals_sorted) - 1, int(round(0.95 * (len(vals_sorted) - 1))))]
    return {'count': len(vals), 'avg': round(statistics.mean(vals), 3),
            'min': round(vals_sorted[0], 3), 'max': round(vals_sorted[-1], 3), 'p95': round(p95, 3)}


@monitor_bp.route('/api/stats', methods=['GET'])
def stats():
    """
    Độ trễ (giây) cho N ảnh gần nhất:
      capture_to_received : chụp ở Client → Server nhận xong
      sent_to_received    : Client bắt đầu gửi → Server nhận xong (thời gian truyền qua mạng)
      capture_to_display  : chụp → ảnh hiện trên Website
      actual_gap          : khoảng cách thực tế giữa 2 lần chụp của cùng 1 camera (so với interval_used)
    Lưu ý: Client và Server ở 2 máy khác nhau phải đồng bộ đồng hồ (NTP) thì số liệu mới đúng.
    """
    limit = min(max(2, request.args.get('limit', 100, type=int)), 1000)
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images ORDER BY capture_time DESC, id DESC LIMIT %s', (limit,))
    rows = cur.fetchall()
    cur.execute('SELECT COUNT(*) AS n FROM images')
    total = cur.fetchone()['n']
    conn.close()

    rows.reverse()  # cũ → mới để tính khoảng cách giữa các lần chụp
    items = []
    # 1 Client có thể chạy nhiều camera (cột source = id camera) → tính khoảng cách theo từng camera
    last_capture = {}
    for r in rows:
        gap = None
        key = (r.get('client_id'), r.get('source'))
        if r.get('client_id') and key in last_capture:
            gap = seconds_between(last_capture[key], r['capture_time'])
        last_capture[key] = r['capture_time']
        items.append({
            'id': r['id'],
            'client_id': r.get('client_id'),
            'source': r.get('source'),
            'capture_time': iso(r['capture_time']),
            'interval_used': r.get('interval_used'),
            'actual_gap': gap,
            'capture_to_received': seconds_between(r['capture_time'], r['received_time']),
            'sent_to_received': seconds_between(r.get('sent_time'), r['received_time']),
            'capture_to_display': seconds_between(r['capture_time'], r.get('displayed_time')),
            'file_size_kb': r['file_size_kb'],
        })
    items.reverse()

    return jsonify({
        'total_images': total,
        'sample_size': len(items),
        'summary': {k: _summary([i[k] for i in items])
                    for k in ('capture_to_received', 'sent_to_received', 'capture_to_display', 'actual_gap')},
        'items': items,
    })
