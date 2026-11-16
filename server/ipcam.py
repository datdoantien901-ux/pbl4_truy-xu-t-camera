"""
Xem camera IP trực tiếp trên Website (trang /ipcam).

Trình duyệt không mở được RTSP → Server làm trung gian:
    camera IP ──RTSP/HTTP──▶ Server (OpenCV đọc frame, nén JPEG) ──MJPEG/HTTP──▶ trình duyệt <img>

Mỗi camera chỉ có MỘT luồng đọc (CameraReader) dùng chung cho mọi người đang xem:
    - luồng đọc ghi frame mới nhất vào bộ đệm, báo cho người xem qua threading.Condition
    - mỗi người xem (1 request HTTP) chờ frame mới rồi gửi đi → không mở camera nhiều lần
    - không còn ai xem quá IDLE_SECONDS giây → luồng đọc tự dừng, giải phóng camera
"""
import os
import re
import threading
import time
import urllib.parse

try:
    import cv2
except ImportError:          # Server vẫn chạy được, chỉ mất chức năng Camera IP
    cv2 = None

from settings import log

OPEN_TIMEOUT_MS = 6000     # chờ kết nối camera tối đa 6 giây (IP sai → báo lỗi nhanh)
READ_TIMEOUT_MS = 6000
IDLE_SECONDS = 20          # không ai xem 20 giây → đóng camera
STREAM_FPS = 10            # gửi tối đa 10 khung/giây cho trình duyệt (đủ mượt, đỡ tốn mạng)
STREAM_WIDTH = 960         # thu nhỏ trước khi gửi
JPEG_QUALITY = 75

# Mẫu đường dẫn theo hãng (giống client/.env.example). {ip} {port} {user} {password}
PRESETS = {
    'ipwebcam':  ('Điện thoại Android (app IP Webcam)', 'http://{auth}{ip}:{port}/video', 8080),
    'dahua':     ('Imou / Dahua', 'rtsp://{auth}{ip}:{port}/cam/realmonitor?channel=1&subtype=1', 554),
    'ezviz':     ('Ezviz', 'rtsp://{auth}{ip}:{port}/h264_stream', 554),
    'hikvision': ('Hikvision', 'rtsp://{auth}{ip}:{port}/Streaming/Channels/102', 554),
    'tapo':      ('TP-Link Tapo', 'rtsp://{auth}{ip}:{port}/stream2', 554),
    'onvif':     ('RTSP chung (thử /stream1)', 'rtsp://{auth}{ip}:{port}/stream1', 554),
}
_IP_RE = re.compile(r'^[A-Za-z0-9.-]{1,253}$')   # IPv4 hoặc tên máy


def available():
    return cv2 is not None


def build_url(preset, ip, port=None, user='', password=''):
    """Ghép URL camera từ IP + hãng. Trả về (url, lỗi)."""
    if preset not in PRESETS:
        return None, 'Chưa chọn loại camera'
    ip = (ip or '').strip()
    if not _IP_RE.match(ip):
        return None, 'Địa chỉ IP không hợp lệ (vd 192.168.1.20)'
    _, pattern, default_port = PRESETS[preset]
    try:
        port = int(port or default_port)
        assert 1 <= port <= 65535
    except (ValueError, AssertionError):
        return None, 'Cổng phải là số 1–65535'
    auth = ''
    if user:
        auth = urllib.parse.quote(user, safe='')
        if password:
            auth += ':' + urllib.parse.quote(password, safe='')
        auth += '@'
    return pattern.format(auth=auth, ip=ip, port=port), None


def check_url(url):
    """Chỉ nhận rtsp:// http:// https:// (không cho đọc file trên máy Server)."""
    url = (url or '').strip()
    u = urllib.parse.urlparse(url)
    if u.scheme not in ('rtsp', 'rtsps', 'http', 'https') or not u.hostname:
        return None, 'URL phải bắt đầu bằng rtsp:// hoặc http:// và có địa chỉ camera'
    return url, None


def mask_url(url):
    """Ẩn mật khẩu: rtsp://admin:***@192.168.1.20/... (không gửi mật khẩu camera ra trình duyệt)."""
    return re.sub(r'(://[^:/@]+):[^@/]*@', r'\1:***@', url or '')


def _open(url):
    if url.startswith('rtsp'):
        # RTSP qua TCP: ổn định hơn UDP (không mất gói / vỡ hình); phải đặt trước khi mở
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp'
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                                                 cv2.CAP_PROP_READ_TIMEOUT_MSEC, READ_TIMEOUT_MS])
    if not cap.isOpened():
        cap.release()
        return None
    return cap


def _encode(frame):
    h, w = frame.shape[:2]
    if w > STREAM_WIDTH:
        frame = cv2.resize(frame, (STREAM_WIDTH, int(h * STREAM_WIDTH / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buf.tobytes() if ok else None, frame.shape[1], frame.shape[0]


def snapshot(url):
    """Thử kết nối và lấy 1 khung hình. Trả về (jpeg_bytes, width, height, lỗi)."""
    if cv2 is None:
        return None, 0, 0, 'Server chưa cài OpenCV (pip install opencv-python)'
    t = time.time()
    cap = _open(url)
    if cap is None:
        return None, 0, 0, (f'Không kết nối được camera sau {time.time() - t:.0f} giây. Kiểm tra IP, cổng, '
                            'tài khoản / mật khẩu và camera có cùng mạng LAN với Server không.')
    try:
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok or frame is None:
        return None, 0, 0, 'Kết nối được nhưng không đọc được hình (sai đường dẫn luồng?)'
    jpg, w, h = _encode(frame)
    return jpg, w, h, None


class CameraReader(threading.Thread):
    """Luồng đọc 1 camera, giữ khung hình mới nhất cho nhiều người xem."""

    def __init__(self, key, url, name):
        super().__init__(name=f'IPCam-{key}', daemon=True)
        self.key, self.url, self.label = key, url, name
        self.cond = threading.Condition()
        self.jpeg = None          # khung hình mới nhất (JPEG)
        self.seq = 0              # số thứ tự khung → người xem biết đã có khung mới
        self.error = None
        self.viewers = 0
        self.last_viewer = time.time()
        self.running = True

    def run(self):
        log.info('[IPCAM] Mở %s (%s)', self.label, mask_url(self.url))
        cap = None
        last_encode = 0.0
        while self.running:
            if self.viewers == 0 and time.time() - self.last_viewer > IDLE_SECONDS:
                break   # không ai xem → đóng camera
            if cap is None:
                cap = _open(self.url)
                if cap is None:
                    self._set_error('Không kết nối được camera, đang thử lại…')
                    time.sleep(3)
                    continue
                self.error = None
            ok = cap.grab()   # grab liên tục để bỏ khung cũ trong bộ đệm → hình luôn mới nhất
            if not ok:
                cap.release()
                cap = None
                self._set_error('Mất kết nối camera, đang kết nối lại…')
                time.sleep(1)
                continue
            if time.time() - last_encode < 1 / STREAM_FPS:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                continue
            last_encode = time.time()
            jpg, _, _ = _encode(frame)
            with self.cond:
                self.jpeg = jpg
                self.seq += 1
                self.cond.notify_all()
        if cap is not None:
            cap.release()
        with self.cond:
            self.running = False
            self.cond.notify_all()
        log.info('[IPCAM] Đóng %s (không còn ai xem)', self.label)

    def _set_error(self, msg):
        with self.cond:
            self.error = msg
            self.cond.notify_all()


class StreamHub:
    """Quản lý các luồng đọc: mỗi camera tối đa 1 luồng, tạo khi có người xem."""

    def __init__(self):
        self.lock = threading.Lock()
        self.readers = {}

    def _reader(self, key, url, name):
        with self.lock:
            r = self.readers.get(key)
            if r is None or not r.is_alive() or not r.running or r.url != url:
                if r is not None:
                    r.running = False
                r = CameraReader(key, url, name)
                self.readers[key] = r
                r.start()
            with r.cond:
                r.viewers += 1
            return r

    def mjpeg(self, key, url, name):
        """Generator cho Response multipart/x-mixed-replace: mỗi phần là 1 ảnh JPEG."""
        r = self._reader(key, url, name)
        seq = -1
        try:
            while True:
                with r.cond:
                    r.cond.wait_for(lambda: r.seq != seq or not r.running, timeout=10)
                    if not r.running:
                        return
                    jpg, seq = r.jpeg, r.seq
                if jpg is None:
                    continue
                yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
                       + str(len(jpg)).encode() + b'\r\n\r\n' + jpg + b'\r\n')
        finally:   # trình duyệt đóng tab / chuyển trang → Flask đóng generator
            with r.cond:
                r.viewers -= 1
                r.last_viewer = time.time()

    def status(self, key):
        r = self.readers.get(key)
        if r is None or not r.running:
            return {'running': False, 'viewers': 0, 'error': None}
        return {'running': True, 'viewers': r.viewers, 'error': r.error, 'has_frame': r.jpeg is not None}

    def stop(self, key):
        with self.lock:
            r = self.readers.pop(key, None)
        if r is not None:
            r.running = False


hub = StreamHub()
