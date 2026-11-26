# Server — nhận diện vật thể YOLOv5

> Mã chức năng: `server-yolo` · Nhánh sửa lỗi: `fix/server-yolo` · Cập nhật lần cuối: **2026-11-26**

Mỗi ảnh Client gửi lên được nhận diện bằng YOLOv5s (ONNX chính thức Ultralytics v7.0, 80 loại COCO) chạy bằng OpenCV DNN — không cần PyTorch. Producer–Consumer: request `POST /api/images` (producer) → `queue.Queue(500)` → 1 luồng `YoloWorker` (consumer, luồng duy nhất dùng `cv2.dnn.Net`). Kết quả: bảng `detections` + cột `images.detected_time`, `detect_ms`, `object_count`. Ảnh còn `detected_time IS NULL` được quét bù mỗi 30 giây (còn tồn thì quét tiếp ngay). Thiếu mô hình / `PBL4_YOLO=0` → Server vẫn chạy, `/api/detect/status` báo lý do.

## File thuộc chức năng này

- `server/detector.py` — `YoloV5` (letterbox 640, giải mã đầu ra, NMS theo loại), `DetectWorker`, `VI_NAMES`, dòng lệnh `--download` / thử 1 ảnh
- `server/routes/detect.py` — `/api/detect/status`, `/api/objects`
- `server/models/yolov5s.onnx` — không commit (`.gitignore`)
- Liên quan: `routes/images.py` (`submit`, `?object=`, `objects`, `detections`), `routes/monitor.py` (`detect_time`), `db.py` / `schema.sql` (bảng `detections`), `settings.py` (`YOLO_*`), `detail.html`, `manage.html`, `live.html`, `stats.html`, `_layout.html` (`OBJ_NAMES`, `objSummary`), `openapi.py`

## Lỗi / tồn tại đã biết

- [ ] Ảnh cũ được quét bù có `received_to_detected` rất lớn (nhận diện muộn) → làm lệch số liệu này trong `/api/stats`; giao diện chỉ hiện `detect_time`.
- [ ] Ngưỡng tin cậy 0.35: camera đêm / xa có thể nhận nhầm (vd biển hiệu thành ô tô) hoặc bỏ sót; chỉnh `PBL4_YOLO_CONF`.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-26 | `feature/yolov5` | Tính năng | Thêm nhận diện YOLOv5 (yêu cầu của thầy): luồng nền + hàng đợi, bảng `detections`, quét bù; khung vật thể ở chi tiết ảnh, lọc theo vật thể ở Quản lý ảnh, vật thể ở tab Ảnh từ Client, thời gian YOLOv5 ở Thống kê; Swagger. Test với MySQL thật: 100 ảnh camera giao thông, TB 62 ms/ảnh CPU; lọc "Người" ra 11 ảnh | detector.py, routes/detect.py, routes/images.py, routes/monitor.py, routes/web.py, db.py, schema.sql, settings.py, Server.py, templates/*.html, style.css, openapi.py |
