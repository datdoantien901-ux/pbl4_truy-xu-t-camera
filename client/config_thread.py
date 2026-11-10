"""
Luồng CONFIG: mỗi config_poll_interval giây gọi GET /api/config?client_id=...&cameras=...
và cập nhật SharedConfig → CaptureThread dùng tham số mới ở lần chụp kế tiếp.
Tham số cameras báo cho Server các camera Client khai báo → ô chọn camera trên Website.
"""
import logging
import threading

import requests

log = logging.getLogger('client')


class ConfigThread(threading.Thread):
    def __init__(self, settings, shared_cfg, stop_event, camera_ids=()):
        super().__init__(name='ConfigThread', daemon=True)
        self.url = settings['server_url'] + '/api/config'
        self.params = {'client_id': settings['client_id'], 'cameras': ','.join(camera_ids)}
        self.period = settings['config_poll_interval']
        self.cfg = shared_cfg
        self.stop_event = stop_event

    def run(self):
        while not self.stop_event.is_set():
            try:
                r = requests.get(self.url, params=self.params, timeout=3)
                r.raise_for_status()
                old = self.cfg.update(r.json())
                if old is not None:
                    # Log này là minh chứng cho kiểm thử "điều khiển từ xa"
                    log.info('[CONFIG] Áp dụng cấu hình mới từ server: %s → %s', old, self.cfg.get())
            except Exception as e:
                log.debug('Không lấy được config: %s', e)
            self.stop_event.wait(self.period)
        log.info('ConfigThread dừng')
