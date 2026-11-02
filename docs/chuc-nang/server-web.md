# Server — giao diện web

> Mã chức năng: `server-web` · Nhánh sửa lỗi: `fix/server-web` · Cập nhật lần cuối: **2026-11-02**

Các trang HTML: gallery real-time (`/`), quản lý (`/manage`), cấu hình (`/config`), thống kê (`/stats`), chi tiết ảnh (`/image/<id>`).

## File thuộc chức năng này

- `server/routes/web.py`
- `server/templates/*.html`
- `server/static/style.css`

## Lỗi / tồn tại đã biết

- [ ] `detail.html` cắt chuỗi thời gian (`capture_time[8:10]`) → route phải truyền chuỗi ISO, không truyền datetime.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `refactor/server-web` · `53038c5` | Tái cấu trúc | Tách các trang web ra `routes/web.py` (Blueprint `web`); Server.py chỉ còn khởi động app | routes/web.py, Server.py |
