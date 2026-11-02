# Client — luồng chụp ảnh

> Mã chức năng: `client-capture` · Nhánh sửa lỗi: `fix/client-capture` · Cập nhật lần cuối: **2026-11-02**

`CaptureThread` (producer): đọc frame, mỗi `capture_interval` giây chụp, resize + nén JPEG, lưu file atomic (file tạm → `os.replace`), ghi SQLite, đưa id vào hàng đợi upload; mất luồng → kết nối lại (backoff).

## File thuộc chức năng này

- `client/capture_thread.py`

## Lỗi / tồn tại đã biết

_(chưa có)_

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `refactor/client-capture` · `9c2e642` | Tái cấu trúc | Tách `CaptureThread` ra `capture_thread.py` | Client.py, capture_thread.py |
