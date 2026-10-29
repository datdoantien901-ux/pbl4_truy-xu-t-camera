"""
Lớp trừu tượng cho nguồn video.

Các phần còn lại của Client (chụp ảnh, upload, cấu hình) không cần biết ảnh
đến từ đâu: camera IP qua RTSP, camera điện thoại, webcam, file video hay
luồng YouTube. Muốn đổi nguồn chỉ cần sửa `source` trong client_config.json.

    rtsp    : rtsp://user:pass@192.168.1.20:554/stream1   (camera IP / iPhone OctoStream)
    http    : http://192.168.1.15:8080/video              (luồng MJPEG qua HTTP)
    webcam  : 0, 1, ...                                   (camera gắn vào máy)
    file    : duong/dan/video.mp4                         (test khi không có camera)
    youtube : https://www.youtube.com/watch?v=...         (camera công cộng 0511)
"""
import logging
import os
import time

import cv2

log = logging.getLogger('source')

SUPPORTED_TYPES = ('rtsp', 'http', 'webcam', 'file', 'youtube')


class _SilentYtdlpLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def mask_url(url):
    """Ẩn mật khẩu trong URL trước khi ghi log: rtsp://admin:***@ip/..."""
    s = str(url)
    if '://' in s and '@' in s:
        scheme, rest = s.split('://', 1)
        cred, host = rest.split('@', 1)
        user = cred.split(':', 1)[0]
        return f'{scheme}://{user}:***@{host}'
    return s


class VideoSource:
    def __init__(self, source_type, url, rtsp_transport='tcp',
                 open_timeout_ms=8000, read_timeout_ms=8000):
        source_type = (source_type or '').lower()
        if source_type not in SUPPORTED_TYPES:
            raise ValueError(f'source.type phải là một trong {SUPPORTED_TYPES}, nhận được "{source_type}"')
        self.type = source_type
        self.url = url
        self.rtsp_transport = rtsp_transport
        self.open_timeout_ms = open_timeout_ms
        self.read_timeout_ms = read_timeout_ms
        self.cap = None
        self._file_frame_delay = 0.0   # nguồn file: giả lập tốc độ phát thật
        self._last_grab = 0.0

    # ---------- mở / đóng ----------
    def _resolve_url(self):
        """Trả về thứ truyền được cho cv2.VideoCapture."""
        if self.type == 'webcam':
            return int(self.url)
        if self.type == 'youtube':
            import yt_dlp  # chỉ cần khi dùng YouTube
            opts = {
                'format': 'best[height<=480]/best',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'logger': _SilentYtdlpLogger(),   # lỗi đã được Client ghi log, không in lặp lại
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            return info['url'] if 'url' in info else info.get('formats', [info])[-1]['url']
        return self.url

    def open(self):
        self.release()
        target = self._resolve_url()

        if self.type == 'rtsp':
            # Phải đặt TRƯỚC khi mở VideoCapture thì FFmpeg mới đọc được.
            # TCP ổn định hơn UDP trên Wi-Fi (không vỡ hình khi mất gói).
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = f'rtsp_transport;{self.rtsp_transport}'

        if self.type == 'webcam':
            cap = cv2.VideoCapture(target)
        else:
            params = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.open_timeout_ms,
                      cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.read_timeout_ms]
            cap = cv2.VideoCapture(target, cv2.CAP_FFMPEG, params)

        if not cap.isOpened():
            cap.release()
            raise ConnectionError(f'Không mở được nguồn {self.type}: {mask_url(self.url)}')

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # giảm buffer → giảm độ trễ

        if self.type == 'file':
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            self._file_frame_delay = 1.0 / fps

        self.cap = cap
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        log.info('Đã mở nguồn %s: %s (%dx%d, %.1f fps)', self.type, mask_url(self.url),
                 w, h, cap.get(cv2.CAP_PROP_FPS))

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    # ---------- đọc frame ----------
    def grab(self):
        """Lấy frame khỏi buffer (không giải mã ra ảnh). False = mất luồng."""
        if self.cap is None:
            return False
        if self.type == 'file':
            # File đọc nhanh hơn thời gian thực rất nhiều → chờ cho đúng fps
            wait = self._file_frame_delay - (time.time() - self._last_grab)
            if wait > 0:
                time.sleep(wait)
            self._last_grab = time.time()
            ok = self.cap.grab()
            if not ok:  # hết file → quay lại đầu (lặp vô hạn để test)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok = self.cap.grab()
            return ok
        return self.cap.grab()

    def retrieve(self):
        """Giải mã frame vừa grab thành ảnh numpy."""
        if self.cap is None:
            return False, None
        return self.cap.retrieve()

    def describe(self):
        return f'{self.type}:{mask_url(self.url)}'
