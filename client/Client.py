"""
Client thu nhận ảnh từ Camera — phiên bản đa luồng.

Kiến trúc (mô hình Producer – Consumer):

    ┌──────────────┐  frame mới   ┌──────────────┐  id ảnh   ┌──────────────┐
    │ CaptureThread│ ───────────▶ │  Lưu file +  │ ────────▶ │ UploadThread │ ──HTTP POST──▶ Server
    │  (producer)  │  mỗi N giây  │ SQLite local │  Queue    │  (consumer)  │
    └──────────────┘              └──────────────┘ (bounded) └──────────────┘
           ▲                                                        │ lỗi mạng → backoff,
           │ config dùng chung (Lock)                               │ ảnh nằm lại trong DB,
    ┌──────────────┐                                                │ gửi bù khi có mạng
    │ ConfigThread │ ──HTTP GET /api/config mỗi 10s──▶ Server       ▼
    └──────────────┘
    Main thread: hiện preview (cv2.imshow phải chạy ở luồng chính) và chờ tín hiệu dừng.

Ctrl+C (SIGINT) → set stop_event → các luồng tự thoát vòng lặp → join → giải phóng tài nguyên.

Chạy:  python Client.py                       (dùng client_config.json)
       python Client.py --source-type rtsp --source-url rtsp://192.168.1.15:8554/live
       python Client.py --server http://192.168.1.10:5000 --no-preview
"""
import argparse
import logging
import os
import queue
import signal
import threading
import time
from datetime import datetime

import cv2
import requests

from local_store import LocalStore
from settings import BASE_DIR, DB_PATH, IMAGE_DIR, load_settings, now_iso, setup_logging
from shared_config import SharedConfig
from video_source import VideoSource

log = logging.getLogger('client')


# ===================== LUỒNG CAPTURE (PRODUCER) =====================
class CaptureThread(threading.Thread):
    def __init__(self, settings, source, store, shared_cfg, upload_q, enqueued, stop_event):
        super().__init__(name='CaptureThread', daemon=True)
        self.settings = settings
        self.source = source
        self.store = store
        self.cfg = shared_cfg
        self.upload_q = upload_q
        self.enqueued = enqueued          # (set, lock) để không đưa trùng ảnh vào hàng đợi
        self.stop_event = stop_event
        self.preview_lock = threading.Lock()
        self.preview_frame = None
        self.captured = 0

    def run(self):
        backoff = 2
        while not self.stop_event.is_set():
            try:
                self.source.open()
                backoff = 2
            except Exception as e:
                log.warning('Không mở được nguồn video (%s) → thử lại sau %ds',
                            str(e).replace('ERROR: ', '').rstrip('.'), backoff)
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 30)
                continue

            self._capture_loop()
            self.source.release()
        log.info('CaptureThread dừng (đã chụp %d ảnh)', self.captured)

    def _capture_loop(self):
        last_capture = 0.0
        last_preview = 0.0
        preview_period = 1.0 / max(1, self.settings['preview_fps'])

        while not self.stop_event.is_set():
            # grab() liên tục để rút frame khỏi buffer → ảnh chụp luôn là ảnh mới nhất
            if not self.source.grab():
                log.warning('Mất luồng video. Kết nối lại...')
                return

            now = time.time()
            cfg = self.cfg.get()

            if now - last_capture >= cfg['capture_interval']:
                ok, frame = self.source.retrieve()
                if ok:
                    last_capture = now
                    self._handle_snapshot(frame, cfg)

            if self.settings['show_preview'] and now - last_preview >= preview_period:
                ok, frame = self.source.retrieve()
                if ok:
                    with self.preview_lock:
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
            log.error('Nén JPEG thất bại')
            return
        jpg = buf.tobytes()
        out_h, out_w = frame.shape[:2]

        # Lưu theo thư mục ngày, tên file theo timestamp
        day_dir = os.path.join(IMAGE_DIR, dt.strftime('%Y-%m-%d'))
        os.makedirs(day_dir, exist_ok=True)
        file_name = f"cam_{dt.strftime('%Y%m%d_%H%M%S')}_{dt.microsecond // 1000:03d}.jpg"
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
            self.source.type, cfg['capture_interval'], cfg['jpeg_quality'])
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

    def latest_preview(self):
        with self.preview_lock:
            return self.preview_frame


# ===================== LUỒNG UPLOAD (CONSUMER) =====================
class UploadThread(threading.Thread):
    SCAN_PERIOD = 5   # giây: chu kỳ quét DB tìm ảnh chưa gửi

    def __init__(self, settings, store, upload_q, enqueued, stop_event):
        super().__init__(name='UploadThread', daemon=True)
        self.url = settings['server_url'] + '/api/images'
        self.client_id = settings['client_id']
        self.store = store
        self.upload_q = upload_q
        self.enqueued = enqueued
        self.stop_event = stop_event
        self.session = requests.Session()   # giữ kết nối TCP (keep-alive) giữa các lần gửi
        self.sent = 0
        self.server_ok = True

    def run(self):
        last_scan = 0.0
        self._scan_pending()   # gửi bù ảnh còn tồn từ lần chạy trước
        while not self.stop_event.is_set():
            try:
                capture_id = self.upload_q.get(timeout=1)
            except queue.Empty:
                if time.time() - last_scan >= self.SCAN_PERIOD:
                    self._scan_pending()
                    last_scan = time.time()
                continue
            try:
                self._upload_with_retry(capture_id)
            finally:
                ids, lock = self.enqueued
                with lock:
                    ids.discard(capture_id)
                self.upload_q.task_done()
        log.info('UploadThread dừng (đã gửi %d ảnh, còn %d ảnh chờ gửi)',
                 self.sent, self.store.count_pending())

    def _scan_pending(self):
        ids, lock = self.enqueued
        with lock:
            pending = self.store.pending_ids(limit=self.upload_q.maxsize, exclude=ids)
            added = 0
            for cid in pending:
                try:
                    self.upload_q.put_nowait(cid)
                    ids.add(cid)
                    added += 1
                except queue.Full:
                    break
        if added:
            log.info('[RESEND] Đưa %d ảnh chưa gửi vào hàng đợi', added)

    def _upload_with_retry(self, capture_id):
        backoff = 2
        while not self.stop_event.is_set():
            result = self._upload_once(capture_id)
            if result in ('ok', 'rejected', 'missing'):
                return
            # Lỗi mạng / server down: chờ rồi thử lại cùng ảnh (giữ đúng thứ tự)
            self.stop_event.wait(backoff)
            backoff = min(backoff * 2, 30)

    def _upload_once(self, capture_id):
        rec = self.store.get(capture_id)
        if rec is None or rec['uploaded'] != 0:
            return 'missing'
        abs_path = os.path.join(BASE_DIR, rec['file_path'])
        if not os.path.exists(abs_path):
            self.store.mark_failed(capture_id, 'file không tồn tại', permanent=True)
            log.error('[UPLOAD] #%d: mất file %s', capture_id, abs_path)
            return 'rejected'

        with open(abs_path, 'rb') as f:
            jpg = f.read()
        data = {
            'capture_time': rec['capture_time'],
            'sent_time': now_iso(),
            'width': rec['width'],
            'height': rec['height'],
            'client_id': self.client_id,
            'client_capture_id': capture_id,
            'source': rec['source'],
            'interval_used': rec['interval_used'],
            'quality_used': rec['quality_used'],
        }
        try:
            r = self.session.post(self.url, files={'file': (rec['file_name'], jpg, 'image/jpeg')},
                                  data=data, timeout=(3, 10))
        except requests.RequestException as e:
            self.store.mark_failed(capture_id, e)
            if self.server_ok:
                log.warning('[UPLOAD] Không kết nối được server (%s). Ảnh được giữ lại để gửi bù.',
                            type(e).__name__)
            self.server_ok = False
            return 'retry'

        if r.status_code == 201:
            server_id = r.json().get('id')
            self.store.mark_uploaded(capture_id, server_id, now_iso())
            self.sent += 1
            if not self.server_ok:
                log.info('[UPLOAD] Server đã hoạt động lại. Còn %d ảnh chờ gửi bù.',
                         self.store.count_pending())
            self.server_ok = True
            log.info('[UPLOAD] #%d → server_id=%s', capture_id, server_id)
            return 'ok'
        if 400 <= r.status_code < 500:
            self.store.mark_failed(capture_id, f'HTTP {r.status_code}: {r.text[:150]}', permanent=True)
            log.error('[UPLOAD] #%d bị server từ chối: %s %s', capture_id, r.status_code, r.text[:150])
            return 'rejected'
        self.store.mark_failed(capture_id, f'HTTP {r.status_code}')
        log.warning('[UPLOAD] #%d server lỗi %s, sẽ thử lại', capture_id, r.status_code)
        return 'retry'


# ===================== LUỒNG CONFIG =====================
class ConfigThread(threading.Thread):
    def __init__(self, settings, shared_cfg, stop_event):
        super().__init__(name='ConfigThread', daemon=True)
        self.url = settings['server_url'] + '/api/config'
        self.client_id = settings['client_id']
        self.period = settings['config_poll_interval']
        self.cfg = shared_cfg
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            try:
                r = requests.get(self.url, params={'client_id': self.client_id}, timeout=3)
                r.raise_for_status()
                old = self.cfg.update(r.json())
                if old is not None:
                    # Log này là minh chứng cho kiểm thử "điều khiển từ xa"
                    log.info('[CONFIG] Áp dụng cấu hình mới từ server: %s → %s', old, self.cfg.get())
            except Exception as e:
                log.debug('Không lấy được config: %s', e)
            self.stop_event.wait(self.period)
        log.info('ConfigThread dừng')


# ===================== MAIN =====================
def main():
    parser = argparse.ArgumentParser(description='Client thu nhận ảnh từ Camera')
    parser.add_argument('--config', help='Đường dẫn file cấu hình (mặc định client_config.json)')
    parser.add_argument('--source-type', choices=['rtsp', 'http', 'webcam', 'file', 'youtube'])
    parser.add_argument('--source-url', help='URL / chỉ số webcam / đường dẫn file')
    parser.add_argument('--server', help='Địa chỉ server, vd http://192.168.1.10:5000')
    parser.add_argument('--no-preview', action='store_true', help='Không mở cửa sổ xem trước')
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(args)
    os.makedirs(IMAGE_DIR, exist_ok=True)

    src = settings['source']
    source = VideoSource(src['type'], src['url'], src.get('rtsp_transport', 'tcp'))
    store = LocalStore(DB_PATH)
    shared_cfg = SharedConfig(settings['capture'])
    upload_q = queue.Queue(maxsize=settings['upload_queue_size'])
    enqueued = (set(), threading.Lock())
    stop_event = threading.Event()

    log.info('=== Khởi động Client %s ===', settings['client_id'])
    log.info('Nguồn: %s | Server: %s | Cấu hình ban đầu: %s',
             source.describe(), settings['server_url'], shared_cfg.get())
    log.info('Ảnh chờ gửi bù từ lần chạy trước: %d', store.count_pending())

    def on_signal(sig, frame):
        log.info('Nhận tín hiệu %s. Đang dừng các luồng...', signal.Signals(sig).name)
        stop_event.set()

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, on_signal)

    capture_t = CaptureThread(settings, source, store, shared_cfg, upload_q, enqueued, stop_event)
    threads = [capture_t, ConfigThread(settings, shared_cfg, stop_event)]
    if settings['upload_enabled']:
        threads.append(UploadThread(settings, store, upload_q, enqueued, stop_event))
    for t in threads:
        t.start()

    window = f"Client {settings['client_id']} - {source.type}"
    try:
        while not stop_event.is_set():
            if settings['show_preview']:
                frame = capture_t.latest_preview()
                if frame is not None:
                    cv2.imshow(window, cv2.resize(frame, (640, 360)))
                key = cv2.waitKey(50) & 0xFF
                if key == ord('q'):
                    log.info('Nhấn q. Thoát...')
                    stop_event.set()
                elif frame is not None:
                    try:
                        if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                            log.info('Cửa sổ đã đóng. Thoát...')
                            stop_event.set()
                    except cv2.error:
                        pass
            else:
                stop_event.wait(0.5)
    finally:
        stop_event.set()
        for t in threads:
            t.join(timeout=15)
        source.release()
        if settings['show_preview']:
            cv2.destroyAllWindows()
        log.info('=== Client đã dừng. Ảnh chờ gửi bù: %d ===', store.count_pending())


if __name__ == '__main__':
    main()
