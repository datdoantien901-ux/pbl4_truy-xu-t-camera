# Server — API cấu hình từ xa

> Mã chức năng: `server-config` · Nhánh sửa lỗi: `fix/server-config` · Cập nhật lần cuối: **2026-11-02**

Client lấy cấu hình (`GET /api/config`), Website đặt tham số (`POST /api/config`, giới hạn trong `CONFIG_LIMITS`), lịch sử thay đổi (`/api/config/history`).

## File thuộc chức năng này

- `server/routes/config.py`

## Lỗi / tồn tại đã biết

- [ ] Không có xác thực: ai trong LAN cũng gọi được `POST /api/config`.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `refactor/server-config` · `cae1685` | Tái cấu trúc | Tách API cấu hình ra `routes/config.py` (Blueprint `config`) | routes/config.py, Server.py |
