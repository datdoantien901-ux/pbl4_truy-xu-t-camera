"""
Luồng UPLOAD (consumer): lấy id ảnh từ hàng đợi, gửi multipart lên POST /api/images.
Lỗi mạng / server down → backoff rồi thử lại; ảnh vẫn nằm trong SQLite local (pending)
và được quét lại định kỳ để gửi bù khi có mạng.
"""
import logging
import os
import queue
import threading
import time

import requests

from settings import BASE_DIR, now_iso

log = logging.getLogger('client')


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
