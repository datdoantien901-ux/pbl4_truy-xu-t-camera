"""
Tài liệu API theo chuẩn OpenAPI 3.0 — hiển thị bằng Swagger UI ở trang /apidocs (routes/apidocs.py).

Viết bằng dict Python (không cần cài thêm thư viện). Thêm / sửa API ở routes/*.py thì sửa cả ở đây:
mỗi API là một mục trong PATHS, dùng các hàm tắt bên dưới cho gọn.

Quyền (cột "security"):
    CLIENT  khóa API — header X-API-Key (Client chụp ảnh)
    LOGIN   đã vào Website (cookie phiên: Quản trị viên hoặc Khách)
    ADMIN   cookie phiên của Quản trị viên
"""
from settings import CONFIG_LIMITS

# ---------------------------------------------------------------- hàm tắt
CLIENT = [{'apiKey': []}]
LOGIN = [{'session': []}]
ADMIN = LOGIN          # cùng cookie phiên; Server kiểm tra thêm role = admin (sai quyền → 403)


def ref(name):
    return {'$ref': f'#/components/schemas/{name}'}


def arr(item):
    return {'type': 'array', 'items': item}


def obj(required=None, **props):
    o = {'type': 'object', 'properties': props}
    if required:
        o['required'] = required
    return o


def s(desc=None, example=None, fmt=None, **kw):       # chuỗi
    d = {'type': 'string', **kw}
    if desc: d['description'] = desc
    if example is not None: d['example'] = example
    if fmt: d['format'] = fmt
    return d


def i(desc=None, example=None, **kw):                 # số nguyên
    d = {'type': 'integer', **kw}
    if desc: d['description'] = desc
    if example is not None: d['example'] = example
    return d


def n(desc=None, example=None):                       # số thực
    d = {'type': 'number'}
    if desc: d['description'] = desc
    if example is not None: d['example'] = example
    return d


def b(desc=None):
    return {'type': 'boolean', **({'description': desc} if desc else {})}


def t(desc=None):                                     # thời gian ISO có mili giây
    return s(desc, '2026-11-26T09:15:30.125', nullable=True)


def json_ok(schema, desc='Thành công', code='200'):
    return {code: {'description': desc, 'content': {'application/json': {'schema': schema}}}}


def err(code, desc):
    return {str(code): {'description': desc, 'content': {'application/json': {'schema': ref('Error')}}}}


def body(schema, required=True):
    return {'required': required, 'content': {'application/json': {'schema': schema}}}


def q(name, schema, desc, required=False):            # tham số trên URL (?name=)
    return {'name': name, 'in': 'query', 'required': required, 'description': desc, 'schema': schema}


def p(name, desc='id'):                               # tham số trong đường dẫn (/<id>)
    return {'name': name, 'in': 'path', 'required': True, 'description': desc, 'schema': {'type': 'integer'}}


def op(tag, summary, security, responses, desc=None, params=None, req=None):
    o = {'tags': [tag], 'summary': summary, 'security': security, 'responses': responses}
    if desc: o['description'] = desc
    if params: o['parameters'] = params
    if req: o['requestBody'] = req
    if security is LOGIN or security is ADMIN:
        o['responses'] = {**o['responses'], **err(401, 'Chưa đăng nhập')}
    if security is ADMIN and summary.endswith('(admin)'):
        o['responses'] = {**o['responses'], **err(403, 'Không phải quản trị viên')}
    return o


ID_ONLY = obj(id=i(example=3))
CAPTURE_BODY = body(obj(['capture'], capture=b('true = Client chụp ảnh từ camera này')))

# ---------------------------------------------------------------- kiểu dữ liệu
LIMITS = {k: (lo, hi) for k, lo, hi in CONFIG_LIMITS}


def limited(key, desc, example):
    lo, hi = LIMITS[key]
    return i(f'{desc} ({lo}–{hi})', example, minimum=lo, maximum=hi)


SCHEMAS = {
    'Error': obj(error=s('Thông báo lỗi (tiếng Việt)', 'Không tìm thấy ảnh')),
    'Image': obj(
        id=i(example=128), file_name=s(example='20261126_091530_a1b2c3.jpg'),
        file_path=s('Đường dẫn tải ảnh: GET /<file_path>', 'uploads/20261126_091530_a1b2c3.jpg'),
        capture_time=t('Client chụp'), sent_time=t('Client bắt đầu gửi'),
        received_time=t('Server nhận xong'), displayed_time=t('Ảnh hiện lần đầu trên Website'),
        file_size_kb=n(example=84.25), width=i(example=854), height=i(example=480),
        client_id=s(example='client-01'), client_capture_id=i('Số thứ tự ảnh phía Client', 42),
        client_ip=s(example='192.168.1.12'), original_name=s(example='cam1_000042.jpg'),
        source=s('Id camera', 'yt-abcDEF12345'),
        interval_used=i('Tần suất chụp lúc đó (giây)', 5), quality_used=i('Chất lượng JPEG lúc đó', 80),
        detected_time=t('YOLOv5 nhận diện xong (null = chưa)'), detect_ms=n('Thời gian chạy YOLOv5 (ms)', 64.2),
        object_count=i('Số vật thể tìm thấy', 4),
        objects={'type': 'object', 'additionalProperties': {'type': 'integer'},
                 'description': 'Chỉ có trong danh sách: số vật thể theo loại', 'example': {'car': 3, 'motorcycle': 1}}),
    'ImageDetail': {'allOf': [ref('Image'), obj(detections=arr(ref('Detection')))]},
    'Detection': obj(label=s('Tên loại COCO', 'car'), name=s('Tên tiếng Việt', 'Ô tô'),
                     confidence=n('Độ tin cậy 0–1', 0.9), x1=i(example=242), y1=i(example=182),
                     x2=i(example=400), y2=i(example=323)) | {'description': 'Khung vật thể, tọa độ pixel ảnh gốc'},
    'DetectStatus': obj(enabled=b('Luồng YOLOv5 đang chạy'), reason=s('Lý do không chạy', nullable=True),
                        model=s(example='yolov5s.onnx'), confidence=n('Ngưỡng tin cậy', 0.35),
                        queue=i('Ảnh đang chờ trong hàng đợi', 0), processed=i('Đã xử lý từ lúc Server chạy', 100),
                        avg_ms=n(example=62.5), last_error=s(nullable=True),
                        pending=i('Ảnh chưa nhận diện trong CSDL', 0), detected=i(example=100)),
    'UploadResult': obj(
        id=i(example=128), file_name=s(example='20261126_091530_a1b2c3.jpg'),
        file_path=s(example='uploads/20261126_091530_a1b2c3.jpg'), file_size_kb=n(example=84.25),
        received_time=t(), duplicate=b('Có khi ảnh này đã nhận trước đó (Client gửi lại) — trả bản ghi cũ')),
    'ImagePage': obj(page=i(example=1), per_page=i(example=20), total=i(example=245),
                     total_pages=i(example=13), items=arr(ref('Image'))),
    'Config': obj(
        id=i(example=1),
        capture_interval=limited('capture_interval', 'Tần suất chụp, giây', 5),
        jpeg_quality=limited('jpeg_quality', 'Chất lượng JPEG', 80),
        resize_width=limited('resize_width', 'Chiều rộng ảnh, px', 854),
        max_images=limited('max_images', 'Số ảnh tối đa trên Server', 100),
        updated_at=t(),
        cameras=arr(obj(id=s(example='ip-2'), name=s(example='Camera cổng'),
                        type=s(enum=['youtube', 'rtsp', 'http']), url=s(example='rtsp://192.168.1.20:554/stream1')))
        | {'description': 'Chỉ có khi gọi bằng khóa API: camera Client cần chụp (admin bật "Client chụp ảnh")'}),
    'ConfigUpdate': obj(
        capture_interval=limited('capture_interval', 'Tần suất chụp, giây', 2),
        jpeg_quality=limited('jpeg_quality', 'Chất lượng JPEG', 80),
        resize_width=limited('resize_width', 'Chiều rộng ảnh, px', 854),
        max_images=limited('max_images', 'Số ảnh tối đa trên Server', 100)),
    'ConfigHistory': obj(id=i(example=7), changed_at=t(), field=s(example='capture_interval'),
                         old_value=s(example='5'), new_value=s(example='2'),
                         changed_by=s(example='admin (192.168.1.5)')),
    'Client': obj(client_id=s(example='client-01'), ip=s(example='192.168.1.12'), last_seen=t(),
                  last_activity=s(example='upload', enum=['upload', 'config_poll']),
                  cameras=s('Id camera Client khai báo, cách nhau dấu phẩy', 'yt-abcDEF12345,ip-2'),
                  seconds_ago=n(example=2.4), online=b('Hoạt động trong 30 giây gần nhất')),
    'Camera': obj(id=s(example='yt-abcDEF12345'), name=s(example='Camera ngã tư'), capture=b('Đang bật Client chụp'),
                  image_count=i(example=57), last_capture=t(), last_image=s(example='uploads/2026...jpg', nullable=True),
                  clients=arr(s(example='client-01'))),
    'LatencySummary': obj(count=i(example=50), avg=n(example=0.412), min=n(example=0.201),
                          max=n(example=1.032), p95=n(example=0.88)),
    'Stats': obj(
        total_images=i(example=245), sample_size=i(example=50),
        summary=obj(capture_to_received=ref('LatencySummary'), sent_to_received=ref('LatencySummary'),
                    capture_to_display=ref('LatencySummary'), actual_gap=ref('LatencySummary'),
                    detect_time=ref('LatencySummary'), received_to_detected=ref('LatencySummary')),
        items=arr(obj(id=i(), client_id=s(), source=s(), capture_time=t(), interval_used=i(),
                      actual_gap=n('Khoảng cách thực tế với lần chụp trước của cùng camera (giây)'),
                      capture_to_received=n('Chụp → Server nhận (giây)'),
                      sent_to_received=n('Thời gian truyền qua mạng (giây)'),
                      capture_to_display=n('Chụp → hiển thị trên Website (giây)'),
                      detect_time=n('Thời gian chạy YOLOv5 (giây)'),
                      received_to_detected=n('Server nhận → có kết quả YOLOv5, gồm chờ hàng đợi (giây)'),
                      file_size_kb=n()))),
    'Stream': obj(id=i(example=1), video_id=s(example='abcDEF12345'), title=s(example='Camera ngã tư'),
                  channel=s(example='Kênh giao thông'), added_by=s(example='admin'), added_at=t(),
                  capture=i('1 = Client chụp ảnh từ camera này', 0, enum=[0, 1])),
    'StreamInfo': obj(video_id=s(example='abcDEF12345'), title=s(), channel=s(),
                      live_status=s('is_live, was_live, not_live, is_upcoming…', 'is_live'),
                      embeddable=b('Chủ kênh cho nhúng vào trang web khác'), error=s('Có khi YouTube báo lỗi')),
    'IpCam': obj(id=i(example=2), name=s(example='Camera cổng'),
                 url=s('Đã ẩn mật khẩu', 'rtsp://admin:***@192.168.1.20:554/stream1'),
                 added_by=s(example='admin'), added_at=t(), capture=i(example=0, enum=[0, 1]),
                 status=ref('IpCamStatus')),
    'IpCamStatus': obj(running=b('Luồng đọc camera đang chạy'), viewers=i(example=1),
                       error=s(nullable=True), has_frame=b()),
    'IpCamInput': {'description': 'Gửi `url` đầy đủ, HOẶC `preset` + `ip` (+ port, user, password)', **obj(
        name=s('Chỉ dùng khi lưu', 'Camera cổng'), preset=s('Id lấy từ GET /api/ipcams/presets', 'hikvision'),
        ip=s(example='192.168.1.20'), port=i(example=554), user=s(example='admin'), password=s(fmt='password'),
        url=s(example='http://192.168.1.15:8080/video'))},
    'User': obj(id=i(example=1), username=s(example='admin'), role=s(enum=['admin', 'viewer']),
                created_at=t(), last_login=t()),
    'Me': obj(id=i('null khi là Khách', 1, nullable=True), username=s(example='admin'),
              role=s(enum=['admin', 'viewer']), guest=b('true khi vào bằng chế độ Khách')),
}

# ---------------------------------------------------------------- các API
IMG, CFG, MON, YT, IPC, USR, AUTH, DET = ('Ảnh', 'Cấu hình', 'Giám sát', 'Camera YouTube', 'Camera IP',
                                          'Tài khoản', 'Đăng nhập', 'Nhận diện YOLOv5')

PATHS = {
    # ---------- Ảnh ----------
    '/api/images': {
        'post': op(IMG, 'Client gửi ảnh mới', CLIENT, {
            **json_ok(ref('UploadResult'), 'Đã lưu (hoặc ảnh trùng → `duplicate: true`)', '201'),
            **err(400, 'Thiếu file / sai định dạng / nội dung không phải ảnh'),
            **err(401, 'Thiếu hoặc sai khóa API'), **err(413, 'File quá lớn')},
            desc='Gửi dạng **multipart/form-data**. Server kiểm tra phần đầu file đúng là JPEG/PNG, lưu vào '
                 '`uploads/`, ghi MySQL, rồi tự xóa ảnh cũ nhất nếu vượt `max_images`.\n\n'
                 'Chống nhận trùng: cùng (`client_id`, `client_capture_id`, `capture_time`) → trả lại bản ghi cũ.',
            req={'required': True, 'content': {'multipart/form-data': {'schema': obj(
                ['file'], file=s('Ảnh .jpg / .jpeg / .png', fmt='binary'),
                capture_time=t('Lúc chụp (thiếu → lấy giờ Server nhận)'), sent_time=t('Lúc bắt đầu gửi'),
                client_id=s(example='client-01'), client_capture_id=i(example=42),
                source=s('Id camera', 'yt-abcDEF12345'), width=i(example=854), height=i(example=480),
                interval_used=i(example=5), quality_used=i(example=80))}}}),
        'get': op(IMG, 'Danh sách ảnh (phân trang, lọc)', LOGIN, json_ok(ref('ImagePage')), params=[
            q('page', i(example=1, minimum=1), 'Trang (từ 1)'),
            q('per_page', i(example=20, minimum=1, maximum=100), 'Số ảnh / trang (tối đa 100)'),
            q('camera', s(), 'Id camera (cột source)'),
            q('start', s(example='2026-11-26T08:00:00'), 'Chụp từ'),
            q('end', s(example='2026-11-26T18:00:00'), 'Chụp đến'),
            q('q', s(), 'Tìm trong tên file / tên Client'),
            q('object', s(example='person'), 'Chỉ ảnh có vật thể loại này (YOLOv5: person, car, motorcycle...)')]),
    },
    '/api/images/{id}': {
        'get': op(IMG, 'Chi tiết một ảnh (kèm vật thể YOLOv5)', LOGIN, {**json_ok(ref('ImageDetail')), **err(404, 'Không tìm thấy ảnh')},
                  params=[p('id', 'Id ảnh')]),
        'delete': op(IMG, 'Xóa ảnh (admin)', ADMIN, {**json_ok(obj(message=s(example='Đã xóa'), id=i())),
                                                    **err(404, 'Không tìm thấy ảnh')}, params=[p('id', 'Id ảnh')]),
    },
    '/api/images/{id}/displayed': {
        'post': op(IMG, 'Trình duyệt báo ảnh đã hiển thị', LOGIN, json_ok(ID_ONLY), params=[p('id', 'Id ảnh')],
                   desc='Ghi `displayed_time` (chỉ lần đầu) để đo độ trễ chụp → hiển thị.'),
    },
    '/uploads/{file}': {
        'get': op(IMG, 'Tải file ảnh', LOGIN, {'200': {'description': 'File ảnh', 'content': {
            'image/jpeg': {'schema': s(fmt='binary')}, 'image/png': {'schema': s(fmt='binary')}}}},
            params=[{'name': 'file', 'in': 'path', 'required': True, 'schema': {'type': 'string'},
                     'description': 'Tên file (cột file_name)'}]),
    },
    # ---------- Cấu hình ----------
    '/api/config': {
        'get': op(CFG, 'Lấy cấu hình hiện tại', CLIENT + LOGIN, {**json_ok(ref('Config')), **err(401, 'Sai khóa API / chưa đăng nhập')},
                  desc='Client gọi định kỳ (mặc định 10 giây) **với khóa API** → Server ghi nhận Client còn sống '
                       'và trả thêm `cameras` (camera cần chụp, kèm URL). Website gọi bằng cookie phiên thì không có `cameras`.',
                  params=[q('client_id', s(example='client-01'), 'Id Client (chỉ khi Client gọi)'),
                          q('cameras', s(example='yt-abcDEF12345,ip-2'), 'Camera Client đang khai báo')]),
        'post': op(CFG, 'Đổi cấu hình (admin)', ADMIN, {**json_ok(ref('Config')), **err(400, 'Giá trị ngoài giới hạn')},
                   desc='Chỉ gửi trường cần đổi. Mỗi thay đổi được ghi vào lịch sử; Client áp dụng ở lần hỏi kế tiếp.',
                   req=body(ref('ConfigUpdate'))),
    },
    '/api/config/history': {
        'get': op(CFG, 'Lịch sử thay đổi cấu hình (admin)', ADMIN, json_ok(arr(ref('ConfigHistory'))),
                  params=[q('limit', i(example=50, minimum=1, maximum=500), 'Số dòng')]),
    },
    # ---------- Giám sát ----------
    '/api/stats': {
        'get': op(MON, 'Thống kê độ trễ', LOGIN, json_ok(ref('Stats')),
                  desc='Độ trễ (giây) của N ảnh gần nhất. Client và Server ở 2 máy phải đồng bộ đồng hồ (NTP).',
                  params=[q('limit', i(example=50, minimum=2, maximum=1000), 'Số ảnh gần nhất')]),
    },
    '/api/clients': {'get': op(MON, 'Các Client đã kết nối', LOGIN, json_ok(arr(ref('Client'))))},
    '/api/cameras': {'get': op(MON, 'Danh sách camera (có ảnh / Client khai báo)', LOGIN, json_ok(arr(ref('Camera'))))},
    # ---------- Nhận diện YOLOv5 ----------
    '/api/detect/status': {
        'get': op(DET, 'Trạng thái luồng nhận diện', LOGIN, json_ok(ref('DetectStatus')),
                  desc='Ảnh mới được đưa vào hàng đợi; 1 luồng nền chạy YOLOv5 rồi ghi bảng `detections`. '
                       'Ảnh còn sót (hàng đợi đầy, Server khởi động lại) được quét bù định kỳ.'),
    },
    '/api/objects': {
        'get': op(DET, 'Các loại vật thể đã gặp', LOGIN, json_ok(arr(obj(
            label=s(example='car'), name=s(example='Ô tô'), images=i('Số ảnh có loại này', 50),
            objects=i('Tổng số lần xuất hiện', 157))))),
    },
    # ---------- Camera YouTube ----------
    '/api/streams': {
        'get': op(YT, 'Danh sách livestream', LOGIN, json_ok(arr(ref('Stream')))),
        'post': op(YT, 'Thêm link livestream (admin)', ADMIN, {
            **json_ok(ref('Stream'), 'Đã thêm', '201'), **err(400, 'Link sai / YouTube báo lỗi / không cho nhúng'),
            **err(409, 'Link đã có')}, desc='Server hỏi YouTube (yt-dlp) để kiểm tra video tồn tại và cho nhúng.',
            req=body(obj(['url'], url=s(example='https://www.youtube.com/watch?v=abcDEF12345'),
                         title=s('Bỏ trống → lấy tiêu đề trên YouTube')))),
    },
    '/api/streams/{id}': {
        'patch': op(YT, 'Bật / tắt Client chụp ảnh (admin)', ADMIN, {**json_ok(ref('Stream')), **err(404, 'Không tìm thấy')},
                    params=[p('id')], req=CAPTURE_BODY),
        'delete': op(YT, 'Xóa livestream (admin)', ADMIN, {**json_ok(ID_ONLY), **err(404, 'Không tìm thấy')}, params=[p('id')]),
    },
    '/api/streams/{id}/select': {
        'post': op(YT, 'Chọn camera duy nhất cho Client chụp (admin)', ADMIN,
                   {**json_ok(obj(id=i(), video_id=s(), capture=i(example=1))), **err(404, 'Không tìm thấy')},
                   params=[p('id')], desc='Bật chụp camera này, tắt các livestream khác.'),
    },
    '/api/streams/{id}/check': {
        'get': op(YT, 'Kiểm tra livestream còn phát', LOGIN, {**json_ok(ref('StreamInfo')), **err(404, 'Không tìm thấy')},
                  params=[p('id')]),
    },
    '/api/streams/search': {
        'get': op(YT, 'Tìm livestream đang phát trên YouTube (admin)', ADMIN, {
            **json_ok(arr(obj(video_id=s(), title=s(), channel=s(), added=b('Đã có trong danh sách')))),
            **err(400, 'Thiếu từ khóa'), **err(502, 'Không gọi được YouTube'), **err(503, 'Server chưa cài yt-dlp')},
            params=[q('q', s(example='traffic camera live'), 'Từ khóa', True)]),
    },
    # ---------- Camera IP ----------
    '/api/ipcams': {
        'get': op(IPC, 'Danh sách camera IP', LOGIN, json_ok(arr(ref('IpCam')))),
        'post': op(IPC, 'Lưu camera IP (admin)', ADMIN, {**json_ok(ref('IpCam'), 'Đã lưu', '201'),
                                                       **err(400, 'Thiếu / sai địa chỉ')}, req=body(ref('IpCamInput'))),
    },
    '/api/ipcams/presets': {
        'get': op(IPC, 'Các loại camera / mẫu đường dẫn', LOGIN, json_ok(arr(obj(
            id=s(example='hikvision'), name=s(example='Hikvision'),
            pattern=s(example='rtsp://{ip}:{port}/Streaming/Channels/101'), port=i(example=554))))),
    },
    '/api/ipcams/test': {
        'post': op(IPC, 'Thử kết nối camera → 1 ảnh JPEG (admin)', ADMIN, {
            '200': {'description': 'Ảnh chụp thử (header X-Width, X-Height)',
                    'content': {'image/jpeg': {'schema': s(fmt='binary')}}},
            **err(400, 'Thiếu / sai địa chỉ'), **err(502, 'Không kết nối được camera'), **err(503, 'Server chưa cài OpenCV')},
            req=body(ref('IpCamInput'))),
    },
    '/api/ipcams/{id}': {
        'patch': op(IPC, 'Bật / tắt Client chụp ảnh (admin)', ADMIN, {**json_ok(ref('IpCam')), **err(404, 'Không tìm thấy camera')},
                    params=[p('id')], req=CAPTURE_BODY),
        'delete': op(IPC, 'Xóa camera IP (admin)', ADMIN, {**json_ok(ID_ONLY), **err(404, 'Không tìm thấy camera')}, params=[p('id')]),
    },
    '/api/ipcams/{id}/status': {
        'get': op(IPC, 'Trạng thái luồng đọc camera', LOGIN, json_ok(ref('IpCamStatus')), params=[p('id')]),
    },
    '/ipcam/{id}/stream': {
        'get': op(IPC, 'Luồng video MJPEG', LOGIN, {
            '200': {'description': 'Luồng ảnh JPEG liên tục — mở bằng thẻ `<img>`, Swagger không hiển thị được',
                    'content': {'multipart/x-mixed-replace; boundary=frame': {'schema': s(fmt='binary')}}},
            **err(404, 'Không tìm thấy camera')}, params=[p('id')]),
    },
    # ---------- Tài khoản ----------
    '/api/me': {'get': op(USR, 'Người đang đăng nhập', LOGIN, json_ok(ref('Me')))},
    '/api/me/password': {
        'post': op(USR, 'Tự đổi mật khẩu', LOGIN, {**json_ok(obj(message=s(example='Đã đổi mật khẩu'))),
                                                  **err(400, 'Sai mật khẩu cũ / mật khẩu mới quá ngắn'),
                                                  **err(403, 'Chế độ khách không có mật khẩu')},
                   req=body(obj(['old', 'new'], old=s(fmt='password'), new=s('Ít nhất 6 ký tự', fmt='password')))),
    },
    '/api/users': {
        'get': op(USR, 'Danh sách tài khoản (admin)', ADMIN, json_ok(arr(ref('User')))),
        'post': op(USR, 'Tạo tài khoản quản trị (admin)', ADMIN, {
            **json_ok(obj(id=i(), username=s(), role=s(example='admin')), 'Đã tạo', '201'),
            **err(400, 'Tên / mật khẩu không hợp lệ'), **err(409, 'Tên đăng nhập đã có')},
            req=body(obj(['username', 'password'], username=s('3–50 ký tự: chữ không dấu, số, . _ -', 'sinhvien01'),
                         password=s('Ít nhất 6 ký tự', fmt='password')))),
    },
    '/api/users/{id}': {
        'patch': op(USR, 'Nâng quyền / đặt lại mật khẩu (admin)', ADMIN, {
            **json_ok(obj(id=i(), changes=arr(s(example='đặt lại mật khẩu')))), **err(400, 'Dữ liệu không hợp lệ'),
            **err(404, 'Không tìm thấy tài khoản')}, params=[p('id')],
            req=body(obj(role=s(enum=['admin']), password=s(fmt='password')))),
        'delete': op(USR, 'Xóa tài khoản (admin)', ADMIN, {
            **json_ok(ID_ONLY), **err(400, 'Tự xóa mình / xóa admin cuối cùng'), **err(404, 'Không tìm thấy tài khoản')},
            params=[p('id')]),
    },
    # ---------- Đăng nhập (trang web, trả về chuyển hướng 302 + cookie phiên) ----------
    '/login': {
        'post': {'tags': [AUTH], 'summary': 'Đăng nhập quản trị viên', 'security': [],
                 'description': 'Form HTML. Đúng → 302 về `next` + đặt cookie phiên `session`. '
                                'Sai 5 lần / 5 phút → khóa IP 5 phút (429).',
                 'requestBody': {'required': True, 'content': {'application/x-www-form-urlencoded': {'schema': obj(
                     ['username', 'password'], username=s(example='admin'), password=s(fmt='password'),
                     next=s(example='/live'))}}},
                 'responses': {'302': {'description': 'Đăng nhập thành công'},
                               '401': {'description': 'Sai tên hoặc mật khẩu (trang HTML)'},
                               '429': {'description': 'Sai quá nhiều lần'}}},
    },
    '/login/guest': {
        'post': {'tags': [AUTH], 'summary': 'Vào chế độ Khách (chỉ xem)', 'security': [],
                 'responses': {'302': {'description': 'Đặt cookie phiên khách'}}},
    },
    '/logout': {
        'post': {'tags': [AUTH], 'summary': 'Đăng xuất', 'security': LOGIN,
                 'responses': {'302': {'description': 'Xóa phiên, về trang đăng nhập'}}},
    },
}

SPEC = {
    'openapi': '3.0.3',
    'info': {
        'title': 'PBL4 Camera — REST API',
        'version': '1.0',
        'description': (
            'API giữa **Client** (máy chụp ảnh) và **Server**, và giữa **Website** và Server.\n\n'
            '**Xác thực**\n'
            '- **Client** gửi header `X-API-Key` (khóa `PBL4_API_KEY` trong `.env`) — chỉ dùng cho '
            '`POST /api/images` và `GET /api/config`. Bấm **Authorize** để nhập khóa khi thử.\n'
            '- **Website** dùng cookie phiên: bạn đã đăng nhập nên các nút *Try it out* gửi kèm cookie tự động.\n'
            '- API ghi **(admin)** chỉ quản trị viên gọi được; Khách gọi sẽ nhận 403.\n\n'
            'Mọi thời gian là chuỗi `YYYY-MM-DDTHH:MM:SS.mmm` (mili giây, giờ máy Server). Lỗi trả `{"error": "..."}`.'),
    },
    'tags': [{'name': IMG, 'description': 'Nhận ảnh từ Client, tra cứu, xóa'},
             {'name': CFG, 'description': 'Cấu hình Client từ xa'},
             {'name': MON, 'description': 'Client đang kết nối, camera, thống kê độ trễ'},
             {'name': DET, 'description': 'Vật thể YOLOv5 tìm thấy trong ảnh (người, xe...)'},
             {'name': YT, 'description': 'Livestream YouTube trên trang Camera trực tiếp'},
             {'name': IPC, 'description': 'Camera IP trong mạng LAN'},
             {'name': USR, 'description': 'Tài khoản Website'},
             {'name': AUTH, 'description': 'Lấy cookie phiên (trang web)'}],
    'paths': PATHS,
    'components': {
        'schemas': SCHEMAS,
        'securitySchemes': {
            'apiKey': {'type': 'apiKey', 'in': 'header', 'name': 'X-API-Key',
                       'description': 'Khóa API của Client (PBL4_API_KEY)'},
            'session': {'type': 'apiKey', 'in': 'cookie', 'name': 'session',
                        'description': 'Cookie phiên — trình duyệt tự gửi khi đã đăng nhập'},
        },
    },
}


def spec(server_url=None):
    """Bản đặc tả để trả JSON; server_url = địa chỉ đang truy cập (để nút Try it out gọi đúng máy)."""
    out = dict(SPEC)
    if server_url:
        out['servers'] = [{'url': server_url}]
    return out
