# Tiến trình dự án

> Cập nhật file này ở cuối mỗi phiên làm việc: ghi việc đã xong, việc đang dở, lỗi mới phát hiện.
> Cập nhật lần cuối: **2026-11-02**

## Đã hoàn thành

| Thời điểm | Commit / việc | Nội dung |
|---|---|---|
| 09/2026 | `1efc4b0`, `d1f7623` | Phiên bản đầu: client chụp ảnh đơn luồng, lưu `timestamp/`, `images/` |
| 10/2026 | `8bde8bc` | Client đa luồng (Capture / Upload / Config), nhiều nguồn video, gửi bù ảnh khi mất mạng; trang quản lý và thống kê độ trễ |
| 10/2026 | `ac2fa0a` | Làm lại giao diện web; nguồn YouTube dùng luồng trực tiếp kênh 0511 |
| 11/2026 | `d574d5e` (trên `main`) | Chuyển Server từ SQLite sang MySQL, thêm `schema.sql`, `migrate_sqlite_to_mysql.py` |
| 2026-11-02 | `5d924da` merge `main` → `feature/multithread-client` | Gỡ xung đột: giữ toàn bộ tính năng nhánh đa luồng + chạy hoàn toàn trên MySQL, `DATETIME(3)`, schema/migrate đủ 4 bảng. Bỏ `server/server.db` khỏi git, `.gitignore` thêm `*.db`, `server/uploads/`. Thêm CLAUDE.md, AGENTS.md, PROGRESS.md |

### Đã kiểm thử (2026-11-02, MySQL 8.0.46 cổng 3307, Python 3.13)
- `pip install -r server/requirements.txt` trong venv mới: OK.
- Migrate: 52 ảnh + 1 client + config sang MySQL; chạy lần 2 không thêm trùng.
- 21/21 kiểm thử API qua HTTP đạt: upload, chống trùng, file không hợp lệ (400), lọc/phân trang, chi tiết, displayed, xóa, config GET/POST + validate, history, stats, clients, 5 trang web.
- Chưa chạy thử Client thật kết nối Server MySQL (end-to-end).

## Đang dở — làm tiếp ở phiên sau

1. Chạy end-to-end: Server (MySQL) + Client, kiểm tra gallery, trang Thống kê, kịch bản tắt server rồi bật lại.
2. Tạo PR `feature/multithread-client` → `main`.
3. Hỏi người dùng có dọn file rác đang track không (xem mục Repo bên dưới).

## Lỗi / tồn tại đã biết

### Repo
- **File rác đang được git track** (~309 ảnh + DB từ phiên bản đầu): `timestamp/`, `images/`, `client/timestamp/`, `camera_metadata.db`, `client/camera_metadata.db`. Code hiện tại không dùng các file này (client mới lưu ở `client/data/`). Nên `git rm --cached` và bổ sung `.gitignore` (cần hỏi người dùng trước).
- `.gitignore` có `client/client_config.local.json` nhưng `Client.py` **không đọc** file này (chỉ đọc `--config` hoặc `client_config.json`) → hoặc thêm hỗ trợ, hoặc bỏ dòng đó.
- Chưa có test tự động trong repo.

### Server
- `ON DUPLICATE KEY UPDATE ... VALUES(col)` trong `touch_client()` bị MySQL ≥ 8.0.20 đánh dấu deprecated (vẫn chạy, chỉ là warning). Có thể đổi sang cú pháp alias `AS new` khi cần.
- Không có xác thực: ai trong LAN cũng gọi được `DELETE /api/images/<id>` và `POST /api/config`.
- `cleanup_old_images()` chạy đồng bộ sau mỗi lần upload (thêm 1 kết nối DB / request).
- Mặc định `MYSQL_PORT=3306`; máy phát triển hiện tại dùng **3307** → nhớ đặt biến môi trường.

### Client
- `DEFAULT_SETTINGS` trong `Client.py` có URL YouTube khác với `client_config.json` (link `watch?v=` của luồng live có thể hết hạn → cần cập nhật khi lỗi mở nguồn).
- Nguồn YouTube phụ thuộc `yt-dlp`, dễ hỏng khi YouTube đổi API → `pip install -U yt-dlp`.

## Ghi chú môi trường (máy phát triển)
- Windows 11, Python 3.13, MySQL80 service tại `D:\MySQL\PBL4`, cổng 3307, user `root` (mật khẩu: hỏi người dùng, **không ghi vào repo**).
- Database: `pbl4_camera`.
