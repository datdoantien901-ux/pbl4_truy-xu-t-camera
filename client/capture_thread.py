"""
Luồng CAPTURE (producer): đọc frame từ nguồn video, mỗi capture_interval giây chụp 1 ảnh,
resize + nén JPEG, lưu file (atomic) + ghi SQLite local, rồi đưa id ảnh vào hàng đợi upload.
Mất luồng video → tự kết nối lại (backoff).

Mỗi camera một luồng CaptureThread riêng (tên luồng Capture-<id>); các luồng dùng chung
LocalStore, hàng đợi upload và SharedConfig. Ảnh lưu ở data/images/<id camera>/<ngày>/.
"""
import logging
import os
import queue
import threading
import time
from datetime import datetime

import cv2

from settings import BASE_DIR, IMAGE_DIR

log = logging.getLogger('client')


class CaptureThread(threading.Thread):
    def __init__(self, camera, settings, source, store, shared_cfg, upload_q, enqueued, stop_event):
        super().__init__(name=f"Capture-{camera['id']}", daemon=True)
        self.camera_id = camera['id']
        self.camera_name = camera['name']
        self.settings = settings
        self.source = source
        self.store = store
        self.cfg = shared_cfg
        self.upload_q = upload_q
        self.enqueued = enqueued          # (set, lock) để không đưa trùng ảnh vào hàng đợi
        self.stop_event = stop_event
        self.preview_lock = threading.Lock()
        self.preview_frame = None
        self.preview_active = False       # luồng chính bật cho camera đang xem → chỉ camera đó giải mã preview
        self.connected = False
        self.captured = 0

    def run(self):
        backoff = 2
        while not self.stop_event.is_set():
            try:
                self.source.open()
                backoff = 2
            except Exception as e:
                log.warning('[%s] Không mở được nguồn video (%s) → thử lại sau %ds', self.camera_id,
                            str(e).replace('ERROR: ', '').rstrip('.'), backoff)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue

            self.connected = True
            self._capture_loop()
            self.connected = False
            self.source.release()
        log.info('[%s] CaptureThread dừng (đã chụp %d ảnh)', self.camera_id, self.captured)

    def _capture_loop(self):
        last_capture = 0.0
        last_preview = 0.0
        preview_period = 1.0 / max(1, self.settings['preview_fps'])

        while not self.stop_event.is_set():
            # grab() liên tục để rút frame khỏi buffer → ảnh chụp luôn là ảnh mới nhất
            if not self.source.grab():
                log.warning('[%s] Mất luồng video. Kết nối lại...', self.camera_id)
                return

            now = time.time()
            cfg = self.cfg.get()

            if now - last_capture >= cfg['capture_interval']:
                ok, frame = self.source.retrieve()
                if ok:
                    last_capture = now
                    self._handle_snapshot(frame, cfg)

            if self.preview_active and now - last_preview >= preview_period:
                ok, frame = self.source.retrieve()
                if ok:
                    with self.preview_lock:
                        if self.preview_active:   # có thể vừa bị tắt trong lúc retrieve
                            self.preview_frame = frame
                last_preview = now

    def _handle_snapshot(self, frame, cfg):
        dt = datetime.now()
        capture_time = dt.isoformat(timespec='milliseconds')

        # Xử lý ảnh bằng OpenCV: resize + nén JPEG theo cấu hình
        h, w = frame.shape[:2]
        if cfg['resize_width'] and cfg['resize_width'] != w:
            new_h = int(h * cfg['resize_width'] / w)
            frame = cv2.resize(frame, (cfg['resize_width'], new_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, cfg['jpeg_quality']])
        if not ok:
            log.error('[%s] Nén JPEG thất bại', self.camera_id)
            return
        jpg = buf.tobytes()
        out_h, out_w = frame.shape[:2]

        # Lưu theo thư mục camera / ngày, tên file theo id camera + timestamp (2 camera không trùng tên)
        day_dir = os.path.join(IMAGE_DIR, self.camera_id, dt.strftime('%Y-%m-%d'))
        os.makedirs(day_dir, exist_ok=True)
        file_name = f"{self.camera_id}_{dt.strftime('%Y%m%d_%H%M%S')}_{dt.microsecond // 1000:03d}.jpg"
        file_path = os.path.join(day_dir, file_name)

        # Ghi atomic: ghi file tạm rồi rename → không bao giờ để lại file ảnh hỏng dở
        tmp_path = file_path + '.tmp'
        with open(tmp_path, 'wb') as f:
            f.write(jpg)
        os.replace(tmp_path, file_path)

        size_kb = round(len(jpg) / 1024, 2)
        rel_path = os.path.relpath(file_path, BASE_DIR).replace('\\', '/')
        capture_id = self.store.add_capture(
            file_name, rel_path, capture_time, size_kb, out_w, out_h,
            self.camera_id, cfg['capture_interval'], cfg['jpeg_quality'])
        self.captured += 1

        queued = False
        if self.settings['upload_enabled']:
            ids, lock = self.enqueued
            with lock:
                try:
                    self.upload_q.put_nowait(capture_id)
                    ids.add(capture_id)
                    queued = True
                except queue.Full:
                    pass  # hàng đợi đầy → ảnh vẫn nằm trong DB, UploadThread sẽ gửi bù sau

        log.info('[SAVE] #%d %s | %.2f KB | %dx%d | interval=%ds q=%d | %s',
                 capture_id, file_name, size_kb, out_w, out_h,
                 cfg['capture_interval'], cfg['jpeg_quality'],
                 'đã vào hàng đợi' if queued else 'chờ gửi bù')

    def set_preview_active(self, active):
        """Luồng chính gọi khi đổi camera đang xem; tắt thì bỏ frame cũ để lần sau không hiện ảnh cũ."""
        with self.preview_lock:
            self.preview_active = active
            if not active:
                self.preview_frame = None

    def latest_preview(self):
        with self.preview_lock:
            return self.preview_frame
