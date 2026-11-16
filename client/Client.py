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
    Nhiều camera → mỗi camera một CaptureThread, dùng chung Queue, UploadThread, ConfigThread.
    Danh sách camera mặc định lấy từ Website: admin bật "Client chụp ảnh" ở Camera trực tiếp /
    Camera IP → ConfigThread nhận qua /api/config → CameraManager mở / dừng luồng chụp lúc đang chạy.
    Main thread: hiện preview của 1 camera (cv2.imshow phải chạy ở luồng chính), nhấn 1/2/.../Tab
    để đổi camera đang xem; chờ tín hiệu dừng.

Mỗi chức năng nằm ở một file riêng (file này chỉ khởi động và nối các luồng):
    settings.py         đường dẫn, cấu hình mặc định, đọc cấu hình + client/.env, danh sách camera, log
    shared_config.py    SharedConfig: tham số chụp dùng chung giữa các luồng (có Lock)
    capture_thread.py   CaptureThread: đọc frame, chụp, nén JPEG, lưu file + SQLite
    upload_thread.py    UploadThread: gửi ảnh lên Server, retry, gửi bù
    config_thread.py    ConfigThread: lấy cấu hình + danh sách camera từ Server định kỳ
    camera_manager.py   CameraManager: thêm / dừng CaptureThread khi danh sách camera đổi
    video_source.py     VideoSource: mở nguồn RTSP / HTTP / webcam / file / YouTube
    local_store.py      LocalStore: SQLite local (metadata + hàng đợi gửi bù)

Ctrl+C (SIGINT) → set stop_event → các luồng tự thoát vòng lặp → join → giải phóng tài nguyên.

Chạy:  python Client.py                       (chụp các camera admin bật "Client chụp ảnh" trên Website)
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

from camera_manager import CameraManager
from config_thread import ConfigThread
from local_store import LocalStore
from settings import DB_PATH, IMAGE_DIR, load_cameras, load_settings, setup_logging
from shared_config import SharedConfig
from upload_thread import UploadThread

log = logging.getLogger('client')

PREVIEW_W, PREVIEW_H = 640, 360
KEY_TAB = 9


# ===================== CỬA SỔ XEM TRƯỚC =====================
def pick_view(value, threads):
    """--view nhận số thứ tự (1, 2, ...) hoặc id camera; không khớp → camera đầu tiên."""
    if value:
        ids = [t.camera_id for t in threads]
        if value in ids:
            return ids.index(value)
        if value.isdigit() and 1 <= int(value) <= len(threads):
            return int(value) - 1
        log.warning('--view "%s" không khớp camera nào (%s) → xem camera 1', value, ', '.join(ids))
    return 0


def render_waiting():
    img = np.zeros((PREVIEW_H, PREVIEW_W, 3), np.uint8)
    cv2.putText(img, 'Dang cho danh sach camera tu Website...', (20, PREVIEW_H // 2 - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 2)
    cv2.putText(img, '(admin bat "Chup anh" o Camera truc tiep / Camera IP)', (20, PREVIEW_H // 2 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1)
    return img


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
    from_server = settings['cameras_from_server']
    os.makedirs(IMAGE_DIR, exist_ok=True)

    store = LocalStore(DB_PATH)
    shared_cfg = SharedConfig(settings['capture'])
    upload_q = queue.Queue(maxsize=settings['upload_queue_size'])
    enqueued = (set(), threading.Lock())
    stop_event = threading.Event()
    manager = CameraManager(settings, store, shared_cfg, upload_q, enqueued)

    log.info('=== Khởi động Client %s ===', settings['client_id'])
    if from_server:
        log.info('Camera: lấy từ Website (các camera admin bật "Client chụp ảnh"), cập nhật mỗi %ds',
                 settings['config_poll_interval'])
    else:
        cameras, _ = load_cameras(settings)
        if not cameras:
            log.error('Không có camera nào có URL → kiểm tra "cameras" trong client_config.json và client/.env')
            return 1
        manager.apply(cameras)
    log.info('Server: %s | Cấu hình ban đầu: %s', settings['server_url'], shared_cfg.get())
    log.info('Ảnh chờ gửi bù từ lần chạy trước: %d', store.count_pending())

    def on_signal(sig, frame):
        log.info('Nhận tín hiệu %s. Đang dừng các luồng...', signal.Signals(sig).name)
        stop_event.set()

    signal.signal(signal.SIGINT, on_signal)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, on_signal)

    threads = [ConfigThread(settings, shared_cfg, stop_event, manager, from_server)]
    if settings['upload_enabled']:
        threads.append(UploadThread(settings, store, upload_q, enqueued, stop_event))
    for t in threads:
        t.start()

    window = f"Client {settings['client_id']}"
    viewing = None          # CaptureThread đang hiện trong cửa sổ xem trước
    first_pick = True
    try:
        while not stop_event.is_set():
            if not settings['show_preview']:
                stop_event.wait(0.5)
                continue
            # Danh sách camera có thể đổi bất cứ lúc nào (admin bật / tắt trên Website)
            cams = manager.threads()
            if viewing not in cams:
                if viewing is not None:
                    viewing.set_preview_active(False)
                viewing = None
                if cams:
                    viewing = cams[pick_view(args.view, cams) if first_pick else 0]
                    first_pick = False
                    viewing.set_preview_active(True)
                    log.info('Đang xem: %s (nhấn 1-%d hoặc Tab để đổi luồng)', viewing.camera_name, len(cams))
            if viewing is None:
                cv2.imshow(window, render_waiting())
            else:
                cv2.imshow(window, render_preview(viewing, cams.index(viewing), len(cams)))
            key = cv2.waitKey(50) & 0xFF
            total = len(cams)
            if key == ord('q'):
                log.info('Nhấn q. Thoát...')
                stop_event.set()
            elif viewing is not None and (key == KEY_TAB or ord('1') <= key < ord('1') + total):
                cur = cams.index(viewing)
                new = (cur + 1) % total if key == KEY_TAB else key - ord('1')
                if new != cur:
                    viewing.set_preview_active(False)
                    viewing = cams[new]
                    viewing.set_preview_active(True)
                    log.info('Đổi luồng xem → %s', viewing.camera_name)
            else:
                try:
                    if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                        # Đóng cửa sổ xem trước KHÔNG dừng Client (trước đây dừng hẳn → người dùng tưởng
                        # Client không chụp được). Client vẫn chụp + gửi ảnh; dừng bằng q hoặc Ctrl+C.
                        log.info('Đã đóng cửa sổ xem trước. Client vẫn tiếp tục chụp và gửi ảnh '
                                 '(nhấn Ctrl+C trong terminal để dừng Client).')
                        settings['show_preview'] = False
                        if viewing is not None:
                            viewing.set_preview_active(False)   # không giải mã khung xem trước nữa
                        cv2.destroyAllWindows()
                except cv2.error:
                    pass
    finally:
        stop_event.set()
        manager.stop_all()
        for t in threads:
            t.join(timeout=15)
        if settings['show_preview']:
            cv2.destroyAllWindows()
        log.info('=== Client đã dừng. Ảnh chờ gửi bù: %d ===', store.count_pending())
    return 0


if __name__ == '__main__':
    sys.exit(main())
