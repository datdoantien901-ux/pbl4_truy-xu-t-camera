# Client — luồng gửi ảnh, gửi bù

> Mã chức năng: `client-upload` · Nhánh sửa lỗi: `fix/client-upload` · Cập nhật lần cuối: **2026-11-02**

`UploadThread` (consumer): gửi multipart lên `POST /api/images`, retry backoff khi lỗi mạng, định kỳ quét ảnh `pending` trong SQLite để gửi bù.

## File thuộc chức năng này

- `client/upload_thread.py`

## Lỗi / tồn tại đã biết

_(chưa có)_

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `refactor/client-upload` · `02d13bc` | Tái cấu trúc | Tách `UploadThread` ra `upload_thread.py` | Client.py, upload_thread.py |
