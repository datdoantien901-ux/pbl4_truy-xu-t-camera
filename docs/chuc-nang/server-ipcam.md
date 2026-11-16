# Server — camera IP xem trực tiếp

> Mã chức năng: `server-ipcam` · Nhánh sửa lỗi: `fix/server-ipcam` · Cập nhật lần cuối: **2026-11-16**

Trang `/ipcam`: admin nhập IP camera (chọn hãng → Server ghép đường dẫn RTSP/HTTP, hoặc dán URL), thử kết nối, lưu; mọi người xem trực tiếp. Server đọc camera bằng OpenCV và phát lại cho trình duyệt dạng MJPEG (`multipart/x-mixed-replace`). Mỗi camera 1 luồng đọc (`CameraReader`) dùng chung cho mọi người xem; không ai xem 20 giây → đóng camera.

## File thuộc chức năng này

- `server/ipcam.py` — `PRESETS` (mẫu đường dẫn theo hãng), `build_url`, `check_url`, `mask_url`, `snapshot`, `CameraReader`, `StreamHub` (`hub`)
- `server/routes/ipcams.py` — `/api/ipcams…`, `/ipcam/<id>/stream`
- `server/templates/ipcam.html`
- Liên quan: bảng `ip_cameras` trong `db.py` / `schema.sql`; CSS mục "Camera IP" trong `style.css`; `opencv-python` trong `server/requirements.txt`

## Lỗi / tồn tại đã biết

- [ ] Chưa thử với camera IP thật (mới test bằng camera MJPEG giả dựng trên máy và IP không tồn tại). Đường dẫn RTSP theo hãng lấy từ tài liệu, có thể khác theo đời camera.
- [ ] URL camera (kèm mật khẩu) lưu dạng rõ trong MySQL — chỉ không gửi ra trình duyệt. Server dev của Flask: mỗi người xem giữ 1 luồng xử lý request; nhiều người xem nhiều camera cùng lúc sẽ tốn luồng.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-16 | `feature/client-chup-tu-web` | Tính năng | Cột `ip_cameras.capture`; `PATCH /api/ipcams/<id> {capture}` (admin); nút *Chụp ảnh* trên thẻ camera. Client chụp camera IP qua RTSP/HTTP như camera khác | routes/ipcams.py, db.py, templates/ipcam.html |
| 2026-11-16 | `feature/camera-ip` | Tính năng | Tạo chức năng. Đã test với MySQL thật + camera MJPEG giả (127.0.0.1:8090): thử kết nối 0,4 s ra ảnh 640×480; IP không có camera → lỗi sau 6 s, không lộ mật khẩu; `file://` bị chặn; 3 người xem cùng lúc → 1 luồng đọc; rời trang → tự đóng camera sau 20 s; khách xem được, không thêm/thử được (403). Sửa lỗi ô Cổng bị đặt lại mặc định khi gõ | ipcam.py, routes/ipcams.py, templates/ipcam.html, db.py, schema.sql, static/style.css, requirements.txt |
