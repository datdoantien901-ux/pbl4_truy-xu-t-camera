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

import cv2
import requests

from capture_thread import CaptureThread
from local_store import LocalStore
from settings import DB_PATH, IMAGE_DIR, load_settings, setup_logging
from shared_config import SharedConfig
from upload_thread import UploadThread
from video_source import VideoSource

log = logging.getLogger('client')


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
