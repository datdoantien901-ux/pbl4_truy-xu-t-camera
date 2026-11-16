"""
Luồng CONFIG: mỗi config_poll_interval giây gọi GET /api/config?client_id=...&cameras=...
    - cập nhật SharedConfig → CaptureThread dùng tham số mới ở lần chụp kế tiếp
    - (cameras_from_server) nhận "cameras" = các camera admin bật "Client chụp ảnh" trên Website
      → CameraManager mở / dừng luồng chụp tương ứng, không cần khởi động lại Client
Tham số cameras báo cho Server các camera Client đang chụp → danh sách nguồn trên Website.
"""
import json
import logging
import threading

import requests

log = logging.getLogger('client')


class ConfigThread(threading.Thread):
    def __init__(self, settings, shared_cfg, stop_event, manager, from_server):
        super().__init__(name='ConfigThread', daemon=True)
        self.url = settings['server_url'] + '/api/config'
        self.client_id = settings['client_id']
        self.headers = {'X-API-Key': settings['api_key']} if settings.get('api_key') else {}
        self.period = settings['config_poll_interval']
        self.cfg = shared_cfg
        self.stop_event = stop_event
        self.manager = manager
        self.from_server = from_server
        self.last_cameras = None   # danh sách camera lần trước (so sánh để chỉ áp dụng khi đổi)
        self.warned_no_list = False

    def run(self):
        while not self.stop_event.is_set():
            try:
                params = {'client_id': self.client_id, 'cameras': ','.join(self.manager.ids())}
                r = requests.get(self.url, params=params, headers=self.headers, timeout=3)
                if r.status_code in (401, 403):
                    log.warning('[CONFIG] Server từ chối khóa API (HTTP %s) — kiểm tra PBL4_API_KEY', r.status_code)
                r.raise_for_status()
                data = r.json()
                old = self.cfg.update(data)
                if old is not None:
                    # Log này là minh chứng cho kiểm thử "điều khiển từ xa"
                    log.info('[CONFIG] Áp dụng cấu hình mới từ server: %s → %s', old, self.cfg.get())
                if self.from_server:
                    self._apply_cameras(data)
            except Exception as e:
                log.debug('Không lấy được config: %s', e)
            self.stop_event.wait(self.period)
        log.info('ConfigThread dừng')

    def _apply_cameras(self, data):
        if 'cameras' not in data:
            if not self.warned_no_list:
                log.warning('[CAMERA] Server không gửi danh sách camera (Server bản cũ?) → chưa chụp camera nào')
                self.warned_no_list = True
            return
        sig = json.dumps(data['cameras'], sort_keys=True)
        if sig == self.last_cameras:
            return
        self.last_cameras = sig
        names = ', '.join(c.get('name', c.get('id', '?')) for c in data['cameras']) or '(không có)'
        log.info('[CAMERA] Danh sách camera từ Website: %s', names)
        if not data['cameras']:
            log.warning('[CAMERA] Chưa có camera nào bật "Client chụp ảnh" — vào Website (quyền admin), '
                        'mục Camera trực tiếp hoặc Camera IP, bấm "Chụp ảnh" ở camera cần chụp')
        self.manager.apply(data['cameras'])
