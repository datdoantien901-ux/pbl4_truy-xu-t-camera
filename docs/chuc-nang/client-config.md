# Client — luồng lấy cấu hình từ Server

> Mã chức năng: `client-config` · Nhánh sửa lỗi: `fix/client-config` · Cập nhật lần cuối: **2026-11-16**

`ConfigThread`: mỗi `config_poll_interval` giây gọi `GET /api/config?client_id=...`, cập nhật `SharedConfig`.

## File thuộc chức năng này

- `client/config_thread.py`

## Lỗi / tồn tại đã biết

_(chưa có)_

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-16 | `feature/phan-quyen` | Tính năng | Gửi header `X-API-Key`; 401/403 → log cảnh báo kiểm tra khóa | config_thread.py |
| 2026-11-02 | `feature/web-camera-filter` | Tính năng | Gửi kèm `cameras=<id,...>` (mọi camera đang bật, kể cả chưa có link) khi lấy cấu hình → Website hiện camera trong ô chọn | config_thread.py, Client.py |
| 2026-11-02 | `refactor/client-config` · `77d0ee7` | Tái cấu trúc | Tách `ConfigThread` ra `config_thread.py`; Client.py chỉ còn khởi động | Client.py, config_thread.py |
