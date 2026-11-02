"""
Các trang web (template trong server/templates/):
    /             gallery real-time
    /manage       quản lý ảnh
    /config       cấu hình Client từ xa
    /stats        thống kê độ trễ
    /image/<id>   chi tiết 1 ảnh
"""
from flask import Blueprint, abort, render_template

from db import get_db, to_json
from timeutil import seconds_between

web_bp = Blueprint('web', __name__)


@web_bp.route('/')
def page_index():
    return render_template('index.html')


@web_bp.route('/manage')
def page_manage():
    return render_template('manage.html')


@web_bp.route('/config')
def page_config():
    return render_template('config.html')


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
