"""
Nhận diện vật thể trong ảnh bằng YOLOv5 (mô hình ONNX chính thức của Ultralytics, chạy bằng OpenCV DNN —
không cần PyTorch).

Luồng xử lý (Producer–Consumer, giống Client):
    POST /api/images (luồng request của Flask)  ── submit(id) ──►  queue.Queue  ──►  DetectWorker (1 luồng nền)
    Request nhận ảnh trả lời ngay, không chờ YOLO (~50–150 ms/ảnh trên CPU).
    DetectWorker là luồng DUY NHẤT dùng mạng nơ-ron (cv2.dnn.Net không an toàn khi nhiều luồng gọi cùng lúc),
    ghi kết quả vào bảng detections + cột images.detected_time / detect_ms / object_count.
    Hàng đợi đầy hoặc Server vừa khởi động lại → ảnh còn detected_time NULL được quét bù định kỳ.

Tải mô hình (14 MB, một lần):   python detector.py --download
Thử trên 1 ảnh:                 python detector.py duong/dan/anh.jpg
Tắt nhận diện:                  PBL4_YOLO=0 (server/.env)
"""
import os
import queue
import sys
import threading
import time

from settings import YOLO_CONF, YOLO_ENABLED, YOLO_IOU, YOLO_MODEL, BASE_DIR, log

MODEL_URL = 'https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5s.onnx'
INPUT_SIZE = 640          # mô hình yolov5s.onnx nhận ảnh 640×640
SCAN_SECONDS = 30         # chu kỳ quét bù ảnh chưa nhận diện
SCAN_BATCH = 50

# 80 loại vật thể của bộ dữ liệu COCO (đúng thứ tự đầu ra của mô hình)
COCO = ('person bicycle car motorcycle airplane bus train truck boat traffic_light fire_hydrant stop_sign '
        'parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella handbag '
        'tie suitcase frisbee skis snowboard sports_ball kite baseball_bat baseball_glove skateboard surfboard '
        'tennis_racket bottle wine_glass cup fork knife spoon bowl banana apple sandwich orange broccoli carrot '
        'hot_dog pizza donut cake chair couch potted_plant bed dining_table toilet tv laptop mouse remote '
        'keyboard cell_phone microwave oven toaster sink refrigerator book clock vase scissors teddy_bear '
        'hair_drier toothbrush').split()

# Tên tiếng Việt cho các loại hay gặp ở camera; loại khác hiện tên tiếng Anh
VI_NAMES = {
    'person': 'Người', 'bicycle': 'Xe đạp', 'car': 'Ô tô', 'motorcycle': 'Xe máy', 'bus': 'Xe buýt',
    'truck': 'Xe tải', 'train': 'Tàu hỏa', 'boat': 'Thuyền', 'airplane': 'Máy bay',
    'traffic_light': 'Đèn giao thông', 'stop_sign': 'Biển dừng', 'bench': 'Ghế băng', 'bird': 'Chim',
    'cat': 'Mèo', 'dog': 'Chó', 'horse': 'Ngựa', 'cow': 'Bò', 'backpack': 'Ba lô', 'umbrella': 'Ô (dù)',
    'handbag': 'Túi xách', 'suitcase': 'Va li', 'bottle': 'Chai', 'chair': 'Ghế', 'potted_plant': 'Chậu cây',
    'cell_phone': 'Điện thoại', 'laptop': 'Laptop', 'tv': 'TV',
}


def vi_name(label):
    return VI_NAMES.get(label, label.replace('_', ' '))


# ============ MÔ HÌNH ============
class YoloV5:
    def __init__(self, path, conf=0.35, iou=0.45):
        import cv2
        self.cv2 = cv2
        self.net = cv2.dnn.readNetFromONNX(path)
        self.conf, self.iou = conf, iou

    def _letterbox(self, img):
        """Thu ảnh về 640×640 giữ nguyên tỉ lệ, phần thừa tô xám (đúng cách YOLOv5 được huấn luyện)."""
        cv2 = self.cv2
        h, w = img.shape[:2]
        r = min(INPUT_SIZE / h, INPUT_SIZE / w)
        nw, nh = round(w * r), round(h * r)
        top, left = (INPUT_SIZE - nh) // 2, (INPUT_SIZE - nw) // 2
        resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
        out = cv2.copyMakeBorder(resized, top, INPUT_SIZE - nh - top, left, INPUT_SIZE - nw - left,
                                 cv2.BORDER_CONSTANT, value=(114, 114, 114))
        return out, r, left, top

    def detect(self, img):
        """Ảnh BGR (numpy) → [{label, confidence, x1, y1, x2, y2}] theo tọa độ pixel của ảnh gốc."""
        import numpy as np
        cv2 = self.cv2
        h, w = img.shape[:2]
        boxed, r, left, top = self._letterbox(img)
        self.net.setInput(cv2.dnn.blobFromImage(boxed, 1 / 255.0, (INPUT_SIZE, INPUT_SIZE), swapRB=True))
        out = self.net.forward()[0]                # (25200, 85): cx, cy, w, h, objectness, 80 điểm loại

        out = out[out[:, 4] >= self.conf]          # bỏ ô chắc chắn không có vật thể
        if not len(out):
            return []
        cls = out[:, 5:].argmax(axis=1)
        score = out[:, 4] * out[np.arange(len(out)), 5 + cls]
        keep = score >= self.conf
        out, cls, score = out[keep], cls[keep], score[keep]
        if not len(out):
            return []
        # tâm + kích thước trên ảnh 640 → góc trên-trái + kích thước trên ảnh gốc
        bw, bh = out[:, 2] / r, out[:, 3] / r
        x = (out[:, 0] - left) / r - bw / 2
        y = (out[:, 1] - top) / r - bh / 2
        boxes = np.stack([x, y, bw, bh], axis=1)
        # NMS theo từng loại: 2 khung trùng nhau nhiều (IoU > iou) → giữ khung điểm cao hơn
        idx = cv2.dnn.NMSBoxesBatched(boxes.tolist(), score.tolist(), cls.tolist(), self.conf, self.iou)
        result = []
        for k in np.array(idx).flatten():
            bx, by, bw_, bh_ = boxes[k]
            result.append({
                'label': COCO[cls[k]],
                'confidence': round(float(score[k]), 3),
                'x1': int(max(0, bx)), 'y1': int(max(0, by)),
                'x2': int(min(w, bx + bw_)), 'y2': int(min(h, by + bh_)),
            })
        result.sort(key=lambda d: -d['confidence'])
        return result


# ============ LUỒNG NHẬN DIỆN NỀN ============
class DetectWorker(threading.Thread):
    def __init__(self):
        super().__init__(name='YoloWorker', daemon=True)
        self.queue = queue.Queue(maxsize=500)      # có giới hạn → Server không phình bộ nhớ khi YOLO chậm
        self.model = None
        self.reason = None                         # lý do không chạy (thiếu mô hình, tắt...)
        self.processed = 0
        self.total_ms = 0.0
        self.last_error = None
        self.lock = threading.Lock()               # bảo vệ số liệu đọc từ luồng request (/api/detect/status)

    # --- gọi từ luồng request ---
    def submit(self, image_id):
        if self.model is None:
            return
        try:
            self.queue.put_nowait(image_id)
        except queue.Full:
            pass                                   # quét bù sẽ xử lý sau

    def status(self):
        with self.lock:
            avg = round(self.total_ms / self.processed, 1) if self.processed else None
            return {'enabled': self.model is not None, 'reason': self.reason,
                    'model': os.path.basename(YOLO_MODEL), 'confidence': YOLO_CONF,
                    'queue': self.queue.qsize(), 'processed': self.processed, 'avg_ms': avg,
                    'last_error': self.last_error}

    # --- luồng nền ---
    def load(self):
        if not YOLO_ENABLED:
            self.reason = 'Đã tắt (PBL4_YOLO=0)'
        elif not os.path.exists(YOLO_MODEL):
            self.reason = f'Chưa có mô hình {os.path.relpath(YOLO_MODEL, BASE_DIR)} — chạy: python detector.py --download'
        else:
            try:
                self.model = YoloV5(YOLO_MODEL, YOLO_CONF, YOLO_IOU)
            except Exception as e:                 # OpenCV thiếu / file hỏng
                self.reason = f'Không nạp được mô hình: {e}'
        if self.model is None:
            log.warning('[YOLO] Không chạy nhận diện: %s', self.reason)
        else:
            log.info('[YOLO] Đã nạp %s (ngưỡng tin cậy %.2f)', os.path.basename(YOLO_MODEL), YOLO_CONF)
        return self.model is not None

    def run(self):
        if not self.load():
            return
        last_scan, more = 0, False
        while True:
            # Đến chu kỳ, hoặc lần quét trước còn ảnh tồn mà hàng đợi đã hết → quét tiếp
            if time.monotonic() - last_scan > SCAN_SECONDS or (more and self.queue.empty()):
                last_scan = time.monotonic()
                more = self._scan_backlog() >= SCAN_BATCH
            try:
                image_id = self.queue.get(timeout=1 if more else SCAN_SECONDS)
            except queue.Empty:
                continue
            try:
                self._process(image_id)
            except Exception as e:                 # lỗi 1 ảnh (MySQL tạm mất...) không làm chết luồng
                with self.lock:
                    self.last_error = f'#{image_id}: {e}'
                log.warning('[YOLO] Lỗi xử lý ảnh #%s: %s', image_id, e)

    def _scan_backlog(self):
        from db import get_db
        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute('SELECT id FROM images WHERE detected_time IS NULL ORDER BY id DESC LIMIT %s', (SCAN_BATCH,))
            ids = [r['id'] for r in cur.fetchall()]
            conn.close()
        except Exception as e:
            log.warning('[YOLO] Quét bù lỗi: %s', e)
            return 0
        if ids:
            log.info('[YOLO] Quét bù %d ảnh chưa nhận diện', len(ids))
        for i in ids:
            self.submit(i)
        return len(ids)

    def _process(self, image_id):
        import cv2
        from db import get_db
        from timeutil import now_dt

        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT file_path, detected_time FROM images WHERE id = %s', (image_id,))
        row = cur.fetchone()
        if row is None or row['detected_time'] is not None:   # ảnh đã bị xóa / đã nhận diện (trùng hàng đợi)
            conn.close()
            return
        img = cv2.imread(os.path.join(BASE_DIR, row['file_path']))
        if img is None:
            # File mất / hỏng → đánh dấu đã xử lý (object_count NULL) để không thử lại mãi
            cur.execute('UPDATE images SET detected_time = %s WHERE id = %s', (now_dt(), image_id))
            conn.commit()
            conn.close()
            return

        t0 = time.perf_counter()
        objs = self.model.detect(img)
        ms = round((time.perf_counter() - t0) * 1000, 1)

        cur.execute('DELETE FROM detections WHERE image_id = %s', (image_id,))
        if objs:
            cur.executemany('''INSERT INTO detections (image_id, label, confidence, x1, y1, x2, y2)
                               VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                            [(image_id, d['label'], d['confidence'], d['x1'], d['y1'], d['x2'], d['y2'])
                             for d in objs])
        cur.execute('UPDATE images SET detected_time = %s, detect_ms = %s, object_count = %s WHERE id = %s',
                    (now_dt(), ms, len(objs), image_id))
        conn.commit()
        conn.close()
        with self.lock:
            self.processed += 1
            self.total_ms += ms
        if objs:
            counts = {}
            for d in objs:
                counts[d['label']] = counts.get(d['label'], 0) + 1
            log.info('[YOLO] #%d: %s (%.0f ms)', image_id,
                     ', '.join(f'{vi_name(k)} {v}' for k, v in counts.items()), ms)


worker = DetectWorker()


def start():
    """Server.py gọi một lần khi khởi động."""
    if not worker.is_alive():
        worker.start()


# ============ DÒNG LỆNH ============
def _download():
    import urllib.request
    os.makedirs(os.path.dirname(YOLO_MODEL), exist_ok=True)
    print(f'Tải {MODEL_URL}\n  → {YOLO_MODEL}')
    tmp = YOLO_MODEL + '.part'
    urllib.request.urlretrieve(MODEL_URL, tmp)
    os.replace(tmp, YOLO_MODEL)
    print(f'Xong ({os.path.getsize(YOLO_MODEL) / 1048576:.1f} MB)')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--download':
        _download()
    elif len(sys.argv) > 1:
        import cv2
        m = YoloV5(YOLO_MODEL, YOLO_CONF, YOLO_IOU)
        image = cv2.imread(sys.argv[1])
        if image is None:
            sys.exit('Không đọc được ảnh')
        m.detect(image)                            # lần đầu chậm hơn (khởi tạo) → không tính
        t = time.perf_counter()
        found = m.detect(image)
        print(f'{len(found)} vật thể, {(time.perf_counter() - t) * 1000:.0f} ms')
        for d in found:
            print(f"  {vi_name(d['label']):<14} {d['confidence']:.2f}  ({d['x1']},{d['y1']})–({d['x2']},{d['y2']})")
    else:
        print(__doc__)
