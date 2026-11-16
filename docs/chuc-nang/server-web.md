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
| 2026-11-16 | `fix/vao-trang-va-chon-nguon` | Tính năng | Tab *Ảnh từ Client*: thay ô chọn thả xuống bằng danh sách nguồn bên phải (ảnh mới nhất, số ảnh, giờ chụp, chấm xanh nếu có ảnh trong 30 giây); màn hình hẹp đưa danh sách lên trên; thông tin khung hình mới nhất xếp dưới ảnh | templates/live.html, static/style.css |
| 2026-11-16 | `feature/gop-camera-anh` | Tính năng | Gộp trang *Ảnh từ Client* (`index.html`, đã xóa) vào `live.html` thành tab thứ 2; bỏ mục menu riêng; `/` chuyển về `/live?tab=anh` (giữ `?camera=`); CSS `.tabs`, `.tab-bar`. Tab ảnh chỉ làm mới / báo "đã hiển thị" khi đang mở | routes/web.py, templates/live.html, templates/index.html (xóa), templates/_layout.html, static/style.css |
| 2026-11-16 | `feature/camera-ip` | Tính năng | Menu: *Camera trực tiếp* (`/live`, trang mặc định) lên đầu, thêm *Camera IP* (`/ipcam`), *Ảnh trực tiếp* đổi tên thành *Ảnh từ Client*; ô người dùng hiện "Khách · Chỉ xem" + nút Quản trị | templates/_layout.html, index.html, live.html, static/style.css |
| 2026-11-16 | `feature/phan-quyen` | Tính năng | Trang `/login`, `/live`, `/users`, `/account`; `/config`, `/users` chỉ admin. Menu ẩn mục chỉ-admin với viewer; ô người dùng + nút đăng xuất cuối sidebar (vẫn hiện trên điện thoại); nút xóa ảnh (manage, detail) chỉ admin thấy; `fetch` gặp 401 → về trang đăng nhập; `[hidden]` thắng `display:grid` | routes/web.py, templates/_layout.html, manage.html, detail.html, config.html, static/style.css |
| 2026-11-02 | `feature/web-camera-filter` | Tính năng | Ô chọn camera ở *Ảnh trực tiếp* (khung hình lớn + danh sách) và *Quản lý ảnh* (lọc + cột Camera); lựa chọn lưu trên URL `?camera=`; hàm dùng chung `fillCameraSelect` trong `_layout.html` | templates/index.html, templates/manage.html, templates/_layout.html, static/style.css |
| 2026-11-02 | `refactor/server-web` · `53038c5` | Tái cấu trúc | Tách các trang web ra `routes/web.py` (Blueprint `web`); Server.py chỉ còn khởi động app | routes/web.py, Server.py |
