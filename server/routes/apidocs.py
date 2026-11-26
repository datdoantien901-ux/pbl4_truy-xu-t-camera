"""
Tài liệu API (Swagger):
    GET    /apidocs                    trang Swagger UI: xem và gọi thử mọi API     (đăng nhập)
    GET    /api/openapi.json           đặc tả OpenAPI 3.0 (nội dung ở openapi.py)  (đăng nhập)

Swagger UI tải từ CDN jsdelivr → máy xem cần có Internet (giống video YouTube).
"""
from flask import Blueprint, jsonify, render_template, request

import openapi

apidocs_bp = Blueprint('apidocs', __name__)


@apidocs_bp.route('/api/openapi.json', methods=['GET'])
def openapi_json():
    return jsonify(openapi.spec(request.host_url.rstrip('/')))


@apidocs_bp.route('/apidocs')
def page_apidocs():
    return render_template('apidocs.html')
