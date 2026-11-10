"""
Tham số thu nhận dùng chung giữa các luồng: ConfigThread ghi, CaptureThread đọc.
"""
import threading


class SharedConfig:
    """Tham số thu nhận, được ConfigThread ghi và CaptureThread đọc → cần Lock."""

    KEYS = ('capture_interval', 'jpeg_quality', 'resize_width')

    def __init__(self, initial):
        self._lock = threading.Lock()
        self._cfg = {k: int(initial[k]) for k in self.KEYS}
        self.version = 0

    def get(self):
        with self._lock:
            return dict(self._cfg)

    def update(self, new_cfg):
        with self._lock:
            new = {k: int(new_cfg.get(k, self._cfg[k])) for k in self.KEYS}
            if new == self._cfg:
                return None
            old, self._cfg = self._cfg, new
            self.version += 1
            return old
