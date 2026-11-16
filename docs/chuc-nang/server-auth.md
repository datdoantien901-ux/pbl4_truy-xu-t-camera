# Server — đăng nhập, phân quyền, khóa API

> Mã chức năng: `server-auth` · Nhánh sửa lỗi: `fix/server-auth` · Cập nhật lần cuối: **2026-11-16**

Client xác thực bằng khóa API (header `X-API-Key`). Người dùng Website đăng nhập (cookie phiên Flask), quyền `admin` (toàn quyền) hoặc `viewer` (chỉ xem). `guard()` chặn mọi request chưa đăng nhập (mặc định từ chối); route chỉ dành cho admin gắn `@admin_required`.

## File thuộc chức năng này

- `server/auth.py` — `guard()`, `admin_required`, kiểm tra khóa API, chống dò mật khẩu
- `server/routes/users.py` — `/api/me`, `/api/me/password`, `/api/users…`
- `server/templates/login.html`, `users.html`, `account.html`, `forbidden.html`
- Liên quan: bảng `users` + `_create_first_admin()` trong `db.py`; `API_KEY`, `SECRET_KEY`, `ADMIN_*` trong `settings.py`; cấu hình cookie trong `Server.py`; Client gửi khóa trong `upload_thread.py`, `config_thread.py`

## Lỗi / tồn tại đã biết

- [ ] Server chạy HTTP thường → mật khẩu và khóa API đi qua mạng ở dạng rõ. Cần HTTPS khi triển khai thật.
- [ ] Bộ đếm đăng nhập sai nằm trong bộ nhớ tiến trình: khởi động lại Server là mất; nhiều người chung một IP (NAT) có thể bị khóa lây.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-16 | `feature/camera-ip` | Tính năng | Trang đăng nhập chọn vai trò trước: **Người xem** vào thẳng không mật khẩu (phiên khách, chỉ xem, `auth.GUEST`), **Quản trị viên** nhập mật khẩu. `PBL4_ALLOW_GUEST=0` để tắt. Khách bấm *Quản trị* → `/login?mode=admin`; khách không đổi mật khẩu / không vào `/account`. Vào xong về `/live` | auth.py, routes/web.py, routes/users.py, settings.py, templates/login.html, forbidden.html, .env.example |
| 2026-11-16 | `feature/phan-quyen` | Tính năng | Tạo chức năng: khóa API cho Client (`X-API-Key`, so sánh `hmac.compare_digest`); đăng nhập Website (mật khẩu băm werkzeug, `session.clear()` khi đăng nhập chống session fixation, cookie HttpOnly + SameSite=Lax, hết hạn 12 giờ); 2 quyền admin/viewer; quản lý người dùng (không tự xóa / tự hạ quyền, không xóa admin cuối); đổi quyền → phiên cũ mất hiệu lực; khóa IP 5 phút sau 5 lần sai; chặn open redirect ở `next`. Bỏ Flask-Cors (Website và API cùng địa chỉ). Đã test 51 trường hợp qua HTTP với MySQL thật | auth.py, routes/users.py, routes/web.py, Server.py, templates/login.html, users.html, account.html, forbidden.html |
