"""
Quản lý các luồng chụp (CaptureThread) khi danh sách camera thay đổi lúc đang chạy.

Mặc định Client chụp các camera admin bật "Client chụp ảnh" trên Website (mục Camera trực tiếp /
Camera IP). ConfigThread nhận danh sách đó trong /api/config rồi gọi apply():
    camera mới            → tạo VideoSource + CaptureThread, start
    camera bị tắt / xóa   → set cờ dừng riêng của luồng đó (các camera khác vẫn chạy)
    camera đổi URL        → dừng luồng cũ, mở luồng mới
Mỗi CaptureThread có threading.Event riêng; stop_all() (Ctrl+C) set tất cả rồi join.
"""
import logging
import re
import threading

from capture_thread import CaptureThread
from video_source import SUPPORTED_TYPES, VideoSource, mask_url

log = logging.getLogger('client')


class CameraManager:
    def __init__(self, settings, store, shared_cfg, upload_q, enqueued):
        self.settings = settings
        self.store = store
        self.cfg = shared_cfg
        self.upload_q = upload_q
        self.enqueued = enqueued
        self.lock = threading.Lock()      # main thread (preview) đọc, ConfigThread ghi
        self.running = {}                 # id → (CaptureThread, url, stop Event)
        self.version = 0                  # tăng mỗi lần danh sách đổi → preview biết để vẽ lại
        self.stopped = False

    def apply(self, cameras):
        """cameras: [{id, name, type, url}] (từ Server) hoặc [{id, name, source: {...}}] (cấu hình local)."""
        wanted = {}
        for cam in cameras:
            src = cam.get('source') or {'type': cam.get('type'), 'url': cam.get('url')}
            cam_id = re.sub(r'[^A-Za-z0-9_-]', '-', str(cam.get('id') or ''))[:50]
            if not cam_id or not src.get('url') or src.get('type') not in SUPPORTED_TYPES:
                log.warning('Bỏ qua camera không hợp lệ: %s', cam.get('id'))
                continue
            wanted[cam_id] = (cam.get('name') or cam_id, src)

        to_join = []
        with self.lock:
            if self.stopped:
                return
            before = set(self.running)
            for cam_id in list(self.running):
                t, url, ev = self.running[cam_id]
                if cam_id not in wanted or wanted[cam_id][1]['url'] != url:
                    log.info('[CAMERA] Dừng chụp %s (%s)', cam_id,
                             'đổi URL' if cam_id in wanted else 'admin tắt / xóa trên Website')
                    ev.set()
                    to_join.append(t)
                    del self.running[cam_id]
            for cam_id, (name, src) in wanted.items():
                if cam_id in self.running:
                    continue
                ev = threading.Event()
                source = VideoSource(src['type'], src['url'], src.get('rtsp_transport', 'tcp'))
                t = CaptureThread({'id': cam_id, 'name': name}, self.settings, source, self.store, self.cfg,
                                  self.upload_q, self.enqueued, ev)
                self.running[cam_id] = (t, src['url'], ev)
                t.start()
                log.info('[CAMERA] Bắt đầu chụp %s "%s" | %s', cam_id, name, mask_url(src['url']))
            if to_join or set(self.running) != before:
                self.version += 1
        for t in to_join:   # join ngoài lock: luồng có thể đang chờ mở nguồn video vài giây
            t.join(timeout=15)

    def threads(self):
        with self.lock:
            return [t for t, _, _ in self.running.values()]

    def ids(self):
        with self.lock:
            return list(self.running)

    def stop_all(self):
        with self.lock:
            self.stopped = True
            items = list(self.running.values())
            self.running.clear()
        for _, _, ev in items:
            ev.set()
        for t, _, _ in items:
            t.join(timeout=15)
