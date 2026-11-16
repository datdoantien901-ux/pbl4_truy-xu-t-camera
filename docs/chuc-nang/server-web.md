# Server — giao diện web

> Mã chức năng: `server-web` · Nhánh sửa lỗi: `fix/server-web` · Cập nhật lần cuối: **2026-11-16**

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
| 2026-11-16 | `feature/phan-quyen` | Tính năng | Trang `/login`, `/live`, `/users`, `/account`; `/config`, `/users` chỉ admin. Menu ẩn mục chỉ-admin với viewer; ô người dùng + nút đăng xuất cuối sidebar (vẫn hiện trên điện thoại); nút xóa ảnh (manage, detail) chỉ admin thấy; `fetch` gặp 401 → về trang đăng nhập; `[hidden]` thắng `display:grid` | routes/web.py, templates/_layout.html, manage.html, detail.html, config.html, static/style.css |
| 2026-11-02 | `feature/web-camera-filter` | Tính năng | Ô chọn camera ở *Ảnh trực tiếp* (khung hình lớn + danh sách) và *Quản lý ảnh* (lọc + cột Camera); lựa chọn lưu trên URL `?camera=`; hàm dùng chung `fillCameraSelect` trong `_layout.html` | templates/index.html, templates/manage.html, templates/_layout.html, static/style.css |
| 2026-11-02 | `refactor/server-web` · `53038c5` | Tái cấu trúc | Tách các trang web ra `routes/web.py` (Blueprint `web`); Server.py chỉ còn khởi động app | routes/web.py, Server.py |
