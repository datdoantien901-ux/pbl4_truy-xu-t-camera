"""
API ảnh:
    GET    /uploads/<file>             trả file ảnh
    POST   /api/images                 nhận ảnh mới (multipart/form-data)
    GET    /api/images                 danh sách (phân trang, lọc theo thời gian, ?camera=<id>)
    GET    /api/images/<id>            chi tiết 1 ảnh
    DELETE /api/images/<id>            xóa ảnh
    POST   /api/images/<id>/displayed  trình duyệt báo ảnh đã hiển thị (đo độ trễ)
"""
import os
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory

from db import get_db, to_json, touch_client
from settings import ALLOWED_EXT, UPLOAD_FOLDER, log
from storage import cleanup_old_images, looks_like_image, remove_file
from timeutil import iso, normalize_time, now_dt, seconds_between

images_bp = Blueprint('images', __name__)


# ============ PHỤC VỤ FILE ẢNH ============
@images_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ============ API: ẢNH ============
@images_bp.route('/api/images', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'Thiếu field "file" trong form-data'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Tên file rỗng'}), 400

    ext = os.path.splitext(file.filename)[1].lower() or '.jpg'
    if ext not in ALLOWED_EXT:
        return jsonify({'error': 'Chỉ nhận .jpg / .jpeg / .png'}), 400
    if not looks_like_image(file.stream.read(8), ext):
        return jsonify({'error': 'Nội dung file không phải ảnh JPEG/PNG hợp lệ'}), 400
    file.stream.seek(0)

    received_time = now_dt()
    form = request.form
    capture_time = normalize_time(form.get('capture_time')) or received_time
    client_id = form.get('client_id')
    client_capture_id = form.get('client_capture_id', type=int)

    conn = get_db()
    cur = conn.cursor()
    # Client gửi lại ảnh đã nhận (mất gói phản hồi) → trả lại id cũ, không lưu trùng
    if client_id and client_capture_id is not None:
        cur.execute('''SELECT * FROM images WHERE client_id = %s AND client_capture_id = %s
                       AND capture_time = %s''', (client_id, client_capture_id, capture_time))
        dup = cur.fetchone()
        if dup:
            conn.close()
            return jsonify({**to_json(dup), 'duplicate': True}), 201

    unique_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
    file_path = os.path.join(UPLOAD_FOLDER, unique_name)
    file.save(file_path)
    file_size_kb = round(os.path.getsize(file_path) / 1024, 2)

    cur.execute('''
        INSERT INTO images (file_name, file_path, capture_time, received_time, file_size_kb,
                            width, height, sent_time, client_id, client_capture_id, client_ip,
                            original_name, source, interval_used, quality_used)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (unique_name, f'uploads/{unique_name}', capture_time, received_time, file_size_kb,
          form.get('width', type=int), form.get('height', type=int),
          normalize_time(form.get('sent_time')), client_id, client_capture_id,
          request.remote_addr, file.filename, form.get('source'),
          form.get('interval_used', type=int), form.get('quality_used', type=int)))
    image_id = cur.lastrowid
    touch_client(cur, client_id, 'upload')
    conn.commit()
    conn.close()

    log.info('[RECV] #%d từ %s (%s) | %.2f KB | trễ chụp→nhận %ss', image_id,
             client_id or '?', request.remote_addr, file_size_kb,
             seconds_between(capture_time, received_time))
    cleanup_old_images()

    return jsonify({
        'id': image_id,
        'file_name': unique_name,
        'file_path': f'uploads/{unique_name}',
        'file_size_kb': file_size_kb,
        'received_time': iso(received_time),
    }), 201


@images_bp.route('/api/images', methods=['GET'])
def list_images():
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    start = normalize_time(request.args.get('start'))
    end = normalize_time(request.args.get('end'))
    q = (request.args.get('q') or '').strip()
    camera = (request.args.get('camera') or '').strip()   # id camera = cột source

    where, params = [], []
    if camera:
        where.append('source = %s')
        params.append(camera)
    if start:
        where.append('capture_time >= %s')
        params.append(start)
    if end:
        where.append('capture_time <= %s')
        params.append(end)
    if q:
        where.append('(file_name LIKE %s OR original_name LIKE %s OR client_id LIKE %s)')
        params += [f'%{q}%'] * 3
    where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) AS n FROM images {where_sql}', params)
    total = cur.fetchone()['n']
    cur.execute(f'SELECT * FROM images {where_sql} ORDER BY id DESC LIMIT %s OFFSET %s',
                params + [per_page, (page - 1) * per_page])
    items = [to_json(r) for r in cur.fetchall()]
    conn.close()

    return jsonify({
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': (total + per_page - 1) // per_page,
        'items': items,
    })


@images_bp.route('/api/images/<int:image_id>', methods=['GET'])
def get_image(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return jsonify({'error': 'Không tìm thấy ảnh'}), 404
    return jsonify(to_json(row))


@images_bp.route('/api/images/<int:image_id>', methods=['DELETE'])
def delete_image(image_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT file_path FROM images WHERE id = %s', (image_id,))
    row = cur.fetchone()
    if row is None:
        conn.close()
        return jsonify({'error': 'Không tìm thấy ảnh'}), 404
    remove_file(row['file_path'])
    cur.execute('DELETE FROM images WHERE id = %s', (image_id,))
    conn.commit()
    conn.close()
    log.info('[DELETE] #%d bởi %s', image_id, request.remote_addr)
    return jsonify({'message': 'Đã xóa', 'id': image_id})


@images_bp.route('/api/images/<int:image_id>/displayed', methods=['POST'])
def mark_displayed(image_id):
    """Gallery gọi khi ảnh lần đầu hiện lên màn hình → đo độ trễ chụp → hiển thị."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE images SET displayed_time = %s WHERE id = %s AND displayed_time IS NULL',
                (now_dt(), image_id))
    conn.commit()
    conn.close()
    return jsonify({'id': image_id})
