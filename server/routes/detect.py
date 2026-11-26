"""
API nhận diện vật thể YOLOv5 (detector.py):
    GET    /api/detect/status          luồng YOLO có chạy không, hàng đợi, đã xử lý, thời gian TB   (đăng nhập)
    GET    /api/objects                các loại vật thể đã gặp + số ảnh / số lần (cho ô lọc)       (đăng nhập)
"""
from flask import Blueprint, jsonify

import detector
from db import get_db

detect_bp = Blueprint('detect', __name__)


@detect_bp.route('/api/detect/status', methods=['GET'])
def detect_status():
    st = detector.worker.status()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) AS n FROM images WHERE detected_time IS NULL')
    st['pending'] = cur.fetchone()['n']        # ảnh chưa nhận diện (gồm cả ảnh đang trong hàng đợi)
    cur.execute('SELECT COUNT(*) AS n FROM images WHERE detected_time IS NOT NULL')
    st['detected'] = cur.fetchone()['n']
    conn.close()
    return jsonify(st)


@detect_bp.route('/api/objects', methods=['GET'])
def list_objects():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''SELECT label, COUNT(DISTINCT image_id) AS images, COUNT(*) AS objects
                   FROM detections GROUP BY label ORDER BY images DESC, label''')
    rows = [{**r, 'name': detector.vi_name(r['label'])} for r in cur.fetchall()]
    conn.close()
    return jsonify(rows)
