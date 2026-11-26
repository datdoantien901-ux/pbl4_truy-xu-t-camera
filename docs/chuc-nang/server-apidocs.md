# Server — tài liệu API (Swagger / OpenAPI)

> Mã chức năng: `server-apidocs` · Nhánh sửa lỗi: `fix/server-apidocs` · Cập nhật lần cuối: **2026-11-26**

Trang `/apidocs` (mục *Tài liệu API* ở thanh bên trái) hiển thị Swagger UI: danh sách mọi API theo nhóm, tham số, dạng JSON trả về, mã lỗi; nút *Try it out* gọi thử API thật (trình duyệt tự gửi cookie phiên; khóa `X-API-Key` của Client nhập ở nút *Authorize*). Đặc tả OpenAPI 3.0 trả ở `/api/openapi.json`, viết bằng dict Python trong `openapi.py` (không cần thư viện thêm). Cả hai cần đăng nhập (Khách xem được).

## File thuộc chức năng này

- `server/openapi.py` — đặc tả: `SCHEMAS` (kiểu dữ liệu), `PATHS` (từng API), hàm tắt `op`, `obj`, `q`, `p`…
- `server/routes/apidocs.py` — `/apidocs`, `/api/openapi.json`
- `server/templates/apidocs.html` — nạp Swagger UI 5.17.14 từ CDN jsdelivr
- Liên quan: mục nav trong `_layout.html`, CSS `.swagger-wrap` trong `style.css`

## Lỗi / tồn tại đã biết

- [ ] Swagger UI tải từ CDN → máy xem cần Internet; mất mạng thì trang báo lỗi, `/api/openapi.json` vẫn xem được.
- [ ] Đặc tả viết tay: thêm / sửa API trong `routes/*.py` phải sửa cả `openapi.py` (kiểm tra bằng cách so `app.url_map` với `openapi.SPEC['paths']`).

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-26 | `feature/swagger` | Tính năng | Thêm Swagger UI `/apidocs` + đặc tả OpenAPI 3.0 cho đủ 36 API (27 đường dẫn), 2 kiểu xác thực (`X-API-Key`, cookie phiên). Đã thử *Try it out* với phiên khách; chưa đăng nhập → 401 / chuyển trang đăng nhập | openapi.py, routes/apidocs.py, templates/apidocs.html, Server.py, _layout.html, style.css |
