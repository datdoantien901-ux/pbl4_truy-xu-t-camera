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
    Nhiều camera (mảng "cameras" trong client_config.json) → mỗi camera một CaptureThread,
    dùng chung Queue, UploadThread, ConfigThread.
    Main thread: hiện preview của 1 camera (cv2.imshow phải chạy ở luồng chính), nhấn 1/2/.../Tab
    để đổi camera đang xem; chờ tín hiệu dừng.

Mỗi chức năng nằm ở một file riêng (file này chỉ khởi động và nối các luồng):
    settings.py         đường dẫn, cấu hình mặc định, đọc cấu hình + client/.env, danh sách camera, log
    shared_config.py    SharedConfig: tham số chụp dùng chung giữa các luồng (có Lock)
    capture_thread.py   CaptureThread: đọc frame, chụp, nén JPEG, lưu file + SQLite
    upload_thread.py    UploadThread: gửi ảnh lên Server, retry, gửi bù
    config_thread.py    ConfigThread: lấy cấu hình từ Server định kỳ
    video_source.py     VideoSource: mở nguồn RTSP / HTTP / webcam / file / YouTube
    local_store.py      LocalStore: SQLite local (metadata + hàng đợi gửi bù)

Ctrl+C (SIGINT) → set stop_event → các luồng tự thoát vòng lặp → join → giải phóng tài nguyên.

Chạy:  python Client.py                       (dùng client_config.json, chạy mọi camera trong "cameras")
       python Client.py --view nha             (mở cửa sổ xem camera "nha" trước; hoặc --view 2)
       python Client.py --source-type rtsp --source-url rtsp://192.168.1.15:8554/live
       python Client.py --server http://192.168.1.10:5000 --no-preview
"""
import argparse
import logging
import os
import queue
import signal
import sys
import threading

import cv2
import numpy as np

from capture_thread import CaptureThread
from config_thread import ConfigThread
from local_store import LocalStore
from settings import DB_PATH, IMAGE_DIR, load_cameras, load_settings, setup_logging
from shared_config import SharedConfig
from upload_thread import UploadThread
from video_source import VideoSource

log = logging.getLogger('client')

PREVIEW_W, PREVIEW_H = 640, 360
KEY_TAB = 9


# ===================== CỬA SỔ XEM TRƯỚC =====================
def pick_view(value, cameras):
    """--view nhận số thứ tự (1, 2, ...) hoặc id camera; không khớp → camera đầu tiên."""
    if value:
        ids = [c['id'] for c in cameras]
        if value in ids:
            return ids.index(value)
        if value.isdigit() and 1 <= int(value) <= len(cameras):
            return int(value) - 1
        log.warning('--view "%s" không khớp camera nào (%s) → xem camera 1', value, ', '.join(ids))
    return 0


def render_preview(cam_t, index, total):
    """Ảnh mới nhất của camera đang xem + thanh nhãn. cv2.putText chỉ vẽ chữ ASCII → nhãn không dấu."""
    frame = cam_t.latest_preview()
    if frame is None:
        img = np.zeros((PREVIEW_H, PREVIEW_W, 3), np.uint8)
        msg = 'Dang tai hinh...' if cam_t.connected else 'Dang ket noi nguon video...'
        cv2.putText(img, msg, (20, PREVIEW_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)
    else:
        img = cv2.resize(frame, (PREVIEW_W, PREVIEW_H))
    hint = f'Phim 1-{total} / Tab: doi luong   q: thoat' if total > 1 else 'q: thoat'
    cv2.rectangle(img, (0, 0), (PREVIEW_W, 26), (0, 0, 0), -1)
    cv2.putText(img, f'[{index + 1}/{total}] {cam_t.camera_id}', (8, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, hint, (PREVIEW_W - 8 - 7 * len(hint), 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
    return img


# ===================== MAIN =====================
def main():
    parser = argparse.ArgumentParser(description='Client thu nhận ảnh từ Camera')
    parser.add_argument('--config', help='Đường dẫn file cấu hình (mặc định client_config.json)')
    parser.add_argument('--source-type', choices=['rtsp', 'http', 'webcam', 'file', 'youtube'],
                        help='Chạy đúng 1 nguồn này (bỏ qua danh sách "cameras")')
    parser.add_argument('--source-url', help='URL / chỉ số webcam / đường dẫn file')
    parser.add_argument('--server', help='Địa chỉ server, vd http://192.168.1.10:5000')
    parser.add_argument('--no-preview', action='store_true', help='Không mở cửa sổ xem trước')
    parser.add_argument('--view', help='Camera hiện trong cửa sổ xem trước lúc mở: số thứ tự hoặc id')
    args = parser.parse_args()

    setup_logging()
    settings = load_settings(args)
    cameras, declared_ids = load_cameras(settings)
    if not cameras:
        log.error('Không có camera nào có URL → kiểm tra "cameras" trong client_config.json và client/.env')
        return 1
    os.makedirs(IMAGE_DIR, exist_ok=True)

    store = LocalStore(DB_PATH)
    shared_cfg = SharedConfig(settings['capture'])
    upload_q = queue.Queue(maxsize=settings['upload_queue_size'])
    enqueued = (set(), threading.Lock())
    stop_event = threading.Event()

    capture_threads = []
    for cam in cameras:
        src = cam['source']
        source = VideoSource(src['type'], src['url'], src.get('rtsp_transport', 'tcp'))
        capture_threads.append(CaptureThread(cam, settings, source, store, shared_cfg,
                                             upload_q, enqueued, stop_event))

    log.info('=== Khởi động Client %s ===', settings['client_id'])
    for i, t in enumerate(capture_threads, 1):
        log.info('Camera %d: %s (%s) | %s', i, t.camera_id, t.camera_name, t.source.describe())
    log.info('Server: %s | Cấu hình ban đầu: %s', settings['server_url'], shared_cfg.get())
    log.info('Ảnh chờ gửi bù từ lần chạy trước: %d', store.count_pending())

    def on_signal(sig, frame):
        log.info('Nhận tín hiệu %s. Đang dừng các luồng...', signal.Signals(sig).name)
        stop_event.set()

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, on_signal)

    threads = capture_threads + [ConfigThread(settings, shared_cfg, stop_event, declared_ids)]
    if settings['upload_enabled']:
        threads.append(UploadThread(settings, store, upload_q, enqueued, stop_event))
    for t in threads:
        t.start()

    window = f"Client {settings['client_id']}"
    current = pick_view(args.view, cameras)
    total = len(capture_threads)
    if settings['show_preview']:
        capture_threads[current].set_preview_active(True)
        log.info('Đang xem: %s (nhấn 1-%d hoặc Tab để đổi luồng)', capture_threads[current].camera_name, total)
    try:
        while not stop_event.is_set():
            if settings['show_preview']:
                cv2.imshow(window, render_preview(capture_threads[current], current, total))
                key = cv2.waitKey(50) & 0xFF
                if key == ord('q'):
                    log.info('Nhấn q. Thoát...')
                    stop_event.set()
                elif key == KEY_TAB or ord('1') <= key < ord('1') + total:
                    new = (current + 1) % total if key == KEY_TAB else key - ord('1')
                    if new != current:
                        capture_threads[current].set_preview_active(False)
                        capture_threads[new].set_preview_active(True)
                        current = new
                        log.info('Đổi luồng xem → %s', capture_threads[current].camera_name)
                else:
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
        for t in capture_threads:
            t.source.release()
        if settings['show_preview']:
            cv2.destroyAllWindows()
        log.info('=== Client đã dừng. Ảnh chờ gửi bù: %d ===', store.count_pending())
    return 0


if __name__ == '__main__':
    sys.exit(main())
