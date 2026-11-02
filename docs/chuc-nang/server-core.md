# Server — lõi (cấu hình, thời gian, CSDL)

> Mã chức năng: `server-core` · Nhánh sửa lỗi: `fix/server-core` · Cập nhật lần cuối: **2026-11-02**

Đọc cấu hình (biến môi trường, `server/.env`), log, kết nối MySQL, tạo / nâng cấp bảng, chuyển đổi thời gian `DATETIME(3)` ↔ chuỗi ISO.

## File thuộc chức năng này

- `server/Server.py`
- `server/settings.py`
- `server/timeutil.py`
- `server/db.py`
- `server/schema.sql`
- `server/migrate_sqlite_to_mysql.py`
- `server/.env.example`

## Lỗi / tồn tại đã biết

- [ ] `touch_client()` dùng `ON DUPLICATE KEY UPDATE ... VALUES(col)` — MySQL ≥ 8.0.20 báo deprecated (vẫn chạy). Có thể đổi sang cú pháp alias `AS new`.
- [ ] Đổi schema phải sửa cùng lúc `init_db()` (db.py), `schema.sql`, `migrate_sqlite_to_mysql.py`.

## Nhật ký thay đổi

Mới nhất ở trên. Loại: Sửa lỗi / Tính năng / Tái cấu trúc / Tài liệu.

| Ngày | Nhánh · commit | Loại | Nội dung | File |
|---|---|---|---|---|
| 2026-11-02 | `feature/web-camera-filter` | Tính năng | Thêm cột `clients.cameras` (tự thêm cho DB cũ); `touch_client(..., cameras)` cập nhật danh sách camera, `None` → giữ giá trị cũ | db.py, schema.sql |
| 2026-11-02 | `feature/server-env` · `c1d5abe` | Tính năng | Đọc cấu hình MySQL từ `server/.env` (biến terminal được ưu tiên), thêm `.env.example` | settings.py, .env.example |
| 2026-11-02 | `refactor/server-core` · `bab2948` | Tái cấu trúc | Tách cấu hình, thời gian, CSDL khỏi Server.py thành `settings.py`, `timeutil.py`, `db.py`; migrate import trực tiếp các module này | Server.py, settings.py, timeutil.py, db.py, migrate_sqlite_to_mysql.py |
